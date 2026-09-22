import { useState } from 'react'
import { AI_PROMPT_PRESETS } from '../lib/aiPromptPresets'

export default function AIPromptPresets({ value, onChange, includeUs, compact = false }) {
  const [selectedId, setSelectedId] = useState('balanced')
  const [undo, setUndo] = useState(null)
  const selected = AI_PROMPT_PRESETS.find(preset => preset.id === selectedId)
  const applied = AI_PROMPT_PRESETS.find(preset => preset.objective === value)
  const canUndo = undo && value === undo.applied

  function apply() {
    if (!selected || selected.objective === value) return
    setUndo({ before: value, applied: selected.objective })
    onChange(selected.objective)
  }

  return <div className="aio-presets">
    <div className="aio-preset-heading"><label htmlFor="ai-prompt-preset">분석 프리셋</label><span>현재 지침 · {applied?.name || '직접 작성·수정'}</span></div>
    <div className="aio-preset-actions">
      <select id="ai-prompt-preset" value={selectedId} onChange={event => setSelectedId(event.target.value)}>
        {AI_PROMPT_PRESETS.map(preset => <option key={preset.id} value={preset.id}>{preset.name}</option>)}
      </select>
      <button type="button" onClick={apply} disabled={!selected || value === selected.objective}>프리셋 적용</button>
    </div>
    <p className="paper-help">{selected?.description}</p>
    {!compact && <details key={selectedId} className="aio-preset-preview"><summary>지침 미리보기</summary><p>{selected?.objective}</p></details>}
    {selected?.requiresUs && !includeUs && <p className="aio-warning">미국 시세까지 비교하려면 아래 ‘미국 시장 참고 시세 포함’을 켜세요.</p>}
    <div className="aio-preset-footer">{!compact && <span>적용 후 자유롭게 수정하고 설정을 저장하세요.</span>}{canUndo && <button type="button" onClick={() => { onChange(undo.before); setUndo(null) }}>적용 전 지침으로 되돌리기</button>}</div>
  </div>
}
