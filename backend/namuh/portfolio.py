import os
import math

from .client import NamuhError, get_client, number


def optional_number(value):
    if value is None or isinstance(value, bool) or str(value).strip() == '': return None
    try:
        parsed = float(str(value).strip().replace(',', ''))
        if not math.isfinite(parsed): return None
        return int(parsed) if parsed.is_integer() else parsed
    except (ValueError, TypeError, OverflowError): return None


def get_accounts(*, client=None):
    client = client or get_client()
    accounts = []
    for page in client.pages('/n2/acctinfo', {}):
        for row in page.get('Output_0', []):
            if row.get('acct_type') == '01' and row.get('acct_no'):
                account = row['acct_no']
                accounts.append({'id': account, 'label': '*' * max(0, len(account) - 4) + account[-4:]})
    return accounts


def get_balance(account_no='', *, client=None):
    client = client or get_client()
    if not account_no:
        account_no = os.getenv('NAMUH_ACCOUNT_NO', '').strip().replace('-', '')
    if not account_no:
        accounts = get_accounts(client=client)
        if len(accounts) != 1:
            raise NamuhError('조회할 나무증권 계좌를 선택해주세요.' if accounts else 'API에 등록된 실계좌가 없습니다.')
        account_no = accounts[0]['id']
    inputs = {'act_no': account_no, 'bnc_bse_cd': '1', 'ltg_aot_dit_cd': '9',
              'aet_bse': '2', 'qut_dit_cd': 'KRX', 'aly_qut_cd': '1'}
    holdings = []
    summary = {}
    for page in client.pages('/krstock/inquiry/v1/balance', {'Input_0': inputs}):
        summary = page.get('Output_0', {})
        for item in page.get('Output_1', []):
            quantity = number(item.get('rsdl_qty'))
            if quantity <= 0:
                continue
            holdings.append({
                'id': f"{item['iem_cd']}-{len(holdings)}",
                'code': item['iem_cd'], 'name': item['iem_nm'],
                'holding_type': item.get('tp_cd_nm', ''),
                'quantity': quantity, 'avg_price': number(item.get('phs_pr')),
                'current_price': number(item.get('now_pr')),
                'eval_amount': optional_number(item.get('eal_amt')),
                'profit_loss': number(item.get('eal_pls_amt')),
                'profit_rate': number(item.get('pft_rt'))})
    required = ('tot_eal_amt', 'tot_byn_amt', 'tot_eal_pls', 'pft_rt', 'dca')
    if any(key not in summary for key in required):
        raise NamuhError('나무증권 잔고 합계가 반환되지 않았습니다. 다시 조회해주세요.')
    return {'holdings': holdings, 'summary': {
        'total_eval': number(summary['tot_eal_amt']),
        'total_purchase': number(summary['tot_byn_amt']),
        'total_profit_loss': number(summary['tot_eal_pls']),
        'total_profit_rate': number(summary['pft_rt']),
        'cash': number(summary['dca']),
        'cash_orderable_100': optional_number(summary.get('orr_pbl_amt4')),
        'total_assets': optional_number(summary.get('tot_aet_amt')),
        'net_assets': optional_number(summary.get('nas_amt'))}}
