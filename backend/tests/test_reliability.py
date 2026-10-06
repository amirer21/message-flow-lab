import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

os.environ.setdefault('LAB_TOKEN', 'test-token')
os.environ.setdefault('RABBIT_PASSWORD', 'test-password')
from fastapi.testclient import TestClient
from app.main import app
from app.reliability import ReliabilityLab, ReliabilityPublishRequest


class ReliabilityAuthTests(unittest.TestCase):
    def test_unauthorized_requests_are_blocked(self):
        with patch('app.reliability.lab') as lab:
            client = TestClient(app)
            self.assertEqual(client.get('/reliability/snapshot').status_code, 401)
            self.assertEqual(client.post('/reliability/setup').status_code, 401)
            self.assertEqual(client.post('/reliability/publish', json={'body': 'x', 'scenario': 'normal'}).status_code, 401)
            self.assertEqual(client.post('/reliability/receive').status_code, 401)
            lab.call.assert_not_called()


class ReliabilityInputTests(unittest.TestCase):
    def test_invalid_scenario_is_rejected(self):
        client = TestClient(app)
        headers = {'X-Lab-Token': 'test-token'}
        with patch('app.reliability.lab'):
            response = client.post('/reliability/publish', json={'body': 'x', 'scenario': 'invalid'}, headers=headers)
            self.assertEqual(response.status_code, 422)

    def test_empty_body_is_rejected(self):
        client = TestClient(app)
        headers = {'X-Lab-Token': 'test-token'}
        with patch('app.reliability.lab'):
            response = client.post('/reliability/publish', json={'body': '', 'scenario': 'normal'}, headers=headers)
            self.assertEqual(response.status_code, 422)

    def test_too_long_body_is_rejected(self):
        client = TestClient(app)
        headers = {'X-Lab-Token': 'test-token'}
        with patch('app.reliability.lab'):
            response = client.post('/reliability/publish', json={'body': 'x' * 4097, 'scenario': 'normal'}, headers=headers)
            self.assertEqual(response.status_code, 422)


class ReliabilityLabTests(unittest.TestCase):
    def _make_channel(self):
        channel = MagicMock()
        channel.confirm_delivery.return_value = None
        channel.queue_declare.return_value.method.message_count = 0
        channel.connection.channel.return_value = channel
        return channel

    def test_confirm_and_return_are_separate_fields(self):
        """Confirm ACK and Return must not be merged into a single boolean."""
        lab = ReliabilityLab()
        channel = self._make_channel()
        lab.setup(channel)

        # Normal publish: confirmed=True, returned=False
        import pika.exceptions
        channel.basic_publish.return_value = None  # success in confirm mode
        req = ReliabilityPublishRequest(body='hello', scenario='normal')
        result = lab.publish(channel, req)
        self.assertTrue(result['confirmed'])
        self.assertFalse(result['returned'])
        self.assertFalse(result['nacked'])
        self.assertFalse(result['outcome_unknown'])

    def test_mandatory_unroutable_shows_both_confirm_and_return(self):
        """Unroutable mandatory message: confirmed=True AND returned=True."""
        lab = ReliabilityLab()
        channel = self._make_channel()
        lab.setup(channel)

        import pika.exceptions
        channel.basic_publish.side_effect = pika.exceptions.UnroutableError([MagicMock()])
        req = ReliabilityPublishRequest(body='hello', scenario='mandatory_unroutable')
        result = lab.publish(channel, req)
        self.assertTrue(result['confirmed'], "Unroutable message should still be confirmed")
        self.assertTrue(result['returned'], "Unroutable mandatory should be returned")
        self.assertFalse(result['nacked'])

    def test_nack_is_recorded_distinctly(self):
        lab = ReliabilityLab()
        channel = self._make_channel()
        lab.setup(channel)

        import pika.exceptions
        channel.basic_publish.side_effect = pika.exceptions.NackError([MagicMock()])
        req = ReliabilityPublishRequest(body='hello', scenario='normal')
        result = lab.publish(channel, req)
        self.assertFalse(result['confirmed'])
        self.assertTrue(result['nacked'])

    def test_connection_failure_is_not_success(self):
        """Connection failure must not be reported as confirmed."""
        lab = ReliabilityLab()
        channel = self._make_channel()
        lab.setup(channel)

        import pika.exceptions
        channel.basic_publish.side_effect = pika.exceptions.AMQPConnectionError()
        req = ReliabilityPublishRequest(body='hello', scenario='normal')
        result = lab.publish(channel, req)
        self.assertFalse(result['confirmed'])
        self.assertTrue(result['outcome_unknown'])
        self.assertFalse(result['nacked'])

    def test_delivery_mode_differs_by_scenario(self):
        lab = ReliabilityLab()
        channel = self._make_channel()
        lab.setup(channel)

        channel.basic_publish.return_value = None
        persistent = lab.publish(channel, ReliabilityPublishRequest(body='hi', scenario='persistent'))
        self.assertEqual(persistent['delivery_mode'], 2)

        transient = lab.publish(channel, ReliabilityPublishRequest(body='hi', scenario='transient'))
        self.assertEqual(transient['delivery_mode'], 1)

    def test_receive_records_actual_queue_copies(self):
        lab = ReliabilityLab()
        channel = self._make_channel()
        lab._queues = [
            {'id': 'a', 'name': 'test.a', 'binding': 'routed', 'durable': True, 'label': 'A'},
            {'id': 'b', 'name': 'test.b', 'binding': 'persistent', 'durable': True, 'label': 'B'},
            {'id': 'c', 'name': 'test.c', 'binding': 'transient', 'durable': False, 'label': 'C'},
        ]
        lab._exchange = 'phase4.test'
        props = SimpleNamespace(message_id='msg-1', delivery_mode=2)
        channel.basic_get.side_effect = [
            (SimpleNamespace(routing_key='routed', redelivered=False, delivery_tag=1), props,
             json.dumps({'body': 'hello', 'scenario': 'normal'}).encode()),
            (None, None, None),
            (None, None, None),
        ]
        received = lab.receive(channel)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['queue_id'], 'a')
        self.assertEqual(received[0]['message_id'], 'msg-1')
        self.assertEqual(channel.basic_ack.call_count, 1)

    def test_broker_failure_returns_503(self):
        with patch('app.reliability.lab.call', side_effect=RuntimeError('offline')):
            response = TestClient(app).get('/reliability/snapshot', headers={'X-Lab-Token': 'test-token'})
        self.assertEqual(response.status_code, 503)

    def test_publish_without_setup_raises(self):
        lab = ReliabilityLab()
        channel = self._make_channel()
        # _exchange is None before setup
        with self.assertRaises(ValueError):
            lab.publish(channel, ReliabilityPublishRequest(body='hi', scenario='normal'))
