import unittest
from datetime import date, timedelta


class MetricsTests(unittest.TestCase):
    def metrics(self, bars, investors=None):
        from backend.ai.metrics import calculate_metrics
        return calculate_metrics(bars, investors)

    def test_returns_volatility_and_volume_use_prior_sessions(self):
        bars = [dict(time=str(date(2026,8,1)+timedelta(days=i)),close=100,volume=100) for i in range(21)]
        bars[-1].update(close=120,volume=200)
        m = self.metrics(list(reversed(bars)))
        self.assertEqual(m['return_5_pct'],20)
        self.assertEqual(m['return_20_pct'],20)
        self.assertEqual(m['sma_20'],101)
        self.assertIsNone(m['sma_60'])
        self.assertAlmostEqual(m['daily_volatility_20_pct'],4.4721,places=4)
        self.assertEqual(m['volume_ratio_20'],2)

    def test_missing_or_invalid_values_are_not_zero_or_infinite(self):
        m = self.metrics([dict(time='invalid',close=10,volume=100),
                          dict(time='2026-09-11',close=float('nan'),volume=0)])
        self.assertEqual(m['bars'],0)
        self.assertIsNone(m['return_5_pct'])
        self.assertIsNone(m['daily_volatility_20_pct'])
        self.assertIsNone(m['volume_ratio_20'])

    def test_long_horizon_returns_require_full_observation_window(self):
        bars = [dict(time=str(date(2025,1,1)+timedelta(days=i)),close=100+i,volume=100) for i in range(241)]
        m = self.metrics(bars)
        self.assertEqual(m['return_240_pct'],240)
        self.assertEqual(m['sma_120'],280.5)
        self.assertIsNone(self.metrics(bars[:120])['return_120_pct'])

    def test_flow_signs_preserve_missing_values_and_do_not_invent_units(self):
        rows = [dict(date=f'2026-09-{day:02}',foreign=f,institutional=i)
                for day,f,i in [(11,4,1),(10,3,2),(9,-1,3),(8,2,4),(7,1,5)]]
        m = self.metrics([],dict(rows=rows,unit=None))
        self.assertEqual(m['flows']['foreign']['positive_days'],4)
        self.assertEqual(m['flows']['foreign']['latest_buy_streak'],2)
        self.assertEqual(m['flows']['institutional']['positive_days'],5)
        rows[0]['foreign'] = None
        m = self.metrics([],dict(rows=rows,unit=None))
        self.assertIsNone(m['flows']['foreign']['latest_buy_streak'])
        self.assertEqual(m['flows']['foreign']['observations'],4)


if __name__ == '__main__': unittest.main()
