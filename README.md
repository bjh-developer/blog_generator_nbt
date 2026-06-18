# NBT Startup Breakdown Pipeline

Input a company name → the pipeline researches it, synthesizes an editorial
"startup breakdown" for young founders, and writes a JSON file that the Next.js
blog renders as a hyperlinkable long-scroll page.

```
backend/   Python pipeline  (Firecrawl → research → verify → editorial → JSON)
web/       Next.js blog      (reads web/content/breakdowns/*.json, SSG)
docs/      spec + plan
```

## 1. Backend pipeline

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set OPENROUTER_API_KEY and FIRECRAWL_API_KEY
python -m pytest -q         # 26 tests, offline

uvicorn app.main:app --reload          # http://localhost:8000/docs
curl -X POST localhost:8000/generate -H 'content-type: application/json' \
     -d '{"query":"Luma"}'
# → writes web/content/breakdowns/luma.json, returns {slug, confidence, path}
```

Pipeline stages (`backend/app/`):
- `agents/source.py` — Firecrawl v2 `/search` + full markdown scrape + classify
- `agents/research.py` — full content → structured `ResearchDoc` (sourced or null)
- `agents/verify.py` — grounding score + relevance gate (youth-founder goal)
- `agents/editorial.py` — `ResearchDoc` → `StoryBrief` (NBT editorial voice)
- `pipeline.py` — orchestrates, writes the content file

Models (free OpenRouter, override in `.env`): `MODEL_FAST` (triage/relevance,
keep it a small NON-reasoning model), `MODEL_GENERAL` (research/editorial).

## 2. Web blog

```bash
cd web
npm install                 # next, react, recharts, lucide-react, tailwind
npm run dev                 # http://localhost:3000/breakdowns
# /breakdowns           → index of all generated breakdowns
# /breakdowns/[slug]    → long-scroll editorial page
npm run build               # SSG: one static page per content/breakdowns/*.json
```

A sample `web/content/breakdowns/luma.json` ships so the UI renders before you
run the pipeline. Drop `bernoru.woff2` into `web/public/fonts/` for the display
font (falls back to Atkinson Hyperlegible).

Hyperlink the deployed `/breakdowns/<slug>` URLs from your main site.

## Data contract

`StoryBrief` (`backend/app/schemas.py` ↔ `web/lib/types.ts`) is the spine.
Every section is optional and rendered only when present, so all blogs share one
template while emphasis varies by company. Every stat/quote is grounded in a
source; low-confidence items are badged.

## Design

Brand palette (mixed, not pure purple) + Atkinson fonts + lucide icons +
recharts area charts. Section template, order, and color rotation in
`web/lib/theme.ts`. Reference design + decisions: `docs/superpowers/specs/`.
