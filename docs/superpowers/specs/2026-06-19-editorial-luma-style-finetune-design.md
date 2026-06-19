# Editorial fine-tune: match Luma blog style

**Date:** 2026-06-19
**Status:** Approved, pending implementation plan

## Problem

The Carousell breakdown is visibly worse than the Luma reference blog across four
dimensions. Side-by-side:

| Dimension | Luma (target) | Carousell (broken) |
|---|---|---|
| Timeline | 5 events, mixed kinds, headings 4–6 words | 6 events, all `inflection`, headings are 30-word run-on sentences |
| Funding | 2 rounds, both have amounts, chart matches | 13 rounds, 6 with no amount, junk labels (`""`, `"Multiple rounds (unspecified)"`, `"Unspecified"`), duplicate Series A/B/C across guessed years |
| Competitor map | one card per cell, winner top-right (`tr`) | eBay + "Traditional forums" both in `tl`, `tr` empty, winner in `br` |
| Stat bar | "5M+", "$30M", "$1.1B" | "Top 2 Free Lifestyle App in Singapore", "$1.1 billion" |

### Root causes
1. **Funding** — research merges ~8 sources, each guessing rounds → contradictory
   duplicates. `dedupe_funding` keys on (label, year), so `"Series A"` vs
   `"Series A (2015)"` slip through. Amount-less guessed rounds pollute the list.
2. **Timeline** — headings are `research.event` verbatim (long); research tagged
   every event `inflection`. Editorial never rewrites them.
3. **Competitor map** — editorial LLM places cards freely; nothing forces
   one-per-cell or winner→`tr`. QA only *warns* on collisions.
4. **Stats** — `normalize_stat_value` maps "over"→">" but does not abbreviate
   "billion"→"B" or cap length, so prose stats reach the bar.

## Goals

Future breakdowns match Luma's succinctness and a clean 2x2 competitive map,
without regenerating existing blogs. Fix at the **editorial layer** (final-blend
control) plus **QA repair** (deterministic safety net). Research agent prompt and
frontend components are out of scope.

## Design

### 1. Funding cleanup — `backend/app/agents/editorial.py`

Replace `dedupe_funding` with `clean_funding(funding) -> list`, applied in
`build()`. Steps in order:

1. Drop junk-label rounds: label is empty, or (case-insensitive) contains
   `"unspecified"` or `"multiple rounds"`.
2. Drop rounds with no `amount_usd`.
3. Dedupe by `(base_label, year)` where `base_label` is the label with a trailing
   `" (YYYY)"` stripped; backfill `amount_usd` / `valuation_usd` / `investors`
   from a dropped duplicate onto the kept one when the kept one lacks them.
4. Sort chronologically by `date`.

`build()`: if 0 rounds survive, `funding = None`; if ≥1, build the section. Chart
derives only from surviving rounds (all have amounts), so chart and round list
always agree. The "rounds missing amount" QA warning becomes unreachable.

**Decision:** keep the section when ≥1 real round remains (not a stricter "hide if
any round lacks amount").

### 2. Competitive map — prompt + QA repair

**Prompt (`_SYS` in editorial.py):** require exactly 4 quadrants (subject + 3
rivals), exactly one competitor per cell (`tr`/`tl`/`br`/`bl`), subject
`winner=true` placed in `tr`, and `axis_x` + `axis_y` always set.

**`_repair_competitors` in `backend/app/qa.py`** (extends existing dedupe +
single-winner logic):
- After enforcing exactly one winner, move the winner card to `tr`.
- Resolve cell collisions: walk cells in order `tr, tl, br, bl`; if a card's cell
  is already taken, reassign it to the next empty cell. Guarantees a clean 2x2.

QA audit keeps the cell-collision check as an advisory warning (pre-repair signal).

### 3. Timeline rewrite — editorial LLM

Add to `_Narratives`:
```
class _TimelineN(LenientModel):
    year: str = ""
    kind: str = "product"
    heading: str           # <= 6 words
    body: str = ""         # <= 1 sentence

timeline_events: List[_TimelineN] = Field(default_factory=list)
```

**Prompt:** from the research TIMELINE + PRODUCT EVOLUTION (already in the
digest), pick 4–6 key moments, rewrite each heading to ≤6 words, body to one
sentence, assign a varied `kind`
(`founder_story`/`product`/`funding`/`inflection`/`user_delight`), ordered
chronologically.

**`assemble`:** build `TimelineSection` from `nar.timeline_events` when present;
**fall back** to the existing deterministic `timeline_items(rd)` when the LLM
returns none. `timeline_items` is retained as the fallback path. Invalid `kind`
values coerce to `"product"` (mirror existing quadrant coercion).

### 4. Stat bar — `editorial.py`

Extend `normalize_stat_value`: after quantifier mapping, compress units
case-insensitively — ` billion`/`bn` → `B`, ` million`/`mn` → `M`, ` thousand` →
`K` — so `$1.1 billion` → `$1.1B`.

`stat_bar`: drop any stat whose normalized `value` length exceeds 12 characters
(kills prose like "Top 2 Free Lifestyle App in Singapore"); keep up to 4. Luma's
values ("5M+", "300K", "150+", "$30M", "$1.1B") all pass.

## Testing

- `test_editorial.py`: `clean_funding` (drops junk + amount-less, dedupes, sorts,
  backfills); stat unit compression; stat length-drop; timeline built from LLM
  events; timeline fallback to deterministic when LLM empty.
- `test_qa.py`: winner forced to `tr`; cell-collision reassignment yields a clean
  2x2.

## Out of scope
- Research agent extraction prompt (fixed at editorial layer instead).
- Frontend components.
- Regenerating existing breakdown JSON files.
