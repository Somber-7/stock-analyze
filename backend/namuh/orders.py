"""NH PLUG cash/normal-limit KRX order contract. Never retries a mutation."""
import math
from datetime import datetime, timezone, timedelta
from .client import NamuhError, get_client
from .portfolio import get_accounts, get_balance
from .market import get_current_price


def korea_today():
    return datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d')


def integer(value):
    try:
        number = float(value)
        if not math.isfinite(number) or number < 0 or int(number) != number:
            raise ValueError()
        return int(number)
    except (ValueError, TypeError, OverflowError):
        raise NamuhError('주문 관련 수치가 누락되거나 올바르지 않습니다.') from None


class OrderGateway:
    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        return self._client or get_client()

    def accounts(self):
        return get_accounts(client=self.client)

    def balance(self, account):
        return get_balance(account, client=self.client)

    def quote(self, code):
        return get_current_price(code, client=self.client)

    def capacity(self, account, code, side, price):
        payload = {'act_no': account, 'iem_cd': code, 'lon_dt': '', 'cfd_lon_cd': '00'}
        if side == 'buy':
            if isinstance(price,bool) or integer(price) <= 0:
                raise NamuhError('매수가능수량 조회 가격은 양의 정수 원 단위여야 합니다.', stage='input')
            payload.update(ost_dit_cd='1', sby_dit_cd='2', nmn_pr_tp_cd='01', orr_pr=integer(price))
            data, _ = self.client.post('/krstock/inquiry/v1/buyableQuantity', {'Input_0': payload},
                                       success_codes={'00000', '00221', '00166'})
            out = data.get('Output_0') or {}
            try:
                return {'quantity': integer(out.get('csh_orr_pbl_qty')), 'amount': integer(out.get('csh_orr_pbl_amt'))}
            except (NamuhError, AttributeError):
                raise NamuhError('현금 매수가능수량·금액 응답 항목을 확인할 수 없습니다.', stage='fields') from None
        data, _ = self.client.post('/krstock/inquiry/v1/sellableQuantity', {'Input_0': payload})
        return {'quantity': integer((data.get('Output_0') or {}).get('sll_pbl_qty')), 'amount': None}

    def history(self, account, day):
        datetime.strptime(day, '%Y%m%d')
        rows = []
        for page in self.client.pages('/krstock/inquiry/v1/dailyOrderExecution', {'Input_0': {
                'orr_dt': day, 'act_no': account, 'orr_mkt_cd': '00', 'ost_cns_dit': '0'}},
                success_codes={'00000', '00136', '00166', '11512'}):
            output = page.get('Output_0')
            if not isinstance(output, list):
                raise NamuhError('주문 내역 응답 형식이 올바르지 않습니다.')
            if page.get('rsp_cd') == '11512' and output:
                raise NamuhError('주문 내역 응답 코드와 데이터가 일치하지 않습니다.')
            for r in output:
                side_name = str(r.get('sby_dit_cd_nm', '')).replace(' ', '')
                rows.append(dict(broker_id=str(integer(r.get('itg_orr_no'))),
                    original_id=str(integer(r.get('org_itg_orr_no', 0))), day=day,
                    code=r.get('iem_cd', ''), name=r.get('iem_nm', ''), side_name=side_name,
                    side='buy' if side_name == '현금매수' else 'sell' if side_name == '현금매도' else 'other',
                    quantity=integer(r.get('orr_qty')), price=integer(r.get('orr_pr')),
                    filled=integer(r.get('tot_cns_qty')), remaining=integer(r.get('ny_cns_qty')),
                    cancelled=integer(r.get('can_qty')), average_price=float(r.get('cns_avg_uit_pr') or 0),
                    reason=str(r.get('orr_rjt_rsn_cd_nm', '')), market=r.get('rmt_mkt_cd', ''),
                    split=r.get('sor_mkt_sli_yn', 'N'), order_type=r.get('nmn_pr_tp_cd_nm', '')))
        return rows

    def send(self, kind, account, *, code, quantity, price=0, original=None, before_send=None):
        common = {'act_no': account, 'iem_cd': code}
        if kind in ('buy', 'sell'):
            endpoint = 'cashBuy' if kind == 'buy' else 'cashSell'
            success = '00048' if kind == 'buy' else '00047'
            common.update(orr_qty=quantity, orr_pr=price, orr_amt=quantity*price,
                          nmn_pr_tp_cd='01', orr_cnd_dit_cd='00', ssl_nmn_pr_dit_cd='00',
                          rmt_mkt_cd='KRX', sor_mkt_sli_yn='N')
        elif kind in ('modify', 'cancel'):
            endpoint = kind
            success = '00164' if kind == 'modify' else '00192'
            common.update(org_mkt_orr_no=int(original), all_pat_dit_cd='2', cor_qty=quantity)
            if kind == 'modify':
                common.update(cor_pr=price, rmt_mkt_cd='KRX', sor_mkt_sli_yn='N')
        else:
            raise ValueError('Unsupported cash order operation')
        data, _ = self.client.post('/krstock/order/v1/' + endpoint, {'Input_0': common}, success_codes={success}, before_send=before_send)
        output = data.get('Output_0')
        if not isinstance(output, dict):
            raise NamuhError('주문 응답 형식이 올바르지 않습니다. 접수 여부를 확인하세요.')
        broker_id = integer(output.get('mkt_orr_no'))
        if not broker_id:
            raise NamuhError('주문 응답에 주문번호가 없습니다. 접수 여부를 확인하세요.')
        return {'broker_id': str(broker_id), 'response_code': data['rsp_cd']}
