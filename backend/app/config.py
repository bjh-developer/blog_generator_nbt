"""Runtime config from environment. All free-tier friendly defaults."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
CACHE_DIR = DATA_DIR / "cache"          # raw scraped text + prompt cache
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "stories.db"))
# generated StoryBrief JSON files land here; the Next.js app reads this dir
CONTENT_DIR = Path(os.getenv("CONTENT_DIR", BASE_DIR.parent / "web" / "content" / "breakdowns"))

for _p in (DATA_DIR, CACHE_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# --- LLM providers ---------------------------------------------------------
# Active roles run on Cloudflare Workers AI (model ids prefixed "@cf/").
# Fallback stays on OpenRouter for cross-provider failover.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "")
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "")

# Cloudflare Workers AI models (June 2026). Override per-role via env.
# fast: small model for triage/classify (NOT a reasoning model — those are slow)
MODEL_FAST = os.getenv("MODEL_FAST", "@cf/meta/llama-3.1-8b-instruct")
MODEL_GENERAL = os.getenv("MODEL_GENERAL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
# reasoning tier retired — alias to general so any stray role="reasoning" works
MODEL_REASONING = os.getenv("MODEL_REASONING", MODEL_GENERAL)
# fallback stays on OpenRouter (different provider) for failover
MODEL_FALLBACK = os.getenv("MODEL_FALLBACK", "openrouter/owl-alpha")

# Free tier: 20 requests/min cap.
LLM_RPM = int(os.getenv("LLM_RPM", "18"))          # headroom under 20
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))
PROMPT_CACHE = os.getenv("PROMPT_CACHE", "1") == "1"
# Structured outputs (json_schema) at decode time. On by default — DeepSeek V3
# and Llama 3.3 70B both support it on OpenRouter. Set LLM_JSON_SCHEMA=0 in
# .env if switching to a model that rejects structured outputs.
LLM_JSON_SCHEMA = os.getenv("LLM_JSON_SCHEMA", "1") == "1"

# --- search / scrape -------------------------------------------------------
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")    # primary discovery + scrape
FIRECRAWL_SEARCH_API = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_MAX_AGE = int(os.getenv("FIRECRAWL_MAX_AGE", "172800000"))  # 2d cache (ms)
HTTP_UA = os.getenv("HTTP_UA", "Mozilla/5.0 (compatible; BlogGenerator/0.1)")

# --- verification ----------------------------------------------------------
VERIFY_THRESHOLD = float(os.getenv("VERIFY_THRESHOLD", "0.6"))
USE_EMBEDDINGS = os.getenv("USE_EMBEDDINGS", "0") == "1"   # optional local model
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# --- branding (echoed to frontend if needed) -------------------------------
PALETTE = [
    "#352757", "#784eb5", "#cdc5fc", "#e2a9f1", "#faaef1",
    "#5675f0", "#0c3571", "#88e5f6", "#ff914d", "#ffb169", "#fff4de",
]
FONT_PRIMARY = "Bernoru"
FONT_SECONDARY = "Atkinson Hyperlegible"
