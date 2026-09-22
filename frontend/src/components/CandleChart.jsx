import { useState, useEffect, useRef, useCallback } from 'react'
import { createChart } from 'lightweight-charts'

const MA_LINES = [
  { period: 5,   color: '#f0b429' },
  { period: 10,  color: '#ff7043' },
  { period: 20,  color: '#66bb6a' },
  { period: 60,  color: '#42a5f5' },
  { period: 120, color: '#ab47bc' },
]

function calcMA(data, period) {
  const result = []
  for (let i = period - 1; i < data.length; i++) {
    const sum = data.slice(i - period + 1, i + 1).reduce((s, c) => s + c.close, 0)
    result.push({ time: data[i].time, value: +(sum / period).toFixed(2) })
  }
  return result
}

function timeToLabel(time, isIntraday) {
  if (typeof time === 'number') {
    const d = new Date(time * 1000)
    const month = d.getUTCMonth() + 1
    const day = d.getUTCDate()
    if (isIntraday) {
      const h = String(d.getUTCHours()).padStart(2, '0')
      const m = String(d.getUTCMinutes()).padStart(2, '0')
      return `${month}월 ${day}일 ${h}:${m}`
    }
    return `${month}월 ${day}일`
  }
  if (time && typeof time === 'object') {
    return `${time.month}월 ${time.day}일`
  }
  const p = String(time).split('-')
  return `${parseInt(p[1])}월 ${parseInt(p[2])}일`
}

function findCandle(paramTime, data) {
  if (typeof paramTime === 'number') {
    return data.find(d => d.time === paramTime)
  }
  if (typeof paramTime === 'string') {
    return data.find(d => d.time === paramTime)
  }
  // BusinessDay {year, month, day}
  const str = `${paramTime.year}-${String(paramTime.month).padStart(2, '0')}-${String(paramTime.day).padStart(2, '0')}`
  return data.find(d => d.time === str)
}

function makeTickMarkFormatter(isIntraday) {
  return (time) => {
    if (typeof time === 'number') {
      const d = new Date(time * 1000)
      if (isIntraday) {
        return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0')
      }
      return (d.getUTCMonth() + 1) + '/' + d.getUTCDate()
    }
    const t = (time && typeof time === 'object')
      ? time
      : (() => { const p = String(time).split('-'); return { month: +p[1], day: +p[2] } })()
    return t.month + '/' + t.day
  }
}

function makeTimeFormatter(isIntraday) {
  return (time) => {
    if (typeof time === 'number') {
      const d = new Date(time * 1000)
      if (isIntraday) {
        return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
      }
      return `${d.getUTCFullYear()}.${d.getUTCMonth() + 1}.${d.getUTCDate()}`
    }
    const t = (time && typeof time === 'object')
      ? time
      : (() => { const p = String(time).split('-'); return { year: +p[0], month: +p[1], day: +p[2] } })()
    return `${t.year}.${t.month}.${t.day}`
  }
}

const TOOLTIP_W = 190

export default function CandleChart({ data, isIntraday = false }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const maSeriesRefs = useRef([])
  const dataRef = useRef(data)
  const dayBoundaryTimesRef = useRef([])
  const [tooltip, setTooltip] = useState(null)
  const [dayLineXs, setDayLineXs] = useState([])

  useEffect(() => { dataRef.current = data }, [data])

  const updateDayLines = useCallback(() => {
    if (!chartRef.current || !dayBoundaryTimesRef.current.length) {
      setDayLineXs([])
      return
    }
    const ts = chartRef.current.timeScale()
    const xs = dayBoundaryTimesRef.current
      .map(t => ts.timeToCoordinate(t))
      .filter(x => x !== null)
    setDayLineXs(xs)
  }, [])

  useEffect(() => {
    if (!containerRef.current) return

    chartRef.current = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { color: '#181e22' }, textColor: '#96a3a9' },
      grid: {
        vertLines: { color: '#252e33' },
        horzLines: { color: '#252e33' },
      },
      localization: { timeFormatter: makeTimeFormatter(isIntraday) },
      timeScale: {
        timeVisible: isIntraday,
        secondsVisible: false,
        tickMarkFormatter: makeTickMarkFormatter(isIntraday),
      },
    })

    seriesRef.current = chartRef.current.addCandlestickSeries({
      upColor: '#f07c82',
      downColor: '#77a7f5',
      borderUpColor: '#f07c82',
      borderDownColor: '#77a7f5',
      wickUpColor: '#f07c82',
      wickDownColor: '#77a7f5',
    })

    maSeriesRefs.current = MA_LINES.map(({ color }) =>
      chartRef.current.addLineSeries({
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
    )

    chartRef.current.timeScale().subscribeVisibleLogicalRangeChange(updateDayLines)

    chartRef.current.subscribeCrosshairMove((param) => {
      if (!param.time || !param.point || param.point.x < 0 || param.point.y < 0) {
        setTooltip(null)
        return
      }
      const candle = findCandle(param.time, dataRef.current)
      setTooltip(candle ? { candle, x: param.point.x, y: param.point.y,
        cw: containerRef.current?.offsetWidth ?? 600,
        ch: containerRef.current?.offsetHeight ?? 400 } : null)
    })

    return () => {
      chartRef.current.timeScale().unsubscribeVisibleLogicalRangeChange(updateDayLines)
      chartRef.current.remove()
      chartRef.current = null
      seriesRef.current = null
      maSeriesRefs.current = []
    }
  }, [isIntraday, updateDayLines])

  useEffect(() => {
    if (!seriesRef.current || !data.length) return

    chartRef.current.applyOptions({
      localization: { timeFormatter: makeTimeFormatter(isIntraday) },
      timeScale: { tickMarkFormatter: makeTickMarkFormatter(isIntraday) },
    })

    const sorted = [...data].sort((a, b) => (a.time > b.time ? 1 : -1))
    seriesRef.current.setData(sorted)

    MA_LINES.forEach(({ period }, i) => {
      maSeriesRefs.current[i]?.setData(calcMA(sorted, period))
    })

    chartRef.current.timeScale().fitContent()

    // 날짜 경계 계산 (분봉 전용)
    if (isIntraday) {
      const boundaries = []
      let prevDay = null
      for (const c of sorted) {
        const day = Math.floor(c.time / 86400)
        if (prevDay !== null && day !== prevDay) boundaries.push(c.time)
        prevDay = day
      }
      dayBoundaryTimesRef.current = boundaries
    } else {
      dayBoundaryTimesRef.current = []
    }
    updateDayLines()
  }, [data, isIntraday, updateDayLines])

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '2px 8px', display: 'flex', gap: '12px', fontSize: '11px', flexShrink: 0 }}>
        {MA_LINES.map(({ period, color }) => (
          <span key={period} style={{ color }}>MA{period}</span>
        ))}
      </div>
      <div style={{ flex: 1, position: 'relative' }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        {dayLineXs.map((x, i) => (
          <div key={i} style={{
            position: 'absolute', left: x, top: 0, bottom: 0,
            width: 1, background: 'rgba(136, 136, 160, 0.25)',
            pointerEvents: 'none', zIndex: 1,
          }} />
        ))}
        {tooltip && (() => {
          const { candle, x, y, cw, ch } = tooltip
          const up = candle.close >= candle.open
          const closeColor = up ? '#f07c82' : '#77a7f5'
          const left = x + 16 + TOOLTIP_W > cw ? x - TOOLTIP_W - 8 : x + 16
          const top = Math.max(4, Math.min(y - 70, ch - 160))
          return (
            <div style={{
              position: 'absolute', left, top,
              background: 'rgba(24, 30, 34, 0.97)',
              border: '1px solid #3a474d',
              borderRadius: '6px',
              padding: '8px 10px',
              fontSize: '12px',
              color: '#dce5e6',
              pointerEvents: 'none',
              zIndex: 10,
              whiteSpace: 'nowrap',
              lineHeight: '1.9',
            }}>
              <div style={{ color: '#96a3a9', fontSize: '11px', marginBottom: '2px' }}>
                {timeToLabel(candle.time, isIntraday)}
              </div>
              <div>시 <span style={{ color: closeColor }}>{candle.open.toLocaleString()}</span></div>
              <div>고 <span style={{ color: '#f07c82' }}>{candle.high.toLocaleString()}</span></div>
              <div>저 <span style={{ color: '#77a7f5' }}>{candle.low.toLocaleString()}</span></div>
              <div>종 <span style={{ color: closeColor }}>{candle.close.toLocaleString()}</span></div>
              {candle.volume != null && (
                <div>거래량 <span>{candle.volume.toLocaleString()}</span></div>
              )}
              {candle.trading_value > 0 && (
                <div>거래대금 <span>{(candle.trading_value / 100_000_000).toFixed(0)}억</span></div>
              )}
            </div>
          )
        })()}
      </div>
    </div>
  )
}
