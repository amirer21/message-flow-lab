import json
import subprocess
import sys
from concurrent.futures import Future
from threading import Event, Lock, Thread, current_thread
from uuid import uuid4

from .config import settings
from .events import events


class ExperimentConsumer:
    def __init__(self):
        self._lock = Lock()
        self._process = None
        self._reader = None
        self._active = False
        self._pending = None
        self._last_delivery = None
        self._last_ack = None
        self._ready = Event()
        self._requests = {}

    def view(self):
        with self._lock:
            return {"consumer_active": self._active,
                    "pending": dict(self._pending) if self._pending else None}

    def start(self):
        with self._lock:
            if self._process and self._process.poll() is None:
                raise ValueError("실습 Consumer 프로세스가 이미 실행 중입니다.")
            previous_reader = self._reader
        if previous_reader:
            previous_reader.join(timeout=5)
        with self._lock:
            if self._process and self._process.poll() is None:
                raise ValueError("실습 Consumer 프로세스가 이미 실행 중입니다.")
            self._ready = Event()
            self._pending = None
            self._last_delivery = None
            self._last_ack = None
            # Fixed command, no shell and no user-controlled executable or PID.
            self._process = subprocess.Popen(
                [sys.executable, "-u", "-m", "app.phase2_worker"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", bufsize=1,
            )
            self._reader = Thread(target=self._read, args=(self._process,), daemon=True)
            self._reader.start()
        if not self._ready.wait(7) or not self.view()["consumer_active"]:
            self.shutdown()
            raise RuntimeError("실습 Consumer를 연결할 수 없습니다.")
        return self.view()

    def _read(self, process):
        try:
            for line in process.stdout:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                kind = record.get("kind")
                if kind == "ready":
                    with self._lock:
                        self._active = True
                    events.record("CONSUMER_STARTED", worker="consumer-phase2", queue=settings.experiment_queue)
                    self._ready.set()
                elif kind == "event":
                    pending = record["pending"]
                    event_type = record["event_type"]
                    with self._lock:
                        self._last_delivery = dict(pending)
                        if event_type == "ACK_SENT":
                            self._last_ack = dict(pending)
                            self._pending = None
                        else:
                            self._pending = dict(pending)
                    events.record(event_type, pending["message_id"], attempt_id=pending["attempt_id"],
                                  worker="consumer-phase2", queue=settings.experiment_queue,
                                  body=pending["body"], redelivered=pending["redelivered"],
                                  processed=pending["processed"], effect=record.get("effect"))
                elif kind == "response":
                    with self._lock:
                        future = self._requests.pop(record.get("request_id"), None)
                    if future and not future.done():
                        if record.get("ok"):
                            future.set_result({"status": "accepted"})
                        else:
                            future.set_exception(ValueError(record.get("error", "실험 명령 실패")))
                elif kind == "error":
                    events.record("CONSUMER_ERROR", worker="consumer-phase2", queue=settings.experiment_queue, error_type=record.get("error_type"))
        finally:
            return_code = process.wait()
            process.stdout.close()
            process.stdin.close()
            with self._lock:
                last_delivery = dict(self._pending or self._last_ack or {})
                # An older reader must never reset a newly started child.
                if self._process is process:
                    self._active = False
                    self._pending = None
                    requests = list(self._requests.values())
                    self._requests.clear()
                else:
                    requests = []
            for future in requests:
                if not future.done():
                    future.set_exception(RuntimeError("실습 Consumer가 종료됐습니다."))
            self._ready.set()
            events.record("WORKER_EXITED", last_delivery.get("message_id", ""), attempt_id=last_delivery.get("attempt_id"), worker="consumer-phase2", queue=settings.experiment_queue, return_code=return_code)

    def command(self, command, attempt_id=None):
        if command not in {"process", "ack", "stop"}:
            raise ValueError("허용되지 않은 명령입니다.")
        with self._lock:
            if not self._active or not self._process or self._process.poll() is not None:
                raise ValueError("실행 중인 실습 Consumer가 없습니다.")
            request_id = str(uuid4())
            future = Future()
            self._requests[request_id] = future
            try:
                self._process.stdin.write(json.dumps({"command": command, "attempt_id": attempt_id, "request_id": request_id}) + "\n")
                self._process.stdin.flush()
            except (OSError, ValueError) as exc:
                self._requests.pop(request_id, None)
                raise RuntimeError("실습 Consumer 연결이 종료됐습니다.") from exc
        return future.result(timeout=7)

    def crash(self):
        with self._lock:
            process = self._process
            if not self._active or not process or process.poll() is not None:
                raise ValueError("강제 종료할 실습 Consumer가 없습니다.")
            pending = dict(self._pending or self._last_ack or {})
            ack_sent = self._pending is None and self._last_ack is not None
            process.kill()
        process.wait(timeout=5)
        if self._reader:
            self._reader.join(timeout=5)
        events.record("WORKER_KILLED", pending.get("message_id", ""), attempt_id=pending.get("attempt_id"),
                      worker="experiment-controller", queue=settings.experiment_queue, ack_sent=ack_sent)
        return {"status": "killed", "ack_sent": ack_sent}

    def shutdown(self):
        with self._lock:
            process = self._process
        if process and process.poll() is None:
            try:
                self.command("stop")
                process.wait(timeout=5)
            except (RuntimeError, ValueError, TimeoutError):
                process.kill()
                process.wait(timeout=5)
        if self._reader and self._reader is not current_thread():
            self._reader.join(timeout=5)


experiment = ExperimentConsumer()
