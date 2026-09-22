"""Transactional paper book, independent of account and broker order APIs."""
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone

ACTIVE = ('pending', 'partial')
INITIAL_CASH = 10_000_000
MAX_SYMBOLS = 10
FILL_PER_TICK = 10


class PaperError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def positive_integer(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0 and value == int(value))


def validate(client_id, code, side, quantity, limit_price):
    if not isinstance(client_id, str) or not 1 <= len(client_id) <= 100:
        raise PaperError('주문 요청 식별자가 필요합니다.')
    if not isinstance(code, str) or not re.fullmatch(r'[0-9A-Z]{6}', code):
        raise PaperError('국내 종목코드 6자리를 입력하세요.')
    if side not in ('buy', 'sell') or not positive_integer(quantity) or not positive_integer(limit_price):
        raise PaperError('매수·매도 구분과 양의 정수 수량·가격을 확인하세요.')


def remaining(order):
    return order['quantity'] - order['filled']


def reserved(state, code=None):
    return sum(remaining(o) * o['limit_price'] for o in state['orders']
               if o['status'] in ACTIVE and o['side'] == 'buy'
               and (code is None or o['code'] == code))


def symbols(state):
    return {o['code'] for o in state['orders'] if o['status'] in ACTIVE} | {
        r['code'] for r in state['rules'] if r['status'] == 'armed'}


def visible_history(items, active):
    recent = list(reversed(items))
    return [item for item in recent if item['status'] in active] + [
        item for item in recent if item['status'] not in active][:200]


class PaperEngine:
    def __init__(self, path, quote):
        self.path = str(path)
        self.quote = quote
        self.lock = threading.RLock()
        self.tick_lock = threading.Lock()
        self.running = False
        self.enabled = lambda: True
        self.generation = 0
        self.quotes = {}
        self.last_cycle = None
        self.worker_error = ''
        self.shutdown = threading.Event()
        self.worker = None
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS book (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            state = dict(cash=INITIAL_CASH, realized_pnl=0, positions={}, orders=[], rules=[], events=[])
            db.execute('INSERT OR IGNORE INTO book VALUES (1, ?)', (json.dumps(state),))
            state = json.loads(db.execute('SELECT data FROM book WHERE id=1').fetchone()[0])
            state['version'] = state.get('version', 0) + 1
            db.execute('UPDATE book SET data=? WHERE id=1', (json.dumps(state),))
        # Invalid data fails visibly; never silently replace an existing book.
        self.snapshot()

    @contextmanager
    def change(self):
        with self.lock, closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = json.loads(db.execute('SELECT data FROM book WHERE id=1').fetchone()[0])
            yield state
            db.execute('UPDATE book SET data=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))

    def event(self, state, message):
        state['events'].append(dict(at=now(), message=message))
        state['events'] = state['events'][-1000:]

    def check_version(self, state, expected):
        if not self.enabled():
            raise PaperError('현재 실전 모드입니다. 모의매매는 설정에서 모의 모드로 전환한 뒤 사용하세요.')
        if expected is not None and state['version'] != expected:
            raise PaperError('정지 또는 재실행으로 상태가 바뀌었습니다. 최신 상태를 확인한 뒤 다시 요청하세요.')

    def snapshot(self):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            state = json.loads(db.execute('SELECT data FROM book WHERE id=1').fetchone()[0])
            reserve = reserved(state)
            positions = []
            for code, p in state['positions'].items():
                sells = sum(remaining(o) for o in state['orders'] if o['code'] == code
                            and o['side'] == 'sell' and o['status'] in ACTIVE)
                positions.append(dict(code=code, **p, available=p['quantity'] - sells,
                                      average_price=p['cost'] / p['quantity']))
            return dict(mode='paper', version=state['version'], running=self.running, cash=state['cash'],
                        available_cash=state['cash'] - reserve, reserved_cash=reserve,
                        realized_pnl=state['realized_pnl'], positions=positions,
                        orders=visible_history(state['orders'], ACTIVE),
                        rules=visible_history(state['rules'], ('armed',)),
                        events=list(reversed(state['events']))[:100],
                        quotes=json.loads(json.dumps(self.quotes)), last_cycle=self.last_cycle,
                        error=self.worker_error,
                        limits=dict(initial_cash=INITIAL_CASH, symbols=MAX_SYMBOLS,
                                    fill_per_tick=FILL_PER_TICK, interval_seconds=10))

    def check_funds(self, state, order):
        qty = remaining(order)
        code = order['code']
        position = state['positions'].get(code, {'quantity': 0, 'cost': 0})
        if order['side'] == 'buy':
            required = qty * order['limit_price']
            if required > state['cash'] - reserved(state):
                raise PaperError('가상 주문 가능 현금이 부족합니다.')
        else:
            booked = sum(remaining(o) for o in state['orders'] if o['code'] == code
                         and o['side'] == 'sell' and o['status'] in ACTIVE)
            if qty > position['quantity'] - booked:
                raise PaperError('매도 가능한 가상 보유 수량이 부족합니다.')

    def create_order(self, state, client_id, code, side, quantity, limit_price):
        validate(client_id, code, side, quantity, limit_price)
        request = dict(code=code, side=side, quantity=int(quantity), limit_price=int(limit_price))
        for order in state['orders']:
            if order['client_id'] == client_id:
                if order['request'] != request:
                    raise PaperError('같은 요청 식별자로 다른 주문을 등록할 수 없습니다.')
                return order
        if len(symbols(state) | {code}) > MAX_SYMBOLS:
            raise PaperError('동시에 감시할 종목은 최대 10개입니다.')
        order = dict(id=uuid.uuid4().hex, client_id=client_id, request=request,
                     **request, filled=0, fill_value=0, status='pending', created_at=now(),
                     updated_at=now(), source='manual')
        self.check_funds(state, order)
        state['orders'].append(order)
        self.event(state, f'{code} 모의 {"매수" if side == "buy" else "매도"} {quantity}주 접수')
        return order

    def submit(self, *, client_id, code, side, quantity, limit_price, expected_version=None, preflight=None):
        if isinstance(client_id, str) and client_id.startswith('rule:'):
            raise PaperError('조건 주문의 내부 식별자는 수동 주문에 사용할 수 없습니다.')
        with self.change() as state:
            self.check_version(state, expected_version)
            if preflight is not None: preflight()
            return self.create_order(state, client_id, code, side, quantity, limit_price)

    def find_order(self, state, order_id):
        for order in state['orders']:
            if order['id'] == order_id:
                return order
        raise PaperError('주문을 찾을 수 없습니다.')

    def cancel(self, order_id, expected_version=None):
        with self.change() as state:
            self.check_version(state, expected_version)
            order = self.find_order(state, order_id)
            if order['status'] in ACTIVE:
                order.update(status='cancelled', updated_at=now())
                self.event(state, f'{order["code"]} 미체결 {remaining(order)}주 취소')
            return order

    def modify(self, order_id, limit_price, expected_version=None):
        with self.change() as state:
            self.check_version(state, expected_version)
            order = self.find_order(state, order_id)
            if order['status'] not in ACTIVE:
                raise PaperError('미체결 잔량이 있는 주문만 정정할 수 있습니다.')
            validate(order['client_id'], order['code'], order['side'], remaining(order), limit_price)
            old_status = order['status']
            order.update(status='amending', limit_price=int(limit_price))
            self.check_funds(state, order)
            order.update(status=old_status, updated_at=now())
            # Price amendments lose queue priority, preserving already filled quantity.
            state['orders'].remove(order)
            state['orders'].append(order)
            self.event(state, f'{order["code"]} 잔량 지정가 {int(limit_price):,}원 정정')
            return order

    def add_rule(self, *, client_id, code, side, quantity, limit_price, comparison, threshold, expected_version=None):
        validate(client_id, code, side, quantity, limit_price)
        if comparison not in ('gte', 'lte') or not positive_integer(threshold):
            raise PaperError('가격 조건을 확인하세요.')
        request = dict(code=code, side=side, quantity=int(quantity), limit_price=int(limit_price),
                       comparison=comparison, threshold=int(threshold))
        with self.change() as state:
            self.check_version(state, expected_version)
            for rule in state['rules']:
                if rule['client_id'] == client_id:
                    if rule['request'] != request:
                        raise PaperError('같은 요청 식별자의 조건 내용이 다릅니다.')
                    return rule
            if len(symbols(state) | {code}) > MAX_SYMBOLS or sum(r['status'] == 'armed' for r in state['rules']) >= 10:
                raise PaperError('대기 조건과 감시 종목은 최대 10개입니다.')
            rule = dict(id=uuid.uuid4().hex, client_id=client_id, request=request, **request,
                        status='armed', created_at=now(), message='', order_id=None)
            state['rules'].append(rule)
            self.event(state, f'{code} 일회성 가격 조건 등록 (주문 시 잔고 확인)')
            return rule

    def cancel_rule(self, rule_id, expected_version=None):
        with self.change() as state:
            self.check_version(state, expected_version)
            for rule in state['rules']:
                if rule['id'] == rule_id:
                    if rule['status'] == 'armed':
                        rule['status'] = 'cancelled'
                        self.event(state, f'{rule["code"]} 가격 조건 해제')
                    return rule
            raise PaperError('조건을 찾을 수 없습니다.')

    def start(self, expected_version=None):
        with self.lock:
            with self.change() as state:
                self.check_version(state, expected_version)
            if not self.running:
                with self.change() as state:
                    self.event(state, '모의 실행 시작')
                self.running = True
                self.generation += 1

    def stop(self, emergency=False, expected_version=None):
        with self.lock:
            with self.change() as state:
                if not emergency and expected_version is not None:
                    self.check_version(state, expected_version)
                self.running = False
                self.generation += 1
                state['version'] += 1
                if emergency:
                    for o in state['orders']:
                        if o['status'] in ACTIVE:
                            o.update(status='cancelled', updated_at=now())
                    for r in state['rules']:
                        if r['status'] == 'armed':
                            r['status'] = 'cancelled'
                self.event(state, '긴급정지: 미체결 취소·대기 조건 해제' if emergency else '모의 실행 일시정지')

    def apply_price(self, state, code, price, name):
        for rule in state['rules']:
            if rule['status'] != 'armed' or rule['code'] != code:
                continue
            matched = price >= rule['threshold'] if rule['comparison'] == 'gte' else price <= rule['threshold']
            if not matched:
                continue
            try:
                o = self.create_order(state, 'rule:' + rule['id'], code, rule['side'],
                                      rule['quantity'], rule['limit_price'])
                o['source'] = 'rule'
                rule.update(status='fired', order_id=o['id'], message='조건 충족·모의 주문 접수')
            except PaperError as exc:
                rule.update(status='rejected', message=str(exc))
            self.event(state, f'{code} 조건 판단: {rule["message"]}')
        capacity = FILL_PER_TICK
        for order in state['orders']:
            if order['code'] != code or order['status'] not in ACTIVE or capacity <= 0:
                continue
            if (order['side'] == 'buy' and price > order['limit_price']) or (
                    order['side'] == 'sell' and price < order['limit_price']):
                continue
            qty = min(remaining(order), capacity)
            value = qty * price
            if order['side'] == 'buy':
                p = state['positions'].setdefault(code, dict(quantity=0, cost=0, name=name))
                p['quantity'] += qty
                p['cost'] += value
                state['cash'] -= value
            else:
                p = state['positions'][code]
                # Integer KRW cost allocation keeps cash and realized P/L exact.
                cost = p['cost'] if qty == p['quantity'] else p['cost'] * qty // p['quantity']
                p['cost'] -= cost
                p['quantity'] -= qty
                state['cash'] += value
                state['realized_pnl'] += value - cost
                if not p['quantity']:
                    del state['positions'][code]
            order['filled'] += qty
            order['fill_value'] += value
            order.update(status='filled' if not remaining(order) else 'partial', updated_at=now())
            capacity -= qty
            self.event(state, f'{code} 모의 {"매수" if order["side"] == "buy" else "매도"} {qty}주 × {price:,}원 체결')

    def tick(self):
        if not self.tick_lock.acquire(blocking=False):
            return
        try:
            with self.lock:
                if not self.running or not self.enabled():
                    return
                epoch = self.generation
                with closing(sqlite3.connect(self.path)) as db:
                    state = json.loads(db.execute('SELECT data FROM book WHERE id=1').fetchone()[0])
                codes = sorted(symbols(state))
            for code in codes:
                with self.lock:
                    if not self.running or not self.enabled() or self.generation != epoch:
                        return
                began = time.monotonic()
                try:
                    quote = self.quote(code)
                    price = quote.get('price')
                    if not positive_integer(price) or time.monotonic() - began > 30:
                        raise PaperError('시세 값 또는 응답 시간이 유효하지 않습니다.')
                    failure = ''
                except Exception:
                    failure = '시세 조회 실패·지연: 이번 주기 체결을 건너뜁니다.'
                with self.lock:
                    if not self.running or not self.enabled() or self.generation != epoch:
                        return
                    if failure:
                        self.quotes[code] = dict(error=failure, checked_at=now())
                        continue
                    with self.change() as state:
                        self.apply_price(state, code, int(price), str(quote.get('name') or code))
                    self.quotes[code] = dict(price=int(price), name=quote.get('name', code),
                                             checked_at=now(), error='')
            with self.lock:
                self.last_cycle = now()
                self.worker_error = ''
        finally:
            self.tick_lock.release()

    def launch(self):
        if self.worker and self.worker.is_alive():
            return
        self.shutdown.clear()
        def loop():
            while not self.shutdown.is_set():
                try:
                    self.tick()
                except Exception:
                    with self.lock:
                        self.running = False
                        self.generation += 1
                        self.worker_error = '모의 기록 처리 오류로 정지했습니다. 기록 파일과 저장 공간을 확인하세요.'
                self.shutdown.wait(10)
        self.worker = threading.Thread(target=loop, daemon=True, name='paper-quotes')
        self.worker.start()

    def close(self):
        with self.lock:
            self.running = False
            self.generation += 1
            self.shutdown.set()
