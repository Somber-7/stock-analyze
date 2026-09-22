"""Validate supplied daily data, without inventing an exchange holiday calendar."""
from datetime import date, timedelta, timezone

from backend.namuh.portfolio import optional_number

HISTORY_BARS = {'unspecified': 60, 'short': 60, 'medium': 130, 'long': 260}
KST = timezone(timedelta(hours=9))


def prepare_daily(rows, requested, fetched_at):
    local = fetched_at.astimezone(KST)
    today = local.date()
    # Allow the closing bar to settle; this is a reference weekday, not a calendar.
    expected = today if (local.hour, local.minute) >= (15, 40) else today - timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    by_date, conflicts = {}, set()
    invalid = partial = 0
    for row in rows:
        try:
            day = date.fromisoformat(row['time'])
            values = {key: optional_number(row.get(key)) for key in ('open', 'high', 'low', 'close', 'volume')}
            if (day > today or day.weekday() >= 5 or any(values[k] is None or values[k] <= 0 for k in ('open', 'high', 'low', 'close'))
                    or values['volume'] is None or values['volume'] < 0
                    or not values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            invalid += 1
            continue
        if day == today and (local.hour, local.minute) < (15, 40):
            partial += 1
            continue
        normalized = dict(time=day.isoformat(), **values)
        if day in conflicts:
            continue
        if day in by_date and by_date[day] != normalized:
            conflicts.add(day)
            del by_date[day]
            invalid += 1
        else:
            by_date[day] = normalized
    clean = [by_date[day] for day in sorted(by_date)][-requested:]
    latest = max(by_date) if by_date else None
    issues = []
    if invalid:
        issues.append(f'날짜·가격·거래량 오류 또는 상충하는 일봉 {invalid}건을 제외했습니다. 원자료 확인이 필요합니다.')
    if not clean:
        issues.append('분석할 확정 일봉이 없습니다.')
    elif latest < expected:
        issues.append(f'최근 확정 일봉은 {latest}입니다. 기준 평일 {expected} 자료가 없어 휴장·거래정지·조회 지연 여부를 확인해야 합니다.')
    if clean and len(clean) < requested:
        issues.append(f'요청 {requested}개 중 확정 일봉 {len(clean)}개만 확보했습니다. 장기간 추세를 단정하지 마세요.')
    requires_defer = bool(invalid or not clean or latest < expected)
    return clean, dict(status='review' if requires_defer else 'limited' if len(clean) < requested else 'checked',
        requires_defer=requires_defer, requested_bars=requested, completed_bars=len(clean),
        data_date=latest.isoformat() if latest else None, reference_weekday=expected.isoformat(),
        partial_bars=partial, invalid_bars=invalid, issues=issues,
        limitations='휴장일·기간 중 거래일 누락·수정주가 여부는 확인하지 않았습니다. 시세 API에는 거래일 필드가 없어 조회 시각을 거래 시각으로 간주하지 않습니다.')
