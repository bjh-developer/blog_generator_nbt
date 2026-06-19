# Editorial Luma-Style Fine-Tune Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make future startup breakdowns match the Luma reference blog — succinct stat bar + timeline, clean funding, and a proper one-card-per-cell 2x2 competitor map.

**Architecture:** Fix at the editorial layer (final blend, where we control output) plus deterministic QA repair as a safety net. Four independent changes: stat-bar compression, funding cleanup, competitor-map enforcement, LLM-rewritten timeline.

**Tech Stack:** Python 3.10, Pydantic v2, pytest (`asyncio_mode=auto`), OpenRouter via `app.llm.gateway`.

---

## Context for the engineer

- All editorial logic lives in `backend/app/agents/editorial.py`. Pure helpers (slugify, stat_bar, timeline_items, funding_*) are deterministic and unit-tested. One LLM call (`gateway.complete_json(_SYS, digest, _Narratives, ...)`) produces NBT-voice prose into the `_Narratives` schema; `assemble()` turns `(ResearchDoc, _Narratives, sources)` into the final `StoryBrief`.
- QA lives in `backend/app/qa.py`: `audit(sb)` returns `[(severity, msg)]`; `split()` → `(errors, warnings)`; `repair(sb)` deterministically fixes hard-error classes. Pipeline runs audit → repair-on-error → re-audit → write.
- Run all tests from `backend/`: `python -m pytest -q`. Single test: `python -m pytest tests/test_editorial.py::test_name -v`.
- `TimelineKind` valid values: `founder_story`, `product`, `funding`, `inflection`, `user_delight`.

## File structure

- Modify: `backend/app/agents/editorial.py` — stat compression, `clean_funding` (replaces `dedupe_funding`), `_TimelineN` schema + timeline assembly, `_SYS` prompt updates.
- Modify: `backend/app/qa.py` — extend `_repair_competitors` (winner→tr + collision reassignment).
- Modify: `backend/tests/test_editorial.py` — stat + funding + timeline tests (rename existing dedupe test).
- Modify: `backend/tests/test_qa.py` — competitor repair tests.

---

## Task 1: Stat-bar compression + length cap

**Files:**
- Modify: `backend/app/agents/editorial.py` (the `_QUANT` / `normalize_stat_value` / `stat_bar` block)
- Test: `backend/tests/test_editorial.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_editorial.py`:

```python
def test_normalize_stat_compresses_units():
    f = editorial.normalize_stat_value
    assert f("$1.1 billion") == "$1.1B"
    assert f("42 million") == "42M"
    assert f("Over $42 billion") == ">$42B"      # quantifier + unit both applied


def test_stat_bar_drops_overlong_prose_values():
    rd = ResearchDoc(startup_name="Carousell", metrics=[
        Metric(label="App Store Ranking", value="Top 2 Free Lifestyle App in Singapore"),
        Metric(label="Valuation", value="$1.1 billion"),
    ])
    bar = editorial.stat_bar(rd)
    vals = [s.value for s in bar]
    assert "$1.1B" in vals
    assert all(len(v) <= 12 for v in vals)        # prose stat dropped
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && python -m pytest tests/test_editorial.py::test_normalize_stat_compresses_units tests/test_editorial.py::test_stat_bar_drops_overlong_prose_values -v`
Expected: FAIL (`$1.1 billion` not compressed; prose value present).

- [ ] **Step 3: Implement compression + cap**

In `backend/app/agents/editorial.py`, replace the `normalize_stat_value` / `stat_bar` block with:

```python
# quantifier words -> symbol, applied to the front of a stat value
_QUANT = [
    ("more than ", ">"), ("over ", ">"), ("greater than ", ">"), ("at least ", ">"),
    ("less than ", "<"), ("under ", "<"), ("fewer than ", "<"), ("up to ", "<"),
    ("approximately ", "~"), ("approx ", "~"), ("nearly ", "~"), ("almost ", "~"),
    ("around ", "~"), ("about ", "~"),
]
# verbose magnitude words -> compact suffix (first match wins; space forms first)
_UNIT = [(" billion", "B"), (" million", "M"), (" thousand", "K"),
         ("bn", "B"), ("mn", "M")]
_STAT_MAX_LEN = 12


def _compress_units(v: str) -> str:
    low = v.lower()
    for word, sym in _UNIT:
        idx = low.find(word)
        if idx != -1:
            return v[:idx] + sym + v[idx + len(word):]
    return v


def normalize_stat_value(value: str) -> str:
    v = value.strip()
    low = v.lower()
    for word, sym in _QUANT:
        if low.startswith(word):
            v = sym + v[len(word):].lstrip()
            break
    return _compress_units(v)


def stat_bar(rd: ResearchDoc) -> List[StatItem]:
    out: List[StatItem] = []
    for m in rd.metrics:
        val = normalize_stat_value(m.value)
        if len(val) > _STAT_MAX_LEN:
            continue                       # drop prose-like stats (e.g. "Top 2 Free...")
        out.append(StatItem(value=val, label=m.label))
        if len(out) >= 4:
            break
    return out
```

- [ ] **Step 4: Run to verify pass (and no regressions)**

Run: `cd backend && python -m pytest tests/test_editorial.py -v`
Expected: PASS, including existing `test_normalize_stat_value_words_to_symbols` and `test_stat_bar_*`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/editorial.py backend/tests/test_editorial.py
git commit -m "feat(editorial): compress stat units and drop prose stats"
```

---

## Task 2: Funding cleanup (`clean_funding` replaces `dedupe_funding`)

**Files:**
- Modify: `backend/app/agents/editorial.py` (`dedupe_funding` function + its call in `build()`)
- Test: `backend/tests/test_editorial.py`

- [ ] **Step 1: Write failing tests**

In `backend/tests/test_editorial.py`, **replace** the existing `test_dedupe_funding_collapses_and_sorts_and_backfills` with:

```python
def test_clean_funding_drops_junk_amountless_dedupes_sorts():
    funding = [
        FundingRound(round="", date="", amount_usd=None),                       # junk: empty
        FundingRound(round="Multiple rounds (unspecified)", date="2012-2019",
                     valuation_usd=550_000_000),                                # junk label
        FundingRound(round="Grant", date="2012", amount_usd=None),             # no amount
        FundingRound(round="Series C", date="2017", amount_usd=85_000_000),
        FundingRound(round="Series C (2017)", date="2017"),                    # dup, no amount
        FundingRound(round="Seed", date="2013", amount_usd=800_000),
    ]
    out = editorial.clean_funding(funding)
    labels = [f.round for f in out]
    assert labels == ["Seed", "Series C"]            # junk + amount-less gone, sorted by date
    assert all(f.amount_usd for f in out)


def test_clean_funding_backfills_amount_from_duplicate():
    funding = [
        FundingRound(round="Series A", date="2014"),                  # no amount
        FundingRound(round="Series A (2014)", date="2014", amount_usd=7_800_000),
    ]
    out = editorial.clean_funding(funding)
    assert len(out) == 1
    assert out[0].amount_usd == 7_800_000            # backfilled before amount-less drop
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && python -m pytest tests/test_editorial.py::test_clean_funding_drops_junk_amountless_dedupes_sorts tests/test_editorial.py::test_clean_funding_backfills_amount_from_duplicate -v`
Expected: FAIL with `AttributeError: module 'app.agents.editorial' has no attribute 'clean_funding'`.

- [ ] **Step 3: Implement `clean_funding`**

In `backend/app/agents/editorial.py`, **replace** the entire `dedupe_funding` function with (`re` is already imported at top of file):

```python
_FUNDING_JUNK = ("unspecified", "multiple rounds")


def clean_funding(funding: list) -> list:
    """Turn the research merge's noisy funding list into clean, chartable rounds.

    1. drop junk-label rounds (empty / 'unspecified' / 'multiple rounds')
    2. dedupe by (label sans trailing '(YYYY)', year), backfilling amount/val/investors
    3. drop rounds with no amount (can't be charted, clutter the list)
    4. sort chronologically
    """
    kept = []
    for f in funding:
        lbl = (f.round or "").strip()
        if not lbl:
            continue
        if any(j in lbl.lower() for j in _FUNDING_JUNK):
            continue
        kept.append(f)

    by_key: dict = {}
    order: list = []
    for f in kept:
        base = re.sub(r"\s*\(\d{4}\)$", "", f.round).strip().lower()
        key = (base, (f.date or "")[:4])
        if key not in by_key:
            by_key[key] = f
            order.append(key)
        else:
            k = by_key[key]
            if not k.amount_usd and f.amount_usd:
                k.amount_usd = f.amount_usd
            if not k.valuation_usd and f.valuation_usd:
                k.valuation_usd = f.valuation_usd
            if not k.investors and f.investors:
                k.investors = f.investors
    deduped = [by_key[k] for k in order]

    deduped = [f for f in deduped if f.amount_usd]
    deduped.sort(key=lambda f: f.date or "")
    return deduped
```

- [ ] **Step 4: Update the call in `build()`**

In `backend/app/agents/editorial.py`, inside `build()`, replace the dedupe block:

```python
    # collapse duplicate funding rounds the research merge produced across sources
    if rd.funding:
        before = len(rd.funding)
        rd.funding = dedupe_funding(rd.funding)
        if len(rd.funding) != before:
            log.info("funding deduped: %d -> %d rounds", before, len(rd.funding))
```

with:

```python
    # clean the research merge's noisy funding into chartable rounds; an empty
    # result makes assemble() omit the funding section entirely
    if rd.funding:
        before = len(rd.funding)
        rd.funding = clean_funding(rd.funding)
        if len(rd.funding) != before:
            log.info("funding cleaned: %d -> %d rounds", before, len(rd.funding))
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_editorial.py -v`
Expected: PASS. (`assemble()` already sets `funding=None` when no chart and no rounds, so ≥1 survivor → section shows, 0 → omitted.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/editorial.py backend/tests/test_editorial.py
git commit -m "feat(editorial): clean_funding drops junk/amount-less rounds, dedupes"
```

---

## Task 3: Competitor map — winner→tr + collision reassignment

**Files:**
- Modify: `backend/app/qa.py` (`_repair_competitors`)
- Test: `backend/tests/test_qa.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_qa.py`:

```python
def test_repair_forces_winner_into_tr():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Carousell", quadrant="br", winner=True),
        QuadrantItem(name="eBay", quadrant="tl"),
    ]))
    sb = qa.repair(sb)
    winner = next(q for q in sb.competitors.quadrants if q.winner)
    assert winner.quadrant == "tr"


def test_repair_reassigns_colliding_cells_to_unique():
    # the Carousell bug: eBay + forums both in tl
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Carousell", quadrant="br", winner=True),
        QuadrantItem(name="eBay", quadrant="tl"),
        QuadrantItem(name="Forums", quadrant="tl"),
        QuadrantItem(name="Facebook Marketplace", quadrant="bl"),
    ]))
    sb = qa.repair(sb)
    cells = [q.quadrant for q in sb.competitors.quadrants]
    assert len(set(cells)) == len(cells)           # all unique cells
    assert qa.split(qa.audit(sb))[0] == []         # no errors remain
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && python -m pytest tests/test_qa.py::test_repair_forces_winner_into_tr tests/test_qa.py::test_repair_reassigns_colliding_cells_to_unique -v`
Expected: FAIL (winner stays in `br`; colliding cells remain duplicated).

- [ ] **Step 3: Extend `_repair_competitors`**

In `backend/app/qa.py`, **replace** the body of `_repair_competitors` with:

```python
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
            if free:
                q.quadrant = free
        used.add(q.quadrant)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_qa.py -v`
Expected: PASS, including existing `test_repair_enforces_single_winner`, `test_repair_drops_duplicate_competitor`, `test_competitor_*`.

- [ ] **Step 5: Update the editorial prompt for competitors**

In `backend/app/agents/editorial.py`, in `_SYS`, replace the quadrant rule line:

```python
    "- quadrants: place each competitor (and the subject company as winner=true) into "
    "tr/tl/br/bl of a 2x2 positioning map; set axis_x and axis_y. At most 5 quadrants.\n"
```

with:

```python
    "- competitors: EXACTLY 4 quadrants — the subject company plus 3 rivals. Place "
    "exactly ONE per cell (tr/tl/br/bl); never two in the same cell. The subject "
    "company is winner=true and MUST be placed in 'tr'. Always set axis_x and axis_y.\n"
```

- [ ] **Step 6: Run full suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/qa.py backend/app/agents/editorial.py backend/tests/test_qa.py
git commit -m "feat(qa): force competitor winner to tr and reassign colliding cells"
```

---

## Task 4: LLM-rewritten succinct timeline

**Files:**
- Modify: `backend/app/agents/editorial.py` (`_TimelineN` schema, `_Narratives` field + flatten filter, `_SYS` prompt + JSON template, `assemble`)
- Test: `backend/tests/test_editorial.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_editorial.py` (add `_TimelineN` to the existing `from app.agents.editorial import ...` line):

```python
def test_assemble_uses_llm_timeline_events_when_present():
    from app.agents.editorial import _TimelineN
    rd = ResearchDoc(startup_name="Luma")
    nar = _Narratives(hero_line1="a", hero_line2="b", timeline_events=[
        _TimelineN(year="2020", kind="founder_story", heading="The itch to scratch",
                   body="Built a tool for a friend."),
        _TimelineN(year="2023", kind="funding", heading="Series A: $30M",
                   body="Funded the shift to community OS."),
    ])
    sb = editorial.assemble(rd, nar, [])
    assert sb.timeline is not None
    assert [e.heading for e in sb.timeline.events] == ["The itch to scratch", "Series A: $30M"]
    assert sb.timeline.events[0].kind == "founder_story"


def test_assemble_falls_back_to_deterministic_timeline():
    from app.schemas import TimelineEvent
    rd = ResearchDoc(startup_name="Luma", timeline=[
        TimelineEvent(date="2020", kind="product", event="ship v1")])
    nar = _Narratives(hero_line1="a", hero_line2="b")     # no timeline_events
    sb = editorial.assemble(rd, nar, [])
    assert sb.timeline is not None
    assert sb.timeline.events[0].heading == "ship v1"      # deterministic fallback


def test_assemble_coerces_invalid_timeline_kind():
    from app.agents.editorial import _TimelineN
    rd = ResearchDoc(startup_name="Luma")
    nar = _Narratives(hero_line1="a", hero_line2="b", timeline_events=[
        _TimelineN(year="2020", kind="bogus", heading="x", body="y")])
    sb = editorial.assemble(rd, nar, [])
    assert sb.timeline.events[0].kind == "product"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && python -m pytest tests/test_editorial.py::test_assemble_uses_llm_timeline_events_when_present -v`
Expected: FAIL with `ImportError: cannot import name '_TimelineN'`.

- [ ] **Step 3: Add the `_TimelineN` schema**

In `backend/app/agents/editorial.py`, add directly above `class _Quadrant(LenientModel):`:

```python
class _TimelineN(LenientModel):
    year: str = ""
    kind: str = "product"
    heading: str
    body: str = ""
```

- [ ] **Step 4: Add the field + flatten filter to `_Narratives`**

In `_Narratives`, add the field next to the other list fields (e.g. after `loop_nodes`):

```python
    timeline_events: List[_TimelineN] = Field(default_factory=list)
```

Then inside the `_flatten` model_validator, just before `return d`, add a guard that drops malformed entries (mirrors the existing `lessons`/`quadrants` guards):

```python
        if isinstance(d.get("timeline_events"), list):
            d["timeline_events"] = [x for x in d["timeline_events"]
                                    if not isinstance(x, dict) or x.get("heading")]
```

- [ ] **Step 5: Build timeline from `_Narratives` in `assemble` (with fallback)**

In `assemble()`, replace:

```python
    tl_items = timeline_items(rd)
    timeline = TimelineSection(title=nar.timeline_title, events=tl_items) if tl_items else None
```

with:

```python
    _VALID_KINDS = ("founder_story", "product", "funding", "inflection", "user_delight")
    if nar.timeline_events:
        tl_items = [TimelineItem(
            year=t.year,
            kind=(t.kind if t.kind in _VALID_KINDS else "product"),
            heading=t.heading, body=t.body) for t in nar.timeline_events if t.heading]
    else:
        tl_items = timeline_items(rd)        # deterministic fallback
    timeline = TimelineSection(title=nar.timeline_title, events=tl_items) if tl_items else None
```

- [ ] **Step 6: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_editorial.py -v`
Expected: PASS (all three new timeline tests + existing `timeline_items` tests via fallback path).

- [ ] **Step 7: Update the editorial prompt + JSON template**

In `backend/app/agents/editorial.py` `_SYS`, add a timeline rule after the loop_nodes rule:

```python
    "- timeline_events: choose 4-6 KEY moments from the research that define the "
    "success/failure storyline. Each heading <= 6 words; body one sentence. Assign "
    "a varied kind (founder_story/product/funding/inflection/user_delight) — do NOT "
    "tag everything the same. Order chronologically by year.\n"
```

And in the JSON template string in `_SYS`, add after the `"loop_nodes"`/`"loop_center"` keys (before `"funding_title"`):

```python
    '"timeline_events":[{"year":"","kind":"product","heading":"","body":""}],'
```

- [ ] **Step 8: Run full suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS (all tests).

- [ ] **Step 9: Commit**

```bash
git add backend/app/agents/editorial.py backend/tests/test_editorial.py
git commit -m "feat(editorial): LLM rewrites succinct varied-kind timeline with fallback"
```

---

## Final verification

- [ ] Run `cd backend && python -m pytest -q` — all tests pass.
- [ ] Sanity check: with `PROMPT_CACHE=0`, regenerate a noisy company (e.g. `curl -X POST localhost:8000/generate -d '{"query":"Carousell"}'`) and confirm: funding has only amount-bearing rounds, competitor map has one card per cell with the winner in `tr`, timeline headings are short and varied, stat values are compact. (Manual, requires API keys.)

## Notes
- The pipeline already runs `qa.audit` → `qa.repair` → re-audit → write, so Task 3's repair changes take effect automatically.
- No frontend changes: `TimelineItem`, `FundingSection`, `CompetitorSection`, `Hero.stat_bar` shapes are unchanged.
