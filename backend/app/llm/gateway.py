"""OpenRouter gateway: throttle, retry, JSON-mode, Pydantic validation.

All agents call through `complete_json` so schema-invalid model output is a
caught error (one retry) rather than silent hallucination downstream.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .. import config, store
from .models import Role, model_for
import logging

log = logging.getLogger("app.llm.gateway")

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def _provider_for(model: str) -> tuple[str, dict]:
    """Pick (endpoint_url, headers) from the model id prefix.

    `@cf/*` -> Cloudflare Workers AI (OpenAI-compat endpoint).
    Anything else -> OpenRouter (default).
    """
    if model.startswith("@cf/"):
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{config.CF_ACCOUNT_ID}/ai/v1/chat/completions"
        )
        headers = {"Authorization": f"Bearer {config.CF_API_TOKEN}"}
        return url, headers
    url = f"{config.OPENROUTER_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://localhost",
        "X-OpenRouter-Title": "BlogGenerator",
    }
    return url, headers


class _RateLimiter:
    """Simple async token bucket: <= rpm requests per rolling minute."""

    def __init__(self, rpm: int):
        self.min_interval = 60.0 / max(1, rpm)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


_limiter = _RateLimiter(config.LLM_RPM)


# --- staged JSON repair pipeline (for broken OSS-model output) -------------
# Inspired by the GPT-OSS broken-JSON playbook: extract -> cleanup -> structural
# repair -> sanitize, trying a strict parse after each stage. Logs which stage won.

def _stage0_extract(text: str) -> str:
    """Slice the JSON block out of markdown fences / surrounding prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if starts:
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end >= start:
            text = text[start:end + 1]
    return text


def _stage2_cleanup(text: str) -> str:
    """Strip BOM and trailing commas before } or ]."""
    text = text.lstrip("﻿").strip()
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _stage4_sanitize(text: str) -> str:
    """Normalize weird unicode spaces, drop control chars (keep newlines/tabs)."""
    # NBSP, figure space, narrow nbsp, line/para separators -> regular space
    text = re.sub(r"[\u00a0\u2007\u202f\u2028\u2029]", " ", text)
    # BOM and zero-width space -> removed
    text = re.sub(r"[\ufeff\u200b]", "", text)
    return "".join(c for c in text if c >= "\x20" or c in "\n\r\t")


def _stage3_balance(text: str) -> str:
    """Close unterminated strings and balance braces/brackets (string-aware)."""
    stack: list[str] = []
    in_str = esc = False
    for ch in text:
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    if in_str:
        text += '"'
    text += "".join("}" if c == "{" else "]" for c in reversed(stack))
    return text


def _repair_candidates(raw: str) -> list[tuple[str, str]]:
    """Ordered (stage_name, candidate_json) to try, cheap -> aggressive."""
    s0 = _stage0_extract(raw)
    s2 = _stage2_cleanup(s0)
    s4 = _stage4_sanitize(s2)
    s3 = _stage3_balance(s4)
    return [("extract", s0), ("cleanup", s2), ("sanitize", s4), ("balance", s3)]


def _build_body(model, messages, json_mode, temperature, json_schema, sampling):
    body: dict = {"model": model, "messages": messages, "temperature": temperature}
    # optional sampling knobs (top_p, frequency_penalty, presence_penalty, ...)
    for k, v in (sampling or {}).items():
        if v is not None:
            body[k] = v
    # Step 1 (prevention): force JSON at decode time. Prefer structured outputs
    # (json_schema) when enabled; otherwise basic json_object mode.
    if json_schema is not None and config.LLM_JSON_SCHEMA:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "out", "strict": False, "schema": json_schema},
        }
    elif json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


async def _call_model(
    model: str,
    messages: list[dict],
    json_mode: bool,
    temperature: float,
    json_schema: Optional[dict] = None,
    sampling: Optional[dict] = None,
) -> str:
    """Single model: build body, hit its provider, retry on 429/transient."""
    body = _build_body(model, messages, json_mode, temperature, json_schema, sampling)
    url, headers = _provider_for(model)

    cache_key = json.dumps({"m": model, "b": messages, "t": temperature,
                            "s": sampling or {}}, sort_keys=True)
    cached = store.prompt_cache_get(cache_key)
    if cached is not None:
        log.debug("cache hit model=%s", model)
        return cached

    last_err: Optional[Exception] = None
    prompt_preview = messages[-1]["content"][:120].replace("\n", " ")
    log.debug("call model=%s prompt=%.120s", model, prompt_preview)

    for attempt in range(config.LLM_MAX_RETRIES):
        await _limiter.acquire()
        try:
            async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
                r = await client.post(url, headers=headers, json=body)
            if r.status_code == 429:
                # respect server Retry-After if present, else exponential backoff
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else min(30, 3 * (2 ** attempt))
                log.warning("429 rate limited model=%s (attempt %d/%d), retry in %.0fs",
                            model, attempt + 1, config.LLM_MAX_RETRIES, wait)
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            log.debug("response len=%d preview=%.120s", len(content),
                      content[:120].replace("\n", " "))
            store.prompt_cache_put(cache_key, content)
            return content
        except Exception as e:  # noqa: BLE001 - retry on any transient failure
            last_err = e
            wait = 2 ** attempt
            log.warning("LLM error model=%s attempt %d: %s — retry in %ds",
                        model, attempt + 1, e, wait)
            await asyncio.sleep(wait)
    raise LLMError(f"LLM call failed after retries model={model}: {last_err}")


async def _raw_call(
    messages: list[dict],
    role: Role,
    json_mode: bool,
    temperature: float,
    json_schema: Optional[dict] = None,
    sampling: Optional[dict] = None,
) -> str:
    """Try the role's model; on exhaustion fail over once to MODEL_FALLBACK."""
    primary = model_for(role)
    try:
        return await _call_model(primary, messages, json_mode, temperature,
                                 json_schema, sampling)
    except LLMError as e:
        fallback = config.MODEL_FALLBACK
        if not fallback or fallback == primary:
            raise
        log.warning("primary model=%s failed (%s) — failing over to fallback=%s",
                    primary, e, fallback)
        return await _call_model(fallback, messages, json_mode, temperature,
                                 json_schema, sampling)


async def complete_text(
    system: str,
    user: str,
    role: Role = "general",
    temperature: float = 0.3,
    sampling: Optional[dict] = None,
) -> str:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    return await _raw_call(messages, role, json_mode=False, temperature=temperature,
                           sampling=sampling)


def _try_parse(raw: str, schema: Type[T]) -> Optional[T]:
    """Run the staged repair pipeline; return validated instance or None."""
    last: Optional[Exception] = None
    for stage, candidate in _repair_candidates(raw):
        try:
            obj = schema.model_validate_json(candidate)
            if stage != "extract":
                log.info("json repaired at stage=%s schema=%s", stage, schema.__name__)
            return obj
        except (ValidationError, json.JSONDecodeError) as e:
            last = e
    log.debug("all repair stages failed schema=%s err=%s", schema.__name__, last)
    return None


async def complete_json(
    system: str,
    user: str,
    schema: Type[T],
    role: Role = "general",
    temperature: float = 0.2,
    sampling: Optional[dict] = None,
) -> T:
    """Return a validated `schema` instance. Prevention (json mode/schema) +
    staged repair + one reformat-retry."""
    json_schema = schema.model_json_schema()
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    raw = await _raw_call(messages, role, json_mode=True, temperature=temperature,
                          json_schema=json_schema, sampling=sampling)
    for attempt in range(2):
        result = _try_parse(raw, schema)
        if result is not None:
            return result
        log.warning("schema validation fail (attempt %d) schema=%s", attempt + 1, schema.__name__)
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": (
                "Output was not valid for the required schema. "
                "Reply ONLY with corrected JSON, no prose, no code fences, "
                "no trailing commas. Use null for unknown values."
            ),
        })
        raw = await _raw_call(messages, role, json_mode=True, temperature=0.0,
                              json_schema=json_schema)
    raise LLMError("model could not produce schema-valid JSON")
