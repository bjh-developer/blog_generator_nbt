#!/usr/bin/env python3
"""Direct CLI for the breakdown pipeline — no server needed.

    python generate.py "Company Name" [--max-sources N] [--content-dir PATH]

Writes <slug>.json to CONTENT_DIR (env / .env / --content-dir). Exits 1 if the
QA gate rejects the story (nothing is written in that case).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a startup breakdown JSON.")
    p.add_argument("query", help='company name, e.g. "Carousell"')
    p.add_argument("--max-sources", type=int, default=20)
    p.add_argument("--content-dir", help="override CONTENT_DIR for this run")
    args = p.parse_args()

    # config.py reads env at import time — env must be settled before app imports
    if args.content_dir:
        os.environ["CONTENT_DIR"] = str(Path(args.content_dir).resolve())
    load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from app import config, pipeline
    from app.logging_config import setup as setup_logging

    setup_logging()

    sb, errors, warnings = asyncio.run(
        pipeline.generate(args.query, max_sources=args.max_sources)
    )
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        print("QA gate failed — story not written.", file=sys.stderr)
        sys.exit(1)

    # A story with no sources and no lessons means every LLM call failed
    # (e.g. rate-limited) — the pipeline still writes a shell file; unpublish it.
    if not sb.sources and not sb.lessons:
        path = config.CONTENT_DIR / f"{sb.meta.slug}.json"
        path.unlink(missing_ok=True)
        print("empty story (all LLM calls failed?) — removed "
              f"{path}; check rate limits and retry.", file=sys.stderr)
        sys.exit(1)
    print(f"{sb.meta.startup_name} ({sb.meta.slug}) "
          f"confidence={sb.overall_confidence}")
    print(config.CONTENT_DIR / f"{sb.meta.slug}.json")


if __name__ == "__main__":
    main()
