import tempfile
import threading
import unittest
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta
from pathlib import Path

from backend.ai.operation import AIOperation, OperationError
from backend.ai.settings import SettingsError
from backend.trading.paper import PaperEngine
from backend.trading.live import TradingService


class Settings:
    version = 1
    def credentials(self): return dict(version=self.version, provider='openai', model='test', key='secret-test')
    def tavily_credentials(self): raise SettingsError('Tavily 키를 저장하세요.')
    def snapshot(self):
        return dict(version=self.version, provider='openai', profiles={'openai': dict(model='test', has_key=True)})


class Gateway:
    def __init__(self): self.sent = []; self.pending = []; self.qty = 0
    def accounts(self): return [{'id': 'private-account'}]
    def balance(self, account): return dict(holdings=[dict(code='005930', name='삼성전자', quantity=self.qty)], summary=dict(cash=10000000))
    def capacity(self, *args): return dict(quantity=10000)
    def quote(self, code): return dict(code=code, price=100, volume=100)
    def history(self, *args): return self.pending
    def send(self, kind, account, before_send=None, **kwargs):
        if before_send: before_send()
        self.sent.append(kwargs)
        return dict(broker_id=str(len(self.sent)))


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.gateway = Gateway()
        self.paper = PaperEngine(self.root/'paper.db', self.gateway.quote)
        self.trade = TradingService(self.root/'trade.db', self.paper, self.gateway)
        self.settings = Settings()
        self.generated = 0
        self.service = AIOperation(self.root/'ai.db', self.settings, self.trade,
                                   context_loader=self.context, generate_fn=self.generate,
                                   symbols_loader=lambda: [{'code':'005930','name':'삼성전자'}])
        self.service.session_open = lambda: True
        self.service.market_active = lambda code: True
        self.trade.session_open = lambda: True
        self.addCleanup(self.service.close)
        self.configure()
        self.paper.start()

    def configure(self, **extra):
        return self.service.configure(self.service.snapshot()['version'], execution='suggest',
                                      codes=['005930'], interval_minutes=30, objective='국내 주식 분석', include_us=False, **extra)

    def context(self, config, trading):
        return dict(stocks=[dict(code='005930',name='삼성전자',quote=self.gateway.quote('005930'),daily=[])],
                    portfolio=dict(cash=10000000,holdings=[dict(code='005930',quantity=self.gateway.qty)]),
                    warnings=[], fetched_at='2026-09-12T00:00:00+00:00')

    def generate(self, *args):
        self.generated += 1
        return dict(analysis=dict(summary='분석 결과',risks=['변동성'],decisions=[dict(code='005930',target_quantity=10,rationale='근거',assessment='supported',review_conditions='거래량 변화',source_ids=[])]),usage=dict(input_tokens=10,output_tokens=20))

    def test_web_requires_key_and_passes_only_public_symbols(self):
        self.configure(include_web=True)
        with self.assertRaises(SettingsError): self.analyze()
        self.assertEqual(self.generated,0)
        self.settings.tavily_credentials = lambda: dict(version=1,key='tvly-test-key-for-research')
        received = []
        def search(stocks,key,**kwargs):
            received.append(stocks)
            return dict(status='ready',sources=[dict(id='005930-news-1',code='005930',url='https://example.com/news',title='뉴스')],searches=[],usage_credits=2)
        self.service.research_fn = search
        original = self.generate
        def generate(*args):
            self.assertIn('web_research',args[3])
            self.assertNotIn('tvly-',str(args[3]))
            result = original(*args)
            result['analysis']['decisions'][0]['source_ids'] = ['005930-news-1']
            return result
        self.service.generate_fn = generate
        run = self.analyze()
        self.assertEqual(run['status'],'ready')
        self.assertEqual(received,[[dict(code='005930',name='삼성전자')]])
        self.assertEqual(run['web_research']['usage_credits'],2)
        self.assertNotIn('tvly-',str(run))
        self.assertFalse(self.gateway.sent)

    def test_invalid_citation_and_state_change_during_search_stop_generation(self):
        self.settings.tavily_credentials = lambda: dict(version=1,key='tvly-test-key-for-research')
        self.configure(include_web=True)
        def changed(*args,**kwargs):
            self.settings.version += 1
            return dict(status='empty',sources=[],searches=[])
        self.service.research_fn = changed
        self.assertEqual(self.analyze()['status'],'error')
        self.assertEqual(self.generated,0)
        self.configure(include_web=False)
        def invalid(*args):
            result = self.generate(*args)
            result['analysis']['decisions'][0]['source_ids'] = ['invented']
            return result
        self.service.generate_fn = invalid
        self.assertEqual(self.analyze()['status'],'error')

    def test_defer_is_retained_without_orders_and_changed_target_is_rejected(self):
        def deferred(*args):
            result = self.generate(*args)
            result['analysis']['decisions'][0].update(assessment='defer',target_quantity=0)
            return result
        self.service.generate_fn = deferred
        run = self.analyze()
        self.assertEqual(run['status'],'ready')
        self.assertEqual(run['decisions'][0]['assessment'],'defer')
        with self.assertRaises(OperationError): self.execute(run)
        self.assertFalse(self.paper.snapshot()['orders'])
        def invalid(*args):
            result = deferred(*args); result['analysis']['decisions'][0]['target_quantity'] = 10
            return result
        self.service.generate_fn = invalid
        self.assertEqual(self.analyze()['status'],'error')

    def test_investment_horizon_persists_rejects_unknown_and_is_in_run(self):
        self.configure(investment_horizon='medium')
        self.assertEqual(self.service.snapshot()['config']['investment_horizon'],'medium')
        run = self.analyze()
        self.assertEqual(run['investment_horizon'],'medium')
        with self.assertRaises(OperationError): self.configure(investment_horizon='made-up')

    def analyze(self):
        self.service.analyze(self.service.snapshot()['version'], background=False)
        return self.service.snapshot()['runs'][0]

    def execute(self, run, **kwargs):
        return self.service.execute(run['id'], self.service.snapshot()['version'], '005930', **kwargs)

    def live(self):
        self.trade.configure(mode='live', account='private-account', expected_version=self.trade.snapshot()['version'])
        self.trade.start(self.trade.snapshot()['version'])

    def test_analysis_is_read_only_and_names_quantities_are_server_owned(self):
        run = self.analyze()
        self.assertEqual(run['status'], 'ready')
        self.assertEqual(run['decisions'][0]['name'], '삼성전자')
        self.assertEqual(run['decisions'][0]['quantity'], 10)
        self.assertEqual(run['order_plan']['buy_amount'], 1000)
        self.assertEqual(run['order_plan']['rows'][0]['reference_price'], 100)
        self.assertEqual(run['order_plan']['funding_status'], 'unverified')
        self.assertFalse(self.paper.snapshot()['orders'])
        self.assertFalse(self.gateway.sent)
        self.assertNotIn('secret-test', str(self.service.snapshot()))
        self.assertNotIn('private-account', str(self.service.snapshot()))

    def test_previous_analysis_is_scoped_and_changes_are_server_calculated(self):
        first = self.analyze()
        original = self.generate
        def changed(*args):
            prior = args[3]['previous_analysis']
            self.assertEqual(prior['id'], first['id'])
            self.assertNotIn('binding', prior)
            self.assertNotIn('comparison_scope', prior)
            result = original(*args)
            result['analysis']['decisions'][0]['target_quantity'] = 5
            return result
        self.service.generate_fn = changed
        second = self.analyze()
        self.assertEqual(second['status'], 'ready')
        comparison = second['comparison']
        self.assertEqual(comparison['previous_id'], first['id'])
        self.assertEqual(comparison['changed_count'], 1)
        self.assertEqual(second['decisions'][0]['comparison']['target_delta'], -5)
        self.assertFalse(self.gateway.sent)
        self.assertNotIn('comparison_scope', self.service.snapshot()['runs'][0])
        self.service.generate_fn = original
        self.configure(investment_horizon='long')
        self.assertIsNone(self.analyze()['comparison'])
        self.live()
        self.assertIsNone(self.analyze()['comparison'])

    def test_immutable_inputs_and_preferences_survive_setting_changes(self):
        self.configure(holding_purpose='중기 성장성 점검',max_position_pct=40,review_drawdown_pct=10)
        run=self.analyze()
        record=self.service.inputs(run['id'])
        self.assertEqual(record['config']['holding_purpose'],'중기 성장성 점검')
        self.assertEqual(record['context']['investor_preferences']['max_position_pct'],40)
        self.assertEqual(record['context']['dart_research']['status'],'disabled')
        self.assertNotIn('private-account',str(record))
        self.assertNotIn('secret-test',str(record))
        self.assertNotIn('input_snapshot',run)
        self.assertEqual(run['input_record']['sha256'],record['sha256'])
        self.configure()
        self.assertEqual(self.service.inputs(run['id']),record)
        self.service.save_inputs(run['id'],{'overwrite':'forbidden'})
        self.assertEqual(self.service.inputs(run['id']),record)

    def test_observation_does_not_generate_or_change_order_binding(self):
        run=self.analyze()
        version=self.service.snapshot()['version']
        generated=self.generated
        loader=Mock(return_value=[])
        result=self.service.observe(run['id'],chart_loader=loader)
        self.assertEqual(result['run_id'],run['id'])
        self.assertEqual(self.generated,generated)
        self.assertEqual(self.service.snapshot()['version'],version)
        self.assertFalse(self.gateway.sent)
        self.assertEqual({c.args[0] for c in loader.call_args_list},{'005930','069500'})
        self.assertEqual(self.service.snapshot()['runs'][0]['summary'],run['summary'])

    def test_optional_preferences_reject_invalid_values(self):
        for field in ('max_position_pct','review_drawdown_pct'):
            for value in (True,0,-1,101,float('nan'),'20'):
                with self.assertRaises(OperationError):self.configure(**{field:value})

    def test_bad_data_forces_defer_even_if_model_proposes_buy(self):
        original = self.context
        def limited(config, trading):
            data = original(config, trading)
            data['stocks'][0]['data_quality'] = dict(status='review', requires_defer=True, issues=['일봉 날짜 확인 필요'])
            return data
        self.service.context_loader = limited
        run = self.analyze()
        self.assertEqual(run['status'], 'ready')
        decision = run['decisions'][0]
        self.assertEqual(decision['assessment'], 'defer')
        self.assertEqual(decision['target_quantity'], 0)
        self.assertEqual(decision['side'], 'hold')
        self.assertTrue(decision['quality_override'])
        self.assertEqual(decision['market_view'],'unknown')
        self.assertEqual(decision['decision_basis'],'data_missing')
        with self.assertRaises(OperationError): self.execute(run)
        self.assertFalse(self.paper.snapshot()['orders'])

    def test_negative_market_view_is_preserved_without_turning_defer_into_order(self):
        def cautious(*args):
            result=self.generate(*args)
            result['analysis']['decisions'][0].update(target_quantity=0,assessment='defer',
                market_view='negative',decision_basis='preferences_missing',headline='약세는 확인되지만 축소 규모는 유보')
            return result
        self.service.generate_fn=cautious
        run=self.analyze()
        self.assertEqual(run['decisions'][0]['market_view'],'negative')
        self.assertEqual(run['decisions'][0]['decision_basis'],'preferences_missing')
        self.assertEqual(run['decisions'][0]['side'],'hold')
        with self.assertRaises(OperationError): self.execute(run)
        self.assertFalse(self.paper.snapshot()['orders'])

    def test_dart_uses_only_public_symbols_and_result_reaches_model(self):
        self.settings.dart_credentials=lambda:dict(version=1,key='a'*40)
        received=[]
        def research(stocks,key,**kwargs):
            received.append(stocks)
            return dict(status='ready',stocks=[dict(code='005930',status='ready',financials=None,disclosures=[])])
        self.service.dart_fn=research
        original=self.generate
        def generate(*args):
            self.assertIn('dart_research',args[3])
            self.assertNotIn('a'*40,str(args[3]))
            return original(*args)
        self.service.generate_fn=generate
        run=self.analyze()
        self.assertEqual(run['status'],'ready')
        self.assertEqual(run['dart_research']['status'],'ready')
        self.assertEqual(received,[[dict(code='005930',name='삼성전자')]])
        self.assertFalse(self.gateway.sent)

    def test_duplicate_paper_execution_creates_one_order(self):
        run = self.analyze()
        self.execute(run)
        self.execute(run)
        self.assertEqual(len(self.paper.snapshot()['orders']), 1)

    def test_live_needs_ack_and_sends_once(self):
        self.live()
        run = self.analyze()
        with self.assertRaises(OperationError): self.execute(run)
        self.execute(run, live_acknowledged=True)
        self.execute(run, live_acknowledged=True)
        self.assertEqual(len(self.gateway.sent), 1)

    def test_mode_or_connection_change_invalidates_proposal(self):
        run = self.analyze()
        self.settings.version += 1
        with self.assertRaises(OperationError): self.execute(run)
        self.assertFalse(self.paper.snapshot()['orders'])

    def test_pending_symbol_and_changed_position_block_execution(self):
        self.live()
        run = self.analyze()
        self.gateway.pending = [dict(code='005930',remaining=1)]
        with self.assertRaises(OperationError): self.execute(run, live_acknowledged=True)
        self.gateway.pending = []
        self.gateway.qty = 2
        with self.assertRaises(OperationError): self.execute(run, live_acknowledged=True)
        self.assertFalse(self.gateway.sent)

    def test_unrequested_symbol_never_becomes_proposal(self):
        original = self.generate
        def wrong(*args):
            result = original(*args)
            result['analysis']['decisions'][0]['code'] = '000660'
            return result
        self.service.generate_fn = wrong
        self.assertEqual(self.analyze()['status'], 'error')
        self.assertFalse(self.paper.snapshot()['orders'])

    def test_stop_discards_inflight_analysis(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set()
            release.wait(5)
            return self.generate(*args)
        self.service.generate_fn = slow
        self.service.analyze(self.service.snapshot()['version'])
        self.assertTrue(entered.wait(3))
        self.service.control(self.service.snapshot()['version'], 'stop')
        release.set()
        self.service.analysis_thread.join(5)
        self.assertEqual(self.service.snapshot()['runs'][0]['status'], 'interrupted')
        self.assertFalse(self.paper.snapshot()['orders'])

    def test_reopen_keeps_history_and_starts_stopped(self):
        self.analyze()
        reopened = AIOperation(self.root/'ai.db', self.settings, self.trade, context_loader=self.context,
                               generate_fn=self.generate, symbols_loader=lambda: [])
        self.addCleanup(reopened.close)
        state = reopened.snapshot()
        self.assertFalse(state['running'])
        self.assertEqual(len(state['runs']), 1)

    def test_old_analysis_and_config_changes_cannot_execute(self):
        old = self.analyze()
        self.analyze()
        with self.assertRaises(OperationError): self.execute(old)
        latest = self.service.snapshot()['runs'][0]
        self.configure()
        with self.assertRaises(OperationError): self.execute(latest)

    def test_expired_and_moved_price_block_execution(self):
        run = self.analyze()
        with self.service.change() as state:
            state['runs'][-1]['created_at'] = (datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()
        with self.assertRaises(OperationError): self.execute(run)
        run = self.analyze()
        self.paper.quote = lambda code: dict(price=105,volume=100)
        with self.assertRaises(OperationError): self.execute(run)
        self.assertFalse(self.paper.snapshot()['orders'])

    def test_live_stop_during_capacity_prevents_send(self):
        self.live()
        run = self.analyze()
        entered, release = threading.Event(), threading.Event()
        def delayed(*args):
            entered.set()
            release.wait(5)
            return dict(quantity=100)
        self.gateway.capacity = delayed
        executing = threading.Thread(target=lambda: self.execute(run, live_acknowledged=True))
        executing.start()
        self.assertTrue(entered.wait(3))
        stopped = threading.Thread(target=lambda: self.service.control(run['operation_version'], 'stop'))
        stopped.start()
        for _ in range(100):
            if self.service.stop_epoch: break
            threading.Event().wait(.01)
        release.set()
        executing.join(5)
        stopped.join(5)
        self.assertFalse(executing.is_alive())
        self.assertFalse(stopped.is_alive())
        self.assertFalse(self.gateway.sent)

    def test_auto_paper_cycle_and_pending_order_prevent_duplicate(self):
        with self.service.change() as state: state['config']['execution'] = 'paper'
        self.service.control(self.service.snapshot()['version'], 'start')
        self.service.tick()
        self.service.analysis_thread.join(5)
        self.assertEqual(len(self.paper.snapshot()['orders']), 1)
        self.service.next_due = 0
        self.service.tick()
        self.service.analysis_thread.join(5)
        self.assertEqual(len(self.paper.snapshot()['orders']), 1)
        self.assertFalse(self.service.snapshot()['running'])

    def test_auto_rejects_stale_market_day_and_stopped_engine(self):
        with self.service.change() as state: state['config']['execution'] = 'paper'
        self.service.market_active = lambda code: False
        self.service.control(self.service.snapshot()['version'], 'start')
        self.service.tick()
        self.service.analysis_thread.join(5)
        self.assertFalse(self.paper.snapshot()['orders'])
        self.paper.stop()
        with self.assertRaises(OperationError): self.service.control(self.service.snapshot()['version'], 'start')

    def test_suggest_auto_analyzes_without_any_orders(self):
        self.service.control(self.service.snapshot()['version'], 'start')
        self.service.tick()
        self.service.analysis_thread.join(5)
        self.assertEqual(self.generated, 1)
        self.assertFalse(self.paper.snapshot()['orders'])
        self.assertFalse(self.gateway.sent)

    def test_changed_credentials_cannot_be_bound_to_new_version(self):
        original = self.settings.credentials
        def changed():
            credentials = original()
            self.settings.version += 1
            return credentials
        self.settings.credentials = changed
        with self.assertRaises(OperationError): self.analyze()
        self.assertEqual(self.generated, 0)

    def test_pending_order_appearing_during_quote_does_not_send(self):
        self.live()
        run = self.analyze()
        def quote(code):
            self.gateway.pending = [dict(code=code,remaining=1)]
            return dict(price=100,volume=100)
        self.gateway.quote = quote
        self.execute(run, live_acknowledged=True)
        self.assertFalse(self.gateway.sent)

    def test_paper_order_appearing_during_quote_does_not_duplicate(self):
        run = self.analyze()
        def quote(code):
            self.paper.submit(client_id='manual',code=code,side='buy',quantity=1,limit_price=100)
            return dict(price=100,volume=100)
        self.paper.quote = quote
        self.execute(run)
        self.assertEqual(len(self.paper.snapshot()['orders']), 1)

    def test_stop_wins_concurrent_start(self):
        entered, release = threading.Event(), threading.Event()
        original = self.service.current_binding
        def delayed():
            entered.set()
            release.wait(5)
            return original()
        self.service.current_binding = delayed
        version = self.service.snapshot()['version']
        start = threading.Thread(target=lambda: self.service.control(version,'start'))
        start.start()
        self.assertTrue(entered.wait(3))
        stop = threading.Thread(target=lambda: self.service.control(version,'stop'))
        stop.start()
        for _ in range(100):
            if self.service.stop_epoch: break
            threading.Event().wait(.01)
        release.set()
        start.join(5)
        stop.join(5)
        self.assertFalse(start.is_alive())
        self.assertFalse(stop.is_alive())
        self.assertFalse(self.service.snapshot()['running'])

    def test_rejected_report_keeps_diagnostic_and_usage_without_orders(self):
        from backend.ai.providers import ReportValidationError
        issue=dict(code='005930',account='영업활동 현금흐름',field='rationale',text='비교 문장',reason='비교값 미확인')
        def rejected(*args): raise ReportValidationError(issue,dict(input_tokens=100,output_tokens=30))
        self.service.generate_fn=rejected
        run=self.analyze()
        self.assertEqual(run['status'],'error')
        self.assertEqual(run['validation_issue'],issue)
        self.assertEqual(run['usage'],dict(input_tokens=100,output_tokens=30))
        self.assertEqual(run['decisions'],[])
        self.assertFalse(self.gateway.sent)


if __name__ == '__main__': unittest.main()
