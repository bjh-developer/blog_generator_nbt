# NBT Startup Breakdown Blog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a company name into a hyperlinkable, multi-page editorial "startup breakdown" blog that teaches/inspires youth entrepreneurs.

**Architecture:** Python pipeline (Firecrawl full-scrape → ResearchAgent structured JSON → VerifyAgent grounding+relevance → EditorialAgent story_brief JSON) writes one JSON per company into a Next.js app's `content/` dir; Next.js renders a fixed editorial section template (SSG) at `/breakdowns/[slug]`.

**Tech Stack:** Python 3.10, FastAPI, httpx, Firecrawl v2, OpenRouter (free models), Pydantic v2, pytest · Next.js 14 (app router), TypeScript, Tailwind, shadcn/ui, lucide-react, recharts.

---

## Reference files (read before starting)

- Spec: `docs/superpowers/specs/2026-06-14-nbt-startup-breakdown-blog-design.md`
- Existing backend to reuse: `backend/app/llm/gateway.py` (throttle/retry/JSON-repair — keep as-is), `backend/app/agents/source.py` (Firecrawl search — extend for full content), `backend/app/config.py`, `backend/app/store.py`.
- Content reference: `Codex of STARTUP BREAKDOWNS.md` (Luma/ShopBack/Framer + Perplexity→Codex prompts) in user's Downloads.

## File structure

```
backend/app/
  schemas.py            REWRITE: ResearchDoc + StoryBrief (+ sub-models)
  agents/source.py      EXTEND: ensure full markdown content returned
  agents/research.py    NEW: full content -> ResearchDoc
  agents/verify.py      REWRITE: ground + relevance score over ResearchDoc items
  agents/editorial.py   NEW: ResearchDoc -> StoryBrief
  pipeline.py           NEW: orchestrate, write web/content/breakdowns/<slug>.json
  main.py               REWRITE: POST /generate, GET /health
backend/tests/          fixture-driven, offline

web/                    NEW (create-next-app)
  content/breakdowns/*.json
  lib/types.ts          mirror StoryBrief
  lib/theme.ts          brand tokens + per-section accent rotation
  lib/content.ts        load+validate content files
  components/sections/*  one per template section
  components/ui/*        shadcn
  app/breakdowns/page.tsx
  app/breakdowns/[slug]/page.tsx
  app/layout.tsx, globals.css, public/fonts/bernoru.woff2
```

---

# PHASE 1 — Backend data contracts

### Task 1: Rewrite schemas (ResearchDoc + StoryBrief)

**Files:**
- Rewrite: `backend/app/schemas.py`
- Test: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_schemas.py
from app.schemas import ResearchDoc, StoryBrief, StoryMeta, Hero, StatItem


def test_storybrief_minimal_valid():
    sb = StoryBrief(
        meta=StoryMeta(startup_name="Luma", slug="luma", volume="Vol. 01",
                       category_tag="Community Infrastructure", research_date="2026-06-14"),
        hero=Hero(line1="Luma didn't build an event platform.",
                  line2="They built infrastructure for identities.",
                  accent_word_orange="infrastructure", accent_word_purple="identities",
                  subheadline="How a calendar tool became the OS for startup communities.",
                  stat_bar=[StatItem(value="5M+", label="Monthly Attendees")]),
        lessons=[],
    )
    assert sb.meta.slug == "luma"
    assert sb.hero.stat_bar[0].value == "5M+"
    # optional sections default to None and are omitted from the UI
    assert sb.competitors is None


def test_researchdoc_allows_nulls():
    rd = ResearchDoc(startup_name="Luma")
    assert rd.tagline is None
    assert rd.timeline == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && . .venv/bin/activate && python -m pytest tests/test_schemas.py -v`
Expected: FAIL (ImportError: cannot import name 'StoryBrief').

- [ ] **Step 3: Write `backend/app/schemas.py`**

```python
"""Data contracts. ResearchDoc = internal sourced research. StoryBrief = editorial
output that drives the Next.js UI. Mirror StoryBrief in web/lib/types.ts."""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# ---- shared ----
class SourceRef(BaseModel):
    quote: Optional[str] = None
    outlet: Optional[str] = None
    url: Optional[str] = None

# ---- ResearchDoc (internal) ----
class TimelineEvent(BaseModel):
    date: str                       # YYYY | YYYY-MM | YYYY-MM-DD
    kind: Literal["founder_story", "product", "funding", "inflection", "user_delight"] = "product"
    event: str
    significance: str = ""
    source: SourceRef = Field(default_factory=SourceRef)

class Founder(BaseModel):
    name: str
    role: str = ""
    background: str = ""
    why: Optional[str] = None
    source: SourceRef = Field(default_factory=SourceRef)

class FundingRound(BaseModel):
    round: str
    date: str = ""
    amount_usd: Optional[float] = None
    valuation_usd: Optional[float] = None
    investors: List[str] = []
    source: SourceRef = Field(default_factory=SourceRef)

class Metric(BaseModel):
    label: str
    value: str
    date: Optional[str] = None
    source_url: Optional[str] = None

class Competitor(BaseModel):
    name: str
    positioning: str = ""
    strengths: List[str] = []
    weaknesses: List[str] = []
    our_advantage: Optional[str] = None

class Lesson(BaseModel):
    lesson: str
    context: str = ""
    applicable_to: str = ""
    source: SourceRef = Field(default_factory=SourceRef)

class ResearchDoc(BaseModel):
    startup_name: str
    tagline: Optional[str] = None
    pivotal_insight: Optional[str] = None
    origin_story: Optional[str] = None
    timeline: List[TimelineEvent] = []
    founders: List[Founder] = []
    product_evolution: List[TimelineEvent] = []
    funding: List[FundingRound] = []
    metrics: List[Metric] = []
    competitors: List[Competitor] = []
    product_loop_steps: List[str] = []
    lessons: List[Lesson] = []
    sources: List[SourceRef] = []

# ---- StoryBrief (drives UI) ----
class StoryMeta(BaseModel):
    startup_name: str
    slug: str
    volume: str
    category_tag: str
    research_date: str

class StatItem(BaseModel):
    value: str
    label: str

class Hero(BaseModel):
    line1: str
    line2: str
    accent_word_orange: Optional[str] = None
    accent_word_purple: Optional[str] = None
    subheadline: str = ""
    stat_bar: List[StatItem] = []

class CoreInsight(BaseModel):
    title: str
    statement: str
    narrative: str = ""
    icon: str = "Lightbulb"

class TimelineItem(BaseModel):
    year: str
    kind: Literal["founder_story", "product", "funding", "inflection", "user_delight"] = "product"
    heading: str
    body: str = ""

class TimelineSection(BaseModel):
    title: str
    events: List[TimelineItem] = []

class LoopNode(BaseModel):
    label: str
    sub: str = ""

class ProductLoop(BaseModel):
    title: str
    nodes: List[LoopNode] = []        # exactly 4 for the circular diagram
    center_label: str = "NETWORK EFFECT"
    caption: str = ""

class FundingPoint(BaseModel):
    label: str
    value: float
    unit: Optional[str] = None
    date: Optional[str] = None

class FundingRoundView(BaseModel):
    label: str
    date: str = ""
    amount: Optional[str] = None
    valuation: Optional[str] = None
    signal: str = ""

class FundingSection(BaseModel):
    title: str
    narrative: str = ""
    rounds: List[FundingRoundView] = []
    chart: List[FundingPoint] = []
    pricing_note: Optional[str] = None

class QuadrantItem(BaseModel):
    name: str
    their_bet: str = ""
    the_gap: str = ""
    quadrant: Literal["tr", "tl", "br", "bl"] = "tr"
    winner: bool = False

class CompetitorSection(BaseModel):
    title: str
    framing: str = ""
    axis_x: str = ""
    axis_y: str = ""
    quadrants: List[QuadrantItem] = []

class FounderModeFact(BaseModel):
    label: str
    value: str

class FounderMode(BaseModel):
    title: str
    narrative: str = ""
    facts: List[FounderModeFact] = []

class LessonCard(BaseModel):
    number: int
    headline: str
    body: str = ""
    applicable_to: str = ""

class Closing(BaseModel):
    title: str
    narrative: str = ""
    pull_quote: Optional[str] = None
    attribution: Optional[str] = None

class StoryBrief(BaseModel):
    meta: StoryMeta
    hero: Hero
    core_insight: Optional[CoreInsight] = None
    timeline: Optional[TimelineSection] = None
    product_loop: Optional[ProductLoop] = None
    funding: Optional[FundingSection] = None
    competitors: Optional[CompetitorSection] = None
    founder_mode: Optional[FounderMode] = None
    lessons: List[LessonCard] = []
    closing: Optional[Closing] = None
    sources: List[SourceRef] = []
    overall_confidence: float = 0.0


class GenerateRequest(BaseModel):
    query: str = Field(..., min_length=2)
    max_sources: int = 8
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && . .venv/bin/activate && python -m pytest tests/test_schemas.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Delete obsolete tests/modules that import the old schema**

Remove `backend/tests/test_design.py`, `backend/tests/test_summarize_parse.py`, `backend/tests/test_verify.py` (old shapes), and old `backend/app/agents/{summarize,design}.py`, `backend/app/orchestrator.py`. Keep `gateway`, `source`, `config`, `store`, `test_json_repair.py`, `test_source_helpers.py`.

Run: `cd backend && . .venv/bin/activate && python -m pytest -q`
Expected: PASS (json_repair + source_helpers + schemas).

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(backend): ResearchDoc + StoryBrief schemas"`

---

# PHASE 2 — Source full content

### Task 2: Ensure SourceAgent returns full scraped markdown

**Files:**
- Modify: `backend/app/agents/source.py` (return full text; raise scrape limit)
- Test: `backend/tests/test_source_full.py`

- [ ] **Step 1: Write the failing test** (pure helper, no network)

```python
# backend/tests/test_source_full.py
from app.agents.source import _normalize_results

def test_normalize_keeps_full_markdown():
    raw = {"data": {"web": [
        {"url": "https://x.com/a", "title": "A", "markdown": "M" * 5000,
         "metadata": {"title": "A"}},
    ]}}
    out = _normalize_results(raw)
    assert len(out) == 1
    assert len(out[0]["text"]) == 5000
    assert out[0]["domain"] == "x.com"
```

- [ ] **Step 2: Run** `pytest tests/test_source_full.py -v` → FAIL (no `_normalize_results`).

- [ ] **Step 3:** In `source.py`, extract the response-parsing block of `_firecrawl_search` into a module-level pure function and call it:

```python
def _normalize_results(data: dict) -> list[dict]:
    body = data.get("data", data)
    results = body.get("web", []) if isinstance(body, dict) else (body or [])
    out: list[dict] = []
    for x in results:
        url = x.get("url", "")
        md = x.get("markdown") or x.get("content") or x.get("description") or ""
        out.append({
            "url": url,
            "title": x.get("title") or x.get("metadata", {}).get("title", ""),
            "domain": urlparse(url).netloc,
            "text": md,
        })
    return out
```
Replace the inline parsing in `_firecrawl_search` with `return _normalize_results(data)`. In `gather`, raise the per-source text cap used downstream (do not truncate to 8000 here; keep full text in the cache file).

- [ ] **Step 4: Run** `pytest tests/test_source_full.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(source): full markdown extraction helper"`

---

# PHASE 3 — Research agent

### Task 3: ResearchAgent (full content → ResearchDoc)

**Files:**
- Create: `backend/app/agents/research.py`
- Test: `backend/tests/test_research.py`

- [ ] **Step 1: Write the failing test** (mock the gateway; assert mapping is pure)

```python
# backend/tests/test_research.py
import asyncio
from app.agents import research
from app.schemas import ResearchDoc

def test_merge_research_prefers_nonnull(monkeypatch):
    doc = research._merge("Luma", [
        {"startup_name": "Luma", "tagline": None, "timeline": [
            {"date": "2020", "kind": "founder_story", "event": "Founded", "significance": "x"}]},
        {"startup_name": "Luma", "tagline": "Event OS", "metrics": [
            {"label": "Hosts", "value": "250K+"}]},
    ])
    assert isinstance(doc, ResearchDoc)
    assert doc.tagline == "Event OS"
    assert len(doc.timeline) == 1
    assert doc.metrics[0].value == "250K+"
```

- [ ] **Step 2: Run** `pytest tests/test_research.py -v` → FAIL.

- [ ] **Step 3: Write `research.py`** — per-source LLM extraction into a partial ResearchDoc, then merge. Prompt mirrors the Codex Perplexity schema, hard rule "null if unverifiable, never fabricate". Key code:

```python
"""ResearchAgent: full article text -> structured, sourced ResearchDoc.
Runs once per source then merges; sets unverifiable fields to null."""
from __future__ import annotations
import logging
from app import store
from app.llm import gateway
from app.schemas import ResearchDoc
log = logging.getLogger("app.agents.research")

_SYS = (
  "You are a startup research analyst building a factual breakdown for a youth "
  "entrepreneur blog. From the ARTICLE, extract ONLY verifiable, story-defining "
  "facts about the company. Set any field you cannot support to null/empty. "
  "Never invent numbers, names, dates, or quotes.\n"
  "Return JSON matching this shape (omit unknowns):\n"
  '{"startup_name":"","tagline":null,"pivotal_insight":null,"origin_story":null,'
  '"timeline":[{"date":"YYYY","kind":"founder_story|product|funding|inflection|user_delight",'
  '"event":"","significance":"","source":{"quote":"","url":""}}],'
  '"founders":[{"name":"","role":"","background":"","why":null,"source":{"quote":"","url":""}}],'
  '"funding":[{"round":"","date":"","amount_usd":null,"valuation_usd":null,"investors":[],'
  '"source":{"quote":"","url":""}}],'
  '"metrics":[{"label":"","value":"","date":null,"source_url":null}],'
  '"competitors":[{"name":"","positioning":"","strengths":[],"weaknesses":[],"our_advantage":null}],'
  '"product_loop_steps":[],"lessons":[{"lesson":"","context":"","applicable_to":"","source":{"quote":"","url":""}}]}'
)

async def _extract_one(text: str, url: str) -> dict:
    from app.schemas import ResearchDoc as _RD
    try:
        rd = await gateway.complete_json(_SYS, f"SOURCE_URL: {url}\n\nARTICLE:\n{text[:16000]}",
                                         _RD, role="general")
        return rd.model_dump()
    except gateway.LLMError as e:
        log.warning("research extract failed %s: %s", url, e)
        return {}

def _merge(name: str, partials: list[dict]) -> ResearchDoc:
    base = {"startup_name": name}
    list_keys = ["timeline","founders","product_evolution","funding","metrics",
                 "competitors","product_loop_steps","lessons","sources"]
    scalar_keys = ["tagline","pivotal_insight","origin_story"]
    for k in list_keys: base[k] = []
    for p in partials:
        for k in scalar_keys:
            if not base.get(k) and p.get(k): base[k] = p[k]
        for k in list_keys:
            if p.get(k): base[k].extend(p[k])
    return ResearchDoc.model_validate(base)

async def run(sources: list, name: str) -> ResearchDoc:
    log.info("=== research: %d sources for %s ===", len(sources), name)
    partials = []
    for s in sources:
        text = store.read_cached_text(s.raw_text_ref)
        if text:
            partials.append(await _extract_one(text, s.url))
    doc = _merge(name, partials)
    log.info("=== research done: %d timeline, %d funding, %d metrics, %d competitors ===",
             len(doc.timeline), len(doc.funding), len(doc.metrics), len(doc.competitors))
    return doc
```

- [ ] **Step 4: Run** `pytest tests/test_research.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(research): full-content -> ResearchDoc agent"`

---

# PHASE 4 — Verify (grounding + relevance)

### Task 4: VerifyAgent over ResearchDoc items

**Files:**
- Rewrite: `backend/app/agents/verify.py`
- Test: `backend/tests/test_verify.py`

- [ ] **Step 1: Write the failing test** (pure grounding; relevance gate mocked)

```python
# backend/tests/test_verify.py
from app.agents import verify

TEXT = "Luma raised $3 million in 2020. It now has 250K+ active hosts across 150 countries."

def test_metric_grounded_high():
    assert verify.ground_score("250K+ active hosts", TEXT) >= 0.8

def test_metric_absent_low():
    assert verify.ground_score("900M users", TEXT) < 0.5

def test_filter_drops_ungrounded_metrics():
    from app.schemas import Metric
    kept = verify.filter_metrics(
        [Metric(label="Hosts", value="250K+"), Metric(label="Users", value="900M")],
        TEXT, threshold=0.5)
    assert [m.value for m in kept] == ["250K+"]
```

- [ ] **Step 2: Run** `pytest tests/test_verify.py -v` → FAIL.

- [ ] **Step 3: Write `verify.py`** — reuse the old fuzzy matcher; add `ground_score`, `filter_metrics`, and an async `relevance_filter` (LLM judge) that scores lessons/quotes against the youth-founder goal:

```python
"""VerifyAgent: ground ResearchDoc items in scraped text + relevance gate."""
from __future__ import annotations
import re, logging
from difflib import SequenceMatcher
from app import config
from app.llm import gateway
from app.schemas import Metric, Lesson
from pydantic import BaseModel
log = logging.getLogger("app.agents.verify")

def _norm(s): return re.sub(r"\s+", " ", s.lower()).strip()

def ground_score(claim: str, text: str) -> float:
    n, h = _norm(claim), _norm(text)
    if not n: return 0.0
    if n in h: return 1.0
    # token-window fuzzy
    win = max(8, len(n)); best = 0.0
    for i in range(0, max(1, len(h) - win + 1), max(1, win // 2)):
        best = max(best, SequenceMatcher(None, n, h[i:i+win]).ratio())
        if best >= 0.95: break
    # numbers in the claim must appear in text
    for num in re.findall(r"\d[\d,.]*", n):
        if num.replace(",", "") not in h.replace(",", ""): best *= 0.4
    return round(best, 3)

def filter_metrics(metrics: list[Metric], text: str, threshold: float = None) -> list[Metric]:
    t = config.VERIFY_THRESHOLD if threshold is None else threshold
    return [m for m in metrics if ground_score(f"{m.value} {m.label}", text) >= t]

class _Rel(BaseModel):
    keep_indices: list[int] = []

async def relevance_filter(items: list[str], goal: str) -> list[int]:
    """Return indices worth keeping for the youth-founder goal. Fail-open."""
    if not items: return []
    listing = "\n".join(f"[{i}] {t}" for i, t in enumerate(items))
    sys = ("You curate insights for an audience of 18-28 aspiring founders. "
           f"GOAL: {goal}. Keep only items that teach or inspire that audience; "
           "drop generic/trivial/PR fluff. Return JSON {\"keep_indices\":[...]}.")
    try:
        r = await gateway.complete_json(sys, listing, _Rel, role="fast")
        return [i for i in r.keep_indices if 0 <= i < len(items)]
    except gateway.LLMError:
        return list(range(len(items)))   # fail-open

GOAL = "teach and inspire aspiring youth entrepreneurs with a real startup story"
```

- [ ] **Step 4: Run** `pytest tests/test_verify.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(verify): grounding + relevance gate"`

---

# PHASE 5 — Editorial agent

### Task 5: EditorialAgent (ResearchDoc → StoryBrief)

**Files:**
- Create: `backend/app/agents/editorial.py`
- Test: `backend/tests/test_editorial.py`

- [ ] **Step 1: Write the failing test** (deterministic assembly helpers; LLM narrative mocked)

```python
# backend/tests/test_editorial.py
from app.agents import editorial
from app.schemas import ResearchDoc, FundingRound, Metric, TimelineEvent

def test_slug_and_volume():
    assert editorial.slugify("Luma.com") == "luma-com"

def test_funding_chart_from_rounds():
    rd = ResearchDoc(startup_name="Luma", funding=[
        FundingRound(round="Seed", date="2020", amount_usd=3_000_000),
        FundingRound(round="Series A", date="2022", amount_usd=30_000_000)])
    pts = editorial.funding_chart(rd)
    assert [p.value for p in pts] == [3.0, 30.0]      # normalized to $M
    assert pts[0].unit == "$M"

def test_stat_bar_from_metrics_only():
    rd = ResearchDoc(startup_name="Luma",
        metrics=[Metric(label="Active Hosts", value="250K+")])
    bar = editorial.stat_bar(rd)
    assert bar[0].value == "250K+"
```

- [ ] **Step 2: Run** `pytest tests/test_editorial.py -v` → FAIL.

- [ ] **Step 3: Write `editorial.py`** — pure assembly helpers (slug, funding_chart, stat_bar, timeline mapping, competitor quadrant mapping) + an async `write_narratives` LLM call producing the prose fields (hero lines, core insight, section narratives, lessons, closing) constrained to the research facts. `build()` composes a `StoryBrief`, leaving a section `None` when its source list is empty. Include the editorial system prompt adapted from the Codex `.md` "CODEX" stage (NBT voice, 2-part contrarian headline, prose not bullets, never invent stats).

Key pure helpers:
```python
import re
from app.schemas import (StoryBrief, StoryMeta, Hero, StatItem, FundingPoint, ...)

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def funding_chart(rd) -> list[FundingPoint]:
    pts = []
    for f in rd.funding:
        if f.amount_usd:
            pts.append(FundingPoint(label=f.round, value=round(f.amount_usd/1e6, 2),
                                    unit="$M", date=f.date or None))
    pts.sort(key=lambda p: p.date or "")
    return pts

def stat_bar(rd) -> list[StatItem]:
    return [StatItem(value=m.value, label=m.label) for m in rd.metrics[:4]]
```
`build()` calls `verify.filter_metrics` + `verify.relevance_filter` (on lessons) before composing, computes `overall_confidence` from kept-item grounding scores, and returns the `StoryBrief`.

- [ ] **Step 4: Run** `pytest tests/test_editorial.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(editorial): ResearchDoc -> StoryBrief"`

---

# PHASE 6 — Pipeline + API

### Task 6: pipeline.py + main.py

**Files:**
- Create: `backend/app/pipeline.py`
- Rewrite: `backend/app/main.py`
- Modify: `backend/app/config.py` (add `CONTENT_DIR` default `../web/content/breakdowns`)
- Test: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test** (write+read a StoryBrief to a temp content dir)

```python
# backend/tests/test_pipeline.py
from app import pipeline
from app.schemas import StoryBrief, StoryMeta, Hero

def test_write_story_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline.config, "CONTENT_DIR", tmp_path)
    sb = StoryBrief(meta=StoryMeta(startup_name="Luma", slug="luma", volume="Vol. 01",
                    category_tag="X", research_date="2026-06-14"),
                    hero=Hero(line1="a", line2="b"))
    path = pipeline.write_story(sb)
    assert path.name == "luma.json"
    assert (tmp_path / "luma.json").exists()
```

- [ ] **Step 2: Run** `pytest tests/test_pipeline.py -v` → FAIL.

- [ ] **Step 3: Write `pipeline.py`**:
```python
"""Orchestrate source -> research -> editorial -> write content file."""
from __future__ import annotations
import json, logging
from pathlib import Path
from app import config
from app.agents import source, research, editorial
from app.schemas import StoryBrief
log = logging.getLogger("app.pipeline")

def write_story(sb: StoryBrief) -> Path:
    config.CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    p = config.CONTENT_DIR / f"{sb.meta.slug}.json"
    p.write_text(sb.model_dump_json(indent=2), encoding="utf-8")
    return p

async def generate(query: str, max_sources: int = 8) -> StoryBrief:
    sources, _arc = await source.gather(query, max_sources=max_sources)
    rd = await research.run(sources, query)
    sb = await editorial.build(rd, sources)
    write_story(sb)
    return sb
```
Add to `config.py`:
```python
CONTENT_DIR = Path(os.getenv("CONTENT_DIR", BASE_DIR.parent / "web" / "content" / "breakdowns"))
```
Rewrite `main.py`: `POST /generate` → `pipeline.generate`, returns `{slug, path}`; `GET /health`.

- [ ] **Step 4: Run** `pytest tests/test_pipeline.py -v` → PASS, then full `pytest -q` (offline, OPENROUTER_API_KEY="") → all green.

- [ ] **Step 5: Live smoke (manual, env-gated):** with real keys, `uvicorn app.main:app` then `curl -X POST localhost:8000/generate -d '{"query":"Luma"}'`; open `web/content/breakdowns/luma.json`, confirm stat_bar values appear in scraped sources.

- [ ] **Step 6: Commit** — `git commit -am "feat(pipeline): generate + write content file; FastAPI /generate"`

---

# PHASE 7 — Next.js app scaffold + theme

### Task 7: Scaffold web app + brand tokens + types

**Files:**
- Create: `web/` via `npx create-next-app@latest web --ts --tailwind --app --eslint --no-src-dir --import-alias "@/*"`
- shadcn: `cd web && npx shadcn@latest init -d` then `npx shadcn@latest add card badge button separator tooltip chart avatar accordion`
- Create: `web/lib/types.ts`, `web/lib/theme.ts`, `web/lib/content.ts`
- Create: `web/public/fonts/bernoru.woff2` (placeholder note: operator supplies Bernoru; fallback Atkinson)

- [ ] **Step 1:** Scaffold + add shadcn components (commands above). Install `lucide-react recharts`.

- [ ] **Step 2: `web/lib/types.ts`** — hand-mirror of `StoryBrief` (and sub-types) from `backend/app/schemas.py`. Exact field names/optionality must match.

- [ ] **Step 3: `web/lib/theme.ts`**:
```ts
export const palette = { cream:"#fff4de", ink:"#352757", purple:"#784eb5",
  lilac:"#cdc5fc", orchid:"#e2a9f1", pink:"#faaef1", blue:"#5675f0",
  navy:"#0c3571", cyan:"#88e5f6", orange:"#ff914d", peach:"#ffb169" } as const;
export const chartColors = [palette.blue, palette.orange, palette.cyan, palette.peach, palette.navy];
// per-section accent rotation so adjacent sections differ
export const sectionAccents = [palette.orange, palette.purple, palette.blue,
  palette.pink, palette.cyan, palette.peach];
export const accentFor = (i:number) => sectionAccents[i % sectionAccents.length];
export const kindColor: Record<string,string> = {
  founder_story: palette.orange, product: palette.purple, funding: palette.blue,
  inflection: palette.cyan, user_delight: palette.pink };
```
Map brand colors into `tailwind.config.ts` `theme.extend.colors` (semantic names) + `globals.css` `@font-face` for Bernoru + cream background. Configure Atkinson Hyperlegible via `next/font/google`.

- [ ] **Step 4: `web/lib/content.ts`** — read+parse content dir:
```ts
import fs from "node:fs"; import path from "node:path";
import type { StoryBrief } from "./types";
const DIR = path.join(process.cwd(), "content", "breakdowns");
export function allSlugs(): string[] {
  if (!fs.existsSync(DIR)) return [];
  return fs.readdirSync(DIR).filter(f=>f.endsWith(".json")).map(f=>f.replace(/\.json$/,""));
}
export function getStory(slug: string): StoryBrief {
  return JSON.parse(fs.readFileSync(path.join(DIR, `${slug}.json`), "utf-8"));
}
```

- [ ] **Step 5: Seed sample content** — copy a hand-written `web/content/breakdowns/luma.json` (from the Codex `.md` Luma data, conforming to StoryBrief) so the UI renders before the pipeline runs live.

- [ ] **Step 6:** `cd web && npm run build` → succeeds. **Commit** — `git add web && git commit -m "feat(web): next.js + shadcn scaffold, brand tokens, content loader"`

---

# PHASE 8 — Section components

### Task 8: Build the section component library

**Files (one component each):** `web/components/sections/{PillNav,Hero,CoreInsight,Timeline,ProductLoop,Funding,Competitors,FounderMode,Lessons,Closing,Footer,ConfidenceBadge}.tsx`

Each is a server component (except interactive ones marked `"use client"`). Props = the matching StoryBrief sub-type. Build order with key requirements:

- [ ] **PillNav** — sticky rounded pill, Home/About/Breakdowns/Contact, Breakdowns active (orange). lucide none.
- [ ] **Hero** (`"use client"` for count-up) — eyebrow `meta.volume · meta.category_tag`; headline renders `line1` then `line2` with `accent_word_orange` wrapped orange + `accent_word_purple` purple; subheadline; **stat bar** = shadcn Cards with IntersectionObserver count-up; lucide `Sparkles` on eyebrow. No blobs.
- [ ] **CoreInsight** — tinted surface (`accentFor`), `Lightbulb`, bold `statement` + `narrative`.
- [ ] **Timeline** — vertical rail, year markers, badge per `kind` via `kindColor`, heading+body. lucide `Circle`/dot.
- [ ] **ProductLoop** (`"use client"`) — SVG circle, 4 nodes positioned at 12/3/6/9 o'clock, dashed connectors (animated via CSS `stroke-dashoffset`, respect `prefers-reduced-motion`), center label pill, caption below. Matches screenshot 1.
- [ ] **Funding** — shadcn **Area chart** (recharts) of `chart` points (x=label/date, y=value, unit in tooltip) + round cards (label/date/amount/valuation/signal) + `pricing_note`. lucide `TrendingUp`, `DollarSign`.
- [ ] **Competitors** — 2×2 grid; place each `QuadrantItem` by `quadrant` (tr/tl/br/bl); winner highlighted (orange ring); axis labels `axis_x`/`axis_y`; card shows their_bet/the_gap.
- [ ] **FounderMode** — stat blocks from `facts`, narrative. lucide `Users`.
- [ ] **Lessons** (dark) — `bg-[#1a1426]`, numbered cards, headline+body, "Save insight" Button (lucide `ArrowUpRight`); orange accents; ensure dark-mode contrast ≥4.5:1.
- [ ] **Closing** — large pull quote (`Quote` icon) + narrative + attribution.
- [ ] **Footer** + **ConfidenceBadge** (small pill, orange if verified else muted; `title` = source URL).

For each component: write a render test with React Testing Library (or a minimal props-render smoke via `vitest` + `@testing-library/react`) asserting key text appears and section omits cleanly when given `null`. Commit after each component: `git commit -am "feat(web): <Section> component"`.

---

# PHASE 9 — Routes

### Task 9: Index + dynamic breakdown page

**Files:** `web/app/breakdowns/page.tsx`, `web/app/breakdowns/[slug]/page.tsx`, `web/app/layout.tsx`

- [ ] **Step 1: `[slug]/page.tsx`** — `generateStaticParams` from `allSlugs()`; `getStory(slug)`; render PillNav + each section in fixed order, skipping when the StoryBrief field is null; pass `accentFor(index)` down. `generateMetadata` sets title/description from `hero` for SEO.
- [ ] **Step 2: `breakdowns/page.tsx`** — index grid of cards (one per slug): startup name, category, hero subheadline, link to `/breakdowns/[slug]`.
- [ ] **Step 3:** `layout.tsx` sets Atkinson body font, cream background, metadata base.
- [ ] **Step 4:** `npm run build` → SSG renders `/breakdowns` + `/breakdowns/luma`. **Commit.**

---

# PHASE 10 — End-to-end verification

### Task 10: Full pipeline → site

- [ ] **Step 1:** Backend live run: `POST /generate {"query":"ShopBack"}` → new `web/content/breakdowns/shopback.json`.
- [ ] **Step 2:** `cd web && npm run dev`; open `/breakdowns/shopback`. Verify: all populated sections render in template order; area chart populates; timeline badges colored by kind; competitor quadrant placed; lessons section dark; fonts/cream applied; confidence badges show; null sections absent.
- [ ] **Step 3:** Generate a second, contrasting company (founder-heavy, e.g. a story with few metrics). Confirm template stays consistent, emphasis shifts (timeline/lessons fuller, funding sparse), zero unsourced stats.
- [ ] **Step 4:** Accessibility pass: keyboard focus rings, color-not-only (badges have text), reduced-motion disables loop animation, contrast on dark Lessons section.
- [ ] **Step 5: Commit** — `git commit -am "test: end-to-end pipeline + site verification"`

---

## Self-review notes (coverage)

- Spec sections → tasks: schemas(T1), full-scrape(T2), research(T3), verify+relevance(T4), editorial(T5), pipeline+API(T6), web scaffold/theme/types(T7), section template(T8), routes/SSG(T9), e2e+a11y(T10). All covered.
- Relevance gate (key problem): T4 `relevance_filter` + T5 applying it + stat_bar only from verified metrics.
- Consistency vs variation: fixed order in T9, null-omission per section, `accentFor` rotation in T7/T8.
- Carried-over working code: `gateway` JSON-repair, `source` Firecrawl, `config`, `store`, `test_json_repair`, `test_source_helpers`.
```
