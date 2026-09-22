"""Deterministic indicators from supplied daily bars; never inferred by the LLM."""
from datetime import date
from statistics import mean, stdev
from backend.namuh.portfolio import optional_number


def _date(value):
    try: return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError): return None


def calculate_metrics(daily, investors=None):
    bars = {}
    for row in daily:
        day, close = _date(row.get('time')), optional_number(row.get('close'))
        if day and close is not None and close > 0:
            bars[day] = dict(close=close, volume=optional_number(row.get('volume')))
    ordered = [bars[day] for day in sorted(bars)]
    closes = [row['close'] for row in ordered]
    n = len(closes)
    rounded = lambda value: round(value, 4) if value is not None else None
    def change(period):
        return rounded((closes[-1]/closes[-period-1]-1)*100) if n > period else None
    result = dict(bars=n, data_date=max(bars) if bars else None,
                  return_5_pct=change(5), return_20_pct=change(20),
                  return_60_pct=change(60), return_120_pct=change(120), return_240_pct=change(240),
                  sma_20=rounded(mean(closes[-20:])) if n >= 20 else None,
                  sma_60=rounded(mean(closes[-60:])) if n >= 60 else None,
                  sma_120=rounded(mean(closes[-120:])) if n >= 120 else None,
                  daily_volatility_20_pct=None, volume_ratio_20=None, flows={})
    if n >= 21:
        returns = [(b/a-1)*100 for a,b in zip(closes[-21:-1], closes[-20:])]
        result['daily_volatility_20_pct'] = rounded(stdev(returns))
        volumes = [row['volume'] for row in ordered[-21:]]
        if all(v is not None and v >= 0 for v in volumes) and mean(volumes[:-1]) > 0:
            result['volume_ratio_20'] = rounded(volumes[-1]/mean(volumes[:-1]))
    rows = {}
    for row in (investors or {}).get('rows', []):
        day = _date(row.get('date'))
        if day: rows.setdefault(day, row)
    recent = [rows[day] for day in sorted(rows, reverse=True)[:5]]
    for field in ('foreign', 'institutional'):
        values = [optional_number(row.get(field)) for row in recent]
        streak = None
        if values and values[0] is not None:
            streak = 0
            for v in values:
                if v is None or v <= 0: break
                streak += 1
        result['flows'][field] = dict(window_rows=len(recent), observations=sum(v is not None for v in values),
            positive_days=sum(v is not None and v > 0 for v in values), latest_buy_streak=streak,
            data_date=max(rows) if rows else None)
    result['method'] = ('일봉 종가 기준 5·20·60·120·240구간 수익률, 20·60·120봉 단순이동평균. 변동성은 최근 20개 일간 수익률의 '
                        '표본 표준편차(%, 비연율화), 거래량 배율은 마지막 봉/직전 20봉 평균. '
                        '수급은 최근 최대 5개 제공 행의 부호만 집계하며 단위 환산 없이 관측 범위 내 연속 매수일을 표시합니다. '
                        'AI 분석은 확정 일봉을 선별하며 상세 검증 결과는 자료 상태를 확인하세요. 거래일 누락·수정주가 적용 여부는 확인되지 않았습니다.')
    return result
