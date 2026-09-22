"""Local UI QA only: all account/quote/order functions use a fake broker.

Run python tests/manual_live_ui.py; visit http://127.0.0.1:64565.
No real credentials are read by the fake broker and no real orders are sent.
"""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
import backend.main as main
from backend.trading.api import get_service
from backend.trading.routes import get_engine
from backend.trading.live import TradingService
from backend.trading.paper import PaperEngine
from backend.watch.service import WatchService
from backend.watch.api import get_watch
from backend.ai.api import get_ai_settings
from backend.ai.settings import AISettings
from backend.ai.operation import AIOperation
from backend.ai.operation_api import get_operation
from test_live_service import FakeBroker


class UiBroker(FakeBroker):
    def accounts(self): return [{'id': '12345678', 'label': '가짜 전송 테스트 ****5678'}]
    def balance(self, account):
        return {'summary': dict(cash=1000000, total_eval=0, total_purchase=0,
                                total_profit_loss=0, total_profit_rate=0), 'holdings': []}
    def send(self, kind, account, **kw):
        result = super().send(kind, account, **kw)
        old = next((r for r in self.rows if r['broker_id'] == kw.get('original')), None)
        if old:
            old.update(remaining=0, cancelled=old['remaining'])
        side = old['side'] if old else kind
        self.rows.append(dict(broker_id=result['broker_id'], original_id=kw.get('original') or '0',
            code=kw['code'], name='테스트 종목', side=side, side_name='현금매수' if side == 'buy' else '현금매도',
            quantity=kw['quantity'], price=kw.get('price', 0), filled=0, average_price=0,
            remaining=0 if kind == 'cancel' else kw['quantity'], cancelled=0,
            reason='확인' if kind == 'cancel' else '정상', market='KRX', split='N', order_type='보통'))
        return result


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='live-ui-qa-') as directory:
        base = Path(directory)
        broker = UiBroker()
        paper = PaperEngine(base/'paper.db', broker.quote)
        service = TradingService(base/'live.db', paper, broker)
        ai = AISettings(base/'ai.enc', fetch_models=lambda *_: [dict(id='gpt-test', name='테스트 모델')])
        main.app.dependency_overrides[get_ai_settings] = lambda: ai
        operation = AIOperation(base/'ai-operation.db', ai, service)
        main.get_operation = lambda: operation
        main.app.dependency_overrides[get_operation] = lambda: operation
        watch = WatchService(base/'watch.db', broker.quote, lambda code: dict(code=code, name='테스트 종목'))
        main.get_watch = lambda: watch
        main.app.dependency_overrides[get_watch] = lambda: watch
        service.session_open = lambda: True
        main.ensure_fresh = lambda: None
        main.get_accounts = broker.accounts
        main.get_balance = lambda account='': broker.balance(account)
        main.get_current_price = broker.quote
        main.get_engine = lambda: paper
        main.get_service = lambda: service
        main.app.dependency_overrides[get_engine] = lambda: paper
        main.app.dependency_overrides[get_service] = lambda: service
        uvicorn.run(main.app, host='127.0.0.1', port=64565, log_level='warning')
