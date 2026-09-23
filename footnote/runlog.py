"""Append-only JSONL logging of every model call and tool call in a run."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from . import config


class RunLogger:
    def __init__(self, run_id: str | None = None, runs_dir: Path | None = None) -> None:
        # A short random suffix keeps runs started in the same second from colliding.
        self.run_id = run_id or f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.dir = runs_dir or config.RUNS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{self.run_id}.jsonl"

    def log(self, kind: str, **fields: Any) -> None:
        record = {"ts": time.time(), "kind": kind, **fields}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
