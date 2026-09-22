import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

from backend.ai.outcomes import evaluate_outcomes


KST = timezone(timedelta(hours=9))


def bar(day, close, **values):
    result = dict(time=day, open=close, high=close, low=close, close=close, volume=100)
    result.update(values)
    return result


class AIOutcomeTests(unittest.TestCase):
    def run_data(self, *, assessment='supported', side='buy'):
        stock_daily = [bar('2026-08-31', 90), bar('2026-09-01', 100)]
        benchmark_daily = [bar('2026-08-31', 190), bar('2026-09-01', 200)]
        return dict(
            id='run-1', completed_at='2026-09-01T07:00:00+00:00',
            investment_horizon='medium',
            decisions=[dict(code='005930', name='삼성전자', assessment=assessment, side=side)],
            input_snapshot=dict(
                schema_version=1,
                config=dict(investment_horizon='medium'),
                context=dict(
                    fetched_at='2026-09-01T06:59:00+00:00',
                    stocks=[dict(code='005930', name='삼성전자', daily=stock_daily, metrics={})],
                    benchmark=dict(code='069500', name='KODEX 200', daily=benchmark_daily))))

    def test_uses_saved_baseline_and_subsequent_trading_observations_without_mutation(self):
        run = self.run_data()
        original = copy.deepcopy(run)
        stock = [bar(f'2026-09-{day:02d}', close) for day, close in
                 [(1, 100), (2, 102), (3, 98), (4, 105), (7, 103), (8, 110),
                  (9, 111), (10, 112), (11, 113), (14, 114), (15, 115),
                  (16, 116), (17, 117), (18, 118), (21, 119), (22, 120),
                  (23, 121), (24, 122), (25, 123), (28, 124), (29, 125)]]
        benchmark = [bar('2026-09-01', 200)] + [
            bar(f'2026-09-{day:02d}', close) for day, close in
            [(2, 202), (3, 198), (4, 205), (7, 204), (8, 220),
             (9, 221), (10, 222), (11, 223), (14, 224), (15, 225),
             (16, 226), (17, 227), (18, 228), (21, 229), (22, 230),
             (23, 231), (24, 232), (25, 233), (28, 234), (29, 240)]]

        result = evaluate_outcomes(run, {'005930': stock}, benchmark,
                                    datetime(2026, 9, 29, 16, 0, tzinfo=KST))

        self.assertEqual(run, original)
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['counts'], dict(total=1, supported=1, deferred=0,
                                                directional_eligible=1))
        self.assertNotIn('hit_rate', json.dumps(result))
        item = result['items'][0]
        self.assertEqual(item['baseline'], dict(date='2026-09-01', close=100,
                                                source='immutable_input_snapshot'))
        five, twenty, sixty = item['horizons']
        self.assertEqual((five['observations'], five['status'], five['end_date']),
                         (5, 'complete', '2026-09-08'))
        self.assertEqual(five['return_pct'], 10.0)
        self.assertEqual(five['max_drawdown_pct'], -3.9216)
        self.assertEqual(five['benchmark_return_pct'], 10.0)
        self.assertEqual(five['excess_return_pp'], 0.0)
        self.assertEqual(five['directional_return_pct'], 10.0)
        self.assertEqual((twenty['status'], twenty['return_pct'], twenty['end_date']),
                         ('complete', 25.0, '2026-09-29'))
        self.assertEqual(sixty['status'], 'pending')
        self.assertEqual(sixty['available_observations'], 20)
        self.assertIsNone(sixty['return_pct'])
        json.dumps(result, allow_nan=False)

    def test_today_is_excluded_until_kst_close_and_same_day_never_counts(self):
        run = self.run_data()
        stock = [bar('2026-09-01', 100), bar('2026-09-02', 101), bar('2026-09-03', 102),
                 bar('2026-09-04', 103), bar('2026-09-07', 104), bar('2026-09-08', 105)]
        before_close = evaluate_outcomes(run, {'005930': stock}, [],
            datetime(2026, 9, 8, 15, 39, tzinfo=KST))['items'][0]['horizons'][0]
        at_close = evaluate_outcomes(run, {'005930': stock}, [],
            datetime(2026, 9, 8, 15, 40, tzinfo=KST))['items'][0]['horizons'][0]
        self.assertEqual(before_close['status'], 'pending')
        self.assertEqual(before_close['available_observations'], 4)
        self.assertEqual(at_close['status'], 'complete')
        self.assertEqual(at_close['end_date'], '2026-09-08')

    def test_defer_is_counted_separately_without_directional_claim(self):
        run = self.run_data(assessment='defer', side='buy')
        stock = [bar('2026-09-01', 100)] + [bar(f'2026-09-{day:02d}', 100 + index)
                 for index, day in enumerate((2, 3, 4, 7, 8), start=1)]
        result = evaluate_outcomes(run, {'005930': stock}, [],
                                   datetime(2026, 9, 8, 16, 0, tzinfo=KST))
        self.assertEqual(result['counts']['deferred'], 1)
        self.assertEqual(result['counts']['directional_eligible'], 0)
        self.assertIsNone(result['items'][0]['horizons'][0]['directional_return_pct'])

    def test_legacy_run_without_snapshot_is_unavailable(self):
        run = self.run_data()
        del run['input_snapshot']
        result = evaluate_outcomes(run, {'005930': [bar('2026-09-02', 110)]}, [],
                                   datetime(2026, 9, 2, 16, 0, tzinfo=KST))
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['reason'], 'immutable_input_snapshot_missing')
        self.assertEqual(result['items'], [])
        self.assertEqual(result['counts'], dict(total=1, supported=1, deferred=0,
                                                directional_eligible=1))

    def test_live_series_must_prove_the_saved_baseline_price_and_date(self):
        future_only = [bar(f'2026-09-{day:02d}', 100 + day) for day in (2, 3, 4, 7, 8)]
        result = evaluate_outcomes(self.run_data(), {'005930': future_only}, [],
            datetime(2026, 9, 8, 16, 0, tzinfo=KST))
        self.assertEqual(result['items'][0]['reason'], 'series_coverage_missing')

        revised = [bar('2026-09-01', 99)] + future_only
        result = evaluate_outcomes(self.run_data(), {'005930': revised}, [],
            datetime(2026, 9, 8, 16, 0, tzinfo=KST))
        self.assertEqual(result['items'][0]['reason'], 'baseline_price_changed')

    def test_duplicate_date_with_different_ohlcv_is_conflicting_even_when_close_matches(self):
        rows = [bar('2026-09-01', 100), bar('2026-09-02', 101),
                bar('2026-09-02', 101, volume=200)]
        result = evaluate_outcomes(self.run_data(), {'005930': rows}, [],
            datetime(2026, 9, 2, 16, 0, tzinfo=KST))
        self.assertEqual(result['items'][0]['reason'], 'conflicting_duplicate_date')

    def test_snapshot_baseline_must_not_follow_fetch_cutoff_or_failed_quality(self):
        run = self.run_data()
        run['input_snapshot']['context']['fetched_at'] = '2026-08-31T06:30:00+00:00'
        result = evaluate_outcomes(run, {'005930': [bar('2026-09-01', 100)]}, [],
            datetime(2026, 9, 2, 16, 0, tzinfo=KST))
        self.assertEqual(result['items'][0]['reason'], 'snapshot_baseline_invalid')

        run = self.run_data()
        run['input_snapshot']['context']['stocks'][0]['data_quality'] = dict(requires_defer=True)
        result = evaluate_outcomes(run, {'005930': [bar('2026-09-01', 100)]}, [],
            datetime(2026, 9, 2, 16, 0, tzinfo=KST))
        self.assertEqual(result['items'][0]['reason'], 'snapshot_baseline_invalid')

    def test_evaluation_before_completion_is_unavailable(self):
        result = evaluate_outcomes(self.run_data(), {'005930': [bar('2026-09-01', 100)]}, [],
            datetime(2026, 9, 1, 15, 59, tzinfo=KST))
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['reason'], 'invalid_evaluation_time')

    def test_invalid_or_conflicting_stock_series_is_unavailable(self):
        for rows in (
            [bar('2026-09-02', 101), bar('2026-09-02', 102)],
            [bar('2026-09-02', float('nan'))],
            [dict(time='2026-09-02', close=101)],
            [bar('2026-09-02', 101, high=100)],
            [bar('2026-09-05', 101)],
            [bar('2026-10-01', 101)],
        ):
            with self.subTest(rows=rows):
                result = evaluate_outcomes(self.run_data(), {'005930': rows}, [],
                    datetime(2026, 9, 8, 16, 0, tzinfo=KST))
                item = result['items'][0]
                self.assertEqual(item['status'], 'unavailable')
                self.assertEqual(item['horizons'][0]['status'], 'unavailable')
                json.dumps(result, allow_nan=False)

    def test_gaps_count_valid_observations_but_benchmark_requires_exact_dates(self):
        stock = [bar(day, close) for day, close in (
            ('2026-09-01', 100),
            ('2026-09-02', 101), ('2026-09-04', 102), ('2026-09-07', 103),
            ('2026-09-09', 104), ('2026-09-11', 110))]
        benchmark = [bar(day, close) for day, close in (
            ('2026-09-01', 200),
            ('2026-09-02', 202), ('2026-09-04', 204), ('2026-09-07', 206),
            ('2026-09-09', 208))]
        metric = evaluate_outcomes(self.run_data(), {'005930': stock}, benchmark,
            datetime(2026, 9, 11, 16, 0, tzinfo=KST))['items'][0]['horizons'][0]
        self.assertEqual(metric['status'], 'complete')
        self.assertEqual(metric['end_date'], '2026-09-11')
        self.assertEqual(metric['benchmark_status'], 'unavailable')
        self.assertEqual(metric['benchmark_reason'], 'exact_end_date_missing')
        self.assertIsNone(metric['benchmark_return_pct'])
        self.assertIsNone(metric['excess_return_pp'])

    def test_benchmark_live_series_must_match_its_saved_baseline(self):
        stock = [bar(f'2026-09-{day:02d}', close) for day, close in
                 ((1, 100), (2, 101), (3, 102), (4, 103), (7, 104), (8, 105))]
        for benchmark, reason in (
            ([bar('2026-09-02', 201), bar('2026-09-08', 210)], 'series_coverage_missing'),
            ([bar('2026-09-01', 199), bar('2026-09-08', 210)], 'baseline_price_changed'),
        ):
            with self.subTest(reason=reason):
                metric = evaluate_outcomes(self.run_data(), {'005930': stock}, benchmark,
                    datetime(2026, 9, 8, 16, 0, tzinfo=KST))['items'][0]['horizons'][0]
                self.assertEqual(metric['status'], 'complete')
                self.assertEqual(metric['benchmark_status'], 'unavailable')
                self.assertEqual(metric['benchmark_reason'], reason)

    def test_sell_direction_inverts_price_observation(self):
        run = self.run_data(side='sell')
        stock = [bar(f'2026-09-{day:02d}', close) for day, close in
                 ((1, 100), (2, 101), (3, 102), (4, 103), (7, 104), (8, 110))]
        metric = evaluate_outcomes(run, {'005930': stock}, [],
            datetime(2026, 9, 8, 16, 0, tzinfo=KST))['items'][0]['horizons'][0]
        self.assertEqual(metric['return_pct'], 10.0)
        self.assertEqual(metric['directional_return_pct'], -10.0)


if __name__ == '__main__':
    unittest.main()
