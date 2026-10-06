import json
from concurrent.futures import Future
from queue import Empty, Queue
from threading import Event, Lock, Thread
from uuid import uuid4

from .config import settings
from .events import events
from .messaging import connection, declare


class ConsumerSession:
    """One controlled teaching consumer, prefetch=1, awaiting a human ACK.

    All channel calls happen on its owning thread. Commands carry attempt_id
    so a delayed or double-clicked ACK cannot acknowledge a later delivery.
    Run one API process; scaling this session requires a shared controller.
    """

    def __init__(self):
        self._lock = Lock()
        self._thread = None
        self._commands = Queue()
        self._pending = None
        self._delivery_tag = None
        self._active = False
        self._ready = Event()
        self._error = None

    def view(self):
        with self._lock:
            return {"pending": dict(self._pending) if self._pending else None, "consumer_active": self._active}

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise ValueError("Consumer가 이미 실행 중입니다.")
            self._commands = Queue()
            self._ready = Event()
            self._error = None
            self._thread = Thread(target=self._run, daemon=True, name="consumer-lab")
            self._thread.start()
        if not self._ready.wait(7):
            raise RuntimeError("Consumer 접속 시간이 초과됐습니다. 상태를 확인하세요.")
        if self._error:
            raise RuntimeError("RabbitMQ Consumer를 연결할 수 없습니다.") from self._error
        return self.view()

    def command(self, kind, attempt_id=None):
        with self._lock:
            if not self._active:
                raise ValueError("실행 중인 Consumer가 없습니다.")
            future = Future()
            self._commands.put((kind, attempt_id, future))
        return future.result(timeout=7)

    def _received(self, channel, method, properties, body):
        text = body.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and isinstance(payload.get("body"), str):
                text = payload["body"]
        except (ValueError, TypeError):
            pass
        pending = {
            "message_id": properties.message_id or str(uuid4()),
            "attempt_id": str(uuid4()), "body": text, "redelivered": method.redelivered,
        }
        with self._lock:
            self._pending = pending
            self._delivery_tag = method.delivery_tag
        events.record("DELIVERED", pending["message_id"], attempt_id=pending["attempt_id"], worker="consumer-lab", body=text, redelivered=method.redelivered)

    def _ack(self, channel, attempt_id):
        with self._lock:
            pending = self._pending
            tag = self._delivery_tag
        if not pending or pending["attempt_id"] != attempt_id:
            raise ValueError("현재 전달과 일치하지 않는 ACK입니다.")
        channel.basic_ack(delivery_tag=tag)
        with self._lock:
            self._pending = None
            self._delivery_tag = None
        events.record("ACK_SENT", pending["message_id"], attempt_id=attempt_id, worker="consumer-lab")

    def _run(self):
        try:
            with connection() as conn:
                channel = conn.channel()
                declare(channel)
                channel.basic_qos(prefetch_count=1)
                channel.basic_consume(queue=settings.queue, on_message_callback=self._received, auto_ack=False)
                with self._lock:
                    self._active = True
                events.record("CONSUMER_STARTED", worker="consumer-lab")
                self._ready.set()
                running = True
                while running and conn.is_open:
                    conn.process_data_events(time_limit=0.2)
                    while True:
                        try:
                            kind, attempt_id, future = self._commands.get_nowait()
                        except Empty:
                            break
                        try:
                            if kind == "ack":
                                self._ack(channel, attempt_id)
                            elif kind == "stop":
                                # Closing requeues any unacknowledged delivery; do not ACK.
                                conn.close()
                                running = False
                                with self._lock:
                                    pending = self._pending
                                if pending:
                                    events.record("CONNECTION_CLOSED", pending["message_id"], attempt_id=pending["attempt_id"], worker="consumer-lab")
                                events.record("CONSUMER_STOPPED", worker="consumer-lab")
                            future.set_result({"status": "accepted"})
                        except Exception as exc:
                            future.set_exception(exc)
                        if not running:
                            break
        except Exception as exc:
            self._error = exc
            events.record("CONSUMER_ERROR", worker="consumer-lab", error_type=type(exc).__name__)
        finally:
            with self._lock:
                self._active = False
                self._pending = None
                self._delivery_tag = None
            self._ready.set()
            while True:
                try:
                    _, _, future = self._commands.get_nowait()
                    if not future.done():
                        future.set_exception(RuntimeError("Consumer 연결이 종료됐습니다."))
                except Empty:
                    break

    def shutdown(self):
        if self.view()["consumer_active"]:
            try:
                self.command("stop")
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=8)


consumer = ConsumerSession()
