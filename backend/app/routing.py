"""Phase 3: one thread owns an isolated, temporary RabbitMQ topology."""
import json
from collections import deque
from concurrent.futures import Future
from datetime import datetime, timezone
from functools import lru_cache
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Literal
from uuid import uuid4

import pika
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .messaging import connection

KINDS = Literal["direct", "fanout", "topic"]
DEFAULTS = {"direct": ["error", "info", "error"], "fanout": ["", "", ""], "topic": ["order.*", "*.completed", "#"]}


def topic_matches(binding, routing_key):
    pattern = binding.split(".") if binding else []
    words = routing_key.split(".") if routing_key else []

    @lru_cache(None)
    def match(i, j):
        if i == len(pattern):
            return j == len(words)
        if pattern[i] == "#":
            return match(i + 1, j) or (j < len(words) and match(i, j + 1))
        return j < len(words) and (pattern[i] == "*" or pattern[i] == words[j]) and match(i + 1, j + 1)

    return match(0, 0)


class SetupRequest(BaseModel):
    exchange_type: KINDS
    bindings: list[str] = Field(min_length=3, max_length=3)

    @field_validator("bindings")
    @classmethod
    def valid_bindings(cls, bindings):
        if any(len(key.encode("utf-8")) > 255 for key in bindings):
            raise ValueError("Binding Key는 UTF-8 기준 255바이트 이하입니다.")
        return bindings


class RoutingPublishRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4096)
    routing_key: str = Field(max_length=255)
    prediction: list[Literal["a", "b", "c"]] = Field(default_factory=list, max_length=3)

    @field_validator("routing_key")
    @classmethod
    def valid_key(cls, key):
        if len(key.encode("utf-8")) > 255:
            raise ValueError("Routing Key는 UTF-8 기준 255바이트 이하입니다.")
        return key


class RoutingLab:
    def __init__(self):
        self._lock = Lock()
        self._thread = None
        self._commands = Queue()
        self._records = deque(maxlen=200)
        self._queues = []
        self._exchange = None
        self._kind = "direct"
        self._received = []
        self._last_publish = None

    def call(self, command, payload=None):
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                self._commands = Queue()
                self._thread = Thread(target=self._run, daemon=True, name="routing-lab")
                self._thread.start()
            future = Future()
            self._commands.put((command, payload, future))
        return future.result(timeout=7)

    def record(self, kind, message_id="", **metadata):
        self._records.append({"event_id": str(uuid4()), "message_id": message_id,
                              "event_type": kind, "timestamp": datetime.now(timezone.utc).isoformat(),
                              "worker": "routing-lab", "metadata": metadata})

    def setup(self, channel, kind, bindings):
        # Delete only this connection's UUID-scoped teaching resources.
        if self._exchange:
            for queue in self._queues:
                channel.queue_delete(queue=queue["name"])
            # The last binding removal auto-deletes this temporary exchange.
        self._kind = kind
        self._exchange = f"phase3.{uuid4().hex}"
        channel.exchange_declare(exchange=self._exchange, exchange_type=kind, auto_delete=True)
        self._queues = []
        for index, binding in enumerate(bindings):
            label = "abc"[index]
            name = f"{self._exchange}.{label}"
            channel.queue_declare(queue=name, exclusive=True, auto_delete=True)
            channel.queue_bind(queue=name, exchange=self._exchange, routing_key=binding)
            self._queues.append({"id": label, "name": name, "binding": binding})
        self._records.clear()
        self._received = []
        self._last_publish = None
        self.record("TOPOLOGY_CREATED", exchange_type=kind)

    def snapshot(self, channel):
        # passive 선언으로 개수만 조회한다. 메시지를 꺼내는 basic_get과 구분한다.
        queues = [{**queue, "ready": channel.queue_declare(queue=queue["name"], passive=True).method.message_count} for queue in self._queues]
        return {"exchange_type": self._kind, "exchange": self._exchange, "queues": queues,
                "events": list(reversed(self._records)), "last_received": self._received,
                "last_publish": self._last_publish, "collected_at": datetime.now(timezone.utc).isoformat()}

    def handle(self, channel, command, payload):
        if command == "setup":
            self.setup(channel, payload.exchange_type, payload.bindings)
        elif command == "bindings":
            if payload.exchange_type != self._kind:
                raise ValueError("Exchange 종류를 바꾸려면 새 실험을 시작하세요.")
            for queue, binding in zip(self._queues, payload.bindings):
                if queue["binding"] != binding:
                    channel.queue_unbind(queue=queue["name"], exchange=self._exchange, routing_key=queue["binding"])
                    channel.queue_bind(queue=queue["name"], exchange=self._exchange, routing_key=binding)
                    queue["binding"] = binding
            self.record("BINDINGS_CHANGED", bindings=payload.bindings)
        elif command == "publish":
            if not payload.body.strip():
                raise ValueError("빈 메시지는 발행할 수 없습니다.")
            message_id = str(uuid4())
            envelope = {"body": payload.body, "prediction": payload.prediction}
            # prediction은 학습 기록이다. 실제 Queue 선택은 RabbitMQ의 Binding이 결정한다.
            channel.basic_publish(exchange=self._exchange, routing_key=payload.routing_key,
                                  body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
                                  properties=pika.BasicProperties(message_id=message_id, content_type="application/json"))
            self._last_publish = {"message_id": message_id, "routing_key": payload.routing_key,
                                  "prediction": payload.prediction, "publisher_confirmed": False}
            self.record("PUBLISH_SENT", message_id, routing_key=payload.routing_key, prediction=payload.prediction)
        elif command == "receive":
            self._received = []
            for queue in self._queues:
                method, properties, body = channel.basic_get(queue=queue["name"], auto_ack=False)
                if method is None:
                    continue
                envelope = json.loads(body)
                item = {"queue_id": queue["id"], "message_id": properties.message_id,
                        "body": envelope["body"], "routing_key": method.routing_key,
                        "prediction": envelope.get("prediction", []), "redelivered": method.redelivered}
                self.record("DELIVERED", **item)
                channel.basic_ack(delivery_tag=method.delivery_tag)
                self.record("ACK_SENT", properties.message_id, queue_id=queue["id"])
                self._received.append(item)
        elif command != "snapshot":
            raise ValueError("허용되지 않은 Routing 동작입니다.")
        return self.snapshot(channel)

    def _run(self):
        future = None
        try:
            with connection() as conn:
                channel = conn.channel()
                self._exchange = None
                self.setup(channel, "direct", DEFAULTS["direct"])
                while conn.is_open:
                    conn.process_data_events(time_limit=0.1)
                    try:
                        command, payload, future = self._commands.get(timeout=0.1)
                    except Empty:
                        continue
                    if command == "end":
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
                future.set_exception(RuntimeError("Routing 실습 연결을 확인하세요."))
        finally:
            with self._lock:
                while True:
                    try:
                        _, _, waiting = self._commands.get_nowait()
                        waiting.set_exception(RuntimeError("Routing 실습 연결이 종료됐습니다."))
                    except Empty:
                        break

    def shutdown(self):
        if self._thread and self._thread.is_alive():
            try:
                self.call("end")
                self._thread.join(timeout=5)
            except (RuntimeError, TimeoutError):
                pass


lab = RoutingLab()
router = APIRouter(prefix="/routing", tags=["Phase 3 Routing"])


def perform(command, payload=None):
    try:
        return lab.call(command, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(503, "Routing 실습 연결을 확인하세요. 실패한 발행을 자동 재시도하지 않습니다.") from exc


@router.get("/snapshot")
def snapshot():
    return perform("snapshot")


@router.post("/setup")
def setup(request: SetupRequest):
    return perform("setup", request)


@router.post("/bindings")
def bindings(request: SetupRequest):
    return perform("bindings", request)


@router.post("/messages")
def messages(request: RoutingPublishRequest):
    return perform("publish", request)


@router.post("/receive")
def receive():
    return perform("receive")
