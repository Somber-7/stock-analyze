"""Isolated UI fixture: generated analysis, account, prices and orders are all fake."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
import backend.main as main
import backend.ai.context as context
from backend.ai.operation import AIOperation
from backend.ai.operation_api import get_operation
from backend.ai.api import get_ai_settings
from backend.ai.settings import AISettings
from backend.ai.metrics import calculate_metrics
from backend.ai.dart import financial_summary
import backend.ai.dart_client as dart_client
import backend.ai.connection_check as connection_check
from backend.trading.api import get_service
from backend.trading.routes import get_engine
from backend.watch.api import get_watch
from backend.watch.service import WatchService
from backend.namuh import stocks
from manual_design_ui import DesignBroker, SYMBOLS, quote, chart, NOW
from backend.trading.live import TradingService
from backend.trading.paper import PaperEngine


def symbols(): return [dict(code=c,name=n) for c,n,p in SYMBOLS]


def reliability_chart(code, **_):
    rows=[]
    day=date(2026,6,1)
    while day<=date(2026,9,15):
        if day.weekday()<5:
            value=(30000 if code=='069500' else quote(code)['price']) + len(rows)*(20 if code=='069500' else -40 if code=='000660' else 40)
            rows.append(dict(time=day.isoformat(),open=value,high=value+10,low=value-10,close=value,volume=100000))
        day+=timedelta(days=1)
    return rows


def load(config, trading):
    return dict(stocks=[dict(code=c,name=quote(c)['name'],quote=quote(c),daily=chart(c),
                            metrics=calculate_metrics(chart(c)), account_weight_pct=0,
                            data_quality=dict(status='review' if c=='0011T0' else 'limited', requires_defer=c=='0011T0',
                                              completed_bars=60,requested_bars=130,data_date='2026-09-11',partial_bars=1,
                                              issues=['화면 검증용: 최근 확정 일봉을 확인하세요.'] if c=='0011T0' else ['요청 기간보다 확보 자료가 짧습니다.'],
                                              limitations='화면 검증용 가상 자료입니다.'),
                            buy_capacity=dict(amount=8000000,quantity=10,reference_price=quote(c)['price'],fetched_at=NOW)) for c in config['codes']],
                portfolio=dict(deposit_cash=0,available_cash=8000000,total_assets=10000000,net_assets=10000000,
                               holdings=[],other_assets=[],cma_balance=8000000,cash_balance=8000000,cash_management_assets=[dict(name='CMA 발행어음',eval_amount=8000000)],
                               assets_source='화면 검증용 가상 계좌',fetched_at=NOW),
                warnings=['화면 검증용 가상 자료입니다.'],fetched_at=NOW,investment_horizon=config.get('investment_horizon','unspecified'))


def generate(provider,key,model,context,objective):
    return dict(analysis=dict(summary='국내 반도체 종목은 가격 추세와 수급을 함께 확인할 필요가 있습니다. 보유 현금을 고려하여 소규모 편입을 제안합니다.',
                 risks=['단기 변동성과 미국 반도체 시장의 영향을 확인하세요.'],
                 decisions=[dict(code=s['code'],target_quantity=2 if s['code']=='005930' else 0,
                                 assessment='defer' if s['code']=='0011T0' else 'supported',
                                 market_view='negative' if s['code']=='0011T0' else 'positive' if s['code']=='005930' else 'mixed',
                                 decision_basis='preferences_missing' if s['code']=='0011T0' else 'sufficient',
                                 headline='가격 약세와 현금 유출은 확인되지만 축소 규모는 보유기간 확인 후 검토' if s['code']=='0011T0' else '추세·수급 개선을 근거로 소규모 편입 검토' if s['code']=='005930' else '신호가 엇갈려 현재 수량 유지',
                                 source_ids=[item['id'] for item in context.get('web_research',{}).get('sources',[]) if item['code']==s['code']],
                                 review_conditions='새 공시와 최근 20구간 수익률·거래량을 함께 확인하면 재검토합니다.',
                                 rationale='가상 자료에 근거한 화면 검증용 제안입니다.') for s in context['stocks']]),
                usage=dict(input_tokens=720,output_tokens=190))


def search(stocks,key,**kwargs):
    return dict(status='ready',fetched_at=NOW,usage_credits=2*len(stocks),requested_queries=2*len(stocks),cached_queries=0,searches=[],
                sources=[dict(id=s['code']+'-news-1',code=s['code'],kind='news',title=s['name']+' 검증용 뉴스',url='https://example.com/news',content='가상 검색 자료: 실제 투자 자료가 아닙니다.',published_at=NOW,fetched_at=NOW) for s in stocks])


def dart_research(stocks,key,**kwargs):
    rows=[]
    for stock in stocks:
        financials=financial_summary([dict(corp_code='00126380',bsns_year='2026',reprt_code='11012',rcept_no='20260814000001',
            sj_div='IS',account_id='ifrs-full_Revenue',account_nm='매출액',currency='KRW',thstrm_amount='120000000',thstrm_add_amount='210000000',
            frmtrm_q_amount='100000000',frmtrm_add_amount='190000000',thstrm_nm='제 57 기 반기',frmtrm_q_nm='제 56 기 반기')], '00126380','2026','11012','CFS')
        financials.update(period_end='2026-06',received_at='2026-08-14',fetched_at=NOW)
        rows.append(dict(code=stock['code'],name=stock['name'],status='partial',financials=financials,
                         disclosures=[dict(title='화면 검증용 반기보고서',receipt_no='20260814000001',received_at='2026-08-14',url=financials['url'])],warnings=['실제 재무자료가 아닌 화면 검증용 숫자입니다.']))
    return dict(status='partial',stocks=rows,sources=[],fetched_at=NOW,scope='화면 검증용 가상 DART 자료입니다.')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='stock-ai-qa-') as directory:
        base = Path(directory)
        broker = DesignBroker()
        paper = PaperEngine(base/'paper.db',quote)
        trading = TradingService(base/'live.db',paper,broker)
        if '--briefing' in sys.argv:
            trading.configure(mode='live',account='12345678',expected_version=trading.snapshot()['version'])
            broker.rows = [dict(broker_id='preview-1',code='005930',name='삼성전자',side='buy',price=70000,remaining=3)]
        ai = AISettings(base/'ai.enc',fetch_models=lambda *_: [dict(id='gpt-test',name='gpt-test')])
        ai.save('openai','gpt-test','sk-fake-ui-key-'+'x'*30,0)
        ai.save_tavily('tvly-fake-ui-key-'+'x'*30,ai.snapshot()['version'])
        dart_client.check_key=lambda key: None
        check_attempts=[]
        def tavily_check(key):
            check_attempts.append(1)
            if '--clarity' in sys.argv and len(check_attempts)==1:
                raise connection_check.ConnectionCheckError('Tavily API 키와 사용량 조회 권한을 확인하세요.')
        connection_check.check_tavily=tavily_check
        if '--clarity' in sys.argv:
            ai.check('openai',ai.snapshot()['version'])
            ai.save_dart('a'*40,True,ai.snapshot()['version'])
            ai.check_dart(ai.snapshot()['version'])
        def fixture_load(config,trading):
            result=load(config,trading)
            if '--reliability' in sys.argv:
                stamp='2026-08-14T08:00:00+00:00'
                result['fetched_at']=stamp
                result['portfolio']['fetched_at']=stamp
                for stock in result['stocks']:
                    stock['daily']=[r for r in reliability_chart(stock['code']) if r['time']<='2026-08-14']
                    stock['raw_daily']=stock['daily']
                    stock['metrics']=calculate_metrics(stock['daily'])
                    stock['data_quality'].update(status='checked',data_date='2026-08-14',requires_defer=False,issues=[])
                    stock['price_basis']=dict(balance_price=stock['quote']['price'],balance_at=stamp,
                        quote_price=stock['quote']['price'],quote_at=stamp,daily_close=stock['daily'][-1]['close'],daily_date='2026-08-14')
                    stock['buy_capacity']['diagnostic']=dict(stage='http',code='IGW40011',http_status=400) if stock['code']=='0011T0' else None
                result['benchmark']=dict(code='069500',name='KODEX 200',daily=[r for r in reliability_chart('069500') if r['time']<='2026-08-14'])
            return result
        operation = AIOperation(base/'operation.db',ai,trading,context_loader=fixture_load,generate_fn=generate,symbols_loader=symbols,research_fn=search,dart_fn=dart_research)
        observe=operation.observe
        operation.observe=lambda run_id: observe(run_id,chart_loader=reliability_chart)
        if '--seed' in sys.argv:
            operation.configure(operation.snapshot()['version'],execution='suggest',codes=['005930','000660','0011T0'],interval_minutes=30,objective='가격 추세와 웹 근거를 비교하는 가상 화면 검증',include_us=True,include_web=True,investment_horizon='medium')
            operation.analyze(operation.snapshot()['version'],background=False)
            operation.analyze(operation.snapshot()['version'],background=False)
            if '--reliability' in sys.argv:
                with operation.change() as state:
                    for run in state['runs']:
                        run.update(created_at='2026-08-14T08:00:00+00:00',completed_at='2026-08-14T08:00:30+00:00')
            if '--clarity' in sys.argv:
                with operation.change() as state:
                    old=state['runs'][0]
                    old['summary']='이전 형식의 분석 결과입니다. '+('가격과 재무자료를 점검한 긴 원문이 보존됩니다. '*18)
                    for d in old['decisions']:
                        for field in ('market_view','headline','decision_basis'): d.pop(field,None)
                        d['rationale']='이전 분석의 결론과 근거를 확인하세요. '+('당시 제공한 자료와 위험 요인을 비교한 원문입니다. '*20)
        operation.session_open = lambda: True
        operation.market_active = lambda code: True
        watch = WatchService(base/'watch.db',quote,lambda code: next((s for s in symbols() if s['code']==code),None))
        if '--briefing' in sys.argv:
            for stock in symbols()[:3]:
                watch.add(stock['code'])
                watch.quotes[stock['code']] = dict(price=quote(stock['code'])['price'],change_rate=1.32,retrieved_at=NOW)
            with watch.change() as state:
                state['alerts'].append(dict(code='005930',name='삼성전자',status='triggered',notified=True,threshold=70000,triggered_at=NOW))
        for dependency, service in ((get_engine,paper),(get_service,trading),(get_ai_settings,ai),(get_operation,operation),(get_watch,watch)):
            def fixed(value):
                return lambda: value
            main.app.dependency_overrides[dependency] = fixed(service)
        main.get_engine,main.get_service,main.get_operation,main.get_watch = lambda:paper,lambda:trading,lambda:operation,lambda:watch
        main.ensure_fresh = stocks.ensure_fresh = lambda **_: None
        context.stock_symbols = symbols
        main.search_stocks = lambda q: [s for s in symbols() if q in s['name'] or q in s['code']]
        stocks.get_snapshot = lambda:dict(stocks=symbols())
        main.get_accounts = broker.accounts
        main.get_balance = lambda account='': broker.balance(account)
        main.get_current_price = quote
        main.get_daily_chart = chart
        main.get_minute_chart = chart
        if '--numbers' in sys.argv:
            main.get_current_price = lambda code: dict(quote(code),change_rate={'005930':1.32,'000660':-.2,'0011T0':0}.get(code,1.32))
            main.get_top100 = lambda: dict(rows=[dict(code=code,name=name,market='KOSPI',rank=i+1,previous_close=price,previous_market_cap=100000,
                quote=dict(price=price,change_rate=[1.32,-.2,0][i],retrieved_at=NOW)) for i,(code,name,price) in enumerate(SYMBOLS[:3])],
                loading=False,refreshing=False,completed=3,next_refresh_seconds=30,downloaded_at=NOW)
            main.get_quote = lambda code: dict(price=184.53,change=-.37,change_rate=-.2,unit='pt' if code=='DJI' else 'USD',data_date='20260914',fetched_at=NOW)
            for i,(code,name,price) in enumerate(SYMBOLS[:3]):
                watch.add(code)
                watch.quotes[code] = dict(price=price,change_rate=[1.32,-.2,0][i],retrieved_at=NOW)
        uvicorn.run(main.app,host='127.0.0.1',port=int(sys.argv[1]) if len(sys.argv)>1 else 64567,log_level='warning')
