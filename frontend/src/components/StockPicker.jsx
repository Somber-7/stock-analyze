import { useEffect, useId, useRef, useState } from 'react'
import { API } from '../lib/tradingApi'
import './StockPicker.css'

export default function StockPicker({ initialCode = '', onChange, label = '주문 종목 · 이름 또는 코드' }) {
  const id = useId()
  const [query, setQuery] = useState(initialCode)
  const [selected, setSelected] = useState(null)
  const [results, setResults] = useState([])
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const sequence = useRef(0)

  useEffect(() => {
    if (selected || !query.trim()) return
    const seq = ++sequence.current
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`${API}/api/stocks/search?q=${encodeURIComponent(query.trim())}`, {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]),
        })
        if (!response.ok) throw new Error('search failed')
        const rows = await response.json()
        if (sequence.current !== seq || controller.signal.aborted) return
        // Only exact codes auto-resolve. Similar names always require an explicit choice.
        const exact = rows.find(row => row.code === query.trim().toUpperCase() && /^[0-9A-Z]{6}$/.test(row.code))
        if (exact) {
          setSelected(exact); setQuery(exact.name); setResults([]); setOpen(false); setStatus('')
          onChange(exact)
        } else {
          setResults(rows); setStatus(rows.length ? '목록에서 종목을 선택하세요.' : '검색 결과가 없습니다. 종목명·코드를 확인하거나 잠시 후 다시 검색하세요.')
        }
      } catch {
        if (sequence.current === seq && !controller.signal.aborted) setStatus('종목 목록을 불러오지 못했습니다. 잠시 후 다시 검색하세요.')
      }
    }, 200)
    return () => { clearTimeout(timer); controller.abort() }
  }, [query, selected, onChange])

  function choose(row) {
    if (!/^[0-9A-Z]{6}$/.test(row.code)) return
    sequence.current++
    setSelected(row); setQuery(row.name); setResults([]); setOpen(false); setStatus(''); setActive(-1)
    onChange(row)
  }

  function edit(value) {
    sequence.current++
    setQuery(value); setSelected(null); setResults([]); setOpen(true); setActive(-1)
    setStatus(value.trim() ? '종목 검색 중…' : '')
    onChange(null)
  }

  function keyDown(event) {
    if (event.key === 'Escape') { setOpen(false); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); setOpen(true)
      setActive(index => event.key === 'ArrowDown' ? Math.min(index + 1, results.length - 1) : Math.max(index - 1, 0))
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      if (open && active >= 0 && results[active]) choose(results[active])
    }
  }

  return <div className="stock-picker" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <label htmlFor={id}>{label}</label>
    <input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open && results.length > 0}
      aria-controls={`${id}-list`} aria-activedescendant={open && active >= 0 && results[active] ? `${id}-${active}` : undefined}
      autoComplete="off" placeholder="삼성전자 또는 005930" value={query} onChange={event => edit(event.target.value)}
      onFocus={() => setOpen(true)} onKeyDown={keyDown} />
    {open && results.length > 0 && <div className="stock-picker-results" id={`${id}-list`} role="listbox" aria-label="종목 검색 결과">
      {results.map((row, index) => <button key={row.code} id={`${id}-${index}`} type="button" role="option"
        aria-selected={active === index} disabled={!/^[0-9A-Z]{6}$/.test(row.code)} onClick={() => choose(row)}>
        <strong>{row.name}</strong><span>{row.code}{!/^[0-9A-Z]{6}$/.test(row.code) && ' · 코드 형식 확인 필요'}</span>
      </button>)}
    </div>}
    {selected ? <div className="stock-picker-selected" role="status"><span>선택한 종목</span><strong>{selected.name}</strong><code>{selected.code}</code></div>
      : <p className="paper-help" role="status">{status || '종목을 검색하고 목록에서 선택하세요.'}</p>}
  </div>
}
