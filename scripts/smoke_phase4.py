"""Phase 4 integration test: Publisher Confirm, mandatory Return, persistent/transient.

Run inside the api container:
    docker compose exec -T api python scripts/smoke_phase4.py
"""
import json
import sys
import time
import httpx

BASE = "http://localhost:8000"
TOKEN = None


def get_token():
    import os
    return os.environ.get("LAB_TOKEN", "")


def headers():
    return {"X-Lab-Token": TOKEN, "Content-Type": "application/json"}


def api(method, path, body=None):
    with httpx.Client(base_url=BASE, timeout=10, trust_env=False) as client:
        if method == "GET":
            r = client.get(path, headers=headers())
        else:
            r = client.post(path, headers=headers(), json=body or {})
        if r.status_code >= 400:
            print(f"  FAIL {method} {path} → {r.status_code}: {r.text[:200]}")
            sys.exit(1)
        return r.json()


def check(condition, message):
    if not condition:
        print(f"  FAIL: {message}")
        sys.exit(1)
    print(f"  OK: {message}")


def main():
    global TOKEN
    TOKEN = get_token()
    if not TOKEN:
        print("LAB_TOKEN 환경변수가 필요합니다.")
        sys.exit(1)

    print("\n=== Phase 4: Publisher Reliability ===\n")

    # 1. Setup new experiment
    print("1. Setup new experiment")
    snap = api("POST", "/reliability/setup")
    check(snap["exchange"] is not None, "Exchange created")
    check(len(snap["queues"]) == 3, "3 queues created")
    check(all(q["ready"] == 0 for q in snap["queues"]), "All queues empty")

    # 2. Normal publish — Confirm ACK, routed to Queue A
    print("\n2. Normal publish (routed)")
    snap = api("POST", "/reliability/publish", {"body": "normal-test", "scenario": "normal"})
    pub = snap["last_publish"]
    check(pub is not None, "last_publish recorded")
    check(pub["confirmed"] is True, "Broker Confirm ACK received")
    check(pub["returned"] is False, "No Return for routed message")
    check(pub["nacked"] is False, "Not NACKed")
    check(pub["outcome_unknown"] is False, "Outcome is known")
    # Check Queue A has the message
    queue_a = next(q for q in snap["queues"] if q["id"] == "a")
    check(queue_a["ready"] == 1, f"Queue A Ready=1 (got {queue_a['ready']})")
    message_id = pub["message_id"]

    # 3. Mandatory unroutable — Confirm ACK + Return
    print("\n3. Mandatory unroutable publish")
    snap = api("POST", "/reliability/publish", {"body": "unroutable-test", "scenario": "mandatory_unroutable"})
    pub = snap["last_publish"]
    check(pub["confirmed"] is True, "Confirm ACK despite unroutable")
    check(pub["returned"] is True, "Return received for unroutable mandatory")
    check(pub["routing_key"] == "unroutable", "Used unroutable key")
    # No queue should gain a message (Queue A still has 1 from previous)
    queue_a = next(q for q in snap["queues"] if q["id"] == "a")
    check(queue_a["ready"] == 1, f"Queue A still Ready=1 (got {queue_a['ready']})")

    # Verify Confirm and Return are recorded as separate events
    events = snap["events"]
    event_types = [e["event_type"] for e in events]
    check("PUBLISH_CONFIRMED" in event_types, "PUBLISH_CONFIRMED event recorded")
    check("PUBLISH_RETURNED" in event_types, "PUBLISH_RETURNED event recorded")
    # Both should be present — not merged
    confirmed_events = [e for e in events if e["event_type"] == "PUBLISH_CONFIRMED"]
    returned_events = [e for e in events if e["event_type"] == "PUBLISH_RETURNED"]
    check(len(confirmed_events) >= 1, f"At least 1 PUBLISH_CONFIRMED (got {len(confirmed_events)})")
    check(len(returned_events) >= 1, f"At least 1 PUBLISH_RETURNED (got {len(returned_events)})")

    # 4. Persistent publish — delivery_mode=2 to durable Queue B
    print("\n4. Persistent publish")
    snap = api("POST", "/reliability/publish", {"body": "persistent-test", "scenario": "persistent"})
    pub = snap["last_publish"]
    check(pub["confirmed"] is True, "Persistent publish confirmed")
    check(pub["delivery_mode"] == 2, "delivery_mode=2")
    queue_b = next(q for q in snap["queues"] if q["id"] == "b")
    check(queue_b["ready"] == 1, f"Queue B Ready=1 (got {queue_b['ready']})")

    # 5. Transient publish — delivery_mode=1 to auto_delete Queue C
    print("\n5. Transient publish")
    snap = api("POST", "/reliability/publish", {"body": "transient-test", "scenario": "transient"})
    pub = snap["last_publish"]
    check(pub["confirmed"] is True, "Transient publish confirmed")
    check(pub["delivery_mode"] == 1, "delivery_mode=1")
    queue_c = next(q for q in snap["queues"] if q["id"] == "c")
    check(queue_c["ready"] == 1, f"Queue C Ready=1 (got {queue_c['ready']})")

    # 6. Receive from all queues
    print("\n6. Receive from all queues")
    snap = api("POST", "/reliability/receive")
    received = snap["last_received"]
    check(len(received) == 3, f"Received from 3 queues (got {len(received)})")
    received_queues = {r["queue_id"] for r in received}
    check(received_queues == {"a", "b", "c"}, f"Received from A, B, C (got {received_queues})")
    # Verify delivery_mode is preserved
    for r in received:
        if r["queue_id"] == "c":
            check(r["delivery_mode"] == 1, f"Transient message delivery_mode=1 (got {r['delivery_mode']})")
        else:
            check(r["delivery_mode"] == 2, f"Persistent message delivery_mode=2 (got {r['delivery_mode']})")

    # All queues should be empty now
    for q in snap["queues"]:
        check(q["ready"] == 0, f"Queue {q['id'].upper()} empty after receive (Ready={q['ready']})")

    # 7. Verify event types in final snapshot
    print("\n7. Verify event completeness")
    expected_types = {"TOPOLOGY_CREATED", "PUBLISH_SENT", "PUBLISH_CONFIRMED", "PUBLISH_RETURNED", "DELIVERED", "ACK_SENT"}
    actual_types = {e["event_type"] for e in snap["events"]}
    for t in expected_types:
        check(t in actual_types, f"Event type {t} recorded")

    print("\n=== Phase 4 PASSED ===")
    print("Note: Broker restart persistence test is manual. Publish persistent+durable,")
    print("restart RabbitMQ (docker compose restart rabbitmq), then check Queue B Ready.")
    print("Transient Queue C will not survive the restart.\n")


if __name__ == "__main__":
    main()
