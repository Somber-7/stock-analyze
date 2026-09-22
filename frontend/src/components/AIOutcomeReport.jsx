import { useEffect, useRef, useState } from 'react'
import { aiOperationRequest } from '../lib/aiOperationApi'
import { timestamp } from '../lib/tradingApi'
import { showToast } from '../lib/toast'
import InlineNumber from './InlineNumber'

const fmt = (value, suffix = '') => value == null || !Number.isFinite(Number(value)) ? '—' : `${Number(value).toLocaleString('ko-KR')}${suffix}`
const horizonStatus = { complete: '관측 완료', pending: '관측 대기', unavailable: '관측 불가' }
const reason = value => ({
  immutable_input_snapshot_missing: '분석 당시 원본 자료가 없습니다.',
  invalid_evaluation_time: '관측 기준 시각을 확인할 수 없습니다.',
  snapshot_baseline_missing: '분석 당시 원본 자료에서 기준 종가를 찾을 수 없습니다.',
  snapshot_baseline_invalid: '완료된 장의 유효한 기준 종가가 아닙니다.',
  stock_observation_unavailable: '종목의 미래 종가를 확인할 수 없습니다.',
  benchmark_observation_unavailable: 'ETF 참고 가격을 확인할 수 없습니다.',
  series_missing: '가격 시계열을 불러오지 못했습니다.',
  invalid_bar: '유효하지 않은 일봉 자료가 포함되어 있습니다.',
  conflicting_duplicate_date: '같은 날짜의 일봉 값이 서로 다릅니다.',
  series_coverage_missing: '기준일을 포함하는 가격 자료가 없습니다.',
  baseline_price_changed: '현재 자료의 기준 종가가 분석 당시 값과 달라 비교할 수 없습니다.',
  insufficient_subsequent_observations: '아직 필요한 거래 관측 수가 쌓이지 않았습니다.',
  exact_baseline_date_missing: 'ETF 참고값에 같은 기준일 자료가 없습니다.',
  exact_end_date_missing: 'ETF 참고값에 같은 종료일 자료가 없습니다.',
}[value] || (value ? '가격 관측 자료를 확인할 수 없습니다.' : ''))

export default function AIOutcomeReport({ runId, inputRecord, initialOutcome }) {
  const [refreshedOutcome, setRefreshedOutcome] = useState(null)
  const [loading, setLoading] = useState(false)
  const request = useRef(null)

  useEffect(() => () => { request.current?.abort() }, [runId])
  const savedAt = Date.parse(initialOutcome?.evaluated_at || '')
  const refreshedAt = Date.parse(refreshedOutcome?.evaluated_at || '')
  const outcome = !refreshedOutcome || (Number.isFinite(savedAt) && (!Number.isFinite(refreshedAt) || savedAt > refreshedAt)) ? initialOutcome : refreshedOutcome

  async function refresh() {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    try {
      const result = await aiOperationRequest(`/runs/${encodeURIComponent(runId)}/outcomes`, {}, controller.signal)
      if (!controller.signal.aborted && request.current === controller) setRefreshedOutcome(result)
    } catch (e) {
      if (!controller.signal.aborted && request.current === controller) showToast(e.message, { tone: 'error' })
    } finally {
      if (!controller.signal.aborted && request.current === controller) { request.current = null; setLoading(false) }
    }
  }

  return <details className="aio-fold aio-outcomes"><summary>분석 후 가격 관측 <small>{outcome ? `방향 판단 ${outcome.counts?.directional_eligible ?? 0}건` : '수동 조회'}</small></summary>
    <p className="paper-help">분석 당시 원본 자료의 기준 종가 이후 5·20·60 거래 관측치를 비교합니다. 실제 주문·체결이나 실제 운용 수익률이 아닙니다.</p>
    {!inputRecord?.stored && <p className="aio-warning">이전 분석에는 분석 당시 원본 자료가 없어 사후 검증을 계산할 수 없습니다.</p>}
    <button type="button" disabled={loading || !inputRecord?.stored} onClick={refresh}>{loading ? '가격 관측 조회 중…' : outcome ? '가격 관측 새로고침' : '가격 관측 조회'}</button>
    {outcome && <div className="aio-outcome-content">
      <p className="paper-help">관측 {timestamp(outcome.evaluated_at)} · 일봉 종가 · 수정주가 적용 미확인 · {outcome.benchmark?.name || '국내 ETF'}는 지수 수익률이 아닌 ETF 참고값입니다.</p>
      <p className="paper-help">전체 {fmt(outcome.counts?.total)} · 판단 가능 {fmt(outcome.counts?.supported)} · 판단 유보 {fmt(outcome.counts?.deferred)} · 방향 판단 {fmt(outcome.counts?.directional_eligible)}</p>
      {outcome.reason && <p className="aio-warning">{reason(outcome.reason)}</p>}
      {(outcome.items || []).map(item => <details className="aio-metrics" key={item.code}><summary>{item.name || item.code} · {item.assessment === 'defer' ? '판단 유보' : item.status === 'unavailable' ? '관측 불가' : '미래 종가 관측'}</summary>
        <p className="paper-help">기준 {item.baseline ? `${item.baseline.date} · ${fmt(item.baseline.close, '원')}` : '없음'}{item.reason ? ` · ${reason(item.reason)}` : ''}</p>
        {!!item.horizons?.length && <div className="aio-plan-scroll"><table className="aio-plan-table aio-outcome-table"><thead><tr><th>관측 구간</th><th>상태</th><th>종목 변동</th><th>최대 낙폭</th><th title="매수 판단은 상승, 매도 판단은 하락을 양수로 표시합니다.">판단 방향*</th><th>ETF 참고</th><th>초과 변동</th></tr></thead><tbody>{item.horizons.map(row => <tr key={row.observations}><td>{row.observations}거래 관측<small>{row.end_date || `${row.available_observations ?? 0}/${row.observations}개 확보`}</small></td><td>{horizonStatus[row.status] || row.status}<small>{reason(row.reason)}</small></td><td><InlineNumber value={row.return_pct} unit="%" signed /></td><td><InlineNumber value={row.max_drawdown_pct} unit="%" signed /></td><td><InlineNumber value={row.directional_return_pct} unit="%" signed /></td><td><InlineNumber value={row.benchmark_return_pct} unit="%" signed /><small>{reason(row.benchmark_reason)}</small></td><td><InlineNumber value={row.excess_return_pp} unit="%p" signed /></td></tr>)}</tbody></table><p className="paper-help">* 매수 판단은 상승, 매도 판단은 하락을 양수로 표시합니다.</p></div>}
      </details>)}
      {!!outcome.limitations?.length && <ul className="paper-help">{outcome.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>}
    </div>}
  </details>
}
