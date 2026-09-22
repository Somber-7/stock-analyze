import unittest

from backend.ai.telemetry import percentile, summarize


def run(status, total=None, model=None, tokens=(None, None), name='gpt-test'):
    record = dict(status=status, provider='openai', model=name,
                  usage=dict(input_tokens=tokens[0], output_tokens=tokens[1]))
    if total is not None: record['timings'] = dict(total_ms=total, model_ms=model)
    return record


class TelemetryTests(unittest.TestCase):
    def test_nearest_rank_percentile(self):
        self.assertIsNone(percentile([], 50))
        self.assertEqual(percentile([5], 95), 5)
        self.assertEqual(percentile(list(range(1, 101)), 50), 50)
        self.assertEqual(percentile(list(range(1, 101)), 95), 95)
        self.assertEqual(percentile([30, 10, 20], 50), 20)

    def test_status_latency_and_tokens(self):
        runs = [run('ready', 1000, 800, (100, 50)), run('ready', 3000, 2500, (200, 70)),
                run('error', 500, None, (None, None)), run('analyzing', 10)]
        overall = summarize(runs)['overall']
        self.assertEqual((overall['runs'], overall['ready'], overall['error']), (3, 2, 1))
        self.assertEqual(overall['total_ms'], dict(p50=1000, p95=3000, samples=3))
        self.assertEqual(overall['model_ms']['samples'], 2)
        self.assertEqual(overall['input_tokens'], dict(total=300, per_run=150, samples=2))
        self.assertEqual(overall['output_tokens']['total'], 120)

    def test_old_runs_without_timings_count_only_toward_status(self):
        overall = summarize([run('ready', tokens=(10, 5)), run('ready', 900, 700, (10, 5))])['overall']
        self.assertEqual(overall['ready'], 2)
        self.assertEqual(overall['total_ms']['samples'], 1)
        self.assertEqual(overall['input_tokens']['samples'], 2)

    def test_window_and_model_groups(self):
        runs = [run('ready', i, i, (1, 1), name='a' if i % 2 else 'b') for i in range(1, 61)]
        result = summarize(runs, limit=50)
        self.assertEqual(result['window'], 50)
        self.assertEqual({g['model']: g['runs'] for g in result['by_model']}, {'a': 25, 'b': 25})

    def test_malformed_counts_are_ignored(self):
        bad = dict(status='ready', usage=dict(input_tokens=-1, output_tokens='5'), timings=dict(total_ms=True))
        overall = summarize([bad])['overall']
        self.assertEqual(overall['input_tokens']['samples'], 0)
        self.assertEqual(overall['total_ms']['samples'], 0)


if __name__ == '__main__': unittest.main()
