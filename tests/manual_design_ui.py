"""Isolated design preview. All prices, balances and orders below are fixtures."""
import sys
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
import backend.main as main
from backend.namuh import stocks
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
from manual_live_ui import UiBroker

SYMBOLS = [('005930', '삼성전자', 71200), ('000660', 'SK하이닉스', 188500),
           ('0011T0', '채비', 5120), ('005380', '현대차', 241500), ('035420', 'NAVER', 178300)]
NOW = datetime.now(timezone.utc).isoformat()


def quote(code):
    _, name, price = next((s for s in SYMBOLS if s[0] == code), SYMBOLS[0])
    return dict(code=code, name=name, price=price, change=price*.0132, change_rate=1.32,
                volume=1829400, open=price*.99, high=price*1.01, low=price*.98,
                w52_high=price*1.3, w52_low=price*.8, market_cap=4252000, per='15.2', pbr='1.3', eps='4684')


def chart(code, **_):
    price = quote(code)['price']
    rows = []
    for i in range(200):
        day = datetime(2025, 12, 1) + timedelta(days=i)
        if day.weekday() > 4: continue
        value = round(price*(.9+i*.0005+.02*math.sin(i*.4)))
        rows.append(dict(time=day.strftime('%Y-%m-%d'), open=value, high=value+900,
                         low=value-800, close=value+round(600*math.sin(i)), volume=1000000))
    return rows


class DesignBroker(UiBroker):
    def quote(self, code): return quote(code)
    def accounts(self): return [{'id': '12345678', 'label': '디자인 검증용 가상 계좌 ****5678'}]
    def balance(self, account):
        holdings = []
        for i, (code, name, price) in enumerate(SYMBOLS[:3]):
            qty = [100, 30, 200][i]
            cost = [69000, 192000, 4900][i]
            holdings.append(dict(id=code, code=code, name=name, holding_type='현금',
                quantity=qty, avg_price=cost, current_price=price, eval_amount=qty*price,
                profit_loss=(price-cost)*qty, profit_rate=(price-cost)/cost*100))
        total = sum(p['eval_amount'] for p in holdings)
        cost = sum(p['avg_price']*p['quantity'] for p in holdings)
        return dict(holdings=holdings, summary=dict(total_eval=total, total_purchase=cost,
            total_profit_loss=total-cost, total_profit_rate=(total-cost)/cost*100, cash=3842000))


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='stock-design-qa-') as directory:
        base = Path(directory)
        broker = DesignBroker()
        paper = PaperEngine(base/'paper.db', quote)
        paper.submit(client_id='preview', code='005930', side='buy', quantity=2, limit_price=70000)
        paper.add_rule(client_id='preview-rule', code='0011T0', side='buy', quantity=10,
                       limit_price=5000, comparison='lte', threshold=5000)
        service = TradingService(base/'live.db', paper, broker)
        ai = AISettings(base/'ai.enc', fetch_models=lambda provider, key: [dict(id=m, name=m) for m in
            {'openai':['gpt-5.6-terra','gpt-5.6-sol'], 'anthropic':['claude-sonnet-5'], 'gemini':['gemini-3.8-flash']}[provider]])
        main.app.dependency_overrides[get_ai_settings] = lambda: ai
        operation = AIOperation(base/'ai-operation.db', ai, service)
        main.get_operation = lambda: operation
        main.app.dependency_overrides[get_operation] = lambda: operation
        watch = WatchService(base/'watch.db', quote, lambda code: next((dict(code=c, name=n) for c,n,p in SYMBOLS if c == code), None))
        watch.session_open = lambda: True
        for code, name, price in SYMBOLS[:3]: watch.add(code)
        watch.add_alert('005930', 'gte', 75000, 'preview-alert')
        watch.add_alert('0011T0', 'lte', 4900, 'preview-alert-2')
        main.get_watch = lambda: watch
        main.app.dependency_overrides[get_watch] = lambda: watch
        main.get_investors = lambda code: dict(code=code, source='나무증권 · KRX (화면 검증용 자료)', unit=None,
            unit_label='제공 수량 · 원본값', data_date='2026-09-11', fetched_at=NOW,
            summary=dict(date='2026-09-11', personal=3643746, institutional=-2208594, foreign=-3550438),
            rows=[dict(date=f'2026-09-{11-i:02d}', personal=3643746-i*912300,
                       institutional=-2208594+i*701500, foreign=-3550438+i*901200) for i in range(5)],
            notes=['API가 제공하지 않은 값은 —로 표시합니다.'])
        main.ensure_fresh = stocks.ensure_fresh = lambda **_: None
        main.get_accounts = broker.accounts
        main.get_balance = lambda account='': broker.balance(account)
        main.get_current_price = quote
        main.get_daily_chart = chart
        main.get_minute_chart = chart
        main.get_quote = lambda code: dict(price={'DJI':42025.2, 'SPY':574.38, 'QQQ':486.32,
            'SOXX':224.87, 'NVDA':128.42, 'AMD':156.71, 'MU':94.35}[code], change=1.23,
            change_rate=1.08, unit='pt' if code=='DJI' else 'USD', data_date='20260910', fetched_at=NOW)
        main.get_top100 = lambda: dict(rows=[dict(code=code, name=name, rank=i+1, market='KOSPI',
            previous_market_cap=4252000//(i+1), previous_close=price-100,
            quote=dict(price=price, change_rate=[1.32,-.74,2.54,.52,-1.25][i], retrieved_at=NOW))
            for i, (code,name,price) in enumerate(SYMBOLS)], downloaded_at=NOW,
            next_refresh_seconds=15, refreshing=False, loading=False)
        main.get_engine = lambda: paper
        main.get_service = lambda: service
        main.app.dependency_overrides[get_engine] = lambda: paper
        main.app.dependency_overrides[get_service] = lambda: service
        uvicorn.run(main.app, host='127.0.0.1', port=64566, log_level='warning')
