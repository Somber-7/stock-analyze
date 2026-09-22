"""Read-only account briefing from existing caches, history and saved analysis."""
import math
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from backend.watch.api import get_watch
from backend.trading.api import get_service
from backend.ai.operation_api import get_operation
from backend.ai.comparison import comparison_scope

router = APIRouter(prefix='/api', tags=['briefing'])
KST = timezone(timedelta(hours=9))


def parsed_time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def watch_briefing(watch, at):
    snapshot = watch.snapshot(viewed=False)
    movers = []
    for item in snapshot['items']:
        quote = item.get('quote') or {}
        retrieved = parsed_time(quote.get('retrieved_at'))
        if (quote.get('error') or retrieved is None or not 0 <= (at - retrieved).total_seconds() <= 120
                or not finite(quote.get('change_rate')) or not finite(quote.get('price')) or quote['price'] <= 0):
            continue
        movers.append(dict(code=item['code'], name=item.get('name', item['code']), price=quote['price'],
                           change_rate=quote['change_rate'], retrieved_at=quote['retrieved_at']))
    alerts = []
    for alert in watch.read()['alerts']:
        triggered = parsed_time(alert.get('triggered_at'))
        if alert['status'] == 'triggered' and triggered and triggered <= at and triggered.astimezone(KST).date() == at.astimezone(KST).date():
            alerts.append({key: alert.get(key) for key in ('code', 'name', 'threshold', 'triggered_at')})
    alerts.sort(key=lambda a: a['triggered_at'], reverse=True)
    movers.sort(key=lambda row: abs(row['change_rate']), reverse=True)
    return dict(status='ready', movers=movers[:5], fresh_count=len(movers),
                stale_count=len(snapshot['items']) - len(movers), total_count=len(snapshot['items']),
                alert_count=len(alerts), alerts=alerts[:5])


def empty_orders(status):
    return dict(status=status, rows=[], pending_count=None, unresolved_count=None, checked_at=None)


def empty_analysis(status):
    return dict(status=status, run_id=None, completed_at=None, changed_count=None, defer_count=None)


def build_briefing(account, watch, trading, operation, *, now=None):
    at = now or datetime.now(timezone.utc)
    day = at.astimezone(KST).strftime('%Y%m%d')
    result = dict(day=at.astimezone(KST).date().isoformat(), fetched_at=at.isoformat(),
                  orders=empty_orders('unavailable'), analysis=empty_analysis('unavailable'))
    try:
        result['watch'] = watch_briefing(watch, at)
    except Exception:
        result['watch'] = dict(status='error', movers=[], alerts=[], alert_count=None, stale_count=None)
    before = trading.read()
    if before['mode'] != 'live' or not account or before['account'] != account:
        return result
    try:
        history = trading.gateway.history(account, day)
        pending = [row for row in history if row['remaining'] > 0]
        result['orders'] = dict(status='ready', pending_count=len(pending),
            rows=[{key: row.get(key) for key in ('code', 'name', 'side', 'remaining', 'price')} for row in pending[:5]],
            unresolved_count=sum(row.get('account') == account and row.get('status') in ('sending', 'unknown')
                                 for row in before['operations']),
            checked_at=datetime.now(timezone.utc).isoformat() if now is None else at.isoformat())
    except Exception:
        result['orders'] = empty_orders('error')
    try:
        settings = operation.settings.snapshot()
        state = operation.read()
        dart = settings.get('tools', {}).get('dart', {})
        scope = comparison_scope(dict(state['config'], include_dart=bool(dart.get('enabled') and dart.get('has_key'))), before)
        run = next((run for run in reversed(state['runs']) if run['status'] == 'ready'
                    and run.get('mode') == 'live' and run.get('comparison_scope') == scope), None)
        result['analysis'] = empty_analysis('empty')
        if run:
            result['analysis'] = dict(status='ready', run_id=run['id'], completed_at=run['completed_at'],
                changed_count=(run.get('comparison') or {}).get('changed_count'),
                defer_count=sum(row.get('assessment') == 'defer' for row in run['decisions']))
        if operation.read()['version'] != state['version'] or operation.settings.snapshot()['version'] != settings['version']:
            result['analysis'] = empty_analysis('changed')
    except Exception:
        result['analysis'] = empty_analysis('error')
    after = trading.read()
    if any(before[key] != after[key] for key in ('version', 'mode', 'account')):
        result.update(orders=empty_orders('changed'), analysis=empty_analysis('changed'))
    else:
        result['orders']['unresolved_count'] = sum(row.get('account') == account and row.get('status') in ('sending', 'unknown')
                                                    for row in after['operations'])
    return result


@router.get('/briefing')
def briefing(account: str = Query(min_length=1, max_length=64), watch=Depends(get_watch),
             trading=Depends(get_service), operation=Depends(get_operation)):
    return build_briefing(account, watch, trading, operation)
