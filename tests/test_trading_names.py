import unittest
from unittest.mock import patch

from backend.namuh import stocks


class TradingNameTests(unittest.TestCase):
    def test_existing_records_get_names_without_changing_order_identity(self):
        book = {'orders': [{'code': '005930', 'request': {'code': '005930'}}],
                'rules': [{'code': '000660'}], 'operations': [{'code': '999999'}],
                'positions': [{'code': '999998', 'name': '이전 종목명'}]}
        with patch.object(stocks, 'get_snapshot', return_value={'stocks': [
                {'code': '005930', 'name': '삼성전자'}, {'code': '000660', 'name': 'SK하이닉스'}]}):
            result = stocks.trading_names(book)
        self.assertEqual(result['orders'][0]['name'], '삼성전자')
        self.assertEqual(result['rules'][0]['name'], 'SK하이닉스')
        self.assertEqual(result['operations'][0]['name'], '')
        self.assertEqual(result['positions'][0]['name'], '이전 종목명')
        self.assertEqual(result['orders'][0]['request'], {'code': '005930'})
        self.assertNotIn('name', book['orders'][0])

    def test_missing_master_keeps_history_available(self):
        with patch.object(stocks, 'get_snapshot', return_value={'stocks': []}):
            result = stocks.trading_names({'orders': [{'code': '005930'}]})
        self.assertEqual(result['orders'], [{'code': '005930', 'name': ''}])


if __name__ == '__main__':
    unittest.main()
