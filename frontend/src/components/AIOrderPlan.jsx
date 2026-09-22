const money = value => value == null ? '미확인' : `${value.toLocaleString('ko-KR')}원`
const CAPACITY = { exceeded: '조회 한도 초과', unverified: '매수 여력 미확인', within_snapshot: '조회 범위 이내', not_applicable: '주문 전 잔고 확인' }

export default function AIOrderPlan({ plan, processed }) {
  if (!plan) return null
  return <section className="paper-card aio-plan" aria-label="주문 계획 미리보기">
    <div className="aio-section-heading"><h3>주문 계획 미리보기</h3><span>분석 당시 기준 · {plan.rows.length}건</span></div>
    {!plan.rows.length ? <p className="paper-help">수량 변경 제안이 없습니다.</p> : <>
      <div className="aio-plan-totals">
        <div><span>예상 매수</span><strong>{money(plan.buy_amount)}</strong></div>
        <div><span>예상 매도</span><strong>{money(plan.sell_amount)}</strong></div>
        <div><span>매수 후 현금 (예상 증감)</span><strong><InlineNumber value={plan.cash_after_buys} unit="원" rate={percentChange(plan.cash_after_buys, plan.available_cash)} title="분석 당시 주문가능금액 대비 예상 변화 · 매도대금 제외" /></strong></div>
      </div>
      {plan.funding_status === 'shortfall' && <p className="aio-plan-alert" role="status">매수 제안 합계가 조회 현금을 {money(plan.shortfall)} 초과합니다.</p>}
      {plan.funding_status === 'unverified' && <p className="aio-plan-alert">가용 현금 또는 기준가가 미확인되어 전체 매수 여력을 계산할 수 없습니다.</p>}
      {plan.capacity_exceeded_count > 0 && <p className="aio-plan-alert">{plan.capacity_exceeded_count}종목이 조회 당시 주문가능 수량·금액을 초과합니다.</p>}
      {processed && <p className="aio-plan-alert">일부 제안은 이미 주문 처리되었습니다. 이 계획의 현금·수량은 처리 전 기준입니다.</p>}
      <details className="aio-fold"><summary>종목별 예상 금액·목표 비중</summary>
        <div className="aio-plan-scroll"><table className="aio-plan-table"><thead><tr><th>종목</th><th>제안</th><th>예상 금액</th><th>목표 비중</th><th>조회 당시 매수 여력</th></tr></thead>
          <tbody>{plan.rows.map(row => <tr key={row.code}><td><strong>{row.name}</strong><small>{row.code}</small></td><td>{row.side === 'buy' ? '매수' : '매도'} {row.quantity.toLocaleString()}주</td><td>{money(row.estimated_amount)}</td><td>{row.target_weight_pct == null ? '미확인' : `${row.target_weight_pct.toFixed(1)}%`}</td><td className={['exceeded', 'unverified'].includes(row.capacity_status) ? 'aio-plan-alert' : ''}>{CAPACITY[row.capacity_status]}</td></tr>)}</tbody>
        </table></div>
        <p className="paper-help">비중은 조회 계좌 총자산 대비 목표 수량의 평가액입니다. 기준가로 계산하며 수수료·세금·가격 변동은 포함하지 않습니다. 매수 여력은 종목별로 같은 현금을 공유합니다.</p>
      </details>
      <p className="paper-help">매도 예상대금은 매수 재원에 합산하지 않습니다. 실제 주문은 종목별로 새 시세·잔고 검증을 거칩니다.</p>
    </>}
  </section>
}
import InlineNumber from './InlineNumber'
import { percentChange } from '../lib/numberDisplay'
