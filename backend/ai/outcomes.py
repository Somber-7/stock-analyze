"""Pure, deterministic post-analysis price observations from caller-supplied bars."""
from datetime import date, datetime, timedelta, timezone
import math


KST = timezone(timedelta(hours=9))
HORIZONS = (5, 20, 60)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _local_datetime(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST)


def _series(rows, now_local):
    """Return validated, deduplicated closes or a stable error code."""
    if not isinstance(rows, list):
        return None, 'series_missing'
    by_day = {}
    today = now_local.date()
    for row in rows:
        if not isinstance(row, dict):
            return None, 'invalid_bar'
        day = _day(row.get('time'))
        values = {key: _number(row.get(key)) for key in ('open', 'high', 'low', 'close')}
        volume = row.get('volume')
        try:
            volume = float(volume)
        except (TypeError, ValueError):
            volume = None
        close = values['close']
        if (day is None or any(value is None for value in values.values())
                or volume is None or not math.isfinite(volume) or volume < 0
                or not values['low'] <= min(values['open'], close)
                <= max(values['open'], close) <= values['high']
                or day.weekday() >= 5 or day > today):
            return None, 'invalid_bar'
        if day == today and (now_local.hour, now_local.minute) < (15, 40):
            continue
        normalized = (values['open'], values['high'], values['low'], close, volume)
        if day in by_day and by_day[day] != normalized:
            return None, 'conflicting_duplicate_date'
        by_day[day] = normalized
    return {day: values[3] for day, values in by_day.items()}, None


def _snapshot_baseline(rows, analysis_day):
    if not isinstance(rows, list):
        return None, None
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        day, close = _day(row.get('time')), _number(row.get('close'))
        if day is not None and day <= analysis_day and day.weekday() < 5 and close is not None:
            candidates.append((day, close))
    return max(candidates) if candidates else (None, None)


def _drawdown(closes):
    peak = closes[0]
    worst = 0.0
    for close in closes[1:]:
        peak = max(peak, close)
        worst = min(worst, (close / peak - 1) * 100)
    return round(worst, 4)


def _empty_metric(horizon, status, reason, available=0):
    return dict(observations=horizon, status=status, reason=reason,
                available_observations=available, end_date=None, return_pct=None,
                max_drawdown_pct=None, directional_return_pct=None,
                benchmark_status='unavailable', benchmark_reason='stock_observation_unavailable',
                benchmark_return_pct=None, excess_return_pp=None)


def evaluate_outcomes(run, series_by_code, benchmark_series, now_datetime):
    """Evaluate 5/20/60 later completed daily closes without I/O or mutation.

    ``series_by_code`` maps a decision code to daily OHLCV-like dictionaries.
    Baselines always come from ``run.input_snapshot``; supplied series can only
    contribute observations strictly after the KST completion date.
    """
    now_local = _local_datetime(now_datetime)
    completed = _local_datetime(run.get('completed_at')) if isinstance(run, dict) else None
    snapshot = run.get('input_snapshot') if isinstance(run, dict) else None
    base = dict(schema_version=1, run_id=run.get('id') if isinstance(run, dict) else None,
                evaluated_at=now_local.isoformat() if now_local else None,
                status='ready', reason=None,
                price_basis='unadjusted_daily_close',
                benchmark=dict(code='069500', name='KODEX 200',
                               classification='domestic_etf_reference'),
                limitations=[
                    '가격은 수정주가 적용 여부가 확인되지 않은 일봉 종가 관측입니다.',
                    '최대 낙폭은 기준일부터 종료일까지 종가만 사용합니다.',
                    '거래일 누락 여부와 장중 경로는 확인하지 않습니다.',
                    '벤치마크는 지수 수익률이 아닌 국내 ETF 참고값입니다.',
                ], counts=dict(total=0, supported=0, deferred=0, directional_eligible=0),
                items=[])
    decisions = run.get('decisions', []) if isinstance(run, dict) and isinstance(run.get('decisions'), list) else []
    counts = base['counts']
    counts['total'] = len(decisions)
    counts['supported'] = sum(row.get('assessment') == 'supported' for row in decisions)
    counts['deferred'] = sum(row.get('assessment') == 'defer' for row in decisions)
    counts['directional_eligible'] = sum(
        row.get('assessment') == 'supported' and row.get('side') in ('buy', 'sell')
        for row in decisions)
    if (not isinstance(snapshot, dict) or snapshot.get('schema_version') != 1
            or not isinstance(snapshot.get('context'), dict)):
        base.update(status='unavailable', reason='immutable_input_snapshot_missing')
        return base
    if completed is None or now_local is None or now_local < completed:
        base.update(status='unavailable', reason='invalid_evaluation_time')
        return base

    context = snapshot['context']
    fetched = _local_datetime(context.get('fetched_at'))
    snapshot_stocks = {row.get('code'): row for row in context.get('stocks', [])
                       if isinstance(row, dict) and row.get('code')}
    benchmark_snapshot = context.get('benchmark') if isinstance(context.get('benchmark'), dict) else {}
    benchmark_closes, benchmark_error = _series(benchmark_series, now_local)

    for decision in decisions:
        code = decision.get('code')
        saved = snapshot_stocks.get(code, {})
        baseline_day, baseline_close = _snapshot_baseline(saved.get('daily'), completed.date())
        item = dict(code=code, name=decision.get('name') or saved.get('name'),
                    assessment=decision.get('assessment'), side=decision.get('side'),
                    status='ready', reason=None, baseline=None, horizons=[])
        if baseline_day is None:
            item.update(status='unavailable', reason='snapshot_baseline_missing')
            item['horizons'] = [_empty_metric(h, 'unavailable', item['reason']) for h in HORIZONS]
            base['items'].append(item)
            continue
        if (fetched is None or baseline_day > fetched.date()
                or (baseline_day == fetched.date() and (fetched.hour, fetched.minute) < (15, 40))
                or (isinstance(saved.get('data_quality'), dict)
                    and saved['data_quality'].get('requires_defer') is True)):
            item.update(status='unavailable', reason='snapshot_baseline_invalid')
            item['horizons'] = [_empty_metric(h, 'unavailable', item['reason']) for h in HORIZONS]
            base['items'].append(item)
            continue
        item['baseline'] = dict(date=baseline_day.isoformat(), close=baseline_close,
                                source='immutable_input_snapshot')
        closes, error = _series(series_by_code.get(code) if isinstance(series_by_code, dict) else None,
                                now_local)
        if error:
            item.update(status='unavailable', reason=error)
            item['horizons'] = [_empty_metric(h, 'unavailable', error) for h in HORIZONS]
            base['items'].append(item)
            continue
        if baseline_day not in closes:
            item.update(status='unavailable', reason='series_coverage_missing')
            item['horizons'] = [_empty_metric(h, 'unavailable', item['reason']) for h in HORIZONS]
            base['items'].append(item)
            continue
        if closes[baseline_day] != baseline_close:
            item.update(status='unavailable', reason='baseline_price_changed')
            item['horizons'] = [_empty_metric(h, 'unavailable', item['reason']) for h in HORIZONS]
            base['items'].append(item)
            continue
        observations = [(day, closes[day]) for day in sorted(closes) if day > completed.date()]
        benchmark_base_day, benchmark_base_close = _snapshot_baseline(
            benchmark_snapshot.get('daily'), completed.date())
        for horizon in HORIZONS:
            if len(observations) < horizon:
                item['horizons'].append(_empty_metric(
                    horizon, 'pending', 'insufficient_subsequent_observations', len(observations)))
                continue
            selected = observations[:horizon]
            end_day, end_close = selected[-1]
            stock_return = round((end_close / baseline_close - 1) * 100, 4)
            metric = dict(observations=horizon, status='complete', reason=None,
                          available_observations=len(observations), end_date=end_day.isoformat(),
                          return_pct=stock_return,
                          max_drawdown_pct=_drawdown([baseline_close] + [value for _, value in selected]),
                          directional_return_pct=(stock_return if decision.get('assessment') == 'supported' and decision.get('side') == 'buy'
                                                  else -stock_return if decision.get('assessment') == 'supported' and decision.get('side') == 'sell'
                                                  else None),
                          benchmark_status='unavailable', benchmark_reason=None,
                          benchmark_return_pct=None, excess_return_pp=None)
            if benchmark_error:
                metric['benchmark_reason'] = benchmark_error
            elif benchmark_base_day != baseline_day or benchmark_base_close is None:
                metric['benchmark_reason'] = 'exact_baseline_date_missing'
            elif baseline_day not in benchmark_closes:
                metric['benchmark_reason'] = 'series_coverage_missing'
            elif benchmark_closes[baseline_day] != benchmark_base_close:
                metric['benchmark_reason'] = 'baseline_price_changed'
            elif end_day not in benchmark_closes:
                metric['benchmark_reason'] = 'exact_end_date_missing'
            else:
                benchmark_return = round((benchmark_closes[end_day] / benchmark_base_close - 1) * 100, 4)
                metric.update(benchmark_status='complete', benchmark_reason=None,
                              benchmark_return_pct=benchmark_return,
                              excess_return_pp=round(stock_return - benchmark_return, 4))
            item['horizons'].append(metric)
        base['items'].append(item)
    return base
