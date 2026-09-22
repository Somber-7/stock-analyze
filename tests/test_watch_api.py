import tempfile
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.watch.api import router, get_watch
from backend.watch.service import WatchService


class WatchApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = WatchService(Path(self.tmp.name)/'watch.db', lambda _: {'price': 5000},
                                    lambda code: dict(code=code, name='채비') if code == '0011T0' else None)
        self.service.session_open = lambda: True
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_watch] = lambda: self.service
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {'X-Watch-Action': 'manage'}

    def post(self, path, body): return self.client.post('/api/watch'+path, json=body, headers=self.headers)

    def test_mutation_guard_input_validation_and_missing_stock(self):
        self.assertEqual(self.client.post('/api/watch/items', json={'code': '0011T0'}).status_code, 422)
        for code in ('0011T', '0011/0', '００１１Ｔ０'):
            self.assertEqual(self.post('/items', {'code': code}).status_code, 422)
        self.assertEqual(self.post('/items', {'code': '999999'}).status_code, 400)
        body = dict(code='0011T0', comparison='gte', threshold=5000, client_id='test')
        self.assertEqual(self.post('/alerts', body).status_code, 400)
        self.assertEqual(self.post('/items', {'code': '0011T0'}).status_code, 200)
        for value in (True, '5000', 1.5, 0, -1):
            self.assertEqual(self.post('/alerts', {**body, 'threshold': value}).status_code, 422)
        self.assertEqual(self.post('/alerts', {**body, 'account': 'forbidden'}).status_code, 422)

    def test_duplicate_ack_and_removal_lifecycle(self):
        self.post('/items', {'code': '0011T0'})
        body = dict(code='0011T0', comparison='gte', threshold=5000, client_id='a')
        first = self.post('/alerts', body).json()
        self.assertEqual(self.post('/alerts', body).json()['id'], first['id'])
        self.assertEqual(self.post('/alerts', {**body, 'threshold': 6000}).status_code, 400)
        self.service.tick()
        self.assertEqual(len(self.client.get('/api/watch/notifications').json()), 1)
        self.assertEqual(self.post('/notifications/ack', {'ids': [first['id']]}).status_code, 200)
        self.assertEqual(self.client.get('/api/watch/notifications').json(), [])
        self.post('/alerts', {**body, 'client_id': 'b'})
        self.assertEqual(self.post('/items/0011T0/remove', {}).status_code, 200)
        state = self.client.get('/api/watch').json()
        self.assertEqual(state['items'], [])
        self.assertEqual({a['status'] for a in state['alerts']}, {'triggered', 'cancelled'})

    def test_notification_poll_does_not_keep_market_requests_active(self):
        before = self.service.last_viewed
        self.client.get('/api/watch/notifications')
        self.assertEqual(self.service.last_viewed, before)
        self.client.get('/api/watch')
        self.assertGreater(self.service.last_viewed, before)


if __name__ == '__main__': unittest.main()
