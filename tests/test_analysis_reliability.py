import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone
from backend.ai.context import load_context


class ReliabilityTests(unittest.TestCase):
    def collect(self, holdings, capacity_error=None):
        trading = Mock()
        trading.snapshot.return_value = dict(mode='live', account='private-account')
        trading.gateway.balance.return_value = dict(summary=dict(cash=800, cash_orderable_100=800,
            total_assets=1800, net_assets=1800), holdings=holdings)
        trading.gateway.capacity.return_value = dict(amount=800, quantity=8)
        if capacity_error: trading.gateway.capacity.side_effect = capacity_error
        day = datetime.now(timezone.utc).date() - timedelta(days=1)
        rows = []
        while len(rows) < 65:
            if day.weekday() < 5: rows.append(dict(time=day.isoformat(),open=100,high=100,low=100,close=100,volume=1))
            day -= timedelta(days=1)
        with patch('backend.ai.context.stock_symbols', return_value=[dict(code='005930',name='삼성전자')]), \
             patch('backend.ai.context.get_current_price', return_value=dict(price=200)), \
             patch('backend.ai.context.get_daily_chart', return_value=rows), \
             patch('backend.ai.context.get_investors', return_value=None):
            return load_context(dict(codes=['005930'],include_us=False,investment_horizon='unspecified'),trading)

    def test_weights_use_balance_not_newer_quotes(self):
        result = self.collect([dict(code='005930',name='삼성전자',quantity=10,avg_price=90,current_price=100,eval_amount=1000)])
        stock = result['stocks'][0]
        self.assertEqual(stock['holding_eval_amount'],1000)
        self.assertAlmostEqual(stock['account_weight_pct'],55.5556)
        self.assertEqual(stock['price_basis']['balance_price'],100)
        self.assertEqual(stock['price_basis']['quote_price'],200)
        self.assertEqual(stock['price_basis']['daily_close'],100)

    def test_sixty_return_retains_baseline_candle(self):
        result = self.collect([])
        self.assertEqual(result['stocks'][0]['metrics']['return_60_pct'],0)
        self.assertGreaterEqual(len(result['stocks'][0]['daily']),61)

    def test_unknown_valuation_does_not_fallback_to_live_price(self):
        stock = self.collect([dict(code='005930',quantity=10,avg_price=90)])['stocks'][0]
        self.assertIsNone(stock['holding_eval_amount'])
        self.assertIsNone(stock['account_weight_pct'])

    def test_capacity_diagnostic_excludes_arbitrary_exception_message(self):
        stock = self.collect([],RuntimeError('private-account secret-key'))['stocks'][0]
        self.assertEqual(stock['buy_capacity']['diagnostic']['stage'],'unexpected')
        self.assertNotIn('private-account',str(stock))
        self.assertNotIn('secret-key',str(stock))


if __name__ == '__main__': unittest.main()
