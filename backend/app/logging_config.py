"""Structured coloured logging for the pipeline. Call setup() once at startup."""
from __future__ import annotations

import logging
import sys


RESET = "\033[0m"
BOLD = "\033[1m"
GREY = "\033[90m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"

_COLOURS = {
    logging.DEBUG:    GREY,
    logging.INFO:     CYAN,
    logging.WARNING:  YELLOW,
    logging.ERROR:    RED,
    logging.CRITICAL: MAGENTA,
}

_TAGS = {
    "app.agents.source":    f"{BLUE}[SOURCE]  {RESET}",
    "app.agents.summarize": f"{GREEN}[SUMM]    {RESET}",
    "app.agents.verify":    f"{YELLOW}[VERIFY]  {RESET}",
    "app.agents.design":    f"{MAGENTA}[DESIGN]  {RESET}",
    "app.llm.gateway":      f"{CYAN}[LLM]     {RESET}",
    "app.orchestrator":     f"{BOLD}[ORCH]    {RESET}",
    "app.store":            f"{GREY}[STORE]   {RESET}",
}


class _Fmt(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        col = _COLOURS.get(record.levelno, "")
        tag = _TAGS.get(record.name, f"[{record.name.split('.')[-1].upper():<8}] ")
        lvl = f"{col}{record.levelname[0]}{RESET}"
        msg = record.getMessage()
        return f"{GREY}{self._time(record)}{RESET} {lvl} {tag}{msg}"

    @staticmethod
    def _time(record: logging.LogRecord) -> str:
        import datetime
        t = datetime.datetime.fromtimestamp(record.created)
        return t.strftime("%H:%M:%S.") + f"{t.microsecond // 1000:03d}"


def setup(level: str = "DEBUG") -> None:
    root = logging.getLogger("app")
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    if root.handlers:
        return
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(_Fmt())
    root.addHandler(h)
    # silence noisy uvicorn access log duplicates at debug
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
