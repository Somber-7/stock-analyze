"""Bounded historical context and deterministic comparisons, never performance claims."""
import hashlib
import json


def comparison_scope(config, trading_state):
    fields = {key: config.get(key) for key in ('objective', 'investment_horizon', 'include_us', 'include_web', 'include_dart', 'holding_purpose', 'max_position_pct', 'review_drawdown_pct')}
    fields.update(codes=sorted(config['codes']), mode=trading_state['mode'], account=trading_state.get('account'))
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def previous_analysis(runs, scope, run_id):
    for run in reversed(runs):
        if run['id'] == run_id or run['status'] != 'ready' or run.get('comparison_scope') != scope:
            continue
        return dict(id=run['id'], completed_at=run['completed_at'], data_at=run.get('data_at'),
                    provider=run['provider'], model=run['model'],
                    decisions=[{key: row.get(key) for key in ('code', 'assessment', 'target_quantity',
                        'current_quantity', 'reference_price', 'rationale', 'review_conditions', 'metrics',
                        'market_view', 'decision_basis', 'headline')} for row in run['decisions']])
    return None


def compare_decision(row, previous):
    prior = next((p for p in (previous or {}).get('decisions', []) if p['code'] == row['code']), None)
    if not prior:
        return None
    before = prior['reference_price']
    # Old records have no separate market opinion; missing is not a neutral opinion.
    market_changed = bool(prior.get('market_view') and row.get('market_view') and prior['market_view'] != row['market_view'])
    basis_changed = bool(prior.get('decision_basis') and row.get('decision_basis') and prior['decision_basis'] != row['decision_basis'])
    return dict(previous_assessment=prior.get('assessment'), previous_target=prior['target_quantity'],
        previous_quantity=prior['current_quantity'], target_delta=row['target_quantity'] - prior['target_quantity'],
        holding_delta=row['current_quantity'] - prior['current_quantity'],
        price_change_pct=round((row['reference_price'] / before - 1) * 100, 4) if before and before > 0 else None,
        changed=row['assessment'] != prior.get('assessment') or row['target_quantity'] != prior['target_quantity'] or market_changed or basis_changed,
        previous_market_view=prior.get('market_view'), previous_decision_basis=prior.get('decision_basis'),
        market_view_changed=market_changed, decision_basis_changed=basis_changed,
        previous_conditions=prior.get('review_conditions'))
