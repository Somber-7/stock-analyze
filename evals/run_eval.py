"""평가셋을 실제 모델에 돌려 규칙별 통과율·소요 시간·토큰을 기록한다.

    python -m evals.run_eval --app-settings            # 앱에 저장된 AI 설정 사용
    python -m evals.run_eval --provider openai --model gpt-5-mini   # 키는 STOCK_EVAL_API_KEY

API 호출 비용이 든다(사례 5개 × --repeat). 키는 출력하거나 결과 파일에 쓰지 않는다.
결과는 evals/results/에 JSON으로 남는다.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.ai.generation import _INCOMPLETE, _MALFORMED, generate
from backend.ai.providers import ProviderError, ReportValidationError
from backend.ai.telemetry import percentile

from .cases import CASES, OBJECTIVE

RESULTS = Path(__file__).parent / 'results'


def run_case(case, generate_fn):
    """한 번 실행. outcome: pass / fail(규칙 위반) / rejected(앱 검증이 응답을 거절) / incomplete / error."""
    ctx = case['build']()
    began = time.monotonic()
    record = dict(case=case['id'], outcome='error', checks=[], usage=None, error='')
    try:
        result = generate_fn(ctx, OBJECTIVE)
        record['usage'] = result['usage']
        record['analysis'] = result['analysis']
        for name, check in case['checks']:
            ok, detail = check(result['analysis'], ctx)
            record['checks'].append(dict(name=name, ok=ok, detail=detail))
        record['outcome'] = 'pass' if all(c['ok'] for c in record['checks']) else 'fail'
    except ReportValidationError as exc:
        record.update(outcome='rejected', usage=exc.usage, error=str(exc))
    except ProviderError as exc:
        message = str(exc)
        record.update(outcome='rejected' if message == _MALFORMED else 'incomplete' if message == _INCOMPLETE else 'error',
                      error=message)
    record['elapsed_ms'] = round((time.monotonic() - began) * 1000)
    return record


def evaluate(generate_fn, cases=CASES, repeat=1, on_record=None):
    records = []
    for case in cases:
        for _ in range(repeat):
            record = run_case(case, generate_fn)
            records.append(record)
            if on_record: on_record(record)
            if record['outcome'] == 'error' and '권한' in record['error']:
                return records  # 키·모델 권한 문제는 반복해도 같다
    return records


def summarize(records, cases=CASES):
    by_case = []
    for case in cases:
        rows = [r for r in records if r['case'] == case['id']]
        if not rows: continue
        outcomes = {k: sum(r['outcome'] == k for r in rows) for k in ('pass', 'fail', 'rejected', 'incomplete', 'error')}
        checks = {}
        for r in rows:
            for c in r['checks']:
                checks.setdefault(c['name'], []).append(c['ok'])
        by_case.append(dict(case=case['id'], title=case['title'], runs=len(rows), **outcomes,
                            checks={k: f'{sum(v)}/{len(v)}' for k, v in checks.items()}))
    answered = [r for r in records if r['outcome'] in ('pass', 'fail')]
    latency = [r['elapsed_ms'] for r in records if r['outcome'] != 'error']
    tokens = {name: sum((r['usage'] or {}).get(name) or 0 for r in records) for name in ('input_tokens', 'output_tokens')}
    return dict(runs=len(records), passed=sum(r['outcome'] == 'pass' for r in records),
                answered=len(answered), rejected=sum(r['outcome'] == 'rejected' for r in records),
                errors=sum(r['outcome'] in ('error', 'incomplete') for r in records),
                latency_ms=dict(p50=percentile(latency, 50), p95=percentile(latency, 95)),
                **tokens, by_case=by_case)


def _credentials(args):
    if args.app_settings:
        from backend.ai.api import get_ai_settings
        state = get_ai_settings().credentials()
        return state['provider'], state['model'], state['key']
    key = os.environ.get('STOCK_EVAL_API_KEY', '')
    if not (args.provider and args.model and key):
        sys.exit('--app-settings 또는 --provider, --model과 STOCK_EVAL_API_KEY 환경변수가 필요합니다.')
    return args.provider, args.model, key


def main():
    parser = argparse.ArgumentParser(description='Stock Analyze AI 분석 평가셋')
    parser.add_argument('--app-settings', action='store_true', help='앱에 저장된 AI 제공자·모델·키 사용')
    parser.add_argument('--provider', choices=('openai', 'anthropic', 'gemini'))
    parser.add_argument('--model')
    parser.add_argument('--repeat', type=int, default=3, help='사례별 반복 횟수 (기본 3)')
    parser.add_argument('--case', action='append', help='특정 사례만 (여러 번 지정 가능)')
    args = parser.parse_args()
    provider, model, key = _credentials(args)
    cases = [c for c in CASES if not args.case or c['id'] in args.case]

    def call(ctx, objective): return generate(provider, key, model, ctx, objective)

    def show(r):
        failed = [c['name'] for c in r['checks'] if not c['ok']]
        print(f"{r['case']:<28} {r['outcome']:<10} {r['elapsed_ms']/1000:>6.1f}s  {', '.join(failed) or r['error'][:60]}")

    records = evaluate(call, cases, args.repeat, on_record=show)
    key = None
    summary = summarize(records, cases)
    finished = datetime.now(timezone.utc)
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{finished:%Y%m%d-%H%M%S}-{provider}-{model.replace('/', '_')}.json"
    path.write_text(json.dumps(dict(provider=provider, model=model, repeat=args.repeat, finished_at=finished.isoformat(),
                                    summary=summary, records=records), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n통과 {summary['passed']}/{summary['runs']} · 앱 검증 거절 {summary['rejected']} · 오류 {summary['errors']}"
          f" · 소요 중앙값 {(summary['latency_ms']['p50'] or 0)/1000:.1f}s · 95% {(summary['latency_ms']['p95'] or 0)/1000:.1f}s"
          f" · 토큰 입력 {summary['input_tokens']:,} 출력 {summary['output_tokens']:,}")
    for row in summary['by_case']:
        print(f"  {row['case']:<28} 통과 {row['pass']}/{row['runs']}  {row['checks']}")
    print(f'결과 파일: {path}')


if __name__ == '__main__': main()
