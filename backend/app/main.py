"""FastAPI trigger around the pipeline. The blog itself is the Next.js app;
this exists so generation can be kicked off remotely.

Two modes on POST /generate:
- Async (admin dashboard): when `callback_url` is set, schedules the ~5-min run
  as a background task, returns 202 immediately, and POSTs the result to the
  callback when done (so no HTTP request is held open for minutes).
- Sync (CLI-style): no callback_url -> runs inline and returns the result.

Both are guarded by a bearer token (GENERATOR_SHARED_SECRET) when configured.
"""
from __future__ import annotations

import hmac
import ipaddress
import logging
import socket
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, pipeline
from .logging_config import setup as _setup_logging
from .schemas import GenerateRequest

_setup_logging()
log = logging.getLogger(__name__)

app = FastAPI(title="NBT Startup Breakdown Pipeline", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def require_token(authorization: Optional[str] = Header(default=None)) -> None:
    """Bearer-token gate. If no secret is configured (local dev), allow."""
    secret = config.GENERATOR_SHARED_SECRET
    if not secret:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1]
    if not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="invalid token")


def validate_callback_url(url: str) -> Tuple[bool, str]:
    """SSRF guard for the completion callback. We POST the result AND the bearer
    secret here, so the destination must be trusted, not an arbitrary URL."""
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return False, "unparseable url"
    if p.scheme not in ("http", "https"):
        return False, "scheme must be http/https"
    host = (p.hostname or "").lower()
    if not host:
        return False, "missing host"

    allow = config.CALLBACK_ALLOWLIST
    if allow:
        return (host in allow), "host not in GENERATOR_CALLBACK_ALLOWLIST"

    # No allowlist configured. If a secret is set (prod), refuse: sending it to an
    # unvetted host would leak it. The allowlist must be configured alongside it.
    if config.GENERATOR_SHARED_SECRET:
        return False, "GENERATOR_CALLBACK_ALLOWLIST required when a secret is set"

    # Local dev (no secret): block non-public IPs (cloud metadata, RFC1918,
    # link-local) to avoid SSRF, but permit loopback for localhost testing.
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:  # noqa: BLE001
        return False, "dns resolution failed"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback:
            continue
        if ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False, f"non-public address {ip}"
    return True, ""


async def _post_callback(url: str, payload: dict) -> None:
    ok, reason = validate_callback_url(url)
    if not ok:
        log.error("refusing callback POST to %s: %s", url, reason)
        return
    headers = {"content-type": "application/json"}
    if config.GENERATOR_SHARED_SECRET:
        headers["authorization"] = f"Bearer {config.GENERATOR_SHARED_SECRET}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception as e:  # noqa: BLE001 - callback failure must not crash the worker
        log.error("callback POST to %s failed: %s", url, e)


async def _run_and_callback(query: str, max_sources: int, job_id: str, callback_url: str) -> None:
    try:
        sb, errors, warnings = await pipeline.generate(query, max_sources=max_sources)
        if errors:
            await _post_callback(
                callback_url,
                {"job_id": job_id, "ok": False, "qa_errors": errors, "qa_warnings": warnings},
            )
            return
        # Empty-shell guard: no sources AND no lessons means every LLM call
        # failed (rate-limited / retired model). Don't ship a blank draft.
        if not sb.sources and not sb.lessons:
            await _post_callback(
                callback_url,
                {"job_id": job_id, "ok": False, "error": "empty_shell"},
            )
            return
        sb.status = "draft"
        await _post_callback(
            callback_url,
            {
                "job_id": job_id,
                "ok": True,
                "slug": sb.meta.slug,
                "brief": sb.model_dump(mode="json"),
                "qa_warnings": warnings,
            },
        )
    except Exception as e:  # noqa: BLE001
        log.exception("generation failed for job %s", job_id)
        await _post_callback(
            callback_url, {"job_id": job_id, "ok": False, "error": str(e)[:500]}
        )


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "llm_configured": bool(config.OPENROUTER_API_KEY),
        "firecrawl_configured": bool(config.FIRECRAWL_API_KEY),
        "auth_required": bool(config.GENERATOR_SHARED_SECRET),
        "content_dir": str(config.CONTENT_DIR),
    }


@app.post("/generate")
async def generate(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_token),
):
    # Async webhook mode.
    if req.callback_url:
        if not req.job_id:
            raise HTTPException(status_code=400, detail="job_id required with callback_url")
        ok, reason = validate_callback_url(req.callback_url)
        if not ok:
            raise HTTPException(status_code=400, detail=f"invalid callback_url: {reason}")
        background_tasks.add_task(
            _run_and_callback, req.query, req.max_sources, req.job_id, req.callback_url
        )
        return JSONResponse({"job_id": req.job_id, "status": "running"}, status_code=202)

    # Sync mode (no callback).
    sb, errors, warnings = await pipeline.generate(req.query, max_sources=req.max_sources)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "qa_failed",
                "slug": sb.meta.slug,
                "qa_errors": errors,
                "qa_warnings": warnings,
            },
        )
    if not sb.sources and not sb.lessons:
        raise HTTPException(status_code=422, detail={"error": "empty_shell", "slug": sb.meta.slug})
    return {
        "slug": sb.meta.slug,
        "startup_name": sb.meta.startup_name,
        "overall_confidence": sb.overall_confidence,
        "brief": sb.model_dump(mode="json"),
        "qa_warnings": warnings,
    }
