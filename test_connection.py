"""Read-only NAMUH smoke test. Never prints tokens or account details."""
from backend.namuh.client import get_client
from backend.namuh.market import get_current_price
from backend.namuh.portfolio import get_accounts, get_balance
from backend.namuh.chart import get_daily_chart, get_minute_chart


def main():
    get_client().get_access_token()
    print("Authentication: OK (token hidden)")
    accounts = get_accounts()
    print("Accounts:", len(accounts), "(numbers hidden)")
    for account in accounts:
        result = get_balance(account['id'])
        print("Balance: OK; holdings:", len(result['holdings']), "(amounts hidden)")
    price = get_current_price('005930')
    assert price['price'] > 0
    print("Current price: OK")
    for period in ('D', 'W', 'M', '1m', '5m'):
        candles = (get_minute_chart('005930', interval=int(period[:-1]))
                   if period.endswith('m') else get_daily_chart('005930', period=period))
        assert candles, f"No candles: {period}"
        assert all(a['time'] < b['time'] for a, b in zip(candles, candles[1:]))
        print(period, "candles:", len(candles))


if __name__ == '__main__':
    main()
