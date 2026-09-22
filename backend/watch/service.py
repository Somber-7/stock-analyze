"""Persistent watchlist and one-shot price alerts. No order API dependency."""
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone, timedelta

from backend.namuh.client import NamuhError


def now(): return datetime.now(timezone.utc).isoformat()


def session_open():
    local = datetime.now(timezone(timedelta(hours=9)))
    return local.weekday() < 5 and '0900' <= local.strftime('%H%M') < '1530'


class WatchService:
    def __init__(self, path, quote, resolve):
        self.path, self.quote, self.resolve = str(path), quote, resolve
        self.lock = threading.RLock()
        self.tick_lock = threading.Lock()
        self.shutdown = threading.Event()
        self.worker = None
        self.session_open = session_open
        self.quotes = {}
        self.last_viewed = -1000
        self.next_cycle = 0
        self.last_cycle = None
        self.refreshing = False
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS watch (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO watch VALUES (1, ?)', (json.dumps({'items': [], 'alerts': []}),))

    @contextmanager
    def change(self):
        with self.lock, closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = json.loads(db.execute('SELECT data FROM watch WHERE id=1').fetchone()[0])
            yield state
            db.execute('UPDATE watch SET data=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))

    def read(self):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            return json.loads(db.execute('SELECT data FROM watch WHERE id=1').fetchone()[0])

    def snapshot(self, viewed=False):
        with self.lock:
            if viewed:
                if time.monotonic() - self.last_viewed > 15: self.next_cycle = 0
                self.last_viewed = time.monotonic()
            state = self.read()
            state['items'] = [{**item, 'quote': dict(self.quotes[item['code']]) if item['code'] in self.quotes else None}
                              for item in state['items']]
            alerts = list(reversed(state['alerts']))
            state['alerts'] = [a for a in alerts if a['status'] == 'armed' or not a.get('notified', True)] + [
                a for a in alerts if a['status'] != 'armed' and a.get('notified', True)][:100]
            return {**state, 'refreshing': self.refreshing, 'last_cycle': self.last_cycle,
                    'next_refresh_seconds': max(0, int(self.next_cycle - time.monotonic())),
                    'session_open': self.session_open(), 'interval_seconds': 30}

    def add(self, code):
        if not re.fullmatch(r'[0-9A-Z]{6}', code): raise ValueError('종목코드를 확인하세요.')
        existing = next((s for s in self.read()['items'] if s['code'] == code), None)
        if existing: return existing
        stock = self.resolve(code)
        if not stock or stock.get('code') != code or not stock.get('name'):
            raise ValueError('나무 종목 목록에서 찾을 수 없습니다. 목록 갱신 후 다시 시도하세요.')
        with self.change() as state:
            existing = next((s for s in state['items'] if s['code'] == code), None)
            if existing: return existing
            item = dict(id=uuid.uuid4().hex, code=code, name=stock['name'], added_at=now())
            state['items'].append(item)
            self.next_cycle = 0
            return item

    def remove(self, code):
        with self.change() as state:
            state['items'] = [s for s in state['items'] if s['code'] != code]
            for alert in state['alerts']:
                if alert['code'] == code and alert['status'] == 'armed':
                    alert.update(status='cancelled', cancelled_at=now())
            self.quotes.pop(code, None)

    def add_alert(self, code, comparison, threshold, client_id):
        if (comparison not in ('gte', 'lte') or type(threshold) is not int or threshold <= 0
                or not isinstance(client_id, str) or not 1 <= len(client_id) <= 100):
            raise ValueError('알림 가격과 조건을 확인하세요.')
        request = dict(code=code, comparison=comparison, threshold=threshold)
        with self.change() as state:
            prior = next((a for a in state['alerts'] if a['client_id'] == client_id), None)
            if prior:
                if prior['request'] != request: raise ValueError('같은 요청으로 다른 알림을 등록할 수 없습니다.')
                return prior
            item = next((s for s in state['items'] if s['code'] == code), None)
            if not item: raise ValueError('관심종목에 먼저 추가하세요.')
            alert = dict(id=uuid.uuid4().hex, client_id=client_id, request=request, **request,
                         name=item['name'], created_at=now(), status='armed', notified=True)
            state['alerts'].append(alert)
            self.next_cycle = 0
            return alert

    def cancel_alert(self, alert_id):
        with self.change() as state:
            alert = next((a for a in state['alerts'] if a['id'] == alert_id), None)
            if not alert: raise ValueError('알림을 찾을 수 없습니다.')
            if alert['status'] == 'armed': alert.update(status='cancelled', cancelled_at=now())

    def notifications(self):
        return [a for a in self.read()['alerts'] if a['status'] == 'triggered' and not a['notified']]

    def acknowledge(self, ids):
        with self.change() as state:
            for alert in state['alerts']:
                if alert['id'] in ids and alert['status'] == 'triggered': alert['notified'] = True

    def tick(self):
        if not self.tick_lock.acquire(blocking=False): return
        try:
            with self.lock:
                self.refreshing = True
                state = self.read()
                visible = time.monotonic() - self.last_viewed < 15
                alert_ids = {a['id'] for a in state['alerts'] if a['status'] == 'armed'}
                alert_codes = {a['code'] for a in state['alerts'] if a['status'] == 'armed'} if self.session_open() else set()
                items = [s for s in state['items'] if visible or s['code'] in alert_codes]
            for item in items:
                if self.shutdown.is_set(): break
                code = item['code']
                # Recheck membership and page lease before spending an API request.
                current = self.read()
                if not any(s['id'] == item['id'] for s in current['items']): continue
                if time.monotonic() - self.last_viewed >= 15 and not (
                    self.session_open() and any(a['code'] == code and a['status'] == 'armed' for a in current['alerts'])):
                    continue
                started = time.monotonic()
                try:
                    quote = self.quote(code)
                    value = quote.get('price')
                    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                            not math.isfinite(value) or value <= 0 or value != int(value) or
                            time.monotonic() - started > 30):
                        raise ValueError('Invalid or late quote')
                    rate = quote.get('change_rate')
                    rate = rate if isinstance(rate, (int, float)) and math.isfinite(rate) else None
                    with self.change() as fresh:
                        if not any(s['id'] == item['id'] for s in fresh['items']): continue
                        self.quotes[code] = dict(price=int(value), change_rate=rate, retrieved_at=now(), error='')
                        if self.shutdown.is_set() or not self.session_open(): continue
                        for alert in fresh['alerts']:
                            if alert['id'] not in alert_ids or alert['code'] != code or alert['status'] != 'armed': continue
                            hit = value >= alert['threshold'] if alert['comparison'] == 'gte' else value <= alert['threshold']
                            if hit: alert.update(status='triggered', observed_price=int(value), triggered_at=now(), notified=False)
                except (NamuhError, ValueError, TypeError, KeyError):
                    with self.lock:
                        if any(s['id'] == item['id'] for s in self.read()['items']):
                            self.quotes[code] = {**self.quotes.get(code, {}), 'error': '시세 확인 실패 · 다음 주기에 재조회합니다.'}
        finally:
            with self.lock:
                self.refreshing = False
                self.last_cycle = now()
                self.next_cycle = time.monotonic() + 30
            self.tick_lock.release()

    def launch(self):
        def run():
            while not self.shutdown.wait(.5):
                if time.monotonic() < self.next_cycle: continue
                try: self.tick()
                except Exception:
                    # Keep the monitor alive without exposing response or database details.
                    self.next_cycle = time.monotonic() + 30
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def close(self):
        self.shutdown.set()
        if self.worker: self.worker.join(timeout=2)
