"""Model routing by role. Free OpenRouter models; configurable via env."""
from __future__ import annotations

from typing import Literal

from .. import config

Role = Literal["fast", "general", "research", "editorial", "reasoning", "fallback"]


def model_for(role: Role) -> str:
    # Read config live so env/test overrides aren't shadowed by an import-time snapshot.
    by_role: dict[str, str] = {
        "fast": config.MODEL_FAST,
        "general": config.MODEL_GENERAL,
        "research": config.MODEL_RESEARCH,
        "editorial": config.MODEL_EDITORIAL,
        "reasoning": config.MODEL_REASONING,
        "fallback": config.MODEL_FALLBACK,
    }
    return by_role.get(role, config.MODEL_GENERAL)
