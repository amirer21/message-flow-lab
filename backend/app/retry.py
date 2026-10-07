"""Phase 5: Failure classification, Retry with TTL, and Dead Letter Queue."""
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

from .messaging import connection

SCENARIOS = Literal["transient_2x", "permanent", "retry_exceed"]
MAX_RETRIES = 3
RETRY_TTL_MS = 5000


class RetryPublishRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4096)
    scenario: SCENARIOS


class RetryLab:
    """One thread owns a Confirm-mode channel with Phase 5 retry topology."""

    def __init__(self):
        self._lock = Lock()
        self._thread = None
        self._commands: Queue = Queue()
        self._records: deque = deque(maxlen=500)
        self._queues: list[dict] = []
        self._work_exchange: str | None = None
        self._retry_exchange: str | None = None
        self._dead_exchange: str | None = None
        self._last_publish: dict | None = None
        self._last_process: dict | None = None

    def call(self, command, payload=None):
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                self._commands = Queue()
                self._thread = Thread(target=self._run, daemon=True, name="retry-lab")
                self._thread.start()
            future = Future()
            self._commands.put((command, payload, future))
        return future.result(timeout=7)

    def record(self, kind, message_id="", **metadata):
        self._records.append({
            "event_id": str(uuid4()), "message_id": message_id,
            "event_type": kind, "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker": "retry-lab", "metadata": metadata,
        })

    def setup(self, channel):
        # Clean up previous topology
        if self._work_exchange:
            for queue in self._queues:
                try:
                    channel.queue_delete(queue=queue["name"])
                except Exception:
                    pass
            for ex in [self._work_exchange, self._retry_exchange, self._dead_exchange]:
                try:
                    channel.exchange_delete(exchange=ex)
                except Exception:
                    pass

        uid = uuid4().hex
        self._work_exchange = f"phase5.{uid}.work"
        self._retry_exchange = f"phase5.{uid}.retry"
        self._dead_exchange = f"phase5.{uid}.dead"

        # Work exchange + queue
        channel.exchange_declare(exchange=self._work_exchange, exchange_type="direct", durable=True)
        work_q = f"{self._work_exchange}.q"
        channel.queue_declare(queue=work_q, durable=True)
        channel.queue_bind(queue=work_q, exchange=self._work_exchange, routing_key="job")

        # Dead exchange + queue
        channel.exchange_declare(exchange=self._dead_exchange, exchange_type="direct", durable=True)
        dead_q = f"{self._dead_exchange}.q"
        channel.queue_declare(queue=dead_q, durable=True)
        channel.queue_bind(queue=dead_q, exchange=self._dead_exchange, routing_key="job")

        # Retry exchange + queue (TTL → DLX back to work exchange)
        channel.exchange_declare(exchange=self._retry_exchange, exchange_type="direct", durable=True)
        retry_q = f"{self._retry_exchange}.q"
        channel.queue_declare(queue=retry_q, durable=True, arguments={
            "x-message-ttl": RETRY_TTL_MS,
            "x-dead-letter-exchange": self._work_exchange,
            "x-dead-letter-routing-key": "job",
        })
        channel.queue_bind(queue=retry_q, exchange=self._retry_exchange, routing_key="job")

        self._queues = [
            {"id": "work", "name": work_q, "role": "work", "label": "작업 Queue"},
            {"id": "retry", "name": retry_q, "role": "retry", "label": "재시도 대기 Queue"},
            {"id": "dead", "name": dead_q, "role": "dead", "label": "Dead Letter Queue"},
        ]
        self._records.clear()
        self._last_publish = None
        self._last_process = None
        self.record("TOPOLOGY_CREATED",
                     work_exchange=self._work_exchange,
                     retry_exchange=self._retry_exchange,
                     dead_exchange=self._dead_exchange)

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
        return {
            "work_exchange": self._work_exchange,
            "queues": queues,
            "events": list(reversed(self._records)),
            "last_publish": self._last_publish,
            "last_process": self._last_process,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    def publish(self, channel, request: RetryPublishRequest):
        if not request.body.strip():
            raise ValueError("빈 메시지는 발행할 수 없습니다.")
        if not self._work_exchange:
            raise ValueError("실험을 먼저 시작하세요.")

        message_id = str(uuid4())
        scenario = request.scenario

        properties = pika.BasicProperties(
            message_id=message_id,
            correlation_id=message_id,
            content_type="application/json",
            delivery_mode=2,
            headers={"x-retry-count": 0, "x-scenario": scenario},
        )
        body_bytes = json.dumps({
            "body": request.body, "scenario": scenario,
        }, ensure_ascii=False).encode("utf-8")

        self.record("PUBLISH_SENT", message_id, scenario=scenario)

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
            "message_id": message_id, "scenario": scenario, "confirmed": confirmed,
        }
        return self._last_publish

    def process(self, channel):
        """Consume one message from work queue and apply scenario logic."""
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
        retry_count = headers.get("x-retry-count", 0)
        scenario = headers.get("x-scenario", envelope.get("scenario", ""))

        self.record("PROCESSING_STARTED", message_id,
                     retry_count=retry_count, scenario=scenario)

        # Detect if message came back via DLX (retry return)
        x_death = headers.get("x-death")
        if x_death:
            self.record("RETRY_RETURNED", message_id, retry_count=retry_count,
                         x_death_count=len(x_death) if isinstance(x_death, list) else 0)

        # Decide outcome based on scenario
        outcome = self._decide(scenario, retry_count)

        if outcome == "success":
            self.record("PROCESSING_SUCCEEDED", message_id, retry_count=retry_count)
            self.record("ACK_SENT", message_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        elif outcome == "retry":
            # Transient failure, retry allowed
            new_count = retry_count + 1
            self.record("PROCESSING_FAILED", message_id,
                         retry_count=retry_count, failure_type="transient")
            retry_props = pika.BasicProperties(
                message_id=message_id,
                correlation_id=properties.correlation_id,
                content_type="application/json",
                delivery_mode=2,
                headers={
                    "x-retry-count": new_count,
                    "x-scenario": scenario,
                },
            )
            channel.basic_publish(
                exchange=self._retry_exchange, routing_key="job",
                body=body, properties=retry_props, mandatory=True,
            )
            self.record("RETRY_SCHEDULED", message_id,
                         retry_count=new_count, ttl_ms=RETRY_TTL_MS)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            self.record("ACK_SENT", message_id)
        else:
            # DLQ — permanent failure or retry limit exceeded
            failure_type = "permanent" if scenario == "permanent" else "retry_exceeded"
            self.record("PROCESSING_FAILED", message_id,
                         retry_count=retry_count, failure_type=failure_type)
            dlq_props = pika.BasicProperties(
                message_id=message_id,
                correlation_id=properties.correlation_id,
                content_type="application/json",
                delivery_mode=2,
                headers={
                    "x-retry-count": retry_count,
                    "x-scenario": scenario,
                    "x-failure-type": failure_type,
                },
            )
            channel.basic_publish(
                exchange=self._dead_exchange, routing_key="job",
                body=body, properties=dlq_props, mandatory=True,
            )
            self.record("DLQ_STORED", message_id,
                         retry_count=retry_count, failure_type=failure_type)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            self.record("ACK_SENT", message_id)

        confirmed = True  # All internal publishes are in confirm mode
        self._last_process = {
            "message_id": message_id, "scenario": scenario,
            "retry_count": retry_count, "outcome": outcome,
            "confirmed": confirmed,
        }
        return self._last_process

    def _decide(self, scenario: str, retry_count: int) -> str:
        """Decide outcome: 'success', 'retry', or 'dlq'."""
        if scenario == "transient_2x":
            # Succeed on 3rd attempt (retry_count >= 2)
            if retry_count >= 2:
                return "success"
            return "retry"
        elif scenario == "permanent":
            # Always fails permanently → immediate DLQ
            return "dlq"
        elif scenario == "retry_exceed":
            # Always transient failure, eventually exceeds max retries
            if retry_count >= MAX_RETRIES:
                return "dlq"
            return "retry"
        return "dlq"

    def handle(self, channel, command, payload):
        if command == "setup":
            self.setup(channel)
        elif command == "publish":
            self.publish(channel, payload)
        elif command == "process":
            self.process(channel)
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
                            for ex in [self._work_exchange, self._retry_exchange, self._dead_exchange]:
                                try:
                                    channel.exchange_delete(exchange=ex)
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
                future.set_exception(RuntimeError("재시도 실습 연결을 확인하세요."))
        finally:
            with self._lock:
                while True:
                    try:
                        _, _, waiting = self._commands.get_nowait()
                        waiting.set_exception(RuntimeError("재시도 실습 연결이 종료됐습니다."))
                    except Empty:
                        break

    def shutdown(self):
        if self._thread and self._thread.is_alive():
            try:
                self.call("end")
                self._thread.join(timeout=5)
            except (RuntimeError, TimeoutError):
                pass


lab = RetryLab()
router = APIRouter(prefix="/retry", tags=["Phase 5 실패·Retry·DLQ"])


def perform(command, payload=None):
    try:
        return lab.call(command, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(503, "재시도 실습 연결을 확인하세요.") from exc


@router.get("/snapshot")
def snapshot():
    return perform("snapshot")


@router.post("/setup")
def setup():
    return perform("setup")


@router.post("/publish")
def publish(request: RetryPublishRequest):
    return perform("publish", request)


@router.post("/process")
def process():
    return perform("process")
