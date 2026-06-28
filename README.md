# NBT Blog Post Generator

Type a company name. The pipeline researches it, writes an editorial "startup
breakdown" for young founders, and produces a JSON file that a Next.js blog
renders as a hyperlinkable long-scroll page.

```
company name ─▶ backend pipeline ─▶ web/content/breakdowns/<slug>.json ─▶ blog page
```

- **backend/** — Python pipeline: Firecrawl research → fact extraction → verify →
  editorial → JSON. FastAPI server triggers it.
- **web/** — Next.js blog that statically renders each JSON into a page.
- **[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)** — how it works inside

---

## Prerequisites

- Python 3.10+
- Node.js 18+ (Next.js 16)
- Two API keys:
  - **OpenRouter** — the LLM provider. Get one at <https://openrouter.ai/keys>.
  - **Firecrawl** — web search + scrape. Get one at <https://firecrawl.dev>.

---

## Part 1 — Generate a blog post (backend)

### 1. Install

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure keys

```bash
cp .env.example .env
```

Open `.env` and fill in the two keys. The defaults for everything else work:

```bash
OPENROUTER_API_KEY=sk-or-...        # required
FIRECRAWL_API_KEY=fc-...            # required
PROMPT_CACHE=0                      # 0 = always generate fresh (recommended while iterating)
```

> **Tip:** leave `PROMPT_CACHE=0` while you're testing. With caching on, regenerating
> the *same* company returns the previous result instead of a fresh one.

### 3. (Optional) check your setup

```bash
python -m pytest -q          # runs offline, no keys needed — confirms install is sane
uvicorn app.main:app --reload
# then in another terminal:
curl localhost:8000/health   # shows whether both keys are detected
```

### 4. Generate

Start the server (if not already running):

```bash
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

Request a breakdown by company name:

```bash
curl -X POST localhost:8000/generate \
     -H 'content-type: application/json' \
     -d '{"query":"Carousell", "max_sources":20}'
```
>`max_sources` is the number of search results returned by firecrawl and can vary (up to 100). Recommended to keep it at 20 as it's a good balance between resourcefulness and cost.

The pipeline runs (research can take ~5 minutes — it scrapes and reads several
articles) and writes `web/content/breakdowns/carousell.json`.

**Response:**
```json
{
  "slug": "carousell",
  "startup_name": "Carousell",
  "overall_confidence": 0.73,
  "path": ".../web/content/breakdowns/carousell.json",
  "qa_warnings": ["funding: 1 round(s) missing an amount, ..."]
}
```

- `overall_confidence` — average grounding of the stats kept (0–1).
- `qa_warnings` — advisory issues; the post was still written.
- **HTTP 422 with `qa_errors`** — the quality gate found a hard problem it could not
  auto-repair, so **nothing was written**. Fix the input (or the data) and retry.
  See [TECHNICAL_DOCUMENTATION.md §2.4](TECHNICAL_DOCUMENTATION.md) for the full check list.

Request options: `{"query": "<name>", "max_sources": 8}` — `max_sources` (default 8)
caps how many articles are researched.

---

## Part 2 — View the blog (web)

```bash
cd web
npm install
npm run dev        # http://localhost:3000/breakdowns
```

- `/breakdowns` — index of every generated breakdown.
- `/breakdowns/<slug>` — the long-scroll editorial page.

A sample `luma.json` ships so the UI renders before you run the pipeline.

To publish statically:

```bash
# set the real origin so canonical / OpenGraph / JSON-LD URLs are correct
NEXT_PUBLIC_SITE_URL=https://yoursite.com npm run build   # one static page per JSON
```

Each page ships canonical + OpenGraph + Twitter tags and JSON-LD structured data
(Article + Breadcrumb + FAQ, for SEO and answer-engine harvesting). `sitemap.xml`
and `robots.txt` are deliberately left to the main site this route deploys into.

Then hyperlink the deployed `/breakdowns/<slug>` URLs from your main site.

For the display font, drop `bernoru.woff2` into `web/public/fonts/` (falls back to
Atkinson Hyperlegible).

---

## End-to-end, in short

```bash
# backend (one-time setup)
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add OPENROUTER_API_KEY + FIRECRAWL_API_KEY

# generate
uvicorn app.main:app --reload
curl -X POST localhost:8000/generate -H 'content-type: application/json' -d '{"query":"Notion"}'

# view
cd ../web && npm install && npm run dev      # open /breakdowns/notion
```

---

## What you get

Every breakdown shares one template; sections appear only when the research
supports them:

- **Hero** — short catchy headline + a stat bar.
- **Core insight** — the one non-obvious idea behind the company.
- **Timeline** — 4–6 key milestones (founding, first product, pivots, funding).
- **Product loop** — the growth/network-effect flywheel.
- **Funding & pricing** — how they got their first money + how the product earns money,
  with a capital-raised bar chart and round cards.
- **Competitive map** — a 2×2 positioning matrix (winner top-right).
- **Founder mode** — founder background and how the company started.
- **Lessons** — 3–4 takeaways for builders.
- **Closing** — the NBT take + a pull quote.

Every stat/quote is grounded in a scraped source; low-confidence items are filtered
or badged. Each page also has a reading-progress bar and a desktop section-nav rail
with scroll-spy, and is mobile-responsive throughout.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Same result every regenerate | Set `PROMPT_CACHE=0` in `.env`, or use a new company name. |
| `OPENROUTER_API_KEY not set` | Fill `.env`; restart `uvicorn` so it reloads. |
| `/health` shows `firecrawl_configured: false` | Add `FIRECRAWL_API_KEY`, restart. |
| HTTP 422 `qa_errors` | The QA gate blocked a bad post; check the listed errors. |
| Thin / empty sections | Few sources survived research; raise `max_sources` or pick a more-covered company. |
| Hitting rate limits | Lower `LLM_RPM` in `.env` (free tier ≈ 20/min). |
| Blog page 404 | The JSON isn't in `web/content/breakdowns/`; confirm the generate step wrote it. |

---

## Architecture & internals

See **[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)** — pipeline stages, the LLM gateway,
the QA audit/repair gate, data contracts, and how to extend the system.
