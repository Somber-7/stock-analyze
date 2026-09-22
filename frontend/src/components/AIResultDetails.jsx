import { timestamp } from '../lib/tradingApi'
import { HORIZONS } from '../lib/investmentHorizons'
import InlineNumber from './InlineNumber'

const fmt = (value, suffix = '') => value == null || !Number.isFinite(Number(value)) ? '미확인' : `${Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}${suffix}`
const capacityReason = diagnostic => {
  if (!diagnostic) return null
  const labels = { unauthorized: '인증 정보를 확인할 수 없음', forbidden: '조회 권한이 없음', rate_limited: '조회 요청 한도를 초과함', timeout: '조회 시간이 초과됨', unavailable: '증권사 조회 서비스를 사용할 수 없음', invalid_response: '조회 응답 형식을 확인할 수 없음', missing: '주문가능금액 자료가 없음' }
  const stages = { auth: '인증 단계에서 확인하지 못함', http: '증권사 HTTP 요청이 실패함', transport: '증권사 연결에 실패함', decode: '증권사 응답을 해석하지 못함', business: '증권사에서 조회를 거절함', fields: '주문가능금액 필드를 확인하지 못함', input: '조회 입력을 확인할 수 없음' }
  return labels[diagnostic.code] || stages[diagnostic.stage] || '주문가능금액 조회에서 확인하지 못함'
}

export function AnalysisChanges({ decision }) {
  const c = decision.comparison
  if (!c) return null
  return <details className="aio-metrics"><summary>지난 분석 대비 · {c.changed ? '판단·목표 변경' : '판단·목표 동일'}</summary>
    {c.previous_market_view && <p className="paper-help">가격·재무 평가: {({ positive:'긍정적',negative:'부정적',mixed:'엇갈림',unknown:'자료 미확인' })[c.previous_market_view] || '미분류'} → {({ positive:'긍정적',negative:'부정적',mixed:'엇갈림',unknown:'자료 미확인' })[decision.market_view] || '미분류'}</p>}
    <dl className="aio-data-grid"><div><dt>목표 수량</dt><dd>{fmt(c.previous_target, '주')} → <InlineNumber value={decision.target_quantity} unit="주" direction={c.target_delta} /></dd></div><div><dt>기준가 (지난 분석 대비)</dt><dd><InlineNumber value={decision.reference_price} unit="원" rate={c.price_change_pct} /></dd></div><div><dt>보유 수량 변화</dt><dd><InlineNumber value={c.holding_delta} unit="주" signed /></dd></div><div><dt>이전 판단 상태</dt><dd>{c.previous_assessment === 'defer' ? '판단 유보' : c.previous_assessment === 'supported' ? '판단 가능' : '미확인'}</dd></div></dl>
    {c.previous_conditions && <p className="paper-help">이전 재검토 조건: {c.previous_conditions}</p>}
    <p className="paper-help">분석 시점의 기준가 비교이며 실제 체결·운용 수익률이 아닙니다.</p>
  </details>
}

export function DataQuality({ quality }) {
  if (!quality) return null
  return <details className="aio-metrics"><summary>자료 상태 · {{ checked: '기본 검사 통과', limited: '기간 자료 부족', review: '확인 필요' }[quality.status] || '미확인'}</summary>
    <p className="paper-help">확정 일봉 {quality.completed_bars ?? '—'} / 요청 {quality.requested_bars ?? '—'}개 · 기준일 {quality.data_date || '미확인'}{quality.partial_bars > 0 && ` · 장중 봉 ${quality.partial_bars}개 제외`}</p>
    {!!quality.issues?.length && <ul>{quality.issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul>}
    <p className="paper-help">{quality.limitations}</p>
  </details>
}

export function AccountContext({ portfolio, horizon }) {
  if (!portfolio) return null
  return <div className="aio-account-context">
    <h4>분석에 사용한 계좌 자산</h4>
    <dl className="aio-data-grid">
      <div><dt>API 예수금 (CMA 제외)</dt><dd>{fmt(portfolio.deposit_cash, '원')}</dd></div>
      <div><dt>CMA 현금성 잔액</dt><dd>{fmt(portfolio.cma_balance, '원')}</dd></div>
      <div><dt>예수금 + CMA 잔액</dt><dd>{fmt(portfolio.cash_balance, '원')}</dd></div>
      <div><dt>100% 주문가능금액</dt><dd>{fmt(portfolio.available_cash, '원')}</dd></div>
      <div><dt>조회 계좌 총자산</dt><dd>{fmt(portfolio.total_assets, '원')}</dd></div>
      <div><dt>조회 계좌 순자산</dt><dd>{fmt(portfolio.net_assets, '원')}</dd></div>
    </dl>
    <p className="paper-help">투자기간: {HORIZONS[horizon] || '미지정'} · 계좌 조회 {timestamp(portfolio.fetched_at)}</p>
    {!!portfolio.cash_management_assets?.length && <p className="paper-help">{portfolio.cash_management_assets.map(asset => asset.name).join(', ')}: 계좌에서 현금으로 운용하는 잔액입니다. 총자산에 포함된 금액으로 별도 가산하지 않으며, 실제 매수 여력은 주문가능금액으로 확인합니다.</p>}
    {!!portfolio.other_assets?.length && <details><summary>기타 보유 자산 {portfolio.other_assets.length}개</summary><ul>{portfolio.other_assets.map((asset, index) => <li key={index}>{asset.name} · {fmt(asset.eval_amount, '원')}</li>)}</ul><p className="paper-help">매매 대상에서 제외하며 평가액을 주문가능금액에 더하지 않습니다.</p></details>}
    <p className="paper-help">{portfolio.assets_source} 기준입니다. 총자산과 순자산은 별도 값이며 계좌 밖 자산은 포함하지 않습니다. 종목별 주문가능금액은 합산할 수 없습니다.</p>
  </div>
}

export function DecisionMetrics({ decision }) {
  const m = decision.metrics
  const capacity = decision.buy_capacity
  const prices = decision.price_basis
  if (!m && !capacity) return null
  return <details className="aio-metrics"><summary>정량 지표·주문가능금액 확인</summary>
    <dl className="aio-data-grid">
      <div><dt>계좌 총자산 대비 비중</dt><dd>{fmt(decision.account_weight_pct, '%')}</dd></div>
      <div><dt>종목별 현금 주문가능금액</dt><dd>{fmt(capacity?.amount, '원')}</dd></div>
      <div><dt>기준가에서 매수 가능</dt><dd>{fmt(capacity?.quantity, '주')}</dd></div>
      {prices && <><div><dt>잔고 평가가</dt><dd>{fmt(prices.balance_price, '원')}<small>{prices.balance_at ? ` · 잔고 ${timestamp(prices.balance_at)}` : ''}</small></dd></div><div><dt>조회 시세</dt><dd>{fmt(prices.quote_price, '원')}<small>{prices.quote_at ? ` · 조회 ${timestamp(prices.quote_at)}` : ''}{prices.quote_trade_time ? ` · 체결 ${timestamp(prices.quote_trade_time)}` : ' · 체결 시각 미확인'}</small></dd></div><div><dt>확정 일봉 종가</dt><dd>{fmt(prices.daily_close, '원')}<small>{prices.daily_date ? ` · ${prices.daily_date}` : ' · 기준일 미확인'}</small></dd></div><div><dt>비중 평가 기준</dt><dd>{{ balance_price: '잔고 평가가', quote_price: '조회 시세', daily_close: '확정 일봉 종가' }[prices.valuation_basis] || prices.valuation_basis || '미확인'}</dd></div></>}
      {m && <><div><dt>최근 5구간 수익률</dt><dd>{fmt(m.return_5_pct, '%')}</dd></div><div><dt>최근 20구간 수익률</dt><dd>{fmt(m.return_20_pct, '%')}</dd></div><div><dt>20봉 / 60봉 이동평균</dt><dd>{fmt(m.sma_20, '원')} / {fmt(m.sma_60, '원')}</dd></div><div><dt>20구간 일간 변동성</dt><dd>{fmt(m.daily_volatility_20_pct, '%')}</dd></div><div><dt>직전 20봉 대비 거래량</dt><dd>{fmt(m.volume_ratio_20, '배')}</dd></div></>}
    </dl>
    {m && (m.return_60_pct != null || m.sma_120 != null) && <dl className="aio-data-grid"><div><dt>60구간 수익률</dt><dd>{fmt(m.return_60_pct, '%')}</dd></div><div><dt>120구간 수익률</dt><dd>{fmt(m.return_120_pct, '%')}</dd></div><div><dt>240구간 수익률</dt><dd>{fmt(m.return_240_pct, '%')}</dd></div><div><dt>120봉 이동평균</dt><dd>{fmt(m.sma_120, '원')}</dd></div></dl>}
    {m && <><p className="paper-help">일봉 기준 {m.data_date || '미확인'} · 유효 일봉 {m.bars}개</p><p className="paper-help">{m.method}</p><ul className="paper-help">{[['foreign', '외국인'], ['institutional', '기관']].map(([key, label]) => { const flow = m.flows?.[key]; return flow && <li key={key}>{label}: {flow.data_date || '일자 미확인'} 기준 {flow.window_rows}개 행 중 유효 {flow.observations}개 · 순매수 {flow.positive_days}일 · 최근 연속 {fmt(flow.latest_buy_streak, '일')}</li> })}</ul></>}
    {capacityReason(capacity?.diagnostic) && <p className="aio-warning">매수 가능 수량 미확인: {capacityReason(capacity.diagnostic)}{capacity.diagnostic.http_status ? ` · HTTP ${capacity.diagnostic.http_status}` : ''}{capacity.diagnostic.code ? ` · 코드 ${capacity.diagnostic.code}` : ''}</p>}
    <p className="paper-help">주문가능금액 조회 {timestamp(capacity?.fetched_at)} · 분석 시점의 참고 값이며 실제 주문 직전에 다시 검증합니다.</p>
  </details>
}

function sourceLink(source) {
  try {
    const url = new URL(source.url)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

export function ResearchSources({ research, ids }) {
  if (!research) return null
  const sources = (research.sources || []).filter(source => (!ids || ids.includes(source.id)) && sourceLink(source))
  if (ids && !sources.length) return null
  return <details className="aio-metrics aio-web-sources"><summary>{ids ? `참고 출처 ${sources.length}개` : `웹 검색 자료 ${sources.length}개 · ${{ ready: '조회 완료', partial: '일부 조회 실패', empty: '자료 없음' }[research.status] || '확인 필요'}`}</summary>
    {!ids && <><p className="paper-help">Tavily 사용 {fmt(research.usage_credits, ' 크레딧')} · 검색 {fmt(research.requested_queries, '건')} · 캐시 {fmt(research.cached_queries, '건')} · 조회 {timestamp(research.fetched_at)}</p><p className="paper-help">검색 발췌 자료이며 원문 전체나 검증된 재무제표를 뜻하지 않습니다. 관련성·게시일·본문을 확인한 자료만 남기며, 일부 누락이 있으면 상태를 일부 조회 실패로 표시합니다.</p>{Object.entries(research.diagnostics?.rejected || {}).map(([reason, amount]) => <p className="paper-help" key={reason}>제외 {reason}: {fmt(amount, '건')}</p>)}{(research.diagnostics?.missing || []).map((item, i) => <p className="aio-warning" key={`${item.code}-${item.kind}-${i}`}>{item.code} · {item.kind}: {item.reason || '관련 자료 없음'}</p>)}{(research.searches || []).filter(query => query.status === 'error').map((query, i) => <p className="aio-warning" key={i}>{query.code} · {query.error || '검색 실패'}</p>)}</>}
    <ul>{sources.map(source => <li key={source.id}><a href={sourceLink(source)} target="_blank" rel="noopener noreferrer">{source.title}</a><p className="paper-help">{source.kind === 'reports' ? '공시·기업 자료' : '뉴스'} · 게시 {source.published_at ? timestamp(source.published_at) : '일자 미확인'} · 수집 {timestamp(source.fetched_at)}</p>{!ids && <p>{source.content}</p>}</li>)}</ul>
  </details>
}
