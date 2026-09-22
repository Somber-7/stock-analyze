import { timestamp } from '../lib/tradingApi'
import InlineNumber from './InlineNumber'
import { percentChange } from '../lib/numberDisplay'

const value = (number, currency) => number == null ? '미확인' : `${Number(number).toLocaleString('ko-KR')} ${currency === 'KRW' ? '원' : currency || '(통화 미확인)'}`
const link = url => /^https:\/\/dart\.fss\.or\.kr\/dsaf001\/main\.do\?rcpNo=\d{14}$/.test(url || '') ? url : null

export default function DartReport({ research, code, ids = [] }) {
  if (!research) return null
  if (!code) return <details className="aio-metrics"><summary>DART 재무·공시 · {research.status === 'ready' ? '조회 완료' : research.status === 'error' ? '조회 실패' : '일부 자료 미확인'}</summary><p className="paper-help">{research.error || research.scope || '종목별 상세에서 재무 수치와 공시 목록을 확인하세요.'}</p><p className="paper-help">조회 {timestamp(research.fetched_at)} · 재무 수치와 공시 목록은 종목별 상세에서 확인할 수 있습니다.</p></details>
  const stock = research.stocks?.find(item => item.code === code)
  const financials = stock?.financials
  return <details className="aio-metrics aio-dart-report"><summary>DART 재무·공시 · {financials?.period_end || '재무자료 미확인'}</summary>
    {(stock?.warnings || [research.error]).filter(Boolean).map((warning, index) => <p className="paper-help" key={index}>{warning}</p>)}
    {financials && <><p className="paper-help">{financials.period_end} · {financials.fs_div === 'CFS' ? '연결 재무제표' : '별도 재무제표'} · 접수 {financials.received_at}</p>
      <dl className="aio-data-grid">{financials.accounts.map(account => <div key={account.name}><dt>{account.name} · {account.period_basis}</dt><dd><InlineNumber value={account.amount} unit={` ${account.currency === 'KRW' ? '원' : account.currency || '(통화 미확인)'}`} rate={account.currency && account.comparison_name ? percentChange(account.amount, account.comparison_amount) : null} title={`비교 기간 ${account.comparison_name || '미확인'} 대비 증감률`} /></dd><dd className="paper-help">{account.period_name}</dd><dd className="paper-help">비교 {account.comparison_name || '기간 미확인'}: {value(account.comparison_amount, account.currency)}</dd>{account.ytd_amount != null && <dd className="paper-help">누적 {value(account.ytd_amount, account.currency)} · 비교 누적 {value(account.comparison_ytd_amount, account.currency)}</dd>}</div>)}</dl>
      {!!financials.missing_accounts?.length && <p className="paper-help">미확인 항목: {financials.missing_accounts.join(', ')}</p>}
      {link(financials.url) && <a href={link(financials.url)} target="_blank" rel="noopener noreferrer">재무 보고서 원문 ↗</a>}<p className="paper-help">재무자료 조회 {timestamp(financials.fetched_at)}</p></>}
    {!!stock?.disclosures?.length && <details className="aio-metrics"><summary>최근 공시 목록 {stock.disclosures.length}건</summary><ul>{stock.disclosures.filter(item => link(item.url)).map(item => <li key={item.receipt_no}><a href={link(item.url)} target="_blank" rel="noopener noreferrer">{item.title}</a><p className="paper-help">접수 {item.received_at}{ids.includes(`${code}-dart-${item.receipt_no}`) && ' · 분석에 인용됨'}</p></li>)}</ul><p className="paper-help">공시 제목·접수일 목록입니다. 본문 전체를 분석한 결과는 아닙니다.</p></details>}
  </details>
}
