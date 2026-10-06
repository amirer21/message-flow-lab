"""Fixed educational child process. Its only commands are process, ack, stop.

STDIN carries commands; STDOUT carries structured events and responses. The
Pika channel is owned exclusively by the main thread. Killing this process
does not kill the API, Broker, or any other worker.
"""
import json
import sys
from queue import Empty, Queue
from threading import Thread
from uuid import uuid4

from .config import settings
from .effects import append_effect
from .messaging import connection, declare


def emit(kind, **fields):
    print(json.dumps({"kind": kind, **fields}, ensure_ascii=False), flush=True)


def main():
    commands = Queue()

    def read_commands():
        for line in sys.stdin:
            try:
                commands.put(json.loads(line))
            except ValueError:
                continue
        commands.put({"command": "stop", "request_id": "parent-disconnected"})

    Thread(target=read_commands, daemon=True).start()
    pending = None
    tag = None
    try:
        with connection() as conn:
            channel = conn.channel()
            declare(channel, settings.experiment_queue)
            channel.basic_qos(prefetch_count=1)

            def receive(ch, method, properties, body):
                nonlocal pending, tag
                text = body.decode("utf-8", errors="replace")
                try:
                    value = json.loads(text)
                    if isinstance(value, dict) and isinstance(value.get("body"), str):
                        text = value["body"]
                except ValueError:
                    pass
                pending = {"message_id": properties.message_id or str(uuid4()),
                           "attempt_id": str(uuid4()), "body": text,
                           "redelivered": method.redelivered, "processed": False}
                tag = method.delivery_tag
                emit("event", event_type="DELIVERED", pending=pending)

            channel.basic_consume(queue=settings.experiment_queue, on_message_callback=receive, auto_ack=False)
            emit("ready")
            running = True
            while running and conn.is_open:
                conn.process_data_events(time_limit=0.1)
                while True:
                    try:
                        command = commands.get_nowait()
                    except Empty:
                        break
                    request_id = command.get("request_id")
                    try:
                        kind = command.get("command")
                        if kind not in {"process", "ack", "stop"}:
                            raise ValueError("허용되지 않은 실험 명령입니다.")
                        if kind == "stop":
                            conn.close()
                            running = False
                        else:
                            if not pending or command.get("attempt_id") != pending["attempt_id"]:
                                raise ValueError("현재 전달과 일치하지 않는 처리 시도입니다.")
                            if kind == "process":
                                if pending["processed"]:
                                    raise ValueError("이 처리 시도는 이미 업무를 반영했습니다.")
                                effect = append_effect(pending["message_id"], pending["attempt_id"])
                                # 업무 기록 후 ACK 전 종료하면 새 전달에서 업무가 반복될 수 있다.
                                pending["processed"] = True
                                emit("event", event_type="PROCESSED", pending=pending, effect=effect)
                            else:
                                if not pending["processed"]:
                                    raise ValueError("업무 반영을 확인한 뒤 ACK를 보내세요.")
                                channel.basic_ack(delivery_tag=tag)
                                emit("event", event_type="ACK_SENT", pending=pending)
                                pending = None
                                tag = None
                        emit("response", request_id=request_id, ok=True)
                    except ValueError as exc:
                        emit("response", request_id=request_id, ok=False, error=str(exc))
                    if not running:
                        break
    except Exception as exc:
        emit("error", error_type=type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
