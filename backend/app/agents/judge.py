"""JudgeAgent: post-generation quality / safety / factuality review.

A reasoning-tier LLM critic (role="judge") re-reads the assembled StoryBrief and
flags weak insights, low-quality or UNSAFE lessons, and weak closings. It does NOT
edit the story — it returns advisory WARNING strings that flow into the pipeline's
qa_warnings so a human reviews the JSON before publishing (flag-for-human).

Every judge call is fail-open: an LLM error yields no warnings, never a crash.
"""
from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from app.llm import gateway
from app.schemas import StoryBrief

log = logging.getLogger("app.agents.judge")

_TEMP = 0.1  # judgments should be stable, not creative
# The judge IS a reasoning-tier model — let it reason, but exclude the reasoning
# tokens from the response so the returned content stays clean JSON.
_REASONING = {"enabled": True, "exclude": True}


# --- verdict schemas -------------------------------------------------------

class _OkVerdict(BaseModel):
    ok: bool = True
    reason: str = ""


class _LessonVerdict(BaseModel):
    index: int
    quality_ok: bool = True
    safety_ok: bool = True
    reason: str = ""


class _LessonVerdicts(BaseModel):
    verdicts: list[_LessonVerdict] = []


# --- individual judges (each fail-open) ------------------------------------

_INSIGHT_SYS = (
    "You judge whether a startup breakdown's CORE INSIGHT is a real insight or a "
    "dud. A real insight names a NON-OBVIOUS causal mechanism or strategic choice "
    "that explains the company's success. REJECT (ok=false) if it merely restates a "
    "fact, is a tautology, or is circular. "
    "Example of a DUD: 'He did not need the company to get rich, he was already rich' "
    "(restates a fact, explains nothing). "
    "Example of a REAL insight: 'They made listing an item feel like posting a story, "
    "so casual users became habitual sellers.' "
    'Return ONLY JSON: {"ok": true|false, "reason": "<short>"}'
)


async def _judge_insight(sb: StoryBrief) -> list[str]:
    ci = sb.core_insight
    if not ci or not ci.statement:
        return []
    user = f"STATEMENT: {ci.statement}\n\nNARRATIVE: {ci.narrative or ''}"
    try:
        v = await gateway.complete_json(_INSIGHT_SYS, user, _OkVerdict,
                                        role="judge", temperature=_TEMP, reasoning=_REASONING)
    except gateway.LLMError:
        return []
    if not v.ok:
        return [f"insight: not a real insight ({v.reason or 'restatement/tautology'}) — rewrite or drop"]
    return []


_LESSON_SYS = (
    "You judge the LESSONS in a startup breakdown written for 18-28 year old founders. "
    "For EACH numbered lesson return two booleans:\n"
    "- safety_ok=false if the lesson endorses or normalises harmful, dangerous, illegal, "
    "unethical, or relationship-destroying behaviour as advice (e.g. 'let your family "
    "disown you', 'drop out and burn your savings', anything a responsible mentor would "
    "not tell a young person to do). This is the priority check.\n"
    "- quality_ok=false if the lesson is generic, trivial, a tautology, or PR fluff "
    "rather than a specific, actionable takeaway.\n"
    'Return ONLY JSON: {"verdicts":[{"index":0,"quality_ok":true,"safety_ok":true,"reason":""}, ...]} '
    "with one entry per lesson, same indices as given."
)


async def _judge_lessons(sb: StoryBrief) -> list[str]:
    if not sb.lessons:
        return []
    listing = "\n".join(
        f"[{i}] {l.headline} — {l.body}" for i, l in enumerate(sb.lessons)
    )
    try:
        r = await gateway.complete_json(_LESSON_SYS, listing, _LessonVerdicts,
                                        role="judge", temperature=_TEMP, reasoning=_REASONING)
    except gateway.LLMError:
        return []
    warns: list[str] = []
    for v in r.verdicts:
        if not (0 <= v.index < len(sb.lessons)):
            continue
        n = v.index + 1
        if not v.safety_ok:
            warns.append(f"lesson {n}: SAFETY — {v.reason or 'endorses harmful/unethical behaviour'} (remove or rewrite)")
        elif not v.quality_ok:
            warns.append(f"lesson {n}: weak ({v.reason or 'generic/tautological'}) — sharpen or drop")
    return warns


_CLOSING_SYS = (
    "You judge the CLOSING take of a startup breakdown. REJECT (ok=false) if it is a "
    "restatement, a tautology, or says nothing pointed — a good closing lands a specific, "
    "resonant takeaway. "
    'Return ONLY JSON: {"ok": true|false, "reason": "<short>"}'
)


async def _judge_closing(sb: StoryBrief) -> list[str]:
    cl = sb.closing
    if not cl or not cl.narrative:
        return []
    user = f"CLOSING: {cl.narrative}\n\nPULL QUOTE: {cl.pull_quote or ''}"
    try:
        v = await gateway.complete_json(_CLOSING_SYS, user, _OkVerdict,
                                        role="judge", temperature=_TEMP, reasoning=_REASONING)
    except gateway.LLMError:
        return []
    if not v.ok:
        return [f"closing: weak take ({v.reason or 'restatement'}) — sharpen"]
    return []


# --- entry point -----------------------------------------------------------

async def review(sb: StoryBrief, corpus: str) -> list[str]:
    """Run all judges concurrently; return advisory warning strings (never raises)."""
    results = await asyncio.gather(
        _judge_insight(sb),
        _judge_lessons(sb),
        _judge_closing(sb),
        return_exceptions=True,
    )
    warns: list[str] = []
    for r in results:
        if isinstance(r, BaseException):
            log.warning("judge sub-check failed: %s", r)
            continue
        warns.extend(r)
    if warns:
        log.warning("judge flagged %d issue(s): %s", len(warns), warns)
    return warns
