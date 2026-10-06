"""Actual SIGKILL experiments against the isolated Phase 2 queue. Never purges.

Run: docker compose exec api python scripts/smoke_phase2.py
"""
import os
import time
import httpx

client = httpx.Client(base_url="http://localhost:8000", headers={"X-Lab-Token": os.environ["LAB_TOKEN"]}, timeout=10)


def snapshot():
    response = client.get("/experiments/snapshot")
    response.raise_for_status()
    return response.json()


def command(action, **body):
    response = client.post(f"/experiments/{action}", json=body)
    response.raise_for_status()
    return response.json()


def wait_for(predicate):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            state = snapshot()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 503:
                raise
            time.sleep(0.5)
            continue
        if predicate(state):
            return state
        time.sleep(0.5)
    raise AssertionError("Experiment state did not converge within 20 seconds")


initial = wait_for(lambda s: True)
if initial["consumer_active"] or any(initial["queue"][key] for key in ["ready", "unacked", "consumers"]):
    raise SystemExit("Phase 2 Queue를 독립된 빈 상태로 준비하세요. 기존 메시지는 삭제하지 않습니다.")

try:
    # A: actual work is recorded, then the child is killed before ACK.
    first_id = command("messages", body="phase2-smoke-before-ack")["message_ids"][0]
    wait_for(lambda s: s["queue"]["ready"] == 1)
    command("start")
    first = wait_for(lambda s: s["pending"] is not None and s["queue"]["unacked"] == 1)["pending"]
    command("process", attempt_id=first["attempt_id"])
    command("crash")
    wait_for(lambda s: s["queue"]["ready"] == 1 and not s["consumer_active"])
    command("start")
    second = wait_for(lambda s: s["pending"] is not None)["pending"]
    assert second["message_id"] == first_id
    assert second["attempt_id"] != first["attempt_id"]
    assert second["redelivered"] is True
    stale = client.post("/experiments/ack", json={"attempt_id": first["attempt_id"]})
    assert stale.status_code == 409, "Stale ACK must not acknowledge a redelivery"
    command("process", attempt_id=second["attempt_id"])
    command("ack", attempt_id=second["attempt_id"])
    state = wait_for(lambda s: not s["pending"] and s["queue"]["ready"] == 0 and s["queue"]["unacked"] == 0)
    assert state["effect_counts"][first_id] == 2
    command("stop")
    print("PASS A: real child killed before ACK → same message redelivered → two persisted effects")

    # B: wait for Broker gauges to reflect ACK before killing the child.
    second_id = command("messages", body="phase2-smoke-after-ack")["message_ids"][0]
    command("start")
    delivered = wait_for(lambda s: s["pending"] is not None)["pending"]
    command("process", attempt_id=delivered["attempt_id"])
    command("ack", attempt_id=delivered["attempt_id"])
    wait_for(lambda s: not s["pending"] and s["queue"]["ready"] == 0 and s["queue"]["unacked"] == 0)
    command("crash")
    command("start")
    time.sleep(2)
    state = snapshot()
    assert state["pending"] is None
    assert state["queue"]["ready"] == 0 and state["queue"]["unacked"] == 0
    assert state["effect_counts"][second_id] == 1
    print("PASS B: Broker reflected ACK → real child killed → no redelivery, one persisted effect")
finally:
    if snapshot()["consumer_active"]:
        command("stop")
    client.close()
