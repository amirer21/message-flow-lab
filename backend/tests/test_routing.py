import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('LAB_TOKEN', 'test-token')
os.environ.setdefault('RABBIT_PASSWORD', 'test-password')
from fastapi.testclient import TestClient
from app.main import app
from app.routing import RoutingLab, RoutingPublishRequest, SetupRequest, topic_matches


class RoutingTests(unittest.TestCase):
    def test_topic_word_boundaries_and_zero_word_hash(self):
        for binding, key, expected in [('order.*','order.created',True), ('order.*','order.created.eu',False),
                ('order.#','order',True), ('#','',True), ('*.completed','payment.completed',True),
                ('*.completed','completed',False), ('#.completed','completed',True),
                ('a.#.b','a.x.y.b',True), ('a.#.b','a.b',True), ('a.#.b','a.x',False)]:
            with self.subTest(binding=binding,key=key):
                self.assertEqual(topic_matches(binding,key),expected)

    def test_unauthorized_actions_never_touch_broker(self):
        with patch('app.routing.lab') as lab:
            client=TestClient(app)
            self.assertEqual(client.get('/routing/snapshot').status_code,401)
            self.assertEqual(client.post('/routing/setup',json={'exchange_type':'direct','bindings':['a','b','c']}).status_code,401)
            self.assertEqual(client.post('/routing/receive',json={}).status_code,401)
            lab.call.assert_not_called()

    def test_invalid_topology_and_multibyte_keys_are_rejected(self):
        client=TestClient(app); headers={'X-Lab-Token':'test-token'}
        with patch('app.routing.lab') as lab:
            for payload in [{'exchange_type':'headers','bindings':['a','b','c']},
                {'exchange_type':'direct','bindings':['a']},
                {'exchange_type':'direct','bindings':['가'*86,'b','c']}]:
                self.assertEqual(client.post('/routing/setup',json=payload,headers=headers).status_code,422)
            self.assertEqual(client.post('/routing/messages',json={'body':'x','routing_key':'가'*86},headers=headers).status_code,422)
            lab.call.assert_not_called()

    def test_exchange_kind_cannot_change_through_binding_update(self):
        lab=RoutingLab()
        with self.assertRaises(ValueError):
            lab.handle(MagicMock(),'bindings',SetupRequest(exchange_type='topic',bindings=['#','#','#']))

    def test_receipts_are_actual_queue_copies_independent_of_prediction(self):
        lab=RoutingLab(); channel=MagicMock()
        lab._queues=[{'id':'a','name':'test.a','binding':'x'},{'id':'b','name':'test.b','binding':'x'}]
        props=SimpleNamespace(message_id='same-id')
        channel.basic_get.side_effect=[(SimpleNamespace(routing_key='x',redelivered=False,delivery_tag=1),props,json.dumps({'body':'hello','prediction':['c']}).encode()),
            (SimpleNamespace(routing_key='x',redelivered=False,delivery_tag=2),props,json.dumps({'body':'hello','prediction':['c']}).encode())]
        channel.queue_declare.return_value.method.message_count=0
        state=lab.handle(channel,'receive',None)
        self.assertEqual([copy['queue_id'] for copy in state['last_received']],['a','b'])
        self.assertEqual({copy['message_id'] for copy in state['last_received']},{'same-id'})
        self.assertEqual(channel.basic_ack.call_count,2)

    def test_broker_failure_is_not_a_success_snapshot(self):
        with patch('app.routing.lab.call',side_effect=RuntimeError('offline')):
            response=TestClient(app).get('/routing/snapshot',headers={'X-Lab-Token':'test-token'})
        self.assertEqual(response.status_code,503)

