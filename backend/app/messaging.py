import json
from contextlib import contextmanager
from uuid import uuid4

import pika

from .config import settings
from .events import events


@contextmanager
def connection():
    params = pika.ConnectionParameters(
        host=settings.rabbit_host, port=settings.rabbit_port,
        virtual_host=settings.rabbit_vhost,
        credentials=pika.PlainCredentials(settings.rabbit_user, settings.rabbit_password),
        heartbeat=30, blocked_connection_timeout=5, socket_timeout=3,
        stack_timeout=5, connection_attempts=1,
    )
    conn = pika.BlockingConnection(params)
    try:
        yield conn
    finally:
        if conn.is_open:
            conn.close()


def declare(channel, queue=None):
    return channel.queue_declare(queue=queue or settings.queue, durable=True)


def publish(body: str, count: int, queue=None):
    queue = queue or settings.queue
    message_ids = []
    with connection() as conn:
        channel = conn.channel()
        declare(channel, queue)
        for index in range(count):
            message_id = str(uuid4())
            text = body if count == 1 else f"{body} {index + 1}"
            channel.basic_publish(
                exchange="", routing_key=queue,
                body=json.dumps({"body": text}, ensure_ascii=False).encode("utf-8"),
                properties=pika.BasicProperties(
                    message_id=message_id, correlation_id=message_id,
                    content_type="application/json", delivery_mode=2,
                ),
            )
            events.record("PUBLISH_SENT", message_id, worker="producer-lab", body=text, exchange="", routing_key=queue, queue=queue)
            message_ids.append(message_id)
    # Phase 1 intentionally does not claim publisher-confirm guarantees.
    return {"message_ids": message_ids, "status": "PUBLISH_SENT", "publisher_confirmed": False}
