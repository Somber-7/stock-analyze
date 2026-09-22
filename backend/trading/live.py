"""Durable live-order outbox and mode coordinator. Never retries unknown sends."""
import json
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from contextlib import closing, contextmanager

from backend.namuh.client import NamuhError, NamuhRejected
from backend.namuh.orders import korea_today
from .paper import now, positive_integer


class TradingError(ValueError):
    pass


def regular_session():
    local = datetime.now(timezone(timedelta(hours=9)))
    return local.weekday() < 5 and '0900' <= local.strftime('%H%M') < '1520'


class TradingService:
    def __init__(self, path, paper, gateway):
        self.path, self.paper, self.gateway = str(path), paper, gateway
        self.lock = threading.RLock()
        self.operation_lock = threading.Lock()
        self.halted = threading.Event()
        self.halted.set()
        self.closed = threading.Event()
        self.worker = None
        self.session_open = regular_session
        self.emergency_active = threading.Event()
        self.emergency_lock = threading.Lock()
        self.emergency_result = None
        self.error = ''
        self.quotes = {}
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS trading (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            initial = dict(mode='paper', account='',
                           version=0, operations=[], rules=[])
            db.execute('INSERT OR IGNORE INTO trading VALUES (1, ?)', (json.dumps(initial),))
        with self.change() as state:
            state.pop('order_limit', None)
            state.pop('daily_limit', None)
            state['version'] += 1
            for op in state['operations']:
                if op['status'] == 'sending':
                    op.update(status='unknown', message='재시작 전 전송 결과를 확인해야 합니다.')
            for rule in state['rules']:
                if rule['status'] == 'executing':
                    rule.update(status='review', message='중단된 조건 실행의 전송 기록을 확인하세요.')
            self.mode = state['mode']
        self.paper.enabled = lambda: self.mode == 'paper'
        self.paper.stop()

    @contextmanager
    def change(self):
        with self.lock, closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = json.loads(db.execute('SELECT data FROM trading WHERE id=1').fetchone()[0])
            yield state
            db.execute('UPDATE trading SET data=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))

    def read(self):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            return json.loads(db.execute('SELECT data FROM trading WHERE id=1').fetchone()[0])

    def used(self, state):
        return sum(o['budget'] for o in state['operations'] if o['day'] == korea_today()
                   and o['account'] == state['account'] and o['status'] != 'rejected')

    def snapshot(self):
        state = self.read()
        ops = list(reversed(state['operations']))
        state['operations'] = [o for o in ops if o['status'] in ('sending', 'unknown')] + [
            o for o in ops if o['status'] not in ('sending', 'unknown')][:200]
        rules = list(reversed(state['rules']))
        state['rules'] = [r for r in rules if r['status'] in ('armed', 'executing')] + [
            r for r in rules if r['status'] not in ('armed', 'executing')][:200]
        state.update(daily_used=self.used(self.read()), running=not self.halted.is_set(),
                     error=self.error, quotes=dict(self.quotes), emergency_result=self.emergency_result,
                     emergency_active=self.emergency_active.is_set(), session_open=self.session_open())
        return state

    def check(self, state, expected, *, running=False):
        if state['version'] != expected:
            raise TradingError('설정·정지 상태가 변경되었습니다. 최신 화면에서 다시 요청하세요.')
        if state['mode'] != 'live' or not state['account']:
            raise TradingError('설정에서 실전 모드와 사용할 계좌를 선택하세요.')
        if running and self.halted.is_set():
            raise TradingError('실전 주문이 잠겨 있습니다. 실전 실행 시작을 먼저 누르세요.')

    def validate_order(self, code, side, quantity, price, client_id):
        if not re.fullmatch(r'[0-9A-Z]{6}', str(code)) or side not in ('buy', 'sell'):
            raise TradingError('국내 종목코드와 매매 구분을 확인하세요.')
        if not positive_integer(quantity) or not positive_integer(price):
            raise TradingError('수량과 지정가는 양의 정수여야 합니다.')
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 100:
            raise TradingError('요청 식별자가 필요합니다.')

    def configure(self, *, mode, account, expected_version):
        if self.emergency_active.is_set(): raise TradingError('긴급 취소 처리 중입니다.')
        if mode not in ('paper', 'live'):
            raise TradingError('설정 값을 확인하세요.')
        if not self.operation_lock.acquire(blocking=False):
            raise TradingError('진행 중인 주문 처리가 끝난 뒤 설정을 변경하세요.')
        try:
            before = self.read()
            if before['version'] != expected_version:
                raise TradingError('설정이 바뀌었습니다. 새로고침 후 다시 저장하세요.')
            if account and account not in {a['id'] for a in self.gateway.accounts()}:
                raise TradingError('API에 등록된 실계좌를 선택하세요.')
            if mode == 'live' and not account:
                raise TradingError('실전 모드에는 계좌 선택이 필요합니다.')
            changing = before['mode'] != mode or before['account'] != account
            if changing and any(o['status'] in ('sending', 'unknown') for o in before['operations']):
                raise TradingError('결과 확인이 필요한 전송 기록부터 확인하세요.')
            if changing and before['mode'] == 'live' and before['account']:
                if any(r['remaining'] > 0 and r.get('reason') == '정상'
                       for r in self.gateway.history(before['account'], korea_today())):
                    raise TradingError('현재 계좌의 미체결 주문을 정리한 뒤 모드·계좌를 변경하세요.')
            with self.change() as state:
                if state['version'] != expected_version:
                    raise TradingError('상태가 바뀌었습니다. 다시 저장하세요.')
                self.halted.set()
                self.paper.stop()
                state.update(mode=mode, account=account)
                state['version'] += 1
                if changing:
                    for rule in state['rules']:
                        if rule['status'] == 'armed': rule['status'] = 'cancelled'
                self.mode = mode
            return self.snapshot()
        finally:
            self.operation_lock.release()

    def start(self, expected_version):
        with self.change() as state:
            if self.emergency_active.is_set(): raise TradingError('긴급 취소 처리 중입니다.')
            self.check(state, expected_version)
            if any(o['status'] in ('sending', 'unknown') for o in state['operations']):
                raise TradingError('결과가 불확실한 주문을 확인한 뒤 실행하세요.')
            self.halted.clear()
            self.error = ''
        return self.snapshot()

    def stop(self):
        # Set immediately, even if an already dispatched broker call holds the lock.
        self.halted.set()
        with self.change() as state:
            self.halted.set()
            state['version'] += 1
        return self.snapshot()

    def refresh(self, day=None):
        state = self.read()
        if not state['account']:
            raise TradingError('설정에서 계좌를 선택하세요.')
        day = day or korea_today()
        rows = self.gateway.history(state['account'], day)
        balance = self.gateway.balance(state['account'])
        return dict(day=day, account=state['account'], rows=rows, balance=balance, checked_at=now())

    def capacity(self, code, side, price):
        state = self.read()
        if not state['account']: raise TradingError('계좌를 선택하세요.')
        self.validate_order(code, side, 1, price, 'capacity')
        return self.gateway.capacity(state['account'], code, side, price)

    def prior(self, state, key, request):
        for op in state['operations']:
            if op['client_id'] == key:
                if op['request'] != request:
                    raise TradingError('같은 식별자로 다른 주문을 보낼 수 없습니다.')
                return op

    def dispatch(self, kind, key, request, account, expected, budget=0, rule_deadline=None, order_day=None, preflight=None):
        # operation_lock serializes capacity checks and submits. lock bridges the last
        # version check and single network send. A committed 'sending' record precedes it.
        with self.lock:
            with self.change() as state:
                self.check(state, expected, running=kind != 'cancel')
                previous = self.prior(state, key, request)
                if previous: return previous
                if any(o['status'] in ('sending', 'unknown') for o in state['operations']) and kind != 'cancel':
                    raise TradingError('결과가 불확실한 주문이 있습니다. 먼저 접수 여부를 확인하세요.')
                op = dict(id=uuid.uuid4().hex, client_id=key, request=request, account=account,
                          kind=kind, code=request['code'], quantity=request['quantity'], price=request.get('price', 0),
                          original=request.get('original'), day=korea_today(), created_at=now(),
                          status='sending', broker_id=None, budget=budget, message='전송 중')
                state['operations'].append(op)
            try:
                def before_send():
                    if preflight is not None: preflight()
                    if op['day'] != korea_today():
                        raise NamuhRejected('날짜가 변경되어 주문을 보내지 않았습니다. 새로 확인하세요.')
                    if kind != 'cancel' and self.halted.is_set():
                        raise NamuhRejected('전송 직전 실행이 중단되어 주문을 보내지 않았습니다.')
                    if rule_deadline is not None and (not self.session_open() or time.monotonic() > rule_deadline):
                        raise NamuhRejected('조건 확인 시간이 지나 주문을 보내지 않았습니다.')
                    if order_day is not None and order_day != korea_today():
                        raise NamuhRejected('주문 날짜가 바뀌어 정정·취소를 보내지 않았습니다.')
                result = self.gateway.send(kind, account, before_send=before_send,
                    **{k: v for k, v in request.items() if k not in ('kind', 'order_day')})
                status, message = 'accepted', '증권사 접수 완료 · 체결은 주문 내역에서 확인'
            except NamuhRejected as exc:
                result, status, message = {}, 'rejected', str(exc)
            except NamuhError as exc:
                result, status, message = {}, 'unknown', str(exc) + ' 접수 여부 확인 전 재전송하지 않습니다.'
                self.halted.set()
            except Exception:
                result, status, message = {}, 'unknown', '전송 결과 불확실 · 자동 재전송하지 않습니다. 증권사 주문 내역을 확인하세요.'
                self.halted.set()
            with self.change() as state:
                stored = next(o for o in state['operations'] if o['id'] == op['id'])
                stored.update(result, status=status, message=message, updated_at=now())
                return dict(stored)

    def order(self, *, client_id, code, side, quantity, price, expected_version, internal=False, rule_deadline=None, preflight=None, prepare=None):
        self.validate_order(code, side, quantity, price, client_id)
        if client_id.startswith('rule:') and not internal:
            raise TradingError('내부 조건 주문 식별자는 사용할 수 없습니다.')
        request = dict(kind=side, code=code, quantity=int(quantity), price=int(price))
        with self.operation_lock:
            state = self.read()
            previous = self.prior(state, client_id, request)
            if previous: return previous
            self.check(state, expected_version, running=True)
            if any(o['status'] in ('sending', 'unknown') for o in state['operations']):
                raise TradingError('전송 결과를 먼저 확인하세요.')
            capacity = self.gateway.capacity(state['account'], code, side, price)
            if quantity > capacity['quantity']:
                raise TradingError('현금 주문 가능 수량이 부족합니다.')
            if prepare is not None: prepare()
            return self.dispatch(side, client_id, request, state['account'], expected_version,
                                 budget=quantity * price if side == 'buy' else 0, rule_deadline=rule_deadline, preflight=preflight)

    def actionable(self, row):
        return (row['remaining'] > 0 and row['side'] in ('buy', 'sell') and row['market'] == 'KRX'
                and row.get('split', 'N') == 'N' and row.get('reason') == '정상'
                and row.get('order_type') in ('보통', '보통가', '지정가'))

    def manage(self, kind, client_id, broker_id, price, expected_version, order_day=None):
        if kind not in ('modify', 'cancel'): raise TradingError('주문 작업을 확인하세요.')
        order_day = order_day or korea_today()
        if order_day != korea_today(): raise TradingError('당일 주문만 정정·취소할 수 있습니다. 주문 내역을 새로 조회하세요.')
        with self.operation_lock:
            state = self.read()
            for op in state['operations']:
                if op['client_id'] == client_id:
                    if op['kind'] != kind or op['original'] != broker_id or op['price'] != price or op['day'] != order_day:
                        raise TradingError('요청 식별자가 다른 작업에 사용되었습니다.')
                    return op
            self.check(state, expected_version, running=kind != 'cancel')
            rows = self.gateway.history(state['account'], korea_today())
            row = next((r for r in rows if r['broker_id'] == broker_id), None)
            if not row or not self.actionable(row):
                raise TradingError('당일 KRX 현금 지정가 미체결 주문만 정정·취소할 수 있습니다.')
            qty = row['remaining']
            budget = 0
            if kind == 'modify':
                self.validate_order(row['code'], row['side'], qty, price, client_id)
                if row['side'] == 'buy':
                    budget = qty * max(0, price - row['price'])
                    capacity = self.gateway.capacity(state['account'], row['code'], 'buy', price)
                    if budget > capacity['amount']:
                        raise TradingError('가격 정정에 필요한 추가 현금이 부족합니다.')
            request = dict(kind=kind, code=row['code'], quantity=qty, price=int(price), original=broker_id, order_day=order_day)
            return self.dispatch(kind, client_id, request, state['account'], expected_version, budget, order_day=order_day)

    def resolve(self, op_id, decision, broker_id, acknowledged, expected_version):
        if not acknowledged: raise TradingError('증권사에서 접수 여부를 확인했음을 체크하세요.')
        with self.operation_lock:
            state = self.read()
            self.check(state, expected_version)
            op = next((o for o in state['operations'] if o['id'] == op_id and o['status'] == 'unknown'), None)
            if not op: raise TradingError('확인 대기 중인 전송 기록이 없습니다.')
            if decision == 'linked':
                rows = self.gateway.history(op['account'], op['day'])
                row = next((r for r in rows if r['broker_id'] == broker_id), None)
                if not row or row['code'] != op['code'] or row['quantity'] != op['quantity']:
                    raise TradingError('주문번호의 종목·수량이 전송 기록과 일치하지 않습니다.')
                if row['market'] != 'KRX' or (op['kind'] != 'cancel' and row['price'] != op['price']):
                    raise TradingError('주문 시장·지정가가 전송 기록과 일치하지 않습니다.')
                if (op['kind'] in ('buy', 'sell') and row['side'] != op['kind']) or (
                        op['original'] and row['original_id'] != op['original']):
                    raise TradingError('원주문 또는 매매 구분이 일치하지 않습니다.')
                if any(o['id'] != op_id and o['account'] == op['account'] and o['day'] == op['day']
                       and o['broker_id'] == broker_id for o in state['operations']):
                    raise TradingError('이미 연결된 증권사 주문번호입니다.')
                result = dict(status='accepted', broker_id=broker_id, message='사용자가 증권사 주문번호를 확인·연결했습니다.')
            elif decision == 'not_sent':
                result = dict(status='rejected', message='사용자가 증권사 미접수를 확인했습니다.')
            else:
                raise TradingError('확인 방법을 선택하세요.')
            with self.change() as current:
                self.check(current, expected_version)
                next(o for o in current['operations'] if o['id'] == op_id).update(result)
            return self.snapshot()

    def add_rule(self, *, client_id, code, side, quantity, price, comparison, threshold, expected_version):
        self.validate_order(code, side, quantity, price, client_id)
        if comparison not in ('gte', 'lte') or not positive_integer(threshold):
            raise TradingError('가격 조건을 확인하세요.')
        request = dict(code=code, side=side, quantity=quantity, price=price, comparison=comparison, threshold=threshold)
        with self.change() as state:
            self.check(state, expected_version)
            for r in state['rules']:
                if r['client_id'] == client_id:
                    if r['request'] != request: raise TradingError('조건 식별자의 내용이 다릅니다.')
                    return r
            if sum(r['status'] == 'armed' for r in state['rules']) >= 10:
                raise TradingError('대기 조건은 최대 10개입니다.')
            rule = dict(id=uuid.uuid4().hex, client_id=client_id, request=request, **request,
                        account=state['account'], status='armed', message='', created_at=now())
            state['rules'].append(rule)
            return rule

    def cancel_rule(self, rule_id, expected_version):
        with self.change() as state:
            self.check(state, expected_version)
            rule = next((r for r in state['rules'] if r['id'] == rule_id), None)
            if not rule: raise TradingError('조건을 찾을 수 없습니다.')
            if rule['status'] == 'armed': rule['status'] = 'cancelled'

    def emergency(self):
        if not self.emergency_lock.acquire(blocking=False):
            self.halted.set()
            return self.snapshot()
        self.emergency_active.set()
        try:
            return self._emergency_cancel()
        finally:
            self.halted.set()
            self.emergency_active.clear()
            self.emergency_lock.release()

    def _emergency_cancel(self):
        self.stop()
        with self.change() as state:
            for rule in state['rules']:
                if rule['status'] == 'armed': rule['status'] = 'cancelled'
        state = self.read()
        if state['mode'] != 'live' or not state['account']: return self.snapshot()
        try:
            result = dict(accepted=0, uncertain=0, rejected=0)
            rows = self.gateway.history(state['account'], korea_today())
            owned = {o['broker_id'] for o in state['operations'] if o['day'] == korea_today()
                     and o['account'] == state['account'] and o['kind'] != 'cancel'}
            for row in rows:
                if row['broker_id'] in owned and self.actionable(row):
                    op = self.manage('cancel', 'emergency:' + uuid.uuid4().hex, row['broker_id'], 0, state['version'])
                    result['uncertain' if op['status'] == 'unknown' else op['status']] += 1
            self.emergency_result = result
            self.error = (f'실전 정지. 취소 접수 {result["accepted"]}건, 결과 불확실 {result["uncertain"]}건, 거절 {result["rejected"]}건. '
                          '증권사 주문 내역에서 최종 취소 여부를 확인하세요.')
        except Exception:
            self.error = '실전 실행은 정지했습니다. 일부 취소를 확인하지 못했으므로 나무 앱에서 미체결을 확인하세요.'
        return self.snapshot()

    def tick(self):
        if self.halted.is_set() or not self.session_open(): return
        state = self.read()
        version = state['version']
        for rule in state['rules']:
            if self.halted.is_set(): return
            if rule['status'] != 'armed' or rule['account'] != state['account']: continue
            try:
                began = time.monotonic()
                quote = self.gateway.quote(rule['code'])
                price = quote.get('price')
                if not positive_integer(price) or time.monotonic() - began > 30 or not self.session_open():
                    raise TradingError('시세 오류 또는 실행 시간 외')
                self.quotes[rule['code']] = dict(price=price, at=now(), error='')
                hit = price >= rule['threshold'] if rule['comparison'] == 'gte' else price <= rule['threshold']
                if not hit: continue
                with self.change() as current:
                    self.check(current, version, running=True)
                    stored = next(r for r in current['rules'] if r['id'] == rule['id'])
                    if stored['status'] != 'armed': continue
                    stored['status'] = 'executing'
                try:
                    op = self.order(client_id='rule:' + rule['id'], code=rule['code'], side=rule['side'],
                                    quantity=rule['quantity'], price=rule['price'], expected_version=version,
                                    internal=True, rule_deadline=began + 30)
                    status = 'fired' if op['status'] == 'accepted' else 'review' if op['status'] == 'unknown' else 'rejected'
                    message = op['message']
                except (TradingError, NamuhError) as exc:
                    status, message = 'rejected', str(exc)
                with self.change() as current:
                    next(r for r in current['rules'] if r['id'] == rule['id']).update(status=status, message=message)
            except Exception:
                self.quotes[rule['code']] = dict(at=now(), error='시세·실행 상태 확인 실패. 이번 판단을 건너뜁니다.')

    def launch(self):
        if self.worker and self.worker.is_alive(): return
        self.closed.clear()
        def loop():
            while not self.closed.wait(10):
                try: self.tick()
                except Exception:
                    self.halted.set()
                    self.error = '실행 기록 오류로 중단했습니다. 기록과 저장 공간을 확인하세요.'
        self.worker = threading.Thread(target=loop, daemon=True, name='live-rules')
        self.worker.start()

    def close(self):
        self.halted.set()
        self.closed.set()
