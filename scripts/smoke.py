"""Real-broker integration: requires an empty, isolated hello queue.

Run: docker compose exec api python scripts/smoke.py
Never purges existing messages. May leave test messages if interrupted.
"""
import os
import time
import httpx

client = httpx.Client(base_url="http://localhost:8000", headers={"X-Lab-Token": os.environ["LAB_TOKEN"]}, timeout=10)


def get_snapshot():
    response = client.get("/snapshot")
    response.raise_for_status()
    return response.json()


def wait_for(predicate):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            state = get_snapshot()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 503:
                raise
            time.sleep(0.5)
            continue
        if predicate(state):
            return state
        time.sleep(0.5)
    raise AssertionError("State did not converge within 20 seconds")


initial = wait_for(lambda s: True)
if initial["consumer_active"] or initial["queue"]["ready"] or initial["queue"]["unacked"] or initial["queue"]["consumers"]:
    raise SystemExit("먼저 독립 실습 Queue를 비우고 Consumer를 멈추세요. 이 검증은 메시지를 자동 삭제하지 않습니다.")
response = client.post("/rabbit/messages", json={"body": "smoke", "count": 3})
response.raise_for_status()
ids = set(response.json()["message_ids"])
wait_for(lambda s: s["queue"]["ready"] == 3 and s["queue"]["unacked"] == 0)
client.post("/consumer/start", json={}).raise_for_status()
seen = set()
try:
    for ready in (2, 1, 0):
        state = wait_for(lambda s: s["pending"] is not None and s["queue"]["ready"] == ready and s["queue"]["unacked"] == 1)
        seen.add(state["pending"]["message_id"])
        client.post("/consumer/ack", json={"attempt_id": state["pending"]["attempt_id"]}).raise_for_status()
    wait_for(lambda s: s["pending"] is None and s["queue"]["ready"] == 0 and s["queue"]["unacked"] == 0)
    assert seen == ids, "Not all published messages were consumed"
    print("PASS: 3 messages → Ready 3 → Unacked 1 → 3 ACKs → empty queue")
finally:
    client.post("/consumer/stop", json={}).raise_for_status()
    client.close()
