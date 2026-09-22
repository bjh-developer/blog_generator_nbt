"""Model preflight: ping every configured model so a generation fails fast with
a clear reason instead of burning ~5 minutes and producing an empty shell when
an OpenRouter model id has been retired/renamed or the account is out of credits.

Classification:
- ok        : model answered.
- fatal     : won't fix itself (404 retired id, 401/403 auth, 402 credits) -> block.
- transient : 429/5xx/timeout (overloaded, rate limited) -> warn but allow; the
              pipeline has retries + fallback for these.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from .. import config
from .gateway import _provider_for
from .models import Role, model_for

log = logging.getLogger("app.llm.preflight")

# Roles whose model being *fatally* broken makes a generation impossible. The
# fallback is included: a transient blip on general/editorial fails over to it,
# so a dead fallback turns a recoverable hiccup into a hard failure.
ESSENTIAL_ROLES: tuple[Role, ...] = ("fast", "general", "editorial", "fallback")
ALL_ROLES: tuple[Role, ...] = ("fast", "general", "editorial", "reasoning", "fallback", "judge")


def _classify(status: Optional[int], detail: str) -> tuple[bool, bool, str]:
    """(ok, fatal, hint) from an HTTP status."""
    if status == 200:
        return True, False, ""
    if status == 404:
        return False, True, (
            "Model id not found — it was renamed or retired on OpenRouter. "
            "Update the MODEL_* env to a currently-available id (openrouter.ai/models)."
        )
    if status in (401, 403):
        return False, True, "Auth rejected — check OPENROUTER_API_KEY."
    if status == 402:
        return False, True, "Out of credits / payment required — top up or use a free model."
    if status == 429:
        return False, False, "Rate limited — transient; retrying usually works."
    if status in (500, 502, 503, 504):
        return False, False, "Provider overloaded/unavailable — transient; retry later or switch model."
    return False, False, detail or "Unknown error."


async def _ping(model: str) -> dict:
    url, headers = _provider_for(model)
    body: dict = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
    if not model.startswith("@cf/"):
        body["reasoning"] = {"enabled": False}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        return {"ok": False, "fatal": False, "status": None, "hint": "Timed out — transient."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "fatal": False, "status": None, "hint": f"Request failed: {e}"[:200]}

    status: Optional[int] = r.status_code
    detail = ""
    if status == 200:
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = {}
        if not data.get("choices"):
            # Some providers return 200 with an error body / no choices.
            err = data.get("error") or {}
            code = err.get("code")
            detail = str(err.get("message") or "")[:200]
            if isinstance(code, int) and code != 200:
                status = code
            else:
                return {"ok": False, "fatal": False, "status": 200,
                        "hint": f"Empty response (no choices) — transient. {detail}".strip()}
    else:
        try:
            detail = str((r.json().get("error") or {}).get("message") or r.text)[:200]
        except Exception:  # noqa: BLE001
            detail = (r.text or "")[:200]

    ok, fatal, hint = _classify(status, detail)
    return {"ok": ok, "fatal": fatal, "status": status, "hint": hint, "detail": detail}


async def check_models(roles: tuple[Role, ...] = ALL_ROLES) -> dict:
    """Ping each configured (deduped) model and report health.

    Returns:
      ok             : no FATAL problem among ESSENTIAL roles (a run may proceed)
      all_ok         : every checked model answered
      models         : [{model, roles, ok, fatal, status, hint, detail}]
      essential_fatal: the subset of essential models that fatally failed
    """
    model_roles: dict[str, list[str]] = {}
    for role in roles:
        model_roles.setdefault(model_for(role), []).append(role)

    checks = await asyncio.gather(*(_ping(m) for m in model_roles))
    models = [{"model": m, "roles": rs, **res} for (m, rs), res in zip(model_roles.items(), checks)]

    essential_fatal = [
        x for x in models if x["fatal"] and any(r in ESSENTIAL_ROLES for r in x["roles"])
    ]
    return {
        "ok": len(essential_fatal) == 0,
        "all_ok": all(x["ok"] for x in models),
        "models": models,
        "essential_fatal": essential_fatal,
    }


def summarize_fatal(health: dict) -> str:
    """One-line human summary of the fatal essential failures (for job.error)."""
    parts = [
        f"{x['model']} [{','.join(x['roles'])}] ({x['status']}): {x['hint']}"
        for x in health.get("essential_fatal", [])
    ]
    return "LLM preflight failed — " + " | ".join(parts) if parts else ""
