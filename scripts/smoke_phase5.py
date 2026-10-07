"""Phase 5 integration test: Retry, DLQ, failure classification.

Run inside the api container:
    docker compose exec -T api python scripts/smoke_phase5.py
"""
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


def queue_ready(snap, role):
    return next(q for q in snap["queues"] if q["role"] == role)["ready"]


def main():
    global TOKEN
    TOKEN = get_token()
    if not TOKEN:
        print("LAB_TOKEN 환경변수가 필요합니다.")
        sys.exit(1)

    print("\n=== Phase 5: Retry · DLQ ===\n")

    # 1. Setup
    print("1. Setup new experiment")
    snap = api("POST", "/retry/setup")
    check(snap["work_exchange"] is not None, "Work exchange created")
    check(len(snap["queues"]) == 3, "3 queues created (work, retry, dead)")
    check(all(q["ready"] == 0 for q in snap["queues"]), "All queues empty")

    # 2. Scenario: permanent — immediate DLQ
    print("\n2. Permanent failure → immediate DLQ")
    snap = api("POST", "/retry/publish", {"body": "permanent-test", "scenario": "permanent"})
    check(snap["last_publish"]["confirmed"] is True, "Publish confirmed")
    check(queue_ready(snap, "work") == 1, "Work queue has 1 message")

    snap = api("POST", "/retry/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "dlq", "Permanent → DLQ")
    check(queue_ready(snap, "work") == 0, "Work queue empty")
    check(queue_ready(snap, "dead") == 1, "Dead queue has 1")
    check(queue_ready(snap, "retry") == 0, "Retry queue empty")

    # 3. Scenario: transient_2x — fail 2x, succeed on 3rd
    print("\n3. Transient 2x failure → retry → success")
    snap = api("POST", "/retry/publish", {"body": "transient-test", "scenario": "transient_2x"})
    check(queue_ready(snap, "work") == 1, "Work queue has 1")

    # First process: fail → retry
    snap = api("POST", "/retry/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "retry", "1st attempt → retry")
    check(proc["retry_count"] == 0, "retry_count=0")
    check(queue_ready(snap, "retry") == 1, "Retry queue has 1")
    check(queue_ready(snap, "work") == 0, "Work queue empty (message in retry)")

    # Wait for TTL expiry (5s + buffer)
    print("  Waiting 7s for TTL expiry...")
    time.sleep(7)

    # Check message returned to work queue
    snap = api("GET", "/retry/snapshot")
    check(queue_ready(snap, "work") == 1, "Message returned to work queue after TTL")
    check(queue_ready(snap, "retry") == 0, "Retry queue empty after TTL")

    # Second process: fail → retry again
    snap = api("POST", "/retry/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "retry", "2nd attempt → retry")
    check(proc["retry_count"] == 1, "retry_count=1")

    print("  Waiting 7s for TTL expiry...")
    time.sleep(7)

    snap = api("GET", "/retry/snapshot")
    check(queue_ready(snap, "work") == 1, "Message returned again after TTL")

    # Third process: success
    snap = api("POST", "/retry/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "success", "3rd attempt → success")
    check(proc["retry_count"] == 2, "retry_count=2")
    check(queue_ready(snap, "work") == 0, "Work queue empty after success")
    check(queue_ready(snap, "dead") == 1, "Dead queue unchanged (still 1 from permanent)")

    # 4. Scenario: retry_exceed — exhaust retries → DLQ
    print("\n4. Retry exceed → 3 retries then DLQ")
    snap = api("POST", "/retry/publish", {"body": "exceed-test", "scenario": "retry_exceed"})

    for attempt in range(3):
        snap = api("POST", "/retry/process")
        proc = snap["last_process"]
        check(proc["outcome"] == "retry", f"Attempt {attempt+1} → retry")
        check(proc["retry_count"] == attempt, f"retry_count={attempt}")
        print(f"  Waiting 7s for TTL expiry (attempt {attempt+1})...")
        time.sleep(7)
        snap = api("GET", "/retry/snapshot")
        check(queue_ready(snap, "work") == 1, f"Message returned after attempt {attempt+1}")

    # 4th process: retry_count=3 → DLQ
    snap = api("POST", "/retry/process")
    proc = snap["last_process"]
    check(proc["outcome"] == "dlq", "After 3 retries → DLQ")
    check(proc["retry_count"] == 3, "retry_count=3")
    check(queue_ready(snap, "dead") == 2, "Dead queue has 2 (permanent + exceed)")
    check(queue_ready(snap, "work") == 0, "Work queue empty")

    # 5. Verify event completeness
    print("\n5. Verify event completeness")
    expected_types = {
        "TOPOLOGY_CREATED", "PUBLISH_SENT", "PUBLISH_CONFIRMED",
        "PROCESSING_STARTED", "PROCESSING_FAILED", "PROCESSING_SUCCEEDED",
        "RETRY_SCHEDULED", "RETRY_RETURNED", "DLQ_STORED", "ACK_SENT",
    }
    actual_types = {e["event_type"] for e in snap["events"]}
    for t in expected_types:
        check(t in actual_types, f"Event type {t} recorded")

    print("\n=== Phase 5 PASSED ===\n")


if __name__ == "__main__":
    main()
