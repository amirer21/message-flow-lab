import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .config import settings


class EventStore:
    """Session snapshot in memory; append-only JSONL for experiment evidence.

    History replay and PostgreSQL persistence are added in Phase 6.
    Logging failure must not repeat a successfully performed messaging action.
    """

    def __init__(self):
        self._events = deque(maxlen=1000)
        self._lock = Lock()
        self.sent = 0
        self.acked = 0
        self._counts = {}

    def record(self, event_type, message_id="", *, attempt_id=None, worker=None, **metadata):
        metadata.setdefault("queue", settings.queue)
        event = {
            "event_id": str(uuid4()), "event_type": event_type, "message_id": message_id,
            "attempt_id": attempt_id, "worker": worker,
            "timestamp": datetime.now(timezone.utc).isoformat(), "metadata": metadata,
        }
        with self._lock:
            self._events.append(event)
            self.sent += event_type == "PUBLISH_SENT"
            self.acked += event_type == "ACK_SENT"
            counts = self._counts.setdefault(metadata["queue"], {"total_sent": 0, "ack_sent": 0})
            counts["total_sent"] += event_type == "PUBLISH_SENT"
            counts["ack_sent"] += event_type == "ACK_SENT"
            try:
                path = Path(settings.event_log)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            except OSError:
                logging.getLogger(__name__).exception("Event journal write failed")
        return event

    def view(self, queue=None):
        with self._lock:
            records = [event for event in reversed(self._events) if queue is None or event["metadata"]["queue"] == queue]
            counts = self._counts.get(queue, {"total_sent": 0, "ack_sent": 0}) if queue else {"total_sent": self.sent, "ack_sent": self.acked}
            return {"events": records, **counts}


events = EventStore()
