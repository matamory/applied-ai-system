"""Structured JSONL logger for DocuBot query runs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


class RunLogger:
    def __init__(self, log_path="logs/external_rag_runs.jsonl", enabled=True):
        self.log_path = log_path
        self.enabled = enabled

    def log(self, payload):
        if not self.enabled:
            return

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
