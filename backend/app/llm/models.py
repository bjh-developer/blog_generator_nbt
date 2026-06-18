"""Model routing by role. Free OpenRouter models; configurable via env."""
from __future__ import annotations

from typing import Literal

from .. import config

Role = Literal["fast", "general", "reasoning", "fallback"]

_BY_ROLE: dict[Role, str] = {
    "fast": config.MODEL_FAST,
    "general": config.MODEL_GENERAL,
    "reasoning": config.MODEL_REASONING,
    "fallback": config.MODEL_FALLBACK,
}


def model_for(role: Role) -> str:
    return _BY_ROLE.get(role, config.MODEL_GENERAL)
