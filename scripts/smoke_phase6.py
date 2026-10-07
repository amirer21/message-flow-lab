"""Phase 6 integration test: Idempotency — deduplicate business effects.

Run inside the api container:
    docker compose exec -T api python scripts/smoke_phase6.py
"""
import sys
import httpx
import os

BASE = "http://localhost:8000"
TOKEN = None


def get_token():
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


def queue_ready(snap, role):
    return next(q for q in snap["queues"] if q["role"] == role)["ready"]


def effect_count(snap):
    return len(snap["effects"])


def main():
    global TOKEN
    TOKEN = get_token()
    if not TOKEN:
        print("LAB_TOKEN 환경변수가 필요합니다.")
        sys.exit(1)

    print("\n=== Phase 6: Idempotency ===\n")

    # 1. Setup
    print("1. Setup new experiment")
    snap = api("POST", "/idempotency/setup")
    check(snap["work_exchange"] is not None, "Work exchange created")
    check(len(snap["queues"]) == 1, "1 queue created (work)")
    check(queue_ready(snap, "work") == 0, "Work queue empty")
    check(effect_count(snap) == 0, "No business effects")
    check(snap["processed_count"] == 0, "No processed commands")

    # 2. Normal — publish and process once
    print("\n2. Normal processing — single message")
    snap = api("POST", "/idempotency/publish", {"idempotency_key": "order-001", "amount": 1000})
    check(snap["last_publish"]["confirmed"] is True, "Publish confirmed")
    check(snap["last_publish"]["idempotency_key"] == "order-001", "Key matches")
    check(queue_ready(snap, "work") == 1, "Work queue has 1 message")

    snap = api("POST", "/idempotency/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "applied", "Effect applied")
    check(proc["was_duplicate"] is False, "Not a duplicate")
    check(proc["idempotency_key"] == "order-001", "Key matches")
    check(queue_ready(snap, "work") == 0, "Work queue empty")
    check(effect_count(snap) == 1, "1 business effect recorded")
    check(snap["processed_count"] == 1, "1 processed command")

    # 3. Duplicate — same key published twice, processed twice
    print("\n3. Duplicate — same key, effects should stay at 1")
    snap = api("POST", "/idempotency/publish", {"idempotency_key": "order-001", "amount": 1000})
    check(queue_ready(snap, "work") == 1, "Work queue has 1 (duplicate)")

    snap = api("POST", "/idempotency/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "skipped", "Duplicate skipped")
    check(proc["was_duplicate"] is True, "Marked as duplicate")
    check(queue_ready(snap, "work") == 0, "Work queue empty")
    check(effect_count(snap) == 1, "Still 1 business effect (no duplicate)")
    check(snap["processed_count"] == 1, "Still 1 processed command")

    # 4. New key — different key should create new effect
    print("\n4. Different key — new effect")
    snap = api("POST", "/idempotency/publish", {"idempotency_key": "order-002", "amount": 2000})
    snap = api("POST", "/idempotency/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "applied", "New key effect applied")
    check(proc["was_duplicate"] is False, "Not a duplicate")
    check(effect_count(snap) == 2, "2 business effects now")
    check(snap["processed_count"] == 2, "2 processed commands")

    # 5. Crash after commit — arm crash, process, then process redelivered
    print("\n5. Crash after commit — redelivery dedup")
    snap = api("POST", "/idempotency/publish", {"idempotency_key": "order-003", "amount": 3000})
    check(queue_ready(snap, "work") == 1, "Work queue has 1")

    # Arm crash
    snap = api("POST", "/idempotency/arm-crash")

    # Process — will commit to DB but NACK (requeue)
    snap = api("POST", "/idempotency/process")
    proc = snap["last_process"]
    check(proc["idempotency_key"] == "order-003", "Key matches")
    # The message was NACKed and requeued, so it should be back in the queue
    check(queue_ready(snap, "work") == 1, "Message requeued after crash")
    # Effect should be recorded (DB committed before crash)
    check(effect_count(snap) == 3, "3 effects (crash committed to DB)")
    check(snap["processed_count"] == 3, "3 processed commands")

    # Process the redelivered message — should be deduplicated
    snap = api("POST", "/idempotency/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "skipped", "Redelivered message deduplicated")
    check(proc["was_duplicate"] is True, "Marked as duplicate")
    check(queue_ready(snap, "work") == 0, "Work queue empty")
    check(effect_count(snap) == 3, "Still 3 effects (no duplicate)")
    check(snap["processed_count"] == 3, "Still 3 processed commands")

    # 6. Verify event completeness
    print("\n6. Verify event completeness")
    expected_types = {
        "TOPOLOGY_CREATED", "PUBLISH_SENT", "PUBLISH_CONFIRMED",
        "PROCESSING_STARTED", "EFFECT_APPLIED", "DUPLICATE_SKIPPED",
        "CRASH_BEFORE_ACK", "CRASH_ARMED", "ACK_SENT",
    }
    actual_types = {e["event_type"] for e in snap["events"]}
    for t in expected_types:
        check(t in actual_types, f"Event type {t} recorded")

    # 7. Verify effects endpoint
    print("\n7. Verify /idempotency/effects endpoint")
    effects = api("GET", "/idempotency/effects")
    check(len(effects) == 3, "Effects endpoint returns 3 records")
    keys = {e["idempotency_key"] for e in effects}
    check(keys == {"order-001", "order-002", "order-003"}, "All keys present")

    print("\n=== Phase 6 PASSED ===\n")


if __name__ == "__main__":
    main()
