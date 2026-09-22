import unittest
from unittest.mock import Mock, patch
from backend.ai.context import portfolio_snapshot, load_context


class AIContextTests(unittest.TestCase):
    def test_cma_is_cash_management_balance_without_double_counting_orderable_funds(self):
        trading = Mock()
        trading.snapshot.return_value = dict(mode='live',account='private-account')
        trading.gateway.balance.return_value = dict(summary=dict(cash=123, cash_orderable_100=7000000,
                                                                total_assets=8015323, net_assets=8015323), holdings=[
            dict(code='0011T0',name='채비',quantity=3,avg_price=5000,eval_amount=15000),
            dict(code='NHKRCMA030',name='CMA 발행어음',quantity=8000000,avg_price=1,eval_amount=8000000),
            dict(code='999999',name='미확인 종목',quantity=2,avg_price=100),
        ])
        with patch('backend.ai.context.stock_symbols',return_value=[dict(code='0011T0',name='채비')]):
            result = portfolio_snapshot(trading)
        self.assertEqual([row['code'] for row in result['holdings']],['0011T0'])
        self.assertEqual(result['deposit_cash'],123)
        self.assertEqual(result['available_cash'],7000000)
        self.assertEqual(result['total_assets'],8015323)
        self.assertEqual(result['cash_management_assets'][0]['eval_amount'],8000000)
        self.assertEqual(result['cma_balance'],8000000)
        self.assertEqual(result['cash_balance'],8000123)
        self.assertEqual(len(result['other_assets']),1)
        self.assertNotIn('quantity',result['other_assets'][0])
        self.assertEqual(result['excluded_holdings_count'],2)
        self.assertNotIn('private-account',str(result))

    def test_unknown_cma_valuation_is_not_guessed_from_quantity(self):
        trading = Mock()
        trading.snapshot.return_value = dict(mode='live', account='private-account')
        trading.gateway.balance.return_value = dict(summary=dict(cash=0,cash_orderable_100=750,total_assets=1000),holdings=[
            dict(code='NHKRCMA030',name='CMA 발행어음',quantity=900,eval_amount=None)])
        with patch('backend.ai.context.stock_symbols',return_value=[]): result = portfolio_snapshot(trading)
        self.assertIsNone(result['cma_balance'])
        self.assertIsNone(result['cash_balance'])
        self.assertEqual(result['available_cash'],750)
        self.assertEqual(result['total_assets'],1000)
        self.assertFalse(result['other_assets'])

    def test_paper_holdings_use_same_domestic_symbol_filter(self):
        trading = Mock()
        trading.snapshot.return_value = dict(mode='paper')
        trading.paper.snapshot.return_value = dict(available_cash=100, positions=[
            dict(code='005930',quantity=2,average_price=100),
            dict(code='UNKNOWN',quantity=1,average_price=1),
        ])
        with patch('backend.ai.context.stock_symbols',return_value=[dict(code='005930',name='삼성전자')]):
            result = portfolio_snapshot(trading)
        self.assertEqual([row['code'] for row in result['holdings']],['005930'])
        self.assertEqual(result['excluded_holdings_count'],1)
        trading.gateway.balance.assert_not_called()

    def test_missing_orderable_cash_is_unknown_even_with_deposit_and_cma(self):
        trading = Mock()
        trading.snapshot.return_value = dict(mode='live',account='private-account')
        trading.gateway.balance.return_value = dict(summary=dict(cash=9000),holdings=[])
        with patch('backend.ai.context.stock_symbols',return_value=[]):
            result = portfolio_snapshot(trading)
        self.assertIsNone(result.get('available_cash', 'missing'))
        self.assertIsNone(result['total_assets'])
        self.assertEqual(result['deposit_cash'],9000)

    def test_context_includes_per_stock_capacity_and_failure_is_unknown_not_zero(self):
        trading = Mock()
        trading.snapshot.return_value = dict(mode='live',account='private-account')
        trading.gateway.balance.return_value = dict(summary=dict(cash=0, cash_orderable_100=800),holdings=[])
        config = dict(codes=['005930'],include_us=False,investment_horizon='medium')
        with patch('backend.ai.context.stock_symbols',return_value=[dict(code='005930',name='삼성전자')]), \
             patch('backend.ai.context.get_current_price',return_value=dict(price=100)), \
             patch('backend.ai.context.get_daily_chart',return_value=[]) as daily, \
             patch('backend.ai.context.get_investors',return_value=None):
            trading.gateway.capacity.return_value = dict(quantity=7,amount=750)
            result = load_context(config,trading)
            self.assertEqual(result['stocks'][0]['buy_capacity']['amount'],750)
            self.assertEqual(result['stocks'][0]['buy_capacity']['quantity'],7)
            self.assertEqual(result['portfolio']['available_cash'],800)
            self.assertEqual(result['investment_horizon'],'medium')
            self.assertEqual([c.kwargs['days'] for c in daily.call_args_list],[132,132])
            self.assertEqual([c.args[0] for c in daily.call_args_list],['005930','069500'])
            self.assertTrue(result['stocks'][0]['data_quality']['requires_defer'])
            self.assertEqual(result['stocks'][0]['metrics']['bars'],0)
            self.assertNotIn('private-account',str(result))
            trading.gateway.capacity.side_effect = RuntimeError('secret upstream')
            result = load_context(config,trading)
            self.assertIsNone(result['stocks'][0]['buy_capacity']['amount'])
            self.assertIsNone(result['stocks'][0]['buy_capacity']['quantity'])
            self.assertTrue(any('주문가능' in warning for warning in result['warnings']))
            self.assertNotIn('secret upstream',str(result))


if __name__ == '__main__': unittest.main()
