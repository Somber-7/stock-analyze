import unittest
from datetime import datetime, timedelta, timezone

from backend.ai.quality import prepare_daily


class QualityTests(unittest.TestCase):
    def bars(self, end='2026-09-14', count=60):
        day = datetime.fromisoformat(end).date()
        rows = []
        while len(rows) < count:
            if day.weekday() < 5:
                rows.append(dict(time=day.isoformat(), open=100, high=110, low=90, close=100, volume=100))
            day -= timedelta(days=1)
        return list(reversed(rows))

    def prepare(self, rows, at='2026-09-15T01:00:00+00:00', requested=60):
        return prepare_daily(rows, requested, datetime.fromisoformat(at))

    def test_intraday_bar_is_excluded_from_completed_indicators(self):
        rows = self.bars('2026-09-15', 61)
        clean, quality = self.prepare(rows)
        self.assertEqual(clean[-1]['time'], '2026-09-14')
        self.assertEqual(quality['partial_bars'], 1)
        self.assertFalse(quality['requires_defer'])
        self.assertEqual(quality['status'], 'checked')

    def test_weekend_uses_friday_and_missing_weekday_is_not_called_holiday(self):
        _, quality = self.prepare(self.bars('2026-09-11'), '2026-09-12T01:00:00+00:00')
        self.assertFalse(quality['requires_defer'])
        _, quality = self.prepare(self.bars('2026-09-11'))
        self.assertTrue(quality['requires_defer'])
        self.assertEqual(quality['status'], 'review')
        self.assertTrue(any('휴장' in note for note in quality['issues']))

    def test_future_and_conflicting_duplicates_never_enter_model(self):
        rows = self.bars()
        rows += [dict(rows[-1], close=101), dict(rows[-1], time='2026-09-16')]
        clean, quality = self.prepare(rows)
        self.assertTrue(quality['requires_defer'])
        self.assertEqual(quality['invalid_bars'], 2)
        self.assertNotIn('2026-09-14', [r['time'] for r in clean])
        self.assertNotIn('2026-09-16', [r['time'] for r in clean])

    def test_empty_and_nonfinite_data_require_defer(self):
        for rows in ([], [dict(time='2026-09-14', close=float('nan'), volume=100)]):
            clean, quality = self.prepare(rows)
            self.assertEqual(clean, [])
            self.assertTrue(quality['requires_defer'])

    def test_short_history_is_limited_without_claiming_listing_date(self):
        _, quality = self.prepare(self.bars(count=25), requested=130)
        self.assertEqual(quality['status'], 'limited')
        self.assertFalse(quality['requires_defer'])
        self.assertEqual(quality['requested_bars'], 130)

    def test_closed_today_and_identical_duplicate_are_usable(self):
        rows = self.bars('2026-09-15')
        rows.append(dict(rows[-1]))
        clean, quality = self.prepare(rows, '2026-09-15T07:00:00+00:00')
        self.assertEqual(len(clean), 60)
        self.assertFalse(quality['requires_defer'])

    def test_invalid_ohlc_and_volume_are_excluded(self):
        rows = self.bars()
        rows[-1]['high'] = 50
        rows[-2]['volume'] = -1
        clean, quality = self.prepare(rows)
        self.assertEqual(len(clean), 58)
        self.assertTrue(quality['requires_defer'])


if __name__ == '__main__': unittest.main()
