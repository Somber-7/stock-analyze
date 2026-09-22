from fastapi import FastAPI
from fastapi.testclient import TestClient
import unittest
import tempfile
from pathlib import Path
from test_live_service import FakeBroker
from backend.trading.live import TradingService
from backend.trading.paper import PaperEngine
from backend.trading.api import router, get_service


class LiveApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.broker = FakeBroker()
        self.service = TradingService(base/'live.db', PaperEngine(base/'paper.db', lambda _: {'price': 1}), self.broker)

    def version(self): return self.service.snapshot()['version']

    def configure(self):
        self.service.configure(mode='live', account='12345678', expected_version=self.version())
        self.service.start(self.version())
    def test_live_route_requires_mode_version_and_uses_saved_account(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_service] = lambda: self.service
        with TestClient(app) as client:
            body = dict(client_id='api', code='005930', side='buy', quantity=1, price=10000)
            self.assertEqual(client.post('/api/trading/orders', json=body).status_code, 422)
            self.configure()
            headers = {'X-Trading-Mode': 'live', 'X-Trading-Version': str(self.version())}
            self.assertEqual(client.post('/api/trading/orders', headers=headers, json={**body, 'account': 'other'}).status_code, 422)
            self.assertEqual(client.post('/api/trading/orders', headers=headers, json=body).status_code, 200)
            self.assertEqual(self.broker.sent[0][1], '12345678')
            self.assertEqual(client.post('/api/trading/control', headers=headers, json={'action': 'pause'}).status_code, 200)
            self.assertEqual(client.post('/api/trading/orders', headers=headers, json={**body, 'client_id': 'stale'}).status_code, 400)

    def test_live_settings_need_explicit_user_acknowledgement(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_service] = lambda: self.service
        with TestClient(app) as client:
            response = client.post('/api/trading/settings', headers={'X-Trading-Version': str(self.version())},
                json={'mode': 'live', 'account': '12345678'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.service.snapshot()['mode'], 'paper')

    def test_alphanumeric_code_reaches_broker_unchanged_and_bad_codes_stay_blocked(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_service] = lambda: self.service
        self.configure()
        headers = {'X-Trading-Mode': 'live', 'X-Trading-Version': str(self.version())}
        body = dict(client_id='chaevi', code='0011T0', side='buy', quantity=1, price=5310)
        with TestClient(app) as client:
            for bad in ('0011T', '0011T00', '0011/0', '００１１Ｔ０'):
                self.assertEqual(client.post('/api/trading/orders', headers=headers,
                    json={**body, 'code': bad}).status_code, 422)
            response = client.post('/api/trading/orders', headers=headers, json=body)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.broker.sent[0][2]['code'], '0011T0')
            response = client.post('/api/trading/rules', headers=headers,
                json={**body, 'client_id': 'chaevi-rule', 'comparison': 'lte', 'threshold': 1})
            self.assertEqual(response.status_code, 200, response.text)
