"""FastAPI trigger around the pipeline. The blog itself is the static Next.js app;
this exists so generation can be kicked off remotely."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import config, pipeline
from .logging_config import setup as _setup_logging
from .schemas import GenerateRequest

_setup_logging()

app = FastAPI(title="NBT Startup Breakdown Pipeline", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "llm_configured": bool(config.OPENROUTER_API_KEY),
        "firecrawl_configured": bool(config.FIRECRAWL_API_KEY),
        "content_dir": str(config.CONTENT_DIR),
    }


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    sb, errors, warnings = await pipeline.generate(req.query, max_sources=req.max_sources)
    if errors:
        # hard QA gate failed: story not written. 422 so the caller doesn't
        # mistake this for a successful publish.
        raise HTTPException(status_code=422, detail={
            "error": "qa_failed",
            "slug": sb.meta.slug,
            "qa_errors": errors,
            "qa_warnings": warnings,
        })
    return {
        "slug": sb.meta.slug,
        "startup_name": sb.meta.startup_name,
        "overall_confidence": sb.overall_confidence,
        "path": str(config.CONTENT_DIR / f"{sb.meta.slug}.json"),
        "qa_warnings": warnings,
    }
