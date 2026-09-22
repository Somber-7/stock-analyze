import ConnectionStatus from './ConnectionStatus'

export default function DartSettings({ settings, apiKey, setApiKey, enabled, setEnabled, busy, manage }) {
  const stored = settings?.tools?.dart
  const dirty = Boolean(apiKey.trim()) || enabled !== Boolean(stored?.enabled)
  return <form className="paper-card ai-editor" onSubmit={event => {
    event.preventDefault()
    if (dirty) manage('dart-save', '/tools/dart/settings', { enabled, ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}) }, 'DART 설정을 저장했습니다. 다음 분석부터 적용됩니다.')
  }}>
    <div className="ai-editor-heading"><h3>DART 재무·공시</h3><span className={`ai-key-status ${stored?.has_key ? 'is-stored' : ''}`}>{stored?.has_key ? '키 저장됨' : '키 미등록'}</span></div>
    <fieldset disabled={Boolean(busy)} className="ai-fields">
      <div className="ai-field"><label htmlFor="dart-api-key">DART 인증키</label><input id="dart-api-key" type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} autoComplete="off" spellCheck={false} autoCapitalize="none" maxLength={40} placeholder={stored?.has_key ? '키 변경 시에만 입력하세요' : '발급받은 40자리 인증키'} /></div>
      <label className="dart-enabled"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} /><span>AI 분석에 재무·공시 자료 포함</span></label>
    </fieldset>
    <div className="ai-save-row"><span className={dirty ? 'ai-dirty' : 'paper-help'}>{dirty ? '저장하지 않은 변경 사항' : stored?.enabled ? '분석에 포함 중' : '분석에 포함하지 않음'}</span><button type="submit" className="paper-primary" disabled={Boolean(busy) || !dirty}>{busy === 'dart-save' ? '저장 중…' : 'DART 설정 저장'}</button></div>
    <div className="ai-check-panel"><div><h4>연결 상태</h4><ConnectionStatus record={stored} /></div><button type="button" disabled={Boolean(busy) || dirty || !stored?.has_key} onClick={() => manage('dart-check', '/tools/dart/check', {}, 'DART 기업 조회로 연결을 확인했습니다.')}>{busy === 'dart-check' ? '확인 중…' : 'DART 연결 확인'}</button></div>
    {dirty && <p className="paper-help ai-action-help">저장 후 연결을 확인할 수 있습니다.</p>}
    <details className="settings-details"><summary>수집 자료·연결 안내</summary><p>종목코드에 맞는 기업의 최근 공시 목록과 매출·영업이익·순이익·자산·부채·자본·영업현금흐름을 조회합니다. 공시 본문 전체는 포함하지 않습니다.</p><p>연결 재무제표를 우선 조회하며 자료가 없으면 별도 재무제표를 구분해 제공합니다. 12월 결산법인만 재무기간을 자동 연결하고, 미확인 항목은 비워둡니다.</p><p>키는 현재 Windows 계정으로 암호화해 저장합니다. 연결 확인은 공개 기업 조회만 수행합니다. 분석 포함을 켜면 다음 분석부터 사용하며 계좌정보는 DART에 전송하지 않습니다.</p><a href="https://opendart.fss.or.kr/" target="_blank" rel="noopener noreferrer">OpenDART 인증키 신청·관리 ↗</a></details>
    <details className="settings-details"><summary>키 관리</summary><div className="ai-key-management"><button type="button" className="paper-danger" disabled={Boolean(busy) || dirty || !stored?.has_key} onClick={() => manage('dart-delete', '/tools/dart/delete-key', {}, 'DART 키를 삭제하고 분석 포함을 해제했습니다.')}>DART 저장된 키 삭제</button></div></details>
  </form>
}
