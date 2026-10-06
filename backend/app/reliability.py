"""Phase 4: Publisher Confirm, mandatory Return, durable/persistent experiments."""
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

SCENARIOS = Literal["normal", "mandatory_unroutable", "persistent", "transient"]


class ReliabilityPublishRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4096)
    scenario: SCENARIOS


class ReliabilityLab:
    """One thread owns a Confirm-mode channel with isolated Phase 4 topology."""

    def __init__(self):
        self._lock = Lock()
        self._thread = None
        self._commands: Queue = Queue()
        self._records: deque = deque(maxlen=500)
        self._queues: list[dict] = []
        self._exchange: str | None = None
        self._last_publish: dict | None = None
        self._received: list[dict] = []
        self._returned: list[dict] = []

    def call(self, command, payload=None):
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                self._commands = Queue()
                self._thread = Thread(target=self._run, daemon=True, name="reliability-lab")
                self._thread.start()
            future = Future()
            self._commands.put((command, payload, future))
        return future.result(timeout=7)

    def record(self, kind, message_id="", **metadata):
        self._records.append({
            "event_id": str(uuid4()), "message_id": message_id,
            "event_type": kind, "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker": "reliability-lab", "metadata": metadata,
        })

    def setup(self, channel):
        if self._exchange:
            for queue in self._queues:
                try:
                    channel.queue_delete(queue=queue["name"])
                except Exception:
                    pass
            try:
                channel.exchange_delete(exchange=self._exchange)
            except Exception:
                pass

        uid = uuid4().hex
        self._exchange = f"phase4.{uid}"
        channel.exchange_declare(exchange=self._exchange, exchange_type="direct", durable=True)

        self._queues = []
        # Queue A: durable, routed — normal confirm test
        name_a = f"{self._exchange}.routed"
        channel.queue_declare(queue=name_a, durable=True)
        channel.queue_bind(queue=name_a, exchange=self._exchange, routing_key="routed")
        self._queues.append({"id": "a", "name": name_a, "binding": "routed", "durable": True, "label": "정상 라우팅"})

        # Queue B: durable, persistent — persistence test
        name_b = f"{self._exchange}.persistent"
        channel.queue_declare(queue=name_b, durable=True)
        channel.queue_bind(queue=name_b, exchange=self._exchange, routing_key="persistent")
        self._queues.append({"id": "b", "name": name_b, "binding": "persistent", "durable": True, "label": "영속 메시지"})

        # Queue C: auto_delete, transient — comparison
        name_c = f"{self._exchange}.transient"
        channel.queue_declare(queue=name_c, durable=False, auto_delete=True)
        channel.queue_bind(queue=name_c, exchange=self._exchange, routing_key="transient")
        self._queues.append({"id": "c", "name": name_c, "binding": "transient", "durable": False, "label": "임시 Queue"})

        self._records.clear()
        self._received = []
        self._last_publish = None
        self._returned = []
        self.record("TOPOLOGY_CREATED", exchange=self._exchange, exchange_type="direct")

    def snapshot(self, channel):
        queues = []
        for queue in self._queues:
            try:
                result = channel.queue_declare(queue=queue["name"], passive=True)
                ready = result.method.message_count
            except pika.exceptions.ChannelClosedByBroker:
                # Queue may have been auto-deleted after reconnect
                channel = channel.connection.channel()
                channel.confirm_delivery()
                ready = None
            queues.append({**queue, "ready": ready})
        return {
            "exchange": self._exchange, "queues": queues,
            "events": list(reversed(self._records)),
            "last_publish": self._last_publish,
            "last_received": self._received,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    def _on_return(self, channel, method, properties, body):
        """Callback for mandatory messages that cannot be routed."""
        info = {
            "message_id": properties.message_id or "",
            "reply_code": method.reply_code,
            "reply_text": method.reply_text,
            "routing_key": method.routing_key,
        }
        self._returned.append(info)
        self.record("PUBLISH_RETURNED", info["message_id"],
                     reply_code=info["reply_code"], reply_text=info["reply_text"],
                     routing_key=info["routing_key"])

    def publish(self, channel, request: ReliabilityPublishRequest):
        if not request.body.strip():
            raise ValueError("빈 메시지는 발행할 수 없습니다.")
        if not self._exchange:
            raise ValueError("실험을 먼저 시작하세요.")

        message_id = str(uuid4())
        scenario = request.scenario

        # Determine routing key, mandatory flag, and delivery mode per scenario
        if scenario == "normal":
            routing_key = "routed"
            mandatory = False
            delivery_mode = 2
        elif scenario == "mandatory_unroutable":
            routing_key = "unroutable"
            mandatory = True
            delivery_mode = 2
        elif scenario == "persistent":
            routing_key = "persistent"
            mandatory = False
            delivery_mode = 2
        elif scenario == "transient":
            routing_key = "transient"
            mandatory = False
            delivery_mode = 1
        else:
            raise ValueError("허용되지 않은 발행 시나리오입니다.")

        self._returned = []
        properties = pika.BasicProperties(
            message_id=message_id, correlation_id=message_id,
            content_type="application/json", delivery_mode=delivery_mode,
        )
        body_bytes = json.dumps({"body": request.body, "scenario": scenario}, ensure_ascii=False).encode("utf-8")

        self.record("PUBLISH_SENT", message_id, scenario=scenario,
                     routing_key=routing_key, mandatory=mandatory,
                     delivery_mode=delivery_mode)

        confirmed = False
        nacked = False
        outcome_unknown = False

        try:
            # In BlockingConnection confirm mode, basic_publish returns True/False
            # or raises UnroutableError/NackError
            channel.basic_publish(
                exchange=self._exchange, routing_key=routing_key,
                body=body_bytes, properties=properties, mandatory=mandatory,
            )
            confirmed = True
            self.record("PUBLISH_CONFIRMED", message_id)
        except pika.exceptions.UnroutableError:
            # Message was confirmed but returned — Confirm ACK + Return both happened
            confirmed = True
            self.record("PUBLISH_CONFIRMED", message_id)
            # Return already recorded via callback, but also record here if callback missed
            if not any(r["message_id"] == message_id for r in self._returned):
                self.record("PUBLISH_RETURNED", message_id, routing_key=routing_key)
                self._returned.append({"message_id": message_id, "routing_key": routing_key,
                                       "reply_code": 312, "reply_text": "NO_ROUTE"})
        except pika.exceptions.NackError:
            nacked = True
            self.record("PUBLISH_NACKED", message_id)
        except (pika.exceptions.AMQPError, OSError):
            outcome_unknown = True
            self.record("PUBLISH_OUTCOME_UNKNOWN", message_id)

        returned = any(r["message_id"] == message_id for r in self._returned)

        self._last_publish = {
            "message_id": message_id, "scenario": scenario,
            "routing_key": routing_key, "mandatory": mandatory,
            "delivery_mode": delivery_mode,
            "confirmed": confirmed, "nacked": nacked,
            "returned": returned, "outcome_unknown": outcome_unknown,
        }
        return self._last_publish

    def receive(self, channel):
        self._received = []
        for queue in self._queues:
            try:
                method, properties, body = channel.basic_get(queue=queue["name"], auto_ack=False)
            except pika.exceptions.ChannelClosedByBroker:
                channel = channel.connection.channel()
                channel.confirm_delivery()
                continue
            if method is None:
                continue
            envelope = json.loads(body)
            item = {
                "queue_id": queue["id"], "message_id": properties.message_id or "",
                "body": envelope.get("body", ""), "routing_key": method.routing_key,
                "scenario": envelope.get("scenario", ""), "redelivered": method.redelivered,
                "delivery_mode": properties.delivery_mode,
            }
            self.record("DELIVERED", item["message_id"], queue_id=queue["id"],
                         routing_key=method.routing_key)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            self.record("ACK_SENT", item["message_id"], queue_id=queue["id"])
            self._received.append(item)
        return self._received

    def handle(self, channel, command, payload):
        if command == "setup":
            self.setup(channel)
        elif command == "publish":
            self.publish(channel, payload)
        elif command == "receive":
            self.receive(channel)
        elif command != "snapshot":
            raise ValueError("허용되지 않은 실험 동작입니다.")
        return self.snapshot(channel)

    def _run(self):
        future = None
        try:
            with connection() as conn:
                channel = conn.channel()
                channel.confirm_delivery()
                channel.add_on_return_callback(self._on_return)
                self._exchange = None
                self.setup(channel)
                while conn.is_open:
                    conn.process_data_events(time_limit=0.1)
                    try:
                        command, payload, future = self._commands.get(timeout=0.1)
                    except Empty:
                        continue
                    if command == "end":
                        # Clean up topology before closing
                        if self._exchange:
                            for queue in self._queues:
                                try:
                                    channel.queue_delete(queue=queue["name"])
                                except Exception:
                                    pass
                            try:
                                channel.exchange_delete(exchange=self._exchange)
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
                future.set_exception(RuntimeError("발행 신뢰성 실습 연결을 확인하세요."))
        finally:
            with self._lock:
                while True:
                    try:
                        _, _, waiting = self._commands.get_nowait()
                        waiting.set_exception(RuntimeError("발행 신뢰성 실습 연결이 종료됐습니다."))
                    except Empty:
                        break

    def shutdown(self):
        if self._thread and self._thread.is_alive():
            try:
                self.call("end")
                self._thread.join(timeout=5)
            except (RuntimeError, TimeoutError):
                pass


lab = ReliabilityLab()
router = APIRouter(prefix="/reliability", tags=["Phase 4 발행 신뢰성"])


def perform(command, payload=None):
    try:
        return lab.call(command, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(503, "발행 신뢰성 실습 연결을 확인하세요. 실패한 발행을 자동 재시도하지 않습니다.") from exc


@router.get("/snapshot")
def snapshot():
    return perform("snapshot")


@router.post("/setup")
def setup():
    return perform("setup")


@router.post("/publish")
def publish(request: ReliabilityPublishRequest):
    return perform("publish", request)


@router.post("/receive")
def receive():
    return perform("receive")
