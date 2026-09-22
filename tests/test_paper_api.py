import tempfile
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.trading.paper import PaperEngine
from backend.trading.routes import router, get_engine


class PaperApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = PaperEngine(Path(self.tmp.name) / 'book.sqlite3', lambda _: {'price': 9000})
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_engine] = lambda: self.engine
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {'X-Paper-Mode': 'paper', 'X-Paper-Version': str(self.engine.snapshot()['version'])}
        self.order = dict(client_id='a', code='005930', side='buy', quantity=2, limit_price=10000)

    def test_only_explicit_paper_requests_accept_mutations(self):
        self.assertEqual(self.client.post('/api/paper/orders', json=self.order).status_code, 422)
        for extra in [{'mode': 'live'}, {'quantity': -1}, {'quantity': 1.5}, {'code': 'AAPL'}]:
            res = self.client.post('/api/paper/orders', json={**self.order, **extra}, headers=self.headers)
            self.assertEqual(res.status_code, 422)
        self.assertEqual(self.engine.snapshot()['orders'], [])

    def test_order_actions_and_stop_preserve_readable_book(self):
        res = self.client.post('/api/paper/orders', json=self.order, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        order_id = res.json()['id']
        res = self.client.post('/api/paper/orders/' + order_id + '/modify',
                               json={'limit_price': 8000}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.client.post('/api/paper/control', json={'action': 'start'}, headers=self.headers)
        self.engine.tick()
        self.client.post('/api/paper/control', json={'action': 'emergency'}, headers=self.headers)
        state = self.client.get('/api/paper').json()
        self.assertFalse(state['running'])
        self.assertEqual(state['orders'][0]['status'], 'cancelled')
        self.assertEqual(state['available_cash'], 10000000)

    def test_insufficient_position_is_client_error_not_server_failure(self):
        res = self.client.post('/api/paper/orders', json={**self.order, 'side': 'sell'}, headers=self.headers)
        self.assertEqual(res.status_code, 400)
        self.assertTrue(res.json()['detail'])
