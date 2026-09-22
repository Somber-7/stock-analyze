import json
import tempfile
import os
from datetime import datetime
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.namuh import stocks


def record(code, name):
    return code.encode('ascii') + b'1' + name.encode('cp949').ljust(41, b' ') + b' ' * 188 + b'\n'


class NamuhStocksTests(unittest.TestCase):
    def test_next_calendar_day_refreshes_even_if_cache_is_less_than_24_hours_old(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / '.namuh_stocks.json'
            file.write_text('[]')
            previous = datetime(2026, 9, 10, 18).timestamp()
            os.utime(file, (previous, previous))
            with patch.object(stocks, 'STOCKS_FILE', file), patch.object(stocks, '_next_attempt', 0), \
                 patch.object(stocks, 'datetime', wraps=datetime) as clock, \
                 patch.object(stocks.threading, 'Thread') as thread:
                clock.now.return_value = datetime(2026, 9, 11, 9, 5)
                stocks.ensure_fresh()
                thread.return_value.start.assert_called_once()

    def test_official_byte_offsets_preserve_korean_names_and_leading_zero(self):
        parsed = stocks.parse_master(record('005930', '삼성전자') + record('000660', 'SK하이닉스'))
        self.assertEqual([(r['code'], r['name']) for r in parsed],
                         [('005930', '삼성전자'), ('000660', 'SK하이닉스')])

    def test_master_cap_is_already_in_hundred_million_won_and_markers_are_removed(self):
        row = bytearray(record('005930', '*삼성전자'))
        row[152:159] = b'0259500'
        row[174:186] = b'000015171092'
        data = stocks.parse_master(bytes(row))[0]
        self.assertEqual(data['name'], '삼성전자')
        self.assertEqual(data['previous_market_cap'], 15171092)
        self.assertEqual(data['previous_close'], 259500)
        self.assertEqual(data['market'], 'KOSPI')

    def test_invalid_master_is_rejected(self):
        for content in (b'', b'<html>Error</html>', record('005930', '삼성전자')[:-1]):
            with self.subTest(content=content[:10]), self.assertRaises(ValueError):
                stocks.parse_master(content)

    def test_only_namuh_master_is_requested_and_search_uses_its_cache(self):
        def respond(request):
            self.assertEqual(str(request.url), 'https://www.nhplug.com/instruments/m_new_stock.mst')
            return httpx.Response(200, content=record('005930', '삼성전자'))
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / '.namuh_stocks.json'
            with patch.object(stocks, 'STOCKS_FILE', file), \
                 httpx.Client(transport=httpx.MockTransport(respond)) as client:
                stocks.refresh_stocks(client=client)
                self.assertEqual(stocks.search('삼성'), [{'code': '005930', 'name': '삼성전자'}])
                self.assertEqual(stocks.search('0059')[0]['name'], '삼성전자')

    def test_failed_download_preserves_last_valid_namuh_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / '.namuh_stocks.json'
            content = json.dumps([{'code': '005930', 'name': '삼성전자'}])
            file.write_text(content, encoding='utf-8')
            with patch.object(stocks, 'STOCKS_FILE', file), \
                 httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
                stocks.refresh_stocks(client=client)
                self.assertEqual(file.read_text(encoding='utf-8'), content)

    def test_old_external_stock_list_is_not_used(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'stocks.json').write_text('[{"code":"OLD","name":"old"}]')
            with patch.object(stocks, 'STOCKS_FILE', Path(directory) / '.namuh_stocks.json'), \
                 patch.object(stocks, 'ensure_fresh'):
                self.assertEqual(stocks.search('old'), [])

    def test_missing_cache_retries_with_backoff_instead_of_requiring_restart(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(stocks, 'STOCKS_FILE', Path(directory) / '.namuh_stocks.json'), \
             patch.object(stocks, '_next_attempt', 0), patch.object(stocks.time, 'monotonic') as clock, \
             patch.object(stocks.threading, 'Thread') as thread:
            clock.return_value = 100
            stocks.search('삼성')
            stocks.search('삼성')
            self.assertEqual(thread.return_value.start.call_count, 1)
            clock.return_value = 161
            stocks.search('삼성')
            self.assertEqual(thread.return_value.start.call_count, 2)
