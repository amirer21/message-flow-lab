import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('LAB_TOKEN', 'test-token')
os.environ.setdefault('RABBIT_PASSWORD', 'test-password')
from fastapi.testclient import TestClient
from app.main import app
from app.retry import RetryLab, RetryPublishRequest, MAX_RETRIES


class RetryAuthTests(unittest.TestCase):
    def test_unauthorized_requests_are_blocked(self):
        with patch('app.retry.lab') as lab:
            client = TestClient(app)
            self.assertEqual(client.get('/retry/snapshot').status_code, 401)
            self.assertEqual(client.post('/retry/setup').status_code, 401)
            self.assertEqual(client.post('/retry/publish', json={'body': 'x', 'scenario': 'transient_2x'}).status_code, 401)
            self.assertEqual(client.post('/retry/process').status_code, 401)
            lab.call.assert_not_called()


class RetryInputTests(unittest.TestCase):
    def test_invalid_scenario_is_rejected(self):
        client = TestClient(app)
        headers = {'X-Lab-Token': 'test-token'}
        with patch('app.retry.lab'):
            response = client.post('/retry/publish', json={'body': 'x', 'scenario': 'invalid'}, headers=headers)
            self.assertEqual(response.status_code, 422)

    def test_empty_body_is_rejected(self):
        client = TestClient(app)
        headers = {'X-Lab-Token': 'test-token'}
        with patch('app.retry.lab'):
            response = client.post('/retry/publish', json={'body': '', 'scenario': 'transient_2x'}, headers=headers)
            self.assertEqual(response.status_code, 422)

    def test_too_long_body_is_rejected(self):
        client = TestClient(app)
        headers = {'X-Lab-Token': 'test-token'}
        with patch('app.retry.lab'):
            response = client.post('/retry/publish', json={'body': 'x' * 4097, 'scenario': 'transient_2x'}, headers=headers)
            self.assertEqual(response.status_code, 422)


class RetryLabTests(unittest.TestCase):
    def _make_channel(self):
        channel = MagicMock()
        channel.confirm_delivery.return_value = None
        channel.queue_declare.return_value.method.message_count = 0
        channel.connection.channel.return_value = channel
        return channel

    def test_setup_creates_three_queues_and_three_exchanges(self):
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)
        self.assertIsNotNone(lab._work_exchange)
        self.assertIsNotNone(lab._retry_exchange)
        self.assertIsNotNone(lab._dead_exchange)
        self.assertEqual(len(lab._queues), 3)
        roles = {q['role'] for q in lab._queues}
        self.assertEqual(roles, {'work', 'retry', 'dead'})

    def test_publish_confirms_message(self):
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)
        channel.basic_publish.return_value = None
        req = RetryPublishRequest(body='hello', scenario='transient_2x')
        result = lab.publish(channel, req)
        self.assertTrue(result['confirmed'])
        self.assertEqual(result['scenario'], 'transient_2x')

    def test_publish_without_setup_raises(self):
        lab = RetryLab()
        channel = self._make_channel()
        with self.assertRaises(ValueError):
            lab.publish(channel, RetryPublishRequest(body='hi', scenario='transient_2x'))

    def test_transient_2x_fails_twice_then_succeeds(self):
        """transient_2x: retry_count<2 → retry, retry_count>=2 → success."""
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)

        # First attempt (retry_count=0) → retry
        self._setup_basic_get(channel, retry_count=0, scenario='transient_2x')
        result = lab.process(channel)
        self.assertEqual(result['outcome'], 'retry')
        self.assertEqual(result['retry_count'], 0)

        # Second attempt (retry_count=1) → retry
        self._setup_basic_get(channel, retry_count=1, scenario='transient_2x')
        result = lab.process(channel)
        self.assertEqual(result['outcome'], 'retry')

        # Third attempt (retry_count=2) → success
        self._setup_basic_get(channel, retry_count=2, scenario='transient_2x')
        result = lab.process(channel)
        self.assertEqual(result['outcome'], 'success')

    def test_permanent_goes_directly_to_dlq(self):
        """permanent: always DLQ regardless of retry_count."""
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)
        self._setup_basic_get(channel, retry_count=0, scenario='permanent')
        result = lab.process(channel)
        self.assertEqual(result['outcome'], 'dlq')

    def test_retry_exceed_goes_to_dlq_after_max(self):
        """retry_exceed: retries until MAX_RETRIES then DLQ."""
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)

        # Before max → retry
        self._setup_basic_get(channel, retry_count=MAX_RETRIES - 1, scenario='retry_exceed')
        result = lab.process(channel)
        self.assertEqual(result['outcome'], 'retry')

        # At max → dlq
        self._setup_basic_get(channel, retry_count=MAX_RETRIES, scenario='retry_exceed')
        result = lab.process(channel)
        self.assertEqual(result['outcome'], 'dlq')

    def test_retry_publishes_to_retry_exchange(self):
        """When outcome is retry, message is published to retry exchange."""
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)
        channel.basic_publish.return_value = None
        self._setup_basic_get(channel, retry_count=0, scenario='transient_2x')
        lab.process(channel)
        # Find the call to retry exchange
        calls = channel.basic_publish.call_args_list
        retry_call = [c for c in calls if c.kwargs.get('exchange', c.args[0] if c.args else '') == lab._retry_exchange
                      or (c[1].get('exchange') == lab._retry_exchange if isinstance(c[1], dict) else False)]
        # Check basic_publish was called with retry exchange
        found_retry = any(
            call.kwargs.get('exchange') == lab._retry_exchange
            for call in calls
        )
        self.assertTrue(found_retry, f"Expected publish to retry exchange {lab._retry_exchange}")

    def test_dlq_publishes_to_dead_exchange(self):
        """When outcome is dlq, message is published to dead exchange."""
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)
        channel.basic_publish.return_value = None
        self._setup_basic_get(channel, retry_count=0, scenario='permanent')
        lab.process(channel)
        calls = channel.basic_publish.call_args_list
        found_dead = any(
            call.kwargs.get('exchange') == lab._dead_exchange
            for call in calls
        )
        self.assertTrue(found_dead, f"Expected publish to dead exchange {lab._dead_exchange}")

    def test_original_message_is_always_acked(self):
        """Original message must be ACKed regardless of outcome."""
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)
        channel.basic_publish.return_value = None

        for scenario in ['transient_2x', 'permanent', 'retry_exceed']:
            channel.basic_ack.reset_mock()
            self._setup_basic_get(channel, retry_count=0, scenario=scenario)
            lab.process(channel)
            channel.basic_ack.assert_called()

    def test_x_death_header_triggers_retry_returned_event(self):
        """x-death header from DLX should record RETRY_RETURNED event."""
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)
        channel.basic_publish.return_value = None
        self._setup_basic_get(channel, retry_count=1, scenario='transient_2x',
                              x_death=[{"queue": "test", "count": 1}])
        lab.process(channel)
        event_types = [r['event_type'] for r in lab._records]
        self.assertIn('RETRY_RETURNED', event_types)

    def test_process_empty_queue_raises(self):
        lab = RetryLab()
        channel = self._make_channel()
        lab.setup(channel)
        channel.basic_get.return_value = (None, None, None)
        with self.assertRaises(ValueError):
            lab.process(channel)

    def test_broker_failure_returns_503(self):
        with patch('app.retry.lab.call', side_effect=RuntimeError('offline')):
            response = TestClient(app).get('/retry/snapshot', headers={'X-Lab-Token': 'test-token'})
        self.assertEqual(response.status_code, 503)

    def _setup_basic_get(self, channel, retry_count=0, scenario='transient_2x', x_death=None):
        headers = {'x-retry-count': retry_count, 'x-scenario': scenario}
        if x_death is not None:
            headers['x-death'] = x_death
        props = SimpleNamespace(
            message_id=f'msg-{retry_count}',
            correlation_id='corr-1',
            delivery_mode=2,
            headers=headers,
        )
        method = SimpleNamespace(routing_key='job', redelivered=False, delivery_tag=100 + retry_count)
        body = json.dumps({'body': 'test', 'scenario': scenario}).encode()
        channel.basic_get.return_value = (method, props, body)
