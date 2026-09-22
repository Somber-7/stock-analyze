const SCOPES = { models: '인증·모델 목록 확인', usage: '사용량 조회 확인', company: '기업 조회 확인', accounts: '계좌 조회 확인' }

export function connectionStatus(record, now = Date.now()) {
  if (!record) return { tone: 'muted', label: '불러오는 중', detail: '확인 기록 불러오는 중', checkedAt: null }
  const connection = record.connection || {}
  const checkedAt = Number.isFinite(Date.parse(connection.checked_at)) ? connection.checked_at : null
  const detail = SCOPES[connection.scope] || '연결 확인'
  if (connection.status === 'checking') return { tone: 'checking', label: '확인 중', detail, checkedAt }
  if (!record.has_key) return { tone: 'muted', label: '키 미등록', detail: '키 등록 후 확인', checkedAt: null }
  if (connection.status === 'error') return { tone: 'error', label: '확인 실패', detail: connection.message || '다시 확인해 주세요', checkedAt }
  if (connection.status === 'success' && checkedAt) {
    if (now - Date.parse(checkedAt) > 24 * 60 * 60 * 1000) return { tone: 'stale', label: '재확인 필요', detail: `${detail} · 24시간 경과`, checkedAt }
    return { tone: 'success', label: '확인됨', detail, checkedAt }
  }
  return { tone: 'muted', label: '미확인', detail: '저장된 키 · 연결 확인 필요', checkedAt }
}

export function withConnection(settings, target, connection) {
  if (!settings || !target) return settings
  const group = target === 'tavily' || target === 'dart' ? 'tools' : 'profiles'
  return { ...settings, [group]: { ...settings[group], [target]: { ...settings[group]?.[target], connection } } }
}
