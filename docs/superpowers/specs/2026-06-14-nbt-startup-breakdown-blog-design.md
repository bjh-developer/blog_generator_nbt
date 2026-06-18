# NBT Startup Breakdown Blog — Design Spec

**Date:** 2026-06-14
**Status:** Approved (design), pending implementation plan

## Context

We are pivoting an earlier single-interactive-component prototype into a **content
pipeline that turns a company name into a hyperlinkable, multi-page editorial blog**.
The operator inputs a company name; the pipeline researches it, synthesizes an
editorial "startup breakdown" (in the voice of *Next Big Thing*, a Singapore youth
startup community), and emits a data file that a Next.js site renders as a polished,
long-scroll blog page. The operator hyperlinks these pages from their main site so
readers consume them like blog posts.

**Goal:** with all gathered info about a specific company, produce a storyline that
**teaches and inspires aspiring youth entrepreneurs**.

**Key problem this design solves:** previously extracted stats/quotes were often
irrelevant. The new pipeline synthesizes a narrative and applies a relevance gate so
only impactful, story-defining facts and quotes survive.

Reference material: 4 approved screenshots (Luma breakdown) and the
`Codex of STARTUP BREAKDOWNS.md` (Luma/ShopBack/Framer examples + a Perplexity→Codex
two-stage prompt pipeline).

## Decisions (locked)

- **Frontend:** Next.js + Tailwind + shadcn/ui + lucide + recharts (shadcn area charts).
- **Layout:** one fixed editorial section template; a section renders only when it has
  data. Consistency across blogs; variation only via which sections render, accent
  rotation, headline, and chart data.
- **Pipeline:** two-stage — Research agent (structured, sourced JSON) → Editorial agent
  (story_brief JSON). Mirrors the proven Perplexity→Codex flow in the Codex `.md`.
- **Models:** free OpenRouter models, engineered hard (strong prompts + research/edit
  split + relevance filtering). Model ids configurable via env to upgrade later.
- **Discovery/scrape:** Firecrawl v2 `/search` with FULL markdown content.
- **Per-company page:** single long-scroll page; "multi-page" = site has an index plus
  one page per company.
- **Delivery:** the Next.js app IS the blog. Pipeline writes one JSON per company into
  the app's content dir; Next.js generates a route per file (SSG + on-demand). Operator
  deploys the app and hyperlinks `/breakdowns/[slug]`.
- **No 3D blobs** (removed from reference).

## Architecture

```
CLI / POST /generate  "Luma"
  │
  ├─ 1. SourceAgent    Firecrawl search + FULL markdown scrape (not snippets); dedupe
  ├─ 2. ResearchAgent  synthesize structured research JSON from full content
  │                     (timeline, founders, product evolution, funding, metrics,
  │                      competitors, product loop, lessons) — each field sourced or null
  ├─ 3. VerifyAgent    for each stat/quote: (a) ground in scraped text -> confidence,
  │                     (b) relevance score via LLM judge ("would this teach/inspire a
  │                      youth founder?"); drop ungrounded OR low-relevance items
  └─ 4. EditorialAgent  story_brief JSON in NBT voice (hero, core insight, narratives,
                         lessons, closing take), built ONLY from surviving facts
       │
       └─ writes  web/content/breakdowns/<slug>.json
                              │
        Next.js reads content dir → SSG:
          /breakdowns           index of all breakdowns
          /breakdowns/[slug]    long-scroll editorial page
```

A thin **FastAPI `POST /generate`** wraps the CLI so generation can be triggered
remotely later. The blog itself is static Next.js (no runtime API dependency to read).

## Repository shape

```
backend/                      # Python pipeline (reworked)
  app/
    agents/
      source.py               # KEEP: Firecrawl search + full scrape + arc classify
      research.py             # NEW: full content -> structured research JSON
      verify.py               # EXTEND: grounding + relevance scoring
      editorial.py            # NEW: research JSON -> story_brief JSON
    llm/gateway.py            # KEEP: throttle, retry, JSON repair pipeline, json_schema
    schemas.py                # REWORK: ResearchDoc + StoryBrief models
    pipeline.py               # NEW: orchestrates 1->4, writes web/content file
    main.py                   # FastAPI POST /generate (wraps pipeline), GET health
    config.py                 # KEEP/extend: model + firecrawl + content dir paths
  tests/                      # fixture-driven, offline

web/                          # NEW Next.js app (replaces frontend/)
  content/breakdowns/*.json   # generated story_brief files (pipeline output)
  app/
    breakdowns/page.tsx       # index
    breakdowns/[slug]/page.tsx# long-scroll renderer (generateStaticParams)
  components/sections/        # one component per template section
  components/ui/              # shadcn components
  lib/types.ts                # mirror of StoryBrief schema
  lib/theme.ts                # brand tokens, per-section accent rotation
  public/fonts/               # Bernoru
```

## Data contracts

Two Pydantic models, both also mirrored in `web/lib/types.ts`.

### ResearchDoc (ResearchAgent output, internal)
Structured, source-attributed research. Fields set to `null` when unverifiable
(no fabrication). Shape follows the Codex `.md` Perplexity schema (trimmed):
`startup_name`, `tagline`, `timeline[]` (date, event, significance, source),
`founders[]` (name, role, background, why), `origin_story`, `pivotal_insight`,
`product_evolution[]`, `product_loop` (steps, description), `competitor_matrix[]`
(name, positioning, strengths, weaknesses, our_advantage), `funding[]` (round, date,
amount_usd, valuation_usd, investors), `metrics[]` (label, value, date, source_url),
`lessons[]`, `sources[]`. Every factual item carries a source quote + URL or is null.

### StoryBrief (EditorialAgent output, drives the UI)
Editorial brief the Next.js app renders. Sections map 1:1 to template sections; any
section with no support is `null` and not rendered.
```
meta:        { startup_name, slug, volume, category_tag, research_date }
hero:        { line1, line2, accent_word_orange, accent_word_purple|null,
               subheadline, stat_bar:[{value,label}] }
core_insight:{ title, statement, narrative, icon }
timeline:    { title, events:[{year, kind, heading, body}] }   # kind drives badge color
product_loop:{ title, nodes:[{label, sub}], center_label, caption }   # 4 nodes
funding:     { title, narrative, rounds:[{label,date,amount,valuation,signal}],
               chart:[{label, value, unit, date}], pricing_note }
competitors: { title, framing, axes:{x,y},
               quadrants:[{name, their_bet, the_gap, quadrant, winner:bool}] }
founder_mode:{ title, narrative, facts:[{label,value}] } | null
lessons:     [{ number, headline, body, applicable_to }]
closing:     { title, narrative, pull_quote|null, attribution|null }
sources:     [{ title, outlet, url }]
overall_confidence: float
```
Each rendered stat/quote retains provenance (source URL) for a confidence badge.

## Design system

- **Background:** cream `#fff4de`. **Ink/body:** `#352757`.
- **Primary accent** (eyebrows, CTAs, 1st headline word): orange `#ff914d`.
- **Secondary accent** (2nd headline word, links): purple `#784eb5` / blue `#5675f0`.
- **Soft surfaces/badges:** `#cdc5fc` `#e2a9f1` `#faaef1`.
- **Chart series:** `#5675f0` `#ff914d` `#88e5f6` `#ffb169` `#0c3571`.
- **Dark "Lessons" section:** near-black + `#352757` base, orange accents.
- **Per-section accent rotation:** fixed sequence so adjacent sections differ; avoids
  all-purple monotony while staying on brand.
- **Typography:** display = **Bernoru** (self-hosted, bold rounded); body/eyebrows =
  **Atkinson Hyperlegible**.
- **Icons:** lucide only, single set, 1.5–2px stroke (Sparkles, TrendingUp, Users,
  Globe, DollarSign, Quote, ArrowUpRight, Lightbulb, Target, Repeat).
- Tailwind tokens map these to semantic names (no raw hex in components).

## Section template (fixed order; omit when data null)

1. **Pill nav** (sticky) — Home / About / Breakdowns / Contact; active state highlighted.
2. **Hero** — eyebrow `Startup Breakdown · Vol. NN · Category`; 2-part contrarian
   headline with orange + purple accent words; subheadline; **stat bar** of animated
   count-up cards; scroll cue. (No blobs.)
3. **Core Insight** — bold thesis + supporting prose on a tinted surface; `Lightbulb`.
4. **Founding Timeline** — vertical timeline; year markers; category badge per item
   (Founder Story / Product / Funding / Inflection) with rotating accent.
5. **Product Loop** — circular network-effect SVG: 4 nodes around a center label,
   dashed animated connectors; caption framing it as a compounding loop.
6. **Funding & Growth** — shadcn **area chart** (raise/valuation over time) + round
   cards + pricing logic note.
7. **Competitor Matrix** — 2×2 quadrant with labeled axes; winning quadrant highlighted;
   competitor cards (their bet / the gap).
8. **Founder Mode** (optional) — "how they're organized" stat blocks.
9. **Lessons** — DARK section; numbered lesson cards; "Save insight" affordance.
10. **Final Reflection** — closing editorial take + pull quote.
11. **Footer.**

## Relevance & anti-hallucination (the key problem)

- **Full content** (not snippets) feeds the ResearchAgent so synthesis has real material.
- **ResearchAgent** is instructed to extract only story-defining facts and to set
  unverifiable fields to `null` — never invent.
- **VerifyAgent** scores each stat/quote twice: grounding (substring/fuzzy match against
  scraped text → confidence) and **relevance** (LLM judge against the explicit goal:
  "would this teach or inspire an 18–28 aspiring founder?"). Items failing either gate
  are dropped or badged.
- **EditorialAgent** writes only from surviving items; stat_bar pulls only from verified
  metrics/funding — never invents numbers.
- Every rendered stat/quote keeps a source URL; UI shows a confidence badge.

## Testing / verification

- **Backend (pytest, offline):** fixture research/story_brief JSON → assert schema
  validity, relevance gate drops a planted irrelevant fact, editorial never emits a
  stat absent from research, null sections omitted. JSON repair + lenient parsing tests
  carried over.
- **Pipeline smoke (live, env-gated):** `generate "Luma"` → inspect emitted JSON: every
  stat/quote has a source URL; spot-check 2–3 URLs.
- **Web:** `npm run dev`; load a generated slug → all populated sections render per
  template, area chart populates, fonts/colors applied, confidence badges show, missing
  sections absent. Build `npm run build` for SSG of all content files.
- **Acceptance:** two different companies (one metrics-heavy, one founder-heavy) yield
  consistent template with appropriate section emphasis; zero unsourced stats; output
  reads as an inspiring youth-founder story, not a press release.

## Out of scope (later)

- Auth/admin for generation; human approval queue.
- Scheduled batch ingestion.
- About/Home/Contact page content (nav links present; pages stubbed).
- Paid-model upgrade (env switch already supported).
