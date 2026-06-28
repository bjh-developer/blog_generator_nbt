# Technical Documentation — NBT Blog Post Pipeline

How the system turns a company name into a published "startup/company breakdown" blog
post. Read this to understand internals, extend the pipeline, or debug output.

For setup and day-to-day usage, see the [README](README.md).

---

## 1. System shape

Two halves joined by one JSON file:

```
company name ─▶ backend pipeline ─▶ web/content/breakdowns/<slug>.json ─▶ Next.js blog ─▶ static page
```

- **backend/** — async Python pipeline (FastAPI trigger). Researches, verifies,
  writes the editorial JSON.
- **web/** — Next.js app that statically renders each JSON into a long-scroll page.
- **The contract** — `StoryBrief` (`backend/app/schemas.py` ↔ `web/lib/types.ts`).
  Keep the two in sync by hand; there is no codegen. Every `StoryBrief` section is
  optional and rendered only when present, so all blogs share one template while
  emphasis varies per company.

The backend never renders HTML. It only emits the JSON the frontend reads at build
time (SSG).

---

## 2. Pipeline stages

`backend/app/pipeline.py::generate(query, max_sources)` orchestrates four stages,
then a QA gate. It degrades gracefully — a failed stage yields a thinner
`StoryBrief`, not a crash.

```
gather ──▶ research ──▶ editorial ──▶ QA audit/repair ──▶ write file
(source)   (extract)    (assemble)     (gate)
```

### 2.1 Source — `agents/source.py`
Discovery + scrape + classify.
- **Discover & scrape:** Firecrawl v2 `/search` finds and scrapes articles in one
  call (returns markdown main content). Query is expanded with story-relevant terms
  (`founding OR funding OR pivot OR lessons …`). Limit = `max_sources`.
- **Fallback extract:** if Firecrawl returns thin text (<400 chars), `trafilatura`
  re-extracts from the URL.
- **Dedupe:** by normalized URL + fuzzy title match (`SequenceMatcher > 0.85`).
- **Classify:** one batched LLM call (the `fast` model) labels every candidate
  `success` / `cautionary` / `reject`. Rejected articles are dropped; the dominant
  surviving label sets the story `arc`.
- Returns `(list[Source], arc)`. Each `Source` caches its raw text to disk
  (`backend/data/cache/src_*.txt`) referenced by `raw_text_ref`.

### 2.2 Research — `agents/research.py`
Per-source extraction → merged `ResearchDoc`.
- Each source's full text is sent to the `general` model with a strict "never
  fabricate; null what you can't support" prompt → a partial `ResearchDoc`.
- All sources run **concurrently** (`asyncio.gather`); the gateway's rate limiter
  still spaces the actual HTTP calls.
- `_merge` concatenates list fields (timeline, funding, founders, …) and takes the
  first non-null scalar (tagline, origin_story, …). Merging across sources is why
  funding lists arrive noisy and duplicated — cleaned later in editorial.

### 2.3 Editorial — `agents/editorial.py`
`ResearchDoc` → `StoryBrief`. The heart of the system. Two kinds of work:

**Deterministic, pure, unit-tested helpers** build data-shaped sections:
- `clean_funding` — drops junk/inferred-label rounds (`unspecified`, `implied`,
  `estimated`, …) and amount-less rounds, dedupes by (label sans `(YYYY)`, year)
  with backfill, sorts chronologically.
- `funding_chart` / `funding_rounds` — chart points + round cards; `_fmt_usd` rolls
  ≥ $1B into `$X.XB`.
- `stat_bar` — `normalize_stat_value` maps quantifier words to symbols
  (`over`→`>`), compresses magnitudes (`billion`→`B`) only when digit-attached, then
  drops non-numeric or >12-char prose stats. Max 4.
- `timeline_items` — deterministic **fallback** only: dedupe, keep the most
  storyline-defining kinds (`inflection` > `founder_story` > `funding` > …), cap 6,
  chronological.
- `slugify`, `_research_digest` (caps + dedupes the prompt input so it stays small).

**One constrained LLM call** writes the NBT-voice prose into `_Narratives`
(`gateway.complete_json`, warm sampling for human cadence). `_Narratives` carries
the hero, core insight, `timeline_events` (LLM-chosen key milestones), product
loop, funding/pricing narrative, competitor quadrants, founder mode, lessons,
closing. A `model_validator` (`_flatten`) tolerates free-model drift: un-nests
fields the model wrongly nested and drops malformed list entries.

**Verify gates (run in `build` before the LLM call, via `agents/verify.py`):**
- `semantic_filter_funding` — an LLM (`role="fast"`) drop-only pass that removes
  funding rounds that actually belong to other companies, given the startup name +
  origin/timeline context. Fails open (keeps all) on `LLMError`.
- `filter_metrics` — grounding gate: keeps only metrics supported by the scraped
  corpus (threshold `VERIFY_THRESHOLD`).
- `relevance_filter` — drops off-topic lessons; never empties the list.

`assemble` stitches `ResearchDoc` (facts) + `_Narratives` (prose) into the final
`StoryBrief`. Timeline uses the LLM's `timeline_events`, falling back to
`timeline_items(rd)` when empty. Sections with no support are left `None`.

### 2.4 QA gate — `qa.py` (run in `pipeline.generate`)
A final deterministic consistency pass over the assembled `StoryBrief`.
`audit(sb)` returns `[(severity, message)]`; `split()` → `(errors, warnings)`.

Flow: **audit → if errors, `repair(sb)` → re-audit → write if clean, else block.**

| Check | Severity | Repair |
|---|---|---|
| duplicate funding round label | error | disambiguate with year |
| funding rounds out of chronological order | error | sort |
| later round valuation < earlier | error | clear bad valuation |
| round missing amount (absent from chart) | warning | — (advisory) |
| duplicate competitor label | error | drop dup card |
| > 4 competitor cards | error | cap to 4 (winners first) |
| winner ≠ exactly 1 | error | force exactly one |
| timeline out of chronological order | error | sort |
| hero accent word absent from headline | error | clear the accent word |
| competitor cell collision | warning | reassign to free cells |
| missing axis label | warning | — |

Repair is conservative: it disambiguates, reorders, drops, or clears — never
invents data. It also forces the competitor winner into the top-right (`tr`) cell,
reassigns colliding cells, and **orients axis labels** so the winner's trait sits
on the right (`axis_x`) / top (`axis_y`) end, normalizing any arrow form to `←→`.

`pipeline.generate` returns `(StoryBrief, errors, warnings)`. The file is written
only when `errors` is empty.

---

## 3. LLM gateway — `llm/gateway.py`

Every model call goes through `complete_json` (schema-validated) or
`complete_text`. Responsibilities:

- **Rate limiting** — async token bucket at `LLM_RPM` (default 18, under the free
  tier's 20/min cap).
- **Retry** — exponential backoff on any transient error; honors `Retry-After` on
  HTTP 429.
- **Prompt cache** — when `PROMPT_CACHE=1`, responses are cached to
  `backend/data/cache/llm_*.json` keyed by (model, messages, temperature,
  sampling). **Set `PROMPT_CACHE=0` to force fresh generation** — otherwise the
  same query returns the cached blob.
- **Structured output** — sends `response_format: json_schema` (the Pydantic
  schema) when `LLM_JSON_SCHEMA=1`, else `json_object` mode.
- **Staged JSON repair** — for broken OSS-model output, a 4-stage pipeline
  (extract → cleanup → sanitize → balance) tries a strict parse after each stage,
  then one reformat-retry, before raising `LLMError`.
- **Sampling** — optional `sampling` dict (`top_p`, `frequency_penalty`,
  `presence_penalty`) threaded into the request body. Editorial uses warmer values
  for human-sounding prose; research/triage stay deterministic.

Model routing (`llm/models.py`): roles `fast` / `general` / `reasoning` /
`fallback` map to env-configured model ids. `fast` must be a small NON-reasoning
model (triage/classify is latency-sensitive).

---

## 4. Data contracts — `schemas.py`

- **`LenientModel`** — base class; coerces a `null` sent for a str/list field to
  that field's default, so free-model drift doesn't fail validation.
- **`ResearchDoc`** — internal, source-attributed research (research agent output):
  timeline, founders, funding, metrics, competitors, lessons, each with `SourceRef`.
- **`StoryBrief`** — the UI contract (editorial output). Mirror of
  `web/lib/types.ts`. All sections optional; `overall_confidence` is the mean
  grounding score of surviving metrics.

When you change `StoryBrief`, change `web/lib/types.ts` in the same commit.

---

## 5. Storage & caching — `store.py`, `config.py`

Zero-infra, all on disk under `backend/data/`:
- `cache/src_*.txt` — raw scraped article text (referenced by `Source.raw_text_ref`).
- `cache/llm_*.json` — prompt cache (toggle with `PROMPT_CACHE`).
- `stories.db` — SQLite, present but not on the active path.
- Generated `StoryBrief` JSON is written to `CONTENT_DIR`
  (`web/content/breakdowns/` by default) — the directory the Next.js app reads.

---

## 6. Frontend rendering — `web/`

- `app/breakdowns/page.tsx` — index of all breakdowns.
- `app/breakdowns/[slug]/page.tsx` — dynamic route; `generateStaticParams` lists
  every JSON, so each becomes a static page. `params` is a Promise (Next 15+),
  awaited before use. `generateMetadata` emits canonical + OpenGraph + Twitter
  tags; the page injects JSON-LD (see SEO/AEO below).
- `lib/content.ts` — reads `web/content/breakdowns/*.json`.
- `lib/theme.ts` — brand palette, section color rotation, fonts.
- `components/sections/*` — one component per `StoryBrief` section. The funding
  chart (`Funding.tsx`) is a recharts `BarChart` with per-bar value labels and a
  `minPointSize` so tiny rounds stay visible next to huge ones.
- `components/ui/Eyebrow.tsx` — shared section kicker (Lucide icon + label); used
  by every section so there are no ad-hoc unicode-glyph "icons".

**Reading UX (client components, in `components/sections/`):**
- `ReadingProgress.tsx` — fixed top scroll-progress bar; `scaleX` transform only
  (no reflow), rAF-throttled.
- `SectionNav.tsx` — desktop-only (`xl:`) floating table of contents with
  IntersectionObserver scroll-spy and smooth-scroll (honors reduced-motion). The
  page passes `darkIds` so the rail flips to a light theme over dark sections
  (e.g. Lessons). The TOC is built in `page.tsx` from sections actually present.
  Anchors: each section is wrapped in a `<div id=... className="scroll-mt-28">`.

**SEO / AEO:**
- `lib/seo.ts` — route-local (not in the root layout, so the whole breakdown
  route stays portable into the main site without metadata conflicts). Exposes
  `SITE_URL` (from `NEXT_PUBLIC_SITE_URL`), URL helpers, and `buildJsonLd(story)`
  which returns an **Article** + **BreadcrumbList** + **FAQPage** graph. The
  FAQPage leads with the hero question and adds each lesson as a Q/A pair — the
  surface answer engines lift directly.
- `components/JsonLd.tsx` — server component that emits `<script type="application
  /ld+json">` into the static HTML (read without executing JS). Escapes `<` to
  prevent a stray `</script>` in data from breaking out of the tag.
- **Intentionally omitted:** `sitemap.ts` / `robots.ts` — those are site-global
  and owned by the main site this route is deployed into.

---

## 7. Configuration reference (`config.py` / `.env`)

| Var | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | required for LLM calls |
| `FIRECRAWL_API_KEY` | — | required for discovery + scrape |
| `MODEL_FAST` | `openrouter/owl-alpha` | triage/classify — small, non-reasoning |
| `MODEL_GENERAL` | `openrouter/owl-alpha` | research + editorial |
| `MODEL_REASONING` / `MODEL_FALLBACK` | `openrouter/owl-alpha` | optional roles |
| `LLM_RPM` | 18 | requests/min cap (free tier = 20) |
| `LLM_TIMEOUT` | 90 | per-call timeout (s) |
| `LLM_MAX_RETRIES` | 5 | retry attempts |
| `PROMPT_CACHE` | 1 | cache LLM responses; **0 to force fresh** |
| `LLM_JSON_SCHEMA` | 1 | structured outputs vs json_object mode |
| `VERIFY_THRESHOLD` | 0.6 | grounding score gate for metrics |
| `USE_EMBEDDINGS` | 0 | optional local embedding verify |
| `CONTENT_DIR` | `web/content/breakdowns` | where JSON is written |
| `DATA_DIR` / `DB_PATH` | `backend/data` | cache + SQLite location |

**Frontend env (`web/`):** `NEXT_PUBLIC_SITE_URL` sets the absolute origin used for
canonical, OpenGraph, and JSON-LD URLs (defaults to a placeholder). Set it to the
real deployment origin before building, or canonical tags point at the wrong host.

---

## 8. Extension points

- **New blog section:** add the field to `StoryBrief` (schemas.py) **and**
  `web/lib/types.ts`, emit it from `editorial.assemble`, add a component under
  `web/components/sections/`, render it in `app/breakdowns/[slug]/page.tsx`.
- **New QA rule:** add an `_audit_*` check returning `(severity, msg)`; add a
  matching fixer in `repair()` if it's auto-correctable.
- **Swap models:** override `MODEL_*` in `.env`. Keep `MODEL_FAST` non-reasoning.
- **Tune editorial voice:** edit `_SYS` and the `sampling` dict in
  `editorial.build`.

---

## 9. Tests

`cd backend && python -m pytest -q` — offline (no API keys needed). Covers the
deterministic editorial helpers (clean_funding, stat_bar, timeline), the QA
audit/repair rules, schema leniency, JSON repair, source normalization, and
pipeline wiring.
