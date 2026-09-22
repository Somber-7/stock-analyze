"""Latency and token summary over stored analysis runs; reads records only."""
import math

FINISHED = ('ready', 'error', 'interrupted')


def percentile(values, pct):
    """Nearest-rank percentile; None when there is nothing to rank."""
    if not values: return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def _count(value): return value if type(value) is int and value >= 0 else None


def _group(runs):
    timed = [r['timings'] for r in runs if isinstance(r.get('timings'), dict)]
    def stage(name):
        values = [t[name] for t in timed if _count(t.get(name)) is not None]
        return dict(p50=percentile(values, 50), p95=percentile(values, 95), samples=len(values))
    tokens = {}
    for name in ('input_tokens', 'output_tokens'):
        values = [_count((r.get('usage') or {}).get(name)) for r in runs]
        known = [v for v in values if v is not None]
        tokens[name] = dict(total=sum(known), per_run=round(sum(known) / len(known)) if known else None,
                            samples=len(known))
    return dict(runs=len(runs), ready=sum(r['status'] == 'ready' for r in runs),
                error=sum(r['status'] == 'error' for r in runs),
                interrupted=sum(r['status'] == 'interrupted' for r in runs),
                total_ms=stage('total_ms'), model_ms=stage('model_ms'), context_ms=stage('context_ms'),
                dart_ms=stage('dart_ms'), web_ms=stage('web_ms'), **tokens)


def summarize(runs, limit=50):
    """Summarize the most recent finished runs overall and per provider/model.

    Runs saved before timings were recorded count toward status and tokens only;
    each stage reports its own sample size.
    """
    recent = [r for r in runs if r.get('status') in FINISHED][-limit:]
    models = {}
    for run in recent:
        models.setdefault((run.get('provider', ''), run.get('model', '')), []).append(run)
    return dict(window=len(recent), overall=_group(recent),
                by_model=[dict(provider=p, model=m, **_group(rows)) for (p, m), rows in models.items()])
