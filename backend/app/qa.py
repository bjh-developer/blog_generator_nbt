"""StoryBrief QA audit: a final, deterministic consistency pass over the
assembled story before it ships. Catches the structural mistakes a language
model quietly produces — duplicate funding rounds, dates out of order, chart
points that don't match the round list, contradictory valuations — the kind of
thing visible in the funding section but invisible to grounding/relevance gates.

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


def _year(s: str | None) -> str:
    return (s or "")[:4]


def _money_to_float(s: str | None) -> float | None:
    """'$85M' -> 85e6, '$3.2B' -> 3.2e9. None if unparseable."""
    if not s:
        return None
    m = re.search(r"([\d.]+)\s*([mMbBkK])?", s.replace(",", ""))
    if not m:
        return None
    val = float(m.group(1))
    mult = {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1.0)
    return val * mult


def audit(sb: StoryBrief) -> List[Issue]:
    """Return all (severity, message) issues. Use split() to separate gating
    errors from advisory warnings."""
    issues: List[Issue] = []
    issues += _audit_funding(sb)
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
    _repair_funding(sb)
    _repair_competitors(sb)
    _repair_timeline(sb)
    _repair_hero(sb)
    return sb


def _repair_funding(sb: StoryBrief) -> None:
    f = sb.funding
    if not f:
        return
    f.rounds.sort(key=lambda r: r.date or "")          # chronological

    # disambiguate duplicate labels (e.g. two "Series C" in different years)
    counts: dict = {}
    for r in f.rounds:
        key = r.label.strip().lower()
        if counts.get(key):
            yr = _year(r.date)
            r.label = f"{r.label} ({yr})" if yr else f"{r.label} ({counts[key] + 1})"
        counts[key] = counts.get(key, 0) + 1
    # keep chart point labels in sync with the (possibly renamed) rounds by date
    date_to_label = {r.date: r.label for r in f.rounds if r.date}
    for p in f.chart:
        if p.date in date_to_label:
            p.label = date_to_label[p.date]

    # clear a later valuation that drops below an earlier one (bad parse/units)
    vals = [r for r in f.rounds if r.valuation and _money_to_float(r.valuation) is not None]
    for prev, cur in zip(vals, vals[1:]):
        y1, y2 = _year(prev.date), _year(cur.date)
        if y1 and y2 and y1 <= y2 and _money_to_float(cur.valuation) < _money_to_float(prev.valuation):
            cur.valuation = None


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
    # enforce exactly one winner
    winners = [q for q in c.quadrants if q.winner]
    if c.quadrants and not winners:
        c.quadrants[0].winner = True
    elif len(winners) > 1:
        for q in winners[1:]:
            q.winner = False


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

def _audit_funding(sb: StoryBrief) -> List[Issue]:
    out: List[Issue] = []
    if not sb.funding:
        return out
    rounds = sb.funding.rounds

    # duplicate round labels (the "First funding round x2" bug) — hard
    labels = [r.label.strip().lower() for r in rounds if r.label]
    dups = sorted({l for l in labels if labels.count(l) > 1})
    for d in dups:
        out.append(("error", f"funding: duplicate round label '{d}' appears "
                             f"{labels.count(d)}x"))

    # chronology: rounds, as listed, should be non-decreasing by year — hard
    dated = [(r.label, _year(r.date)) for r in rounds if _year(r.date)]
    years = [y for _, y in dated]
    if years != sorted(years):
        out.append(("error", f"funding: rounds out of chronological order: "
                             f"{[f'{lbl} {y}' for lbl, y in dated]}"))

    # rounds with no amount are absent from the chart — advisory (a round may
    # legitimately have no disclosed amount)
    no_amount = [r.label for r in rounds if not r.amount]
    if no_amount and len(sb.funding.chart) < len(rounds):
        out.append(("warning", f"funding: {len(no_amount)} round(s) missing an "
                               f"amount, so absent from the chart: {no_amount}"))

    # later round valued below an earlier round (usually a parse/units mistake) — hard
    vals = [(r.label, _year(r.date), _money_to_float(r.valuation))
            for r in rounds if r.valuation]
    vals = [v for v in vals if v[2] is not None]
    for (l1, y1, v1), (l2, y2, v2) in zip(vals, vals[1:]):
        if y1 and y2 and y1 <= y2 and v2 < v1:
            out.append(("error", f"funding: valuation drops {l1} ({y1}) ${v1:,.0f} "
                                 f"-> {l2} ({y2}) ${v2:,.0f} — verify units/order"))
    return out


def _audit_competitors(sb: StoryBrief) -> List[Issue]:
    out: List[Issue] = []
    cs = sb.competitors
    if not cs:
        return out
    quads = cs.quadrants

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
