"""Phase 6: Idempotency — deduplicate business effects with DB unique constraint."""
import json
from collections import deque
from concurrent.futures import Future
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Literal
from uuid import uuid4

import pika
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import get_connection, init_db
from .messaging import connection

SCENARIOS = Literal["normal", "duplicate", "crash_after_commit"]
CONSUMER_SCOPE = "phase6-lab"


class IdempotencyPublishRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=256)
    amount: int = Field(ge=1, le=1_000_000)


class IdempotencyLab:
    """Single-threaded lab with Confirm-mode channel for idempotency experiments."""

    def __init__(self):
        self._lock = Lock()
        self._thread = None
        self._commands: Queue = Queue()
        self._records: deque = deque(maxlen=500)
        self._queues: list[dict] = []
        self._work_exchange: str | None = None
        self._last_publish: dict | None = None
        self._last_process: dict | None = None
        self._simulate_crash = False

    def call(self, command, payload=None):
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                self._commands = Queue()
                self._thread = Thread(target=self._run, daemon=True, name="idempotency-lab")
                self._thread.start()
            future = Future()
            self._commands.put((command, payload, future))
        return future.result(timeout=7)

    def record(self, kind, message_id="", **metadata):
        self._records.append({
            "event_id": str(uuid4()), "message_id": message_id,
            "event_type": kind, "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker": "idempotency-lab", "metadata": metadata,
        })

    def setup(self, channel):
        # Clean up previous topology
        if self._work_exchange:
            for queue in self._queues:
                try:
                    channel.queue_delete(queue=queue["name"])
                except Exception:
                    pass
            try:
                channel.exchange_delete(exchange=self._work_exchange)
            except Exception:
                pass

        uid = uuid4().hex
        self._work_exchange = f"phase6.{uid}.work"

        channel.exchange_declare(exchange=self._work_exchange, exchange_type="direct", durable=True)
        work_q = f"{self._work_exchange}.q"
        channel.queue_declare(queue=work_q, durable=True)
        channel.queue_bind(queue=work_q, exchange=self._work_exchange, routing_key="job")

        self._queues = [
            {"id": "work", "name": work_q, "role": "work", "label": "작업 Queue"},
        ]
        self._records.clear()
        self._last_publish = None
        self._last_process = None
        self._simulate_crash = False

        # Reset DB tables (clear existing data, create if not exist)
        init_db(clear=False)
        init_db(clear=True)

        self.record("TOPOLOGY_CREATED", work_exchange=self._work_exchange)

    def publish(self, channel, request: IdempotencyPublishRequest):
        if not self._work_exchange:
            raise ValueError("실험을 먼저 시작하세요.")

        message_id = str(uuid4())
        properties = pika.BasicProperties(
            message_id=message_id,
            correlation_id=message_id,
            content_type="application/json",
            delivery_mode=2,
            headers={
                "x-idempotency-key": request.idempotency_key,
                "x-amount": request.amount,
            },
        )
        body_bytes = json.dumps({
            "idempotency_key": request.idempotency_key,
            "amount": request.amount,
        }, ensure_ascii=False).encode("utf-8")

        self.record("PUBLISH_SENT", message_id,
                     idempotency_key=request.idempotency_key, amount=request.amount)

        confirmed = False
        try:
            channel.basic_publish(
                exchange=self._work_exchange, routing_key="job",
                body=body_bytes, properties=properties, mandatory=True,
            )
            confirmed = True
            self.record("PUBLISH_CONFIRMED", message_id)
        except pika.exceptions.UnroutableError:
            confirmed = True
            self.record("PUBLISH_CONFIRMED", message_id)
        except pika.exceptions.NackError:
            self.record("PUBLISH_NACKED", message_id)
        except (pika.exceptions.AMQPError, OSError):
            self.record("PUBLISH_OUTCOME_UNKNOWN", message_id)

        self._last_publish = {
            "message_id": message_id,
            "idempotency_key": request.idempotency_key,
            "confirmed": confirmed,
        }
        return self._last_publish

    def process(self, channel):
        """Consume one message and apply idempotent processing."""
        if not self._work_exchange:
            raise ValueError("실험을 먼저 시작하세요.")

        work_q = self._queues[0]["name"]
        try:
            method, properties, body = channel.basic_get(queue=work_q, auto_ack=False)
        except pika.exceptions.ChannelClosedByBroker:
            channel = channel.connection.channel()
            channel.confirm_delivery()
            raise ValueError("작업 Queue에서 메시지를 가져올 수 없습니다.")

        if method is None:
            raise ValueError("작업 Queue가 비어 있습니다.")

        envelope = json.loads(body)
        message_id = properties.message_id or ""
        headers = properties.headers or {}
        idempotency_key = headers.get("x-idempotency-key", envelope.get("idempotency_key", ""))
        amount = headers.get("x-amount", envelope.get("amount", 0))

        self.record("PROCESSING_STARTED", message_id,
                     idempotency_key=idempotency_key, amount=amount)

        # Idempotent processing with DB transaction
        conn = get_connection()
        was_duplicate = False
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO processed_commands (consumer_scope, idempotency_key, processed_at) VALUES (?, ?, ?)",
                (CONSUMER_SCOPE, idempotency_key, datetime.now(timezone.utc).isoformat()),
            )
            if cursor.rowcount == 1:
                # New command — apply business effect
                conn.execute(
                    "INSERT INTO business_effects (consumer_scope, idempotency_key, amount, created_at) VALUES (?, ?, ?, ?)",
                    (CONSUMER_SCOPE, idempotency_key, amount, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                self.record("EFFECT_APPLIED", message_id,
                             idempotency_key=idempotency_key, amount=amount)
            else:
                # Duplicate — skip business effect
                conn.commit()
                was_duplicate = True
                self.record("DUPLICATE_SKIPPED", message_id,
                             idempotency_key=idempotency_key)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        outcome = "skipped" if was_duplicate else "applied"

        # Simulate crash after DB commit but before ACK
        if self._simulate_crash:
            self._simulate_crash = False
            self.record("CRASH_BEFORE_ACK", message_id,
                         idempotency_key=idempotency_key, outcome=outcome)
            # NACK with requeue so the message is redelivered
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            self._last_process = {
                "message_id": message_id,
                "idempotency_key": idempotency_key,
                "outcome": outcome,
                "was_duplicate": was_duplicate,
                "crashed": True,
            }
            return self._last_process

        # Normal ACK
        self.record("ACK_SENT", message_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)

        self._last_process = {
            "message_id": message_id,
            "idempotency_key": idempotency_key,
            "outcome": outcome,
            "was_duplicate": was_duplicate,
            "crashed": False,
        }
        return self._last_process

    def duplicate(self, channel, request: IdempotencyPublishRequest):
        """Publish a duplicate message with the same idempotency_key."""
        return self.publish(channel, request)

    def snapshot(self, channel):
        queues = []
        for queue in self._queues:
            try:
                result = channel.queue_declare(queue=queue["name"], passive=True)
                ready = result.method.message_count
            except pika.exceptions.ChannelClosedByBroker:
                channel = channel.connection.channel()
                channel.confirm_delivery()
                ready = None
            queues.append({**queue, "ready": ready})

        # Query DB state
        effects = []
        processed_count = 0
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, consumer_scope, idempotency_key, amount, created_at FROM business_effects ORDER BY id DESC LIMIT 50"
            ).fetchall()
            effects = [dict(r) for r in rows]
            processed_count = conn.execute("SELECT COUNT(*) FROM processed_commands").fetchone()[0]
            conn.close()
        except Exception:
            pass

        return {
            "work_exchange": self._work_exchange,
            "queues": queues,
            "events": list(reversed(self._records)),
            "effects": effects,
            "processed_count": processed_count,
            "last_publish": self._last_publish,
            "last_process": self._last_process,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    def handle(self, channel, command, payload):
        if command == "setup":
            self.setup(channel)
        elif command == "publish":
            self.publish(channel, payload)
        elif command == "process":
            self.process(channel)
        elif command == "set_crash":
            self._simulate_crash = True
            self.record("CRASH_ARMED", simulate=True)
        elif command != "snapshot":
            raise ValueError("허용되지 않은 실험 동작입니다.")
        return self.snapshot(channel)

    def _run(self):
        future = None
        try:
            with connection() as conn:
                channel = conn.channel()
                channel.confirm_delivery()
                self._work_exchange = None
                self.setup(channel)
                while conn.is_open:
                    conn.process_data_events(time_limit=0.1)
                    try:
                        command, payload, future = self._commands.get(timeout=0.1)
                    except Empty:
                        continue
                    if command == "end":
                        if self._work_exchange:
                            for queue in self._queues:
                                try:
                                    channel.queue_delete(queue=queue["name"])
                                except Exception:
                                    pass
                            try:
                                channel.exchange_delete(exchange=self._work_exchange)
                            except Exception:
                                pass
                        conn.close()
                        future.set_result({"status": "ended"})
                        break
                    try:
                        future.set_result(self.handle(channel, command, payload))
                    except ValueError as exc:
                        future.set_exception(exc)
                    future = None
        except Exception as exc:
            if future and not future.done():
                future.set_exception(RuntimeError("멱등성 실습 연결을 확인하세요."))
        finally:
            with self._lock:
                while True:
                    try:
                        _, _, waiting = self._commands.get_nowait()
                        waiting.set_exception(RuntimeError("멱등성 실습 연결이 종료됐습니다."))
                    except Empty:
                        break

    def shutdown(self):
        if self._thread and self._thread.is_alive():
            try:
                self.call("end")
                self._thread.join(timeout=5)
            except (RuntimeError, TimeoutError):
                pass


lab = IdempotencyLab()
router = APIRouter(prefix="/idempotency", tags=["Phase 6 멱등성"])


def perform(command, payload=None):
    try:
        return lab.call(command, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(503, "멱등성 실습 연결을 확인하세요.") from exc


@router.get("/snapshot")
def snapshot():
    return perform("snapshot")


@router.post("/setup")
def setup():
    return perform("setup")


@router.post("/publish")
def publish(request: IdempotencyPublishRequest):
    return perform("publish", request)


@router.post("/process")
def process():
    return perform("process")


@router.post("/arm-crash")
def arm_crash():
    """Arm a simulated crash: next process will commit DB but NACK the message."""
    return perform("set_crash")


@router.get("/effects")
def effects():
    """Query business_effects from DB."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, consumer_scope, idempotency_key, amount, created_at FROM business_effects ORDER BY id DESC LIMIT 50"
        ).fetchall()
        result = [dict(r) for r in rows]
        conn.close()
        return result
    except Exception as exc:
        raise HTTPException(503, f"DB 조회 실패: {exc}") from exc
