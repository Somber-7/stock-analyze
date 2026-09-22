import { useEffect, useRef, useState } from 'react'
import { AccountContext, DecisionMetrics, ResearchSources, DataQuality, AnalysisChanges } from './AIResultDetails'
import { HORIZONS } from '../lib/investmentHorizons'
import { timestamp } from '../lib/tradingApi'
import DartReport from './DartReport'
import AIOrderPlan from './AIOrderPlan'
import InlineNumber from './InlineNumber'
import AIOutcomeReport from './AIOutcomeReport'
import { aiOperationRequest } from '../lib/aiOperationApi'
import { showToast } from '../lib/toast'
import { excerpt, marketAssessment, quantityDecision } from '../lib/analysisReport'
import AIReportText from './AIReportText'

const fmt = (value, suffix = '') => value == null || !Number.isFinite(Number(value)) ? '미확인' : `${Number(value).toLocaleString('ko-KR')}${suffix}`
const seconds = ms => ms == null || !Number.isFinite(Number(ms)) ? '미확인' : `${(Number(ms) / 1000).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}초`
const STAGES = [['context_ms', '시세·잔고'], ['dart_ms', 'DART'], ['web_ms', '웹 검색'], ['model_ms', 'AI 응답']]
function RunTimings({ timings }) {
  if (!timings) return null
  const stages = STAGES.filter(([key]) => timings[key] != null).map(([key, label]) => `${label} ${seconds(timings[key])}`)
  return <>소요 {seconds(timings.total_ms)}{stages.length > 0 && ` (${stages.join(' · ')})`}<br /></>
}
function RecentTelemetry({ telemetry }) {
  const all = telemetry?.overall
  if (!all?.runs) return null
  return <p>최근 {fmt(all.runs, '회')} · 완료 {fmt(all.ready, '회')} · 실패 {fmt(all.error, '회')} · 중단 {fmt(all.interrupted, '회')}<br />소요 중앙값 {seconds(all.total_ms.p50)} · 95% {seconds(all.total_ms.p95)} (AI 응답 중앙값 {seconds(all.model_ms.p50)}, 기록 {fmt(all.total_ms.samples, '회')})<br />회당 토큰 입력 {fmt(all.input_tokens.per_run)} · 출력 {fmt(all.output_tokens.per_run)}</p>
}
const lines = value => Array.isArray(value) ? value : value ? [value] : []
const SIDES = { buy: '매수', sell: '매도', hold: '유지' }
const STATUSES = { analyzing: '분석 중', ready: '분석 완료', error: '분석 오류', interrupted: '분석 중단' }
const ORDER_STATUSES = { submitted: '주문 접수', accepted: '주문 접수', filled: '체결', pending: '처리 중', sending: '전송 준비', executing: '처리 중', rejected: '주문 거절', error: '오류', failed: '실패', skipped: '보류', unknown: '접수 확인 필요', uncertain: '접수 확인 필요' }

function RunInputRecord({ run }) {
  const [loading, setLoading] = useState(false)
  const request = useRef(null)
  useEffect(() => () => request.current?.abort(), [run.id])
  async function download() {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    try {
      const snapshot = await aiOperationRequest(`/runs/${encodeURIComponent(run.id)}/inputs`, undefined, controller.signal)
      if (controller.signal.aborted || request.current !== controller) return
      const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url; link.download = `analysis-input-${run.id}.json`; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch (e) { if (!controller.signal.aborted && request.current === controller) showToast(e.message, { tone: 'error' }) }
    finally { if (!controller.signal.aborted && request.current === controller) { request.current = null; setLoading(false) } }
  }
  const config = run.analysis_config
  return <details className="aio-fold"><summary>분석 입력 기록 <small>{run.input_record?.stored ? '원본 보관됨' : '이전 형식'}</small></summary>
    {run.input_record?.stored ? <><p className="paper-help">스키마 {run.input_record.schema_version ?? '미확인'} · 검증값 {run.input_record.sha256 || '미확인'} · 전체 입력은 자동으로 불러오지 않습니다.</p><button type="button" disabled={loading} onClick={download}>{loading ? '다운로드 준비 중…' : '분석 당시 원본 자료 다운로드'}</button></> : <p className="paper-help">이 분석에는 저장된 분석 당시 원본 자료가 없습니다.</p>}
    {config && <dl className="aio-data-grid"><div><dt>투자기간</dt><dd>{HORIZONS[config.investment_horizon] || '미지정'}</dd></div><div><dt>보유 목적</dt><dd>{config.holding_purpose || '미지정'}</dd></div><div><dt>종목 최대 비중</dt><dd>{fmt(config.max_position_pct, '%')}</dd></div><div><dt>재검토 낙폭</dt><dd>{fmt(config.review_drawdown_pct, '%')}</dd></div></dl>}
    {config && <p className="paper-help">보유 목적과 위험 기준은 분석 참고값이며 실행 주문 제한이 아닙니다.</p>}
  </details>
}

export default function AIAnalysisReport({ run, names, state, expired, hasOrderProposals, canExecute, manualLive, liveAck, setLiveAck, locked, action, onOrders, onExecute }) {
  const decisions = run.decisions || []
  const risks = lines(run.risks)
  const warnings = lines(run.warnings)
  return <div className="aio-report" aria-busy={run.status === 'analyzing'}>
    <div className="aio-report-status"><span className={`aio-badge ${run.status === 'ready' ? 'active' : ''}`}>{STATUSES[run.status] || run.status}</span><span>{timestamp(run.created_at)} · {run.mode === 'live' ? '실전' : '모의'} · {run.source === 'auto' ? '자동' : '직접 분석'}</span></div>
    {run.status === 'analyzing' && <div className="paper-card aio-progress" role="status"><span className="aio-state-dot active" /><div><h3>분석 자료를 살펴보고 있습니다</h3><p>시장 자료·웹 검색·모델 응답을 기다리고 있습니다. 완료되면 자동으로 표시됩니다.</p></div></div>}
    {run.error && <div className="aio-feedback aio-error" role="alert">{run.error}</div>}
    {run.status === 'error' && run.validation_issue && <details className="aio-fold"><summary>검증 상세 · {run.validation_issue.code} · {run.validation_issue.account}</summary><p className="paper-help">{run.validation_issue.reason} · 항목 {run.validation_issue.field}</p><AIReportText text={run.validation_issue.text} /><p className="paper-help">검증에서 채택되지 않은 문장입니다. 주문 제안으로 사용하지 않습니다.</p></details>}
    {run.status === 'ready' && <>
      <div className="aio-context-line aio-comparison-status"><span>{run.comparison ? `지난 분석 대비 판단·목표 변경 ${run.comparison.changed_count}종목` : '같은 계좌·분석 조건으로 비교 가능한 이력이 없습니다.'}</span>{run.comparison && <small>비교 기준 {timestamp(run.comparison.completed_at)} · {run.comparison.provider} / {run.comparison.model}</small>}</div>
      {decisions.some(d => d.quality_override) && <p className="aio-quality-note" role="status">자료 검증으로 {decisions.filter(d => d.quality_override).length}종목 평가 미확인 · 종목별 최종 판단을 확인하세요.</p>}
      <div className="aio-kpis"><div><span>계좌 총자산</span><strong>{fmt(run.portfolio?.total_assets, '원')}</strong><small>{run.portfolio?.allocation?.cash_weight_pct != null ? `현금성 자산 ${Number(run.portfolio.allocation.cash_weight_pct).toFixed(2)}% · 잔고 기준` : '계좌 조회 시점 기준'}</small></div><div><span>주문가능금액</span><strong>{fmt(run.portfolio?.available_cash, '원')}</strong><small>조회 시점의 매수 여력</small></div><div><span>분석 종목</span><strong>{decisions.length}<em>종목</em></strong><small>수량 결정 보류 {decisions.filter(d=>d.assessment === 'defer').length}종목</small></div><div><span>투자기간</span><strong className="aio-kpi-horizon">{HORIZONS[run.investment_horizon] || '미지정'}</strong><small>분석 자료 {timestamp(run.data_at)}</small></div></div>
      {run.summary && <section className="paper-card aio-overview"><h3>핵심 요약</h3><AIReportText text={run.summary} limit={220} label="요약 전체 읽기" /></section>}
      <section className="paper-card aio-decision-list"><div className="aio-section-heading"><h3>종목별 평가</h3><span>가격·재무 평가와 수량 결정을 구분합니다.</span></div>
        <div className="aio-decision-columns" aria-hidden="true"><span>종목 · 핵심 평가</span><span>수량 결정 · 현재 → 목표</span><span>기준가 · 지난 분석 대비</span><span /></div>
        {decisions.map(decision => {
          const market = marketAssessment(decision)
          const quantity = quantityDecision(decision)
          const headline = decision.headline || excerpt(decision.rationale, 100).text
          return <details className="aio-stock-decision" key={decision.code}>
          <summary className="aio-decision-row"><span className="aio-stock-brief"><span className="aio-stock-identity"><strong>{decision.name || names[decision.code] || decision.code}</strong><span className={`aio-market-view ${market.key}`}>{market.label}</span><small>{decision.code}{decision.account_weight_pct != null && ` · 계좌 ${Number(decision.account_weight_pct).toFixed(2)}%`}</small></span>{headline && <span className="aio-stock-headline">{headline}</span>}</span><span className="aio-quantity-decision"><span className={`aio-quantity-label ${quantity.tone}`}>{quantity.label}</span>{quantity.reason && <span className="aio-basis-label">{quantity.reason}</span>}<span className="aio-quantity-change"><span className="aio-before-quantity">{fmt(decision.current_quantity)}</span> → <InlineNumber value={decision.target_quantity} unit="주" direction={decision.assessment === 'defer' ? 0 : decision.target_quantity - decision.current_quantity} /></span></span><span className="aio-reference-price"><small>조회 기준가 · 지난 분석 대비</small><InlineNumber value={decision.reference_price} unit="원" rate={decision.comparison?.price_change_pct} title="지난 분석의 조회 기준가 대비 · 확정 일봉 종가와 다를 수 있습니다" /></span><span className="aio-row-chevron" aria-hidden="true">⌄</span></summary>
          <div className="aio-decision-body"><h4>평가 근거</h4><AIReportText text={decision.rationale} />
            {(decision.review_conditions || decision.review_points?.length > 0) && <div className="aio-review-conditions"><h4>재검토</h4>{decision.review_points?.map(point => <p key={point.window} className="aio-review-level">종가의 {point.window}봉 평균 {point.direction === 'above' ? '상회' : '하회'} 전환 · <InlineNumber value={point.level} unit="원" /></p>)}{!!decision.review_points?.length && <small>{decision.review_points[0].data_date} 계산값 · 다음 분석 시 갱신 · 주문 조건 아님</small>}<AIReportText text={decision.review_conditions} limit={160} label="재검토 조건 전체 읽기" /></div>}
            <details className="aio-fold aio-stock-evidence"><summary>지표·자료·출처 확인</summary>
            {decision.assessment === 'defer' && <p className="paper-help">수량 변경을 유보한 상태입니다. 가격·재무 평가와 주문 실행 여부는 별개이며, 유보는 보유가 유리하다는 뜻이 아닙니다.</p>}
            {!decision.assessment && <p className="paper-help">이전 형식의 분석입니다. 유지·판단 유보 구분은 새 분석부터 적용됩니다.</p>}
            <AnalysisChanges decision={decision} /><DataQuality quality={decision.data_quality} /><DecisionMetrics decision={decision} />{run.dart_research?.status === 'disabled' ? <p className="paper-help">DART 재무·공시 조회를 사용하지 않은 분석입니다.</p> : <DartReport research={run.dart_research} code={decision.code} ids={decision.source_ids || []} />}<ResearchSources research={run.web_research} ids={decision.source_ids || []} />
            </details>
            {decision.execution ? <div className="aio-execution"><strong>{ORDER_STATUSES[decision.execution.status] || decision.execution.status}</strong><span>{decision.execution.message}</span>{decision.execution.price != null && <span>주문 지정가 {fmt(decision.execution.price,'원')}</span>}{decision.execution.order_id && <small>주문 ID {decision.execution.order_id}</small>}</div> : decision.side !== 'hold' && decision.assessment !== 'defer' && <div className="aio-order-action"><span>{manualLive ? '실전' : '모의'} · {SIDES[decision.side]} {fmt(decision.quantity,'주')}</span><button disabled={!canExecute} className={manualLive ? 'paper-danger' : ''} onClick={()=>onExecute(decision)}>{action === `execute-${decision.code}` ? '주문 요청 중…' : `${manualLive ? '실전' : '모의'} ${SIDES[decision.side]} 주문`}</button></div>}
          </div>
        </details>})}
        {hasOrderProposals && <div className="aio-order-status">
          {expired && <p className="aio-warning">제안 유효기간 5분이 지났습니다. 주문하려면 다시 분석하세요.</p>}
          {state.running && <p className="aio-warning">자동 운용 중에는 개별 주문을 실행할 수 없습니다.</p>}
          {!state.engine_running && <p className="aio-warning">주문 엔진이 정지되어 있습니다. 주문 화면에서 시작한 뒤 다시 분석하세요.</p>}
          {manualLive && <label className="aio-check aio-live-ack"><input type="checkbox" checked={liveAck} disabled={locked} onChange={event=>setLiveAck(event.target.checked)} /><span>개별 실전 주문을 실행하면 실제 계좌로 전송됨을 확인했습니다.</span></label>}
          <button onClick={onOrders}>주문 화면 열기 →</button>
        </div>}
      </section>
      {!!run.order_plan?.rows?.length && <details className="aio-fold"><summary>주문 계획 미리보기 <small>{run.order_plan.rows.length}건</small></summary><AIOrderPlan plan={run.order_plan} processed={decisions.some(d => d.execution)} /></details>}
      <details className="aio-fold aio-report-evidence"><summary>위험·분석 자료 <small>위험 {risks.length} · 참고 {warnings.length}</small></summary>
        <div className="aio-evidence-grid"><div>{risks.length > 0 && <details className="aio-fold"><summary>주요 위험 <small>{risks.length}건</small></summary><ul>{risks.map((item,i)=><li key={i}>{item}</li>)}</ul></details>}{warnings.length > 0 && <details className="aio-fold"><summary>데이터 누락·참고 <small>{warnings.length}건</small></summary><ul>{warnings.map((item,i)=><li key={i}>{item}</li>)}</ul></details>}<details className="aio-fold"><summary>평가·수량 결정 읽는 법</summary><p>가격·재무가 부정적이어도 매도 주문이 자동으로 생기지 않습니다. 투자조건 미지정, 자료 부족, 근거 상충, 주문 조건 미확인은 서로 다른 사유입니다. 평가 미확인은 중립 평가가 아니며, 미분류는 평가 항목이 없는 이전 기록입니다.</p></details></div><div><details className="aio-fold"><summary>계좌 자산 상세</summary><AccountContext portfolio={run.portfolio} horizon={run.investment_horizon} /></details><RunInputRecord run={run} />{run.dart_research?.status === 'disabled' ? <details className="aio-metrics"><summary>DART 재무·공시 · 조회 안 함</summary><p className="paper-help">이 분석은 DART 자료 없이 생성되었습니다.</p></details> : <DartReport research={run.dart_research} />}{run.web_research ? <ResearchSources research={run.web_research} /> : <p className="paper-help">웹 검색을 포함하지 않은 분석입니다.</p>}</div></div>
      </details>
      <AIOutcomeReport runId={run.id} inputRecord={run.input_record} initialOutcome={run.outcomes} />
    </>}
    <details className="aio-fold aio-footnote"><summary>실행 정보·주문 조건</summary><p>{run.provider} · {run.model}<br />요청 {timestamp(run.created_at)} · 완료 {timestamp(run.completed_at)}<br />분석 자료 조회 {timestamp(run.data_at)}<br /><RunTimings timings={run.timings} />토큰 입력 {fmt(run.usage?.input_tokens)} · 출력 {fmt(run.usage?.output_tokens)}</p><RecentTelemetry telemetry={state?.telemetry} /><p>제안은 요청 시점부터 5분간 유효합니다. 주문 직전 새 시세를 지정가로 사용하며, 기준가 대비 3% 초과 변동이나 시세 재조회 후 30초 초과 시 전송을 중단합니다. 정지는 이미 접수된 주문을 취소하지 않습니다.</p></details>
  </div>
}
