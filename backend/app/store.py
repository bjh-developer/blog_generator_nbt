"""On-disk caches. Raw scraped text + LLM prompt cache. Zero-infra, free.

Generated stories are written as JSON files by the pipeline (see pipeline.py),
not persisted here.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from . import config


# --- raw text cache --------------------------------------------------------

def cache_text(key: str, text: str) -> str:
    """Persist extracted article text, return a stable ref path (str)."""
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    path = config.CACHE_DIR / f"src_{digest}.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def read_cached_text(ref: str) -> str:
    p = Path(ref)
    return p.read_text(encoding="utf-8") if p.exists() else ""


# --- prompt cache (save free-tier quota in dev) ----------------------------

def prompt_cache_get(key: str) -> Optional[str]:
    if not config.PROMPT_CACHE:
        return None
    p = config.CACHE_DIR / f"llm_{hashlib.sha1(key.encode()).hexdigest()}.json"
    return p.read_text(encoding="utf-8") if p.exists() else None


def prompt_cache_put(key: str, value: str) -> None:
    if not config.PROMPT_CACHE:
        return
    p = config.CACHE_DIR / f"llm_{hashlib.sha1(key.encode()).hexdigest()}.json"
    p.write_text(value, encoding="utf-8")
