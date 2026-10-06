"""Standalone Pika consumer. Run inside API container; stop via Ctrl+C."""
import argparse
import json

from app.events import events
from app.messaging import connection, declare

parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=float, default=2.0)
args = parser.parse_args()
if not 0 <= args.seconds <= 120:
    parser.error("seconds must be between 0 and 120")

with connection() as conn:
    channel = conn.channel()
    declare(channel)
    channel.basic_qos(prefetch_count=1)

    def receive(ch, method, properties, body):
        print(json.dumps({"event": "DELIVERED", "message_id": properties.message_id, "redelivered": method.redelivered, "body": body.decode()}, ensure_ascii=False), flush=True)
        # Process heartbeats while simulating work; no time.sleep in Pika callback.
        conn.sleep(args.seconds)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        print(json.dumps({"event": "ACK_SENT", "message_id": properties.message_id}), flush=True)

    channel.basic_consume(queue="hello", on_message_callback=receive, auto_ack=False)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
