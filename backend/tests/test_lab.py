import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ["LAB_TOKEN"] = "test-token"
os.environ["RABBIT_PASSWORD"] = "test-password"
os.environ["EVENT_LOG"] = str(Path(tempfile.gettempdir()) / "messageflow-unit-events.jsonl")

from fastapi.testclient import TestClient
from app.consumer import ConsumerSession
from app.main import app


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.session = ConsumerSession()
        self.channel = MagicMock()
        self.recorder = patch("app.consumer.events.record").start()
        self.addCleanup(patch.stopall)

    def receive(self, message_id="message-one", tag=7):
        self.session._received(self.channel, SimpleNamespace(delivery_tag=tag, redelivered=False), SimpleNamespace(message_id=message_id), b'{"body":"hello"}')
        return self.session.view()["pending"]["attempt_id"]

    def test_stale_ack_cannot_acknowledge_next_delivery(self):
        attempt = self.receive()
        self.session._ack(self.channel, attempt)
        next_attempt = self.receive("message-two", 8)
        with self.assertRaises(ValueError):
            self.session._ack(self.channel, attempt)
        self.channel.basic_ack.assert_called_once_with(delivery_tag=7)
        self.assertEqual(self.session.view()["pending"]["attempt_id"], next_attempt)

    def test_failed_ack_preserves_pending_and_does_not_claim_success(self):
        attempt = self.receive()
        self.channel.basic_ack.side_effect = RuntimeError("connection lost")
        with self.assertRaises(RuntimeError):
            self.session._ack(self.channel, attempt)
        self.assertIsNotNone(self.session.view()["pending"])
        self.assertFalse(any(call.args[0] == "ACK_SENT" for call in self.recorder.call_args_list))

    def test_plain_text_body_is_not_lost(self):
        self.session._received(self.channel, SimpleNamespace(delivery_tag=3, redelivered=True), SimpleNamespace(message_id="external"), b"plain text")
        pending = self.session.view()["pending"]
        self.assertEqual(pending["body"], "plain text")
        self.assertTrue(pending["redelivered"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"X-Lab-Token": "test-token"}

    def test_unauthorized_publish_does_not_touch_broker(self):
        with patch("app.main.publish") as publish:
            response = self.client.post("/rabbit/messages", json={"body": "hello"})
        self.assertEqual(response.status_code, 401)
        publish.assert_not_called()

    def test_publish_limit_and_empty_payload(self):
        with patch("app.main.publish") as publish:
            for body in [{"body": "hello", "count": 4}, {"body": " "}, {"body": ""}]:
                response = self.client.post("/rabbit/messages", json=body, headers=self.headers)
                self.assertEqual(response.status_code, 422)
        publish.assert_not_called()

    def test_missing_metrics_returns_unavailable_not_zero(self):
        from fastapi import HTTPException
        with patch("app.main.queue_stats", side_effect=HTTPException(503, "unavailable")):
            response = self.client.get("/snapshot", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("queue", response.json())

    def test_snapshot_includes_real_gauge_and_session_observations(self):
        with patch("app.main.queue_stats", return_value={"name": "hello", "ready": 3, "unacked": 1, "consumers": 1}):
            response = self.client.get("/snapshot", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["queue"]["ready"], 3)
        self.assertIn("collected_at", response.json())

    def test_ack_without_consumer_is_conflict(self):
        response = self.client.post("/consumer/ack", json={"attempt_id": "old-attempt"}, headers=self.headers)
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
