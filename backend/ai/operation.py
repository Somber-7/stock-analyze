"""Durable AI proposals. Existing trading engines remain the only order boundary."""
import copy
import json
import math
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone, timedelta

from backend.namuh.client import NamuhError, NamuhRejected
from backend.namuh.orders import korea_today
from backend.trading.live import TradingError, regular_session
from backend.trading.paper import PaperError, ACTIVE, positive_integer
from .context import load_context, portfolio_snapshot, stock_symbols, trading_day_active
from .providers import ProviderError, ReportValidationError
from .settings import SettingsError
from .web_search import research, SearchError
from .comparison import comparison_scope, previous_analysis, compare_decision
from .dart import research as dart_research
from .evidence import enrich_context
from .dart_client import DartError
from .order_plan import build_order_plan
from .archive import build_snapshot
from .outcomes import evaluate_outcomes
from .telemetry import summarize
from backend.namuh.chart import get_daily_chart


class OperationError(ValueError):
    pass


def now(): return datetime.now(timezone.utc).isoformat()


class AIOperation:
    def __init__(self, path, settings, trading, *, context_loader=load_context,
                 generate_fn=None, symbols_loader=stock_symbols, research_fn=research, dart_fn=dart_research):
        self.path, self.settings, self.trading = str(path), settings, trading
        self.context_loader, self.generate_fn, self.symbols_loader = context_loader, generate_fn, symbols_loader
        self.research_fn = research_fn
        self.dart_fn = dart_fn
        self.lock = threading.RLock()
        self.outcome_lock = threading.Lock()
        self.halted = threading.Event()
        self.halted.set()
        self.closed = threading.Event()
        self.busy = False
        self.worker = self.analysis_thread = None
        self.next_due = 0
        self.next_run_at = None
        self.session_open = regular_session
        self.binding = None
        self.stop_epoch = 0
        self.market_active = trading_day_active
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS ai_operation (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS ai_inputs (run_id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            initial = dict(version=0, config=dict(execution='suggest', codes=[], interval_minutes=30,
                          objective='국내 주식의 가격 추세·수급·계좌 자산과 투자기간을 고려해 보유 수량을 제안하세요. 근거가 부족하면 판단 유보로 표시하고 수량을 변경하지 마세요.',
                          include_us=True, include_web=False, investment_horizon='unspecified'), error='', runs=[])
            db.execute('INSERT OR IGNORE INTO ai_operation VALUES (1,?)', (json.dumps(initial),))
        with self.change() as state:
            state['config'].setdefault('investment_horizon', 'unspecified')
            state['config'].setdefault('include_web', False)
            state['config'].setdefault('holding_purpose', '')
            state['config'].setdefault('max_position_pct', None)
            state['config'].setdefault('review_drawdown_pct', None)
            state['version'] += 1
            for run in state['runs']:
                if run['status'] == 'analyzing':
                    run.update(status='interrupted', error='프로그램 재시작으로 분석이 중단되었습니다.')
                for decision in run['decisions']:
                    if (decision.get('execution') or {}).get('status') == 'sending':
                        decision['execution'].update(status='unknown', message='중단된 주문입니다. 주문 화면에서 접수 여부를 확인하세요. 재전송하지 않습니다.')

    @contextmanager
    def change(self):
        with self.lock, closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = json.loads(db.execute('SELECT data FROM ai_operation WHERE id=1').fetchone()[0])
            yield state
            db.execute('UPDATE ai_operation SET data=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))

    def read(self):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            return json.loads(db.execute('SELECT data FROM ai_operation WHERE id=1').fetchone()[0])

    def connection(self):
        state = self.settings.snapshot()
        profile = state['profiles'][state['provider']]
        return dict(provider=state['provider'], model=profile['model'], has_key=profile['has_key'])

    def save_inputs(self, run_id, record):
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT OR IGNORE INTO ai_inputs VALUES (?,?)', (run_id,json.dumps(record,ensure_ascii=False,allow_nan=False)))
            ids=[r['id'] for r in self.read()['runs']]
            if ids:
                db.execute('DELETE FROM ai_inputs WHERE run_id NOT IN ('+','.join('?' for _ in ids)+')',ids)

    def inputs(self, run_id):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            value=db.execute('SELECT data FROM ai_inputs WHERE run_id=?',(run_id,)).fetchone()
        if not value: raise OperationError('이 분석에는 당시 입력 자료가 저장되어 있지 않습니다. 새 분석부터 기록됩니다.')
        return json.loads(value[0])

    def observe(self, run_id, *, chart_loader=get_daily_chart):
        if not self.outcome_lock.acquire(blocking=False): raise OperationError('가격 변화를 확인 중입니다. 완료 후 다시 요청하세요.')
        try:
            run=next((r for r in self.read()['runs'] if r['id']==run_id),None)
            if not run or run['status']!='ready': raise OperationError('완료된 분석을 선택하세요.')
            try: run['input_snapshot']=self.inputs(run_id)
            except OperationError: pass
            series={}
            if run.get('input_snapshot'):
                from concurrent.futures import ThreadPoolExecutor
                codes=list(dict.fromkeys([r['code'] for r in run['decisions']]+['069500']))
                def collect(code):
                    try: return code,chart_loader(code,days=1000)
                    except Exception: return code,None
                with ThreadPoolExecutor(max_workers=3) as pool: series=dict(pool.map(collect,codes))
            result=evaluate_outcomes(run,series,series.get('069500'),datetime.now(timezone.utc))
            with self.change() as state:
                stored=next((r for r in state['runs'] if r['id']==run_id),None)
                if stored is not None: stored['outcomes']=result
            return result
        finally: self.outcome_lock.release()

    def current_binding(self):
        trade = self.trading.snapshot()
        return dict(trade_version=trade['version'], mode=trade['mode'],
                    paper_version=self.trading.paper.snapshot()['version'] if trade['mode'] == 'paper' else None,
                    ai_version=self.settings.snapshot()['version'],
                    stop_epoch=self.stop_epoch)

    def snapshot(self):
        state = self.read()
        trade = self.trading.snapshot()
        telemetry = summarize(state['runs'])
        try: connection = self.connection()
        except SettingsError:
            connection = dict(provider='', model='', has_key=False)
        for run in state['runs']:
            run.pop('binding', None)
            run.pop('comparison_scope', None)
        state['runs'] = list(reversed(state['runs']))[:50]
        return dict(**state, telemetry=telemetry, running=not self.halted.is_set(), busy=self.busy,
                    next_run_at=self.next_run_at, mode=trade['mode'],
                    engine_running=trade['running'] if trade['mode'] == 'live' else self.trading.paper.running,
                    web_search=self.settings.snapshot().get('tools', {}).get('tavily', {'has_key': False}),
                    dart=self.settings.snapshot().get('tools', {}).get('dart', {'enabled': False}),
                    connection=connection, symbols=self.symbols_loader(), holdings=[])

    def holdings(self):
        before = self.current_binding()
        result = portfolio_snapshot(self.trading)['holdings']
        if before != self.current_binding(): raise OperationError('계좌 또는 설정이 변경되었습니다. 다시 불러오세요.')
        return [dict(code=p['code'], name=p['name'], quantity=p['quantity']) for p in result]

    def check_version(self, state, version):
        if state['version'] != version: raise OperationError('AI 운용 상태가 변경되었습니다. 최신 화면에서 다시 요청하세요.')

    def configure(self, version, *, execution, codes, interval_minutes, objective, include_us, investment_horizon='unspecified', include_web=False,
                  holding_purpose='', max_position_pct=None, review_drawdown_pct=None):
        available = {s['code'] for s in self.symbols_loader()}
        if (execution not in ('suggest', 'paper', 'live') or not 1 <= len(codes) <= 10
                or len(set(codes)) != len(codes) or any(c not in available for c in codes)):
            raise OperationError('나무 국내 종목 목록에서 1~10개를 선택하세요.')
        if type(interval_minutes) is not int or not 5 <= interval_minutes <= 1440:
            raise OperationError('분석 주기는 5~1440분으로 입력하세요.')
        if not isinstance(objective, str) or not 1 <= len(objective.strip()) <= 2000 or type(include_us) is not bool:
            raise OperationError('운용 지침과 미국 참고 설정을 확인하세요.')
        if type(include_web) is not bool: raise OperationError('웹 검색 설정을 확인하세요.')
        if investment_horizon not in ('unspecified', 'short', 'medium', 'long'):
            raise OperationError('투자기간을 확인하세요.')
        if not isinstance(holding_purpose,str) or len(holding_purpose)>500:
            raise OperationError('보유 목적은 500자 이내로 입력하세요.')
        for value in (max_position_pct,review_drawdown_pct):
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not 0 < value <= 100):
                raise OperationError('분석 참고 비율은 0 초과 100 이하이거나 미지정이어야 합니다.')
        with self.change() as state:
            self.check_version(state, version)
            self.halted.set()
            self.next_run_at = None
            state['config'] = dict(execution=execution, codes=codes, interval_minutes=interval_minutes,
                                   objective=objective.strip(), include_us=include_us, investment_horizon=investment_horizon, include_web=include_web,
                                   holding_purpose=holding_purpose.strip(),max_position_pct=max_position_pct,review_drawdown_pct=review_drawdown_pct)
            state['version'] += 1
            state['error'] = ''
        return self.snapshot()

    def ensure_engine(self, mode):
        trade = self.trading.snapshot()
        if trade['mode'] != mode: raise OperationError('AI 운용 모드와 매매 설정의 모드가 다릅니다.')
        running = trade['running'] if mode == 'live' else self.trading.paper.running
        if not running: raise OperationError('주문·자동매매 화면에서 현재 모드의 실행을 먼저 시작하세요.')

    def control(self, version, action, live_acknowledged=False):
        if action == 'stop':
            # This flag also guards a broker request waiting on token/rate limiting.
            self.halted.set()
            self.stop_epoch += 1
            self.next_run_at = None
            with self.change() as state:
                self.halted.set()
                self.next_run_at = None
                state['version'] += 1
            return self.snapshot()
        with self.change() as state:
            self.check_version(state, version)
            if action != 'start' or not state['config']['codes']:
                raise OperationError('분석 종목을 저장한 뒤 시작하세요.')
            if self.busy: raise OperationError('진행 중인 분석이 끝난 뒤 시작하세요.')
            self.settings.credentials()
            if state['config'].get('include_web'): self.settings.tavily_credentials()
            execution = state['config']['execution']
            if execution != 'suggest': self.ensure_engine(execution)
            if execution == 'live' and not live_acknowledged:
                raise OperationError('실제 계좌로 AI 주문을 실행함을 확인하세요.')
            self.binding = self.current_binding()
            self.halted.clear()
            state['version'] += 1
            state['error'] = ''
            self.next_due = 0
            self.next_run_at = now()
        return self.snapshot()

    def analyze(self, version, *, background=True, source='manual'):
        with self.change() as state:
            self.check_version(state, version)
            if self.busy: raise OperationError('이미 분석 중입니다. 결과를 기다려주세요.')
            if not state['config']['codes']: raise OperationError('먼저 분석할 종목을 저장하세요.')
            credentials = self.settings.credentials()
            dart_credentials = getattr(self.settings, 'dart_credentials', lambda: None)()
            if dart_credentials:
                if dart_credentials['version'] != credentials['version']:
                    raise OperationError('DART 설정이 변경되었습니다. 다시 분석하세요.')
                credentials['dart_key'] = dart_credentials['key']
                dart_credentials.clear()
            if state['config'].get('include_web'):
                search_credentials = self.settings.tavily_credentials()
                if search_credentials['version'] != credentials['version']:
                    raise OperationError('검색 설정이 변경되었습니다. 다시 분석하세요.')
                credentials['tavily_key'] = search_credentials['key']
                search_credentials.clear()
            binding = self.current_binding()
            if binding['ai_version'] != credentials['version']:
                raise OperationError('AI 연결 설정이 변경되었습니다. 다시 분석하세요.')
            state['version'] += 1
            analysis_version = state['version']
            run = dict(id=uuid.uuid4().hex, created_at=now(), completed_at=None,
                       comparison_scope=comparison_scope(dict(state['config'],include_dart=bool(credentials.get('dart_key'))), self.trading.snapshot()),
                       operation_version=analysis_version,
                       status='analyzing', source=source, mode=binding['mode'], binding=binding,
                       provider=credentials['provider'], model=credentials['model'], summary='', risks=[],
                       warnings=[], error='', usage={}, decisions=[])
            state['runs'].append(run)
            state['runs'] = state['runs'][-200:]
            state['error'] = ''
            config = copy.deepcopy(state['config'])
            self.busy = True
        args = (run['id'], config, credentials, binding, analysis_version, source)
        if background:
            self.analysis_thread = threading.Thread(target=self._analyze, args=args, daemon=True, name='ai-analysis')
            self.analysis_thread.start()
        else: self._analyze(*args)
        return self.snapshot()

    def _analyze(self, run_id, config, credentials, binding, version, source):
        began = time.monotonic()
        timings = {}
        def timed(stage, fn, *args, **kwargs):
            start = time.monotonic()
            try: return fn(*args, **kwargs)
            finally: timings[stage] = round((time.monotonic() - start) * 1000)
        try:
            context = timed('context_ms', self.context_loader, config, self.trading)
            context['investor_preferences']={key:config.get(key) for key in ('holding_purpose','max_position_pct','review_drawdown_pct')}
            if self.read()['version'] != version or self.current_binding() != binding or self.closed.is_set():
                raise OperationError('분석 중 설정 또는 실행 상태가 변경되었습니다.')
            history = self.read()['runs']
            scope = next(r['comparison_scope'] for r in history if r['id'] == run_id)
            prior = previous_analysis(history, scope, run_id)
            context['previous_analysis'] = prior
            if credentials.get('dart_key'):
                def dart_cancelled():
                    return self.closed.is_set() or self.read()['version'] != version or self.current_binding() != binding
                try:
                    context['dart_research'] = timed('dart_ms', self.dart_fn, [dict(code=s['code'],name=s['name']) for s in context['stocks']],
                                                          credentials['dart_key'],cancelled=dart_cancelled)
                except DartError as exc:
                    context['dart_research'] = dict(status='error',stocks=[],sources=[],error=str(exc))
                if dart_cancelled(): raise OperationError('DART 조회 중 설정 또는 실행 상태가 변경되었습니다.')
                if context['dart_research']['status'] != 'ready':
                    context['warnings'].append('DART 재무·공시 자료 일부를 확인하지 못했습니다. 누락 항목은 0이나 문제가 없다는 뜻이 아닙니다.')
            else:
                context['dart_research']=dict(status='disabled',stocks=[],sources=[])
                context['warnings'].append('DART 연동이 꺼져 있어 확정 재무 주요계정은 포함되지 않았습니다.')
            if config.get('include_web'):
                def cancelled():
                    return self.closed.is_set() or self.read()['version'] != version or self.current_binding() != binding
                aliases_by_code={r['code']:r.get('aliases',[]) for r in context.get('dart_research',{}).get('stocks',[])}
                research_stocks=[dict(code=s['code'],name=s['name']) for s in context['stocks']]
                financial_codes={r['code'] for r in context.get('dart_research',{}).get('stocks',[])
                                 if (r.get('financials') or {}).get('accounts')}
                for stock in research_stocks:
                    if aliases_by_code.get(stock['code']): stock['aliases']=aliases_by_code[stock['code']]
                    if stock['code'] in financial_codes: stock['has_dart_financials']=True
                context['web_research'] = timed('web_ms', self.research_fn,
                    research_stocks,
                    credentials['tavily_key'], cancelled=cancelled)
                if cancelled(): raise OperationError('웹 검색 중 설정 또는 실행 상태가 변경되었습니다.')
                web = context['web_research']
                context['warnings'].append('웹 검색 발췌 자료입니다. 원문 전체·재무제표 항목의 검증을 대신하지 않으며 게시일 미확인 자료는 최신 정보로 단정하지 않습니다.')
                if web['status'] in ('empty', 'partial'):
                    context['warnings'].append('일부 웹 검색 실패 또는 검색 자료 부족이 있습니다. 확인되지 않은 뉴스·실적을 추정하지 마세요.')
            if self.generate_fn is None:
                from .generation import generate
                generate_fn = generate
            else: generate_fn = self.generate_fn
            from .generation import _INSTRUCTIONS
            enrich_context(context)
            input_snapshot=build_snapshot(config,context,_INSTRUCTIONS)
            self.save_inputs(run_id,input_snapshot)
            result = timed('model_ms', generate_fn, credentials['provider'], credentials['key'], credentials['model'], context, config['objective'])
            output = result['analysis']
            rows = output['decisions']
            if len(rows) != len(config['codes']) or {r['code'] for r in rows} != set(config['codes']):
                raise OperationError('AI 응답의 종목이 선택 범위와 일치하지 않습니다. 다시 분석하세요.')
            stocks = {s['code']: s for s in context['stocks']}
            quantities = {}
            for holding in context['portfolio']['holdings']:
                quantities[holding['code']] = quantities.get(holding['code'], 0) + holding['quantity']
            decisions = []
            for row in rows:
                qty = row['target_quantity']
                if type(qty) is not int or not 0 <= qty <= 1_000_000_000:
                    raise OperationError('AI가 올바르지 않은 목표 수량을 반환했습니다.')
                source_ids = row.get('source_ids')
                allowed_sources = {s['id'] for field in ('web_research','dart_research') for s in context.get(field, {}).get('sources', []) if s['code'] == row['code']}
                if not isinstance(source_ids, list) or len(source_ids) > 6 or any(not isinstance(i, str) or i not in allowed_sources for i in source_ids):
                    raise OperationError('AI 응답의 웹 출처를 검색 자료에서 확인할 수 없습니다.')
                stock = stocks[row['code']]
                price = stock['quote']['price']
                if not positive_integer(price): raise OperationError('분석 기준 시세를 확인할 수 없습니다.')
                current = quantities.get(row['code'], 0)
                delta = qty - current
                if row.get('assessment') not in ('supported', 'defer') or not isinstance(row.get('review_conditions'), str) or not row['review_conditions'].strip():
                    raise OperationError('AI의 판단 상태와 재검토 조건을 확인할 수 없습니다.')
                if row['assessment'] == 'defer' and delta != 0:
                    raise OperationError('판단 유보 결과가 보유 수량 변경을 제안해 해당 분석을 중단했습니다.')
                quality = stock.get('data_quality')
                override = bool(quality and quality.get('requires_defer'))
                if override:
                    row = dict(row, target_quantity=current, assessment='defer',
                               market_view='unknown',decision_basis='data_missing',
                               headline='확정 일봉 검증을 통과하지 못해 가격·수량 판단을 유보했습니다.',
                               rationale='자료 검증 결과 핵심 시세 자료를 확인해야 하므로 판단을 유보합니다. ' + ' '.join(quality['issues']),
                               review_conditions='자료 상태를 확인하고 확정 일봉을 다시 조회한 뒤 분석하세요.', source_ids=[])
                    delta = 0
                decisions.append(dict(**row, name=stock['name'], current_quantity=current,
                                      quantity=abs(delta), side='buy' if delta > 0 else 'sell' if delta < 0 else 'hold',
                                      reference_price=price, execution=None, metrics=stock.get('metrics'),
                                      buy_capacity=stock.get('buy_capacity'), account_weight_pct=stock.get('account_weight_pct'),
                                      price_basis=stock.get('price_basis'),
                                      review_points=stock.get('review_points',[]),
                                      data_quality=quality, quality_override=override))
                decisions[-1]['comparison'] = compare_decision(decisions[-1], prior)
            comparison = dict(previous_id=prior['id'], completed_at=prior['completed_at'],
                              provider=prior['provider'], model=prior['model'],
                              changed_count=sum(bool(d['comparison'] and d['comparison']['changed']) for d in decisions)) if prior else None
            with self.change() as state:
                stored = next(r for r in state['runs'] if r['id'] == run_id)
                changed = state['version'] != version or self.current_binding() != binding or self.closed.is_set()
                timings['total_ms'] = round((time.monotonic() - began) * 1000)
                stored['timings'] = timings
                if changed:
                    stored.update(status='interrupted', completed_at=now(), error='설정 변경 또는 정지로 분석 결과의 주문 연결을 중단했습니다.')
                    return
                stored.update(status='ready', summary=output['summary'], risks=output['risks'],
                              decisions=decisions, usage=result['usage'], warnings=context['warnings'],
                              completed_at=now(), data_at=context['fetched_at'],
                              portfolio=context['portfolio'], investment_horizon=config['investment_horizon'],
                              analysis_config=copy.deepcopy(config),input_record=dict(stored=True,schema_version=1,sha256=input_snapshot['sha256']),
                              comparison=comparison, order_plan=build_order_plan(decisions, context['portfolio']),
                              dart_research=context.get('dart_research'),
                              web_research=context.get('web_research'))
                if time.monotonic() - began > 300:
                    stored['warnings'].append('분석에 5분 이상 소요되어 이 결과로 주문할 수 없습니다. 다시 분석하세요.')
            if source == 'auto' and config['execution'] != 'suggest':
                for decision in sorted(decisions, key=lambda d: d['side'] != 'sell'):
                    if decision['side'] == 'hold' or decision['assessment'] == 'defer': continue
                    if self.halted.is_set(): break
                    self.execute(run_id, version, decision['code'], live_acknowledged=config['execution'] == 'live', automatic=True)
        except Exception as exc:
            safe = str(exc) if isinstance(exc, (OperationError, ProviderError, SettingsError, SearchError)) else 'AI 분석 또는 주문 준비에 실패했습니다. 연결·잔고·시세 상태를 확인하세요.'
            with self.change() as state:
                stored = next(r for r in state['runs'] if r['id'] == run_id)
                if stored['status'] == 'analyzing':
                    stored.update(status='error', error=safe, completed_at=now(),
                                  timings=dict(timings, total_ms=round((time.monotonic() - began) * 1000)))
                if isinstance(exc,ReportValidationError):
                    stored.update(validation_issue=copy.deepcopy(exc.issue),usage=copy.deepcopy(exc.usage))
                state['error'] = safe
            if source == 'auto':
                self.halted.set()
                self.next_run_at = None
        finally:
            credentials.clear()
            self.busy = False

    def execute(self, run_id, version, code, live_acknowledged=False, *, automatic=False):
        with self.lock:
            state = self.read()
            self.check_version(state, version)
            run = next((r for r in state['runs'] if r['id'] == run_id), None)
            if not run or run['status'] != 'ready': raise OperationError('실행할 분석 결과를 찾을 수 없습니다.')
            decision = next((d for d in run['decisions'] if d['code'] == code), None)
            if not decision: raise OperationError('분석된 종목을 선택하세요.')
            if decision.get('assessment') == 'defer': raise OperationError('판단 유보 결과는 주문하지 않습니다. 필요한 자료를 보완한 뒤 다시 분석하세요.')
            if decision['execution']: return self.snapshot()  # durable at-most-once intent
            if decision['side'] == 'hold': raise OperationError('보유 유지 제안은 주문하지 않습니다.')
            if run['mode'] == 'live' and not live_acknowledged:
                raise OperationError('실제 계좌로 주문함을 확인하세요.')
            self._execution_guard(run, version, automatic)
            trade = self.trading.snapshot()
            if run['mode'] == 'paper':
                book = self.trading.paper.snapshot()
                pending = any(o['code'] == code and o['status'] in ACTIVE for o in book['orders'])
                held = sum(p['quantity'] for p in book['positions'] if p['code'] == code)
            else:
                pending = any(o['code'] == code and o['remaining'] > 0 for o in self.trading.gateway.history(trade['account'], korea_today()))
                balance = self.trading.gateway.balance(trade['account'])
                held = sum(p['quantity'] for p in balance['holdings'] if p['code'] == code)
            if pending: raise OperationError('이 종목에 미체결 주문이 있어 추가 주문을 보류했습니다.')
            if held != decision['current_quantity']:
                raise OperationError('분석 후 보유 수량이 변경되었습니다. 다시 분석하세요.')
            if automatic and not self.market_active(code):
                raise OperationError('당일 거래 일봉이 확인되지 않아 자동 주문을 보류했습니다. 휴장·거래정지 여부를 확인하세요.')
            quote_began = time.monotonic()
            quote = self.trading.gateway.quote(code) if run['mode'] == 'live' else self.trading.paper.quote(code)
            price = quote.get('price')
            if not positive_integer(price) or abs(price / decision['reference_price'] - 1) > .03:
                raise OperationError('기준가 대비 시세가 3% 넘게 변했거나 유효하지 않습니다. 다시 분석하세요.')
            if automatic and (not math.isfinite(quote.get('volume', 0)) or quote.get('volume', 0) <= 0):
                raise OperationError('거래량을 확인할 수 없어 자동 주문을 보류했습니다.')
            self._execution_guard(run, version, automatic)
            client_id = 'ai:' + run_id + ':' + code
            with self.change() as current:
                d = next(d for r in current['runs'] if r['id'] == run_id for d in r['decisions'] if d['code'] == code)
                d['execution'] = dict(status='sending', message='주문 전송 준비', order_id=None, price=price)
            try:
                def prepare():
                    # Called while the trading engine serializes orders. A manual
                    # order submitted during model/quote latency must be visible.
                    self._execution_guard(run, version, automatic)
                    if run['mode'] == 'live':
                        try:
                            history = self.trading.gateway.history(trade['account'], korea_today())
                            holdings = self.trading.gateway.balance(trade['account'])['holdings']
                        except NamuhError:
                            raise OperationError('주문 직전 잔고·미체결 내역을 확인하지 못했습니다.') from None
                        outstanding = any(o['code'] == code and o['remaining'] > 0 for o in history)
                    else:
                        book = self.trading.paper.snapshot()
                        history, holdings = book['orders'], book['positions']
                        outstanding = any(o['code'] == code and o['status'] in ACTIVE for o in history)
                    if outstanding or sum(p['quantity'] for p in holdings if p['code'] == code) != held:
                        raise OperationError('주문 직전 미체결 또는 보유 수량이 변경되어 전송을 중단했습니다.')

                def preflight():
                    try:
                        self._execution_guard(run, version, automatic)
                        if time.monotonic() - quote_began > 30:
                            raise OperationError('주문 직전 시세 확인 후 30초가 지나 전송을 중단했습니다.')
                    except (OperationError, SettingsError) as exc: raise NamuhRejected(str(exc)) from None
                if run['mode'] == 'live':
                    order = self.trading.order(client_id=client_id, code=code, side=decision['side'],
                             quantity=decision['quantity'], price=price, expected_version=run['binding']['trade_version'],
                             preflight=preflight, prepare=prepare)
                    status, message = order['status'], order['message']
                else:
                    def paper_preflight():
                        prepare()
                        preflight()
                    # Same lock order as TradingService.configure: trading then
                    # paper. Holding paper then asking for trading would deadlock.
                    with self.trading.operation_lock, self.trading.lock:
                        order = self.trading.paper.submit(client_id=client_id, code=code, side=decision['side'],
                                 quantity=decision['quantity'], limit_price=price,
                                 expected_version=run['binding']['paper_version'], preflight=paper_preflight)
                    status, message = 'accepted', '모의 주문 접수 · 체결은 주문 화면에서 확인하세요.'
                result = dict(status=status, message=message, order_id=order.get('id'), price=price)
            except (TradingError, PaperError, NamuhRejected, OperationError):
                result = dict(status='rejected', message='주문 가능 수량 또는 실행 상태를 확인하세요. 이 제안은 재전송하지 않습니다.', order_id=None, price=price)
            except Exception:
                result = dict(status='unknown', message='전송 여부를 확인하지 못했습니다. 주문 화면에서 확인하세요. 재전송하지 않습니다.', order_id=None, price=price)
            with self.change() as current:
                d = next(d for r in current['runs'] if r['id'] == run_id for d in r['decisions'] if d['code'] == code)
                d['execution'] = result
                if result['status'] != 'accepted':
                    self.halted.set()
                    self.next_run_at = None
                    current['error'] = result['message']
            return self.snapshot()

    def _execution_guard(self, run, version, automatic):
        self.check_version(self.read(), version)
        if run.get('operation_version') != version:
            raise OperationError('이 결과 이후 AI 운용 설정 또는 분석이 변경되었습니다. 최신 결과로 다시 요청하세요.')
        if self.closed.is_set() or (automatic and self.halted.is_set()): raise OperationError('AI 운용이 정지되었습니다.')
        if self.current_binding() != run['binding']: raise OperationError('계좌·모드·AI 설정 또는 실행 상태가 바뀌었습니다. 다시 분석하세요.')
        if datetime.now(timezone.utc) - datetime.fromisoformat(run['created_at']) > timedelta(minutes=5):
            raise OperationError('분석 후 5분이 지났습니다. 다시 분석하세요.')
        if not self.session_open(): raise OperationError('AI 주문은 평일 09:00~15:20 정규장 시간에만 실행합니다.')
        self.ensure_engine(run['mode'])

    def tick(self):
        if self.halted.is_set() or self.busy: return
        if self.current_binding() != self.binding:
            self._pause_error('계좌·모드·AI 연결 설정이 변경되어 자동 운용을 정지했습니다.')
            return
        state = self.read()
        if state['config']['execution'] != 'suggest':
            try: self.ensure_engine(state['config']['execution'])
            except OperationError as exc:
                self._pause_error(str(exc))
                return
        if not self.session_open() or time.monotonic() < self.next_due: return
        interval = state['config']['interval_minutes'] * 60
        self.next_due = time.monotonic() + interval
        self.next_run_at = (datetime.now(timezone.utc) + timedelta(seconds=interval)).isoformat()
        self.analyze(state['version'], source='auto')

    def _pause_error(self, message):
        self.halted.set()
        self.next_run_at = None
        with self.change() as state:
            state['error'] = message
            state['version'] += 1

    def launch(self):
        if self.worker and self.worker.is_alive(): return
        def loop():
            while not self.closed.wait(2):
                try: self.tick()
                except Exception: self._pause_error('AI 운용 상태를 확인하지 못해 정지했습니다.')
        self.worker = threading.Thread(target=loop, daemon=True, name='ai-operation')
        self.worker.start()

    def close(self):
        self.halted.set()
        self.closed.set()
