"""StoryBrief QA audit: a final, deterministic consistency pass over the
assembled story before it ships. Catches the structural mistakes a language
model quietly produces — duplicate or overlapping competitor cards, more than
one "winner", timeline events out of chronological order, hero accent words that
don't occur in the headline — the kind of thing visible in the rendered page but
invisible to the grounding/relevance gates.

Pure and cheap (no LLM). Returns a list of human-readable issue strings; empty
list == clean. The pipeline logs these and returns them in the API response so a
reviewer sees exactly what to check before publishing.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from app.schemas import StoryBrief

# severity: "error" blocks publishing (hard gate); "warning" is advisory only.
Issue = Tuple[str, str]   # (severity, message)


def audit(sb: StoryBrief) -> List[Issue]:
    """Return all (severity, message) issues. Use split() to separate gating
    errors from advisory warnings."""
    issues: List[Issue] = []
    issues += _audit_competitors(sb)
    issues += _audit_timeline(sb)
    issues += _audit_hero(sb)
    return issues


def split(issues: List[Issue]) -> Tuple[List[str], List[str]]:
    """(errors, warnings) — errors block publishing, warnings are advisory."""
    errors = [m for sev, m in issues if sev == "error"]
    warnings = [m for sev, m in issues if sev == "warning"]
    return errors, warnings


# --- auto-repair -----------------------------------------------------------
# Deterministically fix the hard-error classes so a flawed story can still ship
# instead of being blocked. Each fixer is conservative: it disambiguates,
# reorders, or drops the offending field rather than inventing data.

def repair(sb: StoryBrief) -> StoryBrief:
    _repair_competitors(sb)
    _repair_timeline(sb)
    _repair_hero(sb)
    return sb


# any arrow form the model emits (→, <->, ↔, doubled, trailing) splits the axis
_ARROW_RE = re.compile(r"\s*(?:<->|<>|[←→↔]+)\s*")


def _overlap(text: str, ref: str) -> int:
    """Count of meaningful (len>=4) word tokens shared between text and ref."""
    a = {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4}
    b = {w for w in re.findall(r"[a-z]+", ref.lower()) if len(w) >= 4}
    return len(a & b)


def _orient_axis(axis: str, winner_text: str) -> str:
    """Normalize an axis to 'A ←→ B' with the winner's trait on the right (B).
    Collapses any arrow form to a single '←→', strips stray arrows, and swaps
    the halves if the first matches the winner better. Single-label axes pass
    through unchanged."""
    parts = [p.strip() for p in _ARROW_RE.split(axis) if p.strip()]
    if len(parts) < 2:
        return axis
    left, right = parts[0], parts[-1]
    if _overlap(left, winner_text) > _overlap(right, winner_text):
        left, right = right, left
    return f"{left} ←→ {right}"


def _repair_competitors(sb: StoryBrief) -> None:
    c = sb.competitors
    if not c:
        return
    # drop duplicate-name cards, keep first
    seen: set = set()
    kept = []
    for q in c.quadrants:
        k = q.name.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        kept.append(q)
    c.quadrants = kept

    # at most 4 cards — one per cell. Keep the winner(s) first, then others.
    if len(c.quadrants) > 4:
        c.quadrants = sorted(c.quadrants, key=lambda q: 0 if q.winner else 1)[:4]

    # enforce exactly one winner
    winners = [q for q in c.quadrants if q.winner]
    if c.quadrants and not winners:
        c.quadrants[0].winner = True
    elif len(winners) > 1:
        for q in winners[1:]:
            q.winner = False

    # winner always occupies top-right; everyone else gets a unique remaining cell
    order = ["tr", "tl", "br", "bl"]
    used: set = set()
    for q in c.quadrants:
        if q.winner:
            q.quadrant = "tr"
            used.add("tr")
    for q in c.quadrants:
        if q.winner:
            continue
        if q.quadrant not in order or q.quadrant in used:
            free = next((cell for cell in order if cell not in used), None)
            if free and free in ("tr", "tl", "br", "bl"):
                q.quadrant = free  # type: ignore[assignment]
        used.add(q.quadrant)

    # the winner sits top-right, so the RIGHT end of axis_x and the TOP (second)
    # end of axis_y must describe the winner's traits. Flip a label whose first
    # half matches the winner better than its second half.
    winner = next((q for q in c.quadrants if q.winner), None)
    if winner:
        wtext = f"{winner.their_bet} {winner.the_gap} {winner.name}"
        c.axis_x = _orient_axis(c.axis_x, wtext)
        c.axis_y = _orient_axis(c.axis_y, wtext)


def _repair_timeline(sb: StoryBrief) -> None:
    if sb.timeline:
        sb.timeline.events.sort(key=lambda e: e.year or "")


def _repair_hero(sb: StoryBrief) -> None:
    head = (sb.hero.line1 + " " + sb.hero.line2).lower()
    if sb.hero.accent_word_orange and sb.hero.accent_word_orange.lower() not in head:
        sb.hero.accent_word_orange = None
    if sb.hero.accent_word_purple and sb.hero.accent_word_purple.lower() not in head:
        sb.hero.accent_word_purple = None


# --- audit -----------------------------------------------------------------

def _audit_competitors(sb: StoryBrief) -> List[Issue]:
    out: List[Issue] = []
    cs = sb.competitors
    if not cs:
        return out
    quads = cs.quadrants

    # more than 4 cards can't fit one-per-cell in a 2x2 — hard (repair caps to 4)
    if len(quads) > 4:
        out.append(("error", f"competitors: {len(quads)} cards, expected exactly 4"))

    # duplicate competitor labels — hard (the "overlaps in labels" case)
    names = [q.name.strip().lower() for q in quads if q.name]
    dups = sorted({n for n in names if names.count(n) > 1})
    for d in dups:
        out.append(("error", f"competitors: duplicate label '{d}' appears "
                             f"{names.count(d)}x"))

    # two competitors in the same 2x2 cell visually overlap — advisory
    cells: dict = {}
    for q in quads:
        cells.setdefault(q.quadrant, []).append(q.name)
    for cell, members in cells.items():
        if len(members) > 1:
            out.append(("warning", f"competitors: {len(members)} cards share cell "
                                   f"'{cell}' (overlap): {members}"))

    # exactly one winner (the subject company) should be highlighted — hard
    winners = [q.name for q in quads if q.winner]
    if quads and len(winners) != 1:
        out.append(("error", f"competitors: expected exactly 1 winner, found "
                             f"{len(winners)}: {winners}"))

    # unlabeled axes leave the map meaningless — advisory
    if quads and (not cs.axis_x or not cs.axis_y):
        out.append(("warning", "competitors: map axis label missing "
                               f"(axis_x={cs.axis_x!r}, axis_y={cs.axis_y!r})"))
    return out


def _audit_timeline(sb: StoryBrief) -> List[Issue]:
    out: List[Issue] = []
    if not sb.timeline:
        return out
    years = [e.year for e in sb.timeline.events if e.year]
    if years != sorted(years):
        out.append(("error", f"timeline: events out of chronological order: {years}"))
    return out


def _audit_hero(sb: StoryBrief) -> List[Issue]:
    out: List[Issue] = []
    # accent words must actually occur in the headline they highlight — hard
    for word in (sb.hero.accent_word_orange, sb.hero.accent_word_purple):
        if word and word.lower() not in (sb.hero.line1 + " " + sb.hero.line2).lower():
            out.append(("error", f"hero: accent word '{word}' not found in headline"))
    return out
