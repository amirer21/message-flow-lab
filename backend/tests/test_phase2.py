import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("LAB_TOKEN", "test-token")
os.environ.setdefault("RABBIT_PASSWORD", "test-password")

from fastapi.testclient import TestClient
from app.effects import append_effect, read_effects
from app.experiments import ExperimentConsumer
from app.main import app


class EffectTests(unittest.TestCase):
    def test_redelivery_can_repeat_a_durable_business_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SimpleNamespace(effect_log=str(Path(directory) / "effects.jsonl"))
            with patch("app.effects.settings", settings):
                append_effect("same-message", "attempt-one")
                append_effect("same-message", "attempt-two")
                snapshot = read_effects()
        self.assertEqual(snapshot["effect_counts"]["same-message"], 2)
        self.assertEqual(snapshot["effects_total"], 2)
        self.assertNotEqual(snapshot["effects"][0]["attempt_id"], snapshot["effects"][1]["attempt_id"])

    def test_partial_journal_line_does_not_erase_completed_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "effects.jsonl"
            with patch("app.effects.settings", SimpleNamespace(effect_log=str(path))):
                append_effect("completed", "attempt")
                with path.open("a") as stream:
                    stream.write('{"partial":')
                self.assertEqual(read_effects()["effects_total"], 1)


class ExperimentApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"X-Lab-Token": "test-token"}

    def test_unauthorized_crash_cannot_stop_a_process(self):
        with patch("app.main.experiment") as controller:
            response = self.client.post("/experiments/crash", json={})
        self.assertEqual(response.status_code, 401)
        controller.crash.assert_not_called()

    def test_arbitrary_control_actions_are_not_exposed(self):
        response = self.client.post("/experiments/execute", json={}, headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_ack_requires_attempt_id(self):
        with patch("app.main.experiment") as controller:
            response = self.client.post("/experiments/ack", json={}, headers=self.headers)
        self.assertEqual(response.status_code, 422)
        controller.command.assert_not_called()

    def test_crash_accepts_empty_control_body(self):
        with patch("app.main.experiment") as controller:
            controller.crash.return_value = {"status": "killed"}
            response = self.client.post("/experiments/crash", json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        controller.crash.assert_called_once_with()

    def test_crash_only_targets_the_child_owned_by_the_controller(self):
        controller = ExperimentConsumer()
        child = MagicMock()
        child.poll.return_value = None
        controller._process = child
        controller._active = True
        controller._pending = {"message_id": "one", "attempt_id": "first"}
        with patch("app.experiments.events.record"):
            result = controller.crash()
        child.kill.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=5)
        self.assertFalse(result["ack_sent"])


if __name__ == '__main__':
    unittest.main()
