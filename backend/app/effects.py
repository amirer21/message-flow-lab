"""An intentional, non-idempotent teaching side effect, not a real payment."""
import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import settings


def append_effect(message_id, attempt_id):
    record = {"effect_id": str(uuid4()), "message_id": message_id, "attempt_id": attempt_id,
              "timestamp": datetime.now(timezone.utc).isoformat()}
    path = Path(settings.effect_log)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return record


def read_effects():
    path = Path(settings.effect_log)
    recent = deque(maxlen=200)
    counts = {}
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                    message_id = record["message_id"]
                    counts[message_id] = counts.get(message_id, 0) + 1
                    recent.append(record)
                except (ValueError, KeyError):
                    # A crash can leave a partially written final journal line.
                    continue
    return {"effects": list(reversed(recent)), "effect_counts": counts,
            "effects_total": sum(counts.values())}
