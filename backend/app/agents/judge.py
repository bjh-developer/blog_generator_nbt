"""JudgeAgent: post-generation quality / safety / factuality review.

A reasoning-tier LLM critic (role="judge") re-reads the assembled StoryBrief and
flags weak insights, low-quality or UNSAFE lessons, weak closings, and funding
rounds whose label+year+amount isn't supported by the source corpus. It does NOT
edit the story — it returns advisory WARNING strings that flow into the pipeline's
qa_warnings so a human reviews the JSON before publishing (flag-for-human).

Every judge call is fail-open: an LLM error yields no warnings, never a crash.
A deterministic grounding pass (verify.ground_score) runs regardless of the judge
model being up, so ungrounded funding amounts are caught even when the LLM is down.
"""
from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from app import config
from app.agents import verify
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


class _FundingVerdict(BaseModel):
    index: int
    supported: bool = True
    reason: str = ""


class _FundingVerdicts(BaseModel):
    verdicts: list[_FundingVerdict] = []


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


_FUNDING_SYS = (
    "You fact-check FUNDING rounds against SOURCE EXCERPTS. For EACH numbered round, "
    "supported=true ONLY if the excerpts state that exact round label, that year, and "
    "that amount TOGETHER. supported=false if the amount, year, or label appears to be "
    "mismatched or is not backed by the excerpts (e.g. the excerpt says the $350M was a "
    "different Series or a different year). "
    'Return ONLY JSON: {"verdicts":[{"index":0,"supported":true,"reason":""}, ...]} '
    "one entry per round, same indices."
)


async def _factcheck_funding(sb: StoryBrief, corpus: str) -> list[str]:
    fs = sb.funding
    if not fs or not fs.rounds:
        return []
    warns: list[str] = []

    import re

    def _digits(s: str) -> list[str]:
        return re.findall(r"\d[\d,.]*", s or "")

    # 1a) Deterministic: does each round's amount appear in its OWN cited quote?
    #     Catches a fabricated quote or a quote that doesn't back the number.
    for r in fs.rounds:
        if not r.amount:
            continue
        quote = (r.source.quote if r.source else "") or ""
        if quote:
            nums = {n.replace(",", "") for n in _digits(r.amount)}
            qnums = {n.replace(",", "") for n in _digits(quote)}
            if nums and not (nums & qnums):
                warns.append(f"funding: '{r.label} {r.date} {r.amount}' amount not in its cited quote — verify")

    # 1b) Deterministic grounding — does the amount appear anywhere in the corpus?
    if corpus:
        for r in fs.rounds:
            if not r.amount:
                continue
            claim = f"{r.amount} {r.label}"
            if verify.ground_score(claim, corpus) < config.VERIFY_THRESHOLD:
                warns.append(f"funding: '{r.label} {r.date} {r.amount}' amount not found in sources — verify")

    # 2) LLM cross-check of label↔year↔amount consistency (larger window so the
    #    funding source isn't truncated away — the old 12k cap made this unreliable).
    if corpus:
        listing = "\n".join(
            f"[{i}] {r.label} | year={(r.date or '?')[:4]} | amount={r.amount or '?'}"
            for i, r in enumerate(fs.rounds)
        )
        user = f"SOURCE EXCERPTS:\n{corpus[:40000]}\n\nFUNDING ROUNDS:\n{listing}"
        try:
            res = await gateway.complete_json(_FUNDING_SYS, user, _FundingVerdicts,
                                              role="judge", temperature=_TEMP, reasoning=_REASONING)
            for v in res.verdicts:
                if 0 <= v.index < len(fs.rounds) and not v.supported:
                    r = fs.rounds[v.index]
                    msg = f"funding: '{r.label} {r.date} {r.amount}' {v.reason or 'label/year/amount mismatch'} — verify"
                    if msg not in warns:
                        warns.append(msg)
        except gateway.LLMError:
            pass
    return warns


# --- entry point -----------------------------------------------------------

async def review(sb: StoryBrief, corpus: str) -> list[str]:
    """Run all judges concurrently; return advisory warning strings (never raises)."""
    results = await asyncio.gather(
        _judge_insight(sb),
        _judge_lessons(sb),
        _judge_closing(sb),
        _factcheck_funding(sb, corpus),
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
