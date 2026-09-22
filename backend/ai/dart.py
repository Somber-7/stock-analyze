"""Official disclosure metadata and explicitly labelled financial statement amounts."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import httpx

from .dart_client import DartClient, DartError

ACCOUNTS = (
    ('매출액', ('IS','CIS'), ('ifrs-full_Revenue',), ('매출액','수익(매출액)')),
    ('영업이익', ('IS','CIS'), ('dart_OperatingIncomeLoss',), ('영업이익','영업이익(손실)')),
    ('당기순이익', ('IS','CIS'), ('ifrs-full_ProfitLoss',), ('당기순이익','당기순이익(손실)','반기순이익','반기순이익(손실)','분기순이익','분기순이익(손실)')),
    ('자산총계', ('BS',), ('ifrs-full_Assets',), ('자산총계',)),
    ('부채총계', ('BS',), ('ifrs-full_Liabilities',), ('부채총계',)),
    ('자본총계', ('BS',), ('ifrs-full_Equity',), ('자본총계',)),
    ('영업활동 현금흐름', ('CF',), ('ifrs-full_CashFlowsFromUsedInOperatingActivities',), ('영업활동현금흐름','영업활동으로인한현금흐름')),
)


def amount(value):
    if not isinstance(value,str): return None
    value=value.replace(',','').strip()
    if re.fullmatch(r'\(\d+\)',value): value='-'+value[1:-1]
    return int(value) if re.fullmatch(r'-?\d{1,24}',value) else None


def report_url(receipt):
    return 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt


def financial_summary(rows, corp, year, report, fs_div):
    if not isinstance(rows,list) or not rows or any(not isinstance(r,dict) for r in rows): raise DartError('DART 재무자료 형식을 확인하지 못했습니다.')
    if any(r.get('corp_code') != corp or r.get('bsns_year') != year or r.get('reprt_code') != report for r in rows):
        raise DartError('DART 재무자료의 기업·보고기간이 일치하지 않습니다.')
    receipts={r.get('rcept_no') for r in rows}
    if len(receipts)!=1 or not re.fullmatch(r'\d{14}',next(iter(receipts)) or ''):
        raise DartError('DART 재무자료의 접수번호를 확인하지 못했습니다.')
    accounts=[]
    for label, sections, ids, names in ACCOUNTS:
        candidates=[r for r in rows if r.get('sj_div') in sections and r.get('account_id') in ids]
        if not candidates:
            candidates=[r for r in rows if r.get('sj_div') in sections and str(r.get('account_nm','')).replace(' ','') in names]
        if len(candidates)!=1: continue
        r=candidates[0]
        quarterly=report!='11011' and r['sj_div'] in ('IS','CIS')
        interim_comparison=report!='11011' and r['sj_div'] in ('IS','CIS','CF')
        accounts.append(dict(name=label, account_id=r.get('account_id'), currency=r.get('currency') or None,
            amount=amount(r.get('thstrm_amount')), ytd_amount=amount(r.get('thstrm_add_amount')) if quarterly else None,
            comparison_amount=amount(r.get('frmtrm_q_amount') if interim_comparison else r.get('frmtrm_amount')),
            comparison_ytd_amount=amount(r.get('frmtrm_add_amount')) if quarterly else None,
            period_basis='3개월' if quarterly else '시점 잔액' if r['sj_div']=='BS' else '누적',
            period_name=str(r.get('thstrm_nm',''))[:100],
            comparison_name=str(r.get('frmtrm_q_nm' if interim_comparison else 'frmtrm_nm',''))[:100]))
    receipt=next(iter(receipts))
    return dict(year=year,report_code=report,fs_div=fs_div,accounts=accounts,
                receipt_no=receipt,url=report_url(receipt),missing_accounts=[a[0] for a in ACCOUNTS if a[0] not in {r['name'] for r in accounts}])


def disclosures(payload, corp, today):
    result=[]
    rows=payload.get('list',[])
    if not isinstance(rows,list): raise DartError('DART 공시 목록 형식을 확인하지 못했습니다.')
    for row in rows:
        if not isinstance(row,dict): continue
        receipt, stamp = row.get('rcept_no',''), row.get('rcept_dt','')
        if row.get('corp_code')!=corp or not re.fullmatch(r'\d{14}',receipt): continue
        try: day=datetime.strptime(stamp,'%Y%m%d').date()
        except (ValueError,TypeError): continue
        if day>today: continue
        result.append(dict(title=str(row.get('report_nm',''))[:200],received_at=day.isoformat(),
                           receipt_no=receipt,url=report_url(receipt)))
    return result


def _stock(stock, client, codes, today):
    code=stock['code']
    value=dict(code=code,name=stock['name'],status='missing',financials=None,disclosures=[],warnings=[],fetched_at=None)
    corp=codes.get(code)
    if not corp:
        value['warnings'].append('DART 고유번호와 종목코드를 연결하지 못했습니다.')
        return value
    try:
        company=client.json('company.json',corp_code=corp)
        if company.get('corp_code',corp)!=corp or company.get('stock_code')!=code:
            raise DartError('DART 기업의 종목코드가 일치하지 않습니다.')
        value['aliases']=list(dict.fromkeys(company[k].strip() for k in ('corp_name','corp_name_eng','stock_name')
            if isinstance(company.get(k),str) and 2 <= len(company[k].strip()) <= 100))
        dates=dict(corp_code=corp,end_de=today.strftime('%Y%m%d'),last_reprt_at='Y',sort='date',sort_mth='desc',page_count='20')
        recent=client.json('list.json',**dates,bgn_de=(today-timedelta(days=90)).strftime('%Y%m%d'))
        value['disclosures']=disclosures(recent,corp,today)[:20]
        value['fetched_at']=datetime.fromtimestamp(recent['_fetched_at'],timezone.utc).isoformat()
        if company.get('acc_mt')!='12':
            value['warnings'].append('12월 결산법인이 아니거나 결산월 미확인으로 재무기간 자동 연결을 생략했습니다.')
            value['status']='partial'
            return value
        regular=client.json('list.json',**dates,bgn_de=(today-timedelta(days=730)).strftime('%Y%m%d'),pblntf_ty='A')
        candidates=[]
        for item in disclosures(regular,corp,today):
            match=re.search(r'(사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)',item['title'])
            if not match: continue
            kind,year,month=match.groups()
            report={'03':'11013','06':'11012','09':'11014','12':'11011'}.get(month)
            if not report or (kind=='사업')!=(month=='12') or (kind=='반기')!=(month=='06'): continue
            if date(int(year),int(month),1)>today: continue
            candidates.append((year,month,item['received_at'],report))
        if not candidates:
            value['warnings'].append('조회 범위에서 재무자료를 연결할 정기보고서를 확인하지 못했습니다.')
        else:
            year,month,_,report=max(candidates)
            for division in ('CFS','OFS'):
                payload=client.json('fnlttSinglAcntAll.json',corp_code=corp,bsns_year=year,reprt_code=report,fs_div=division)
                if payload['status']=='013': continue
                financials=financial_summary(payload.get('list'),corp,year,report,division)
                receipt_date=datetime.strptime(financials['receipt_no'][:8],'%Y%m%d').date()
                if receipt_date>today: raise DartError('재무자료 접수일이 조회일보다 뒤입니다.')
                financials.update(period_end=f'{year}-{month}',received_at=receipt_date.isoformat(),
                                  fetched_at=datetime.fromtimestamp(payload['_fetched_at'],timezone.utc).isoformat())
                value['financials']=financials
                if financials['missing_accounts']:
                    value['warnings'].append('일부 주요계정을 단일 항목으로 확인하지 못했습니다. 미확인 항목을 0으로 해석하지 마세요.')
                break
            if not value['financials']: value['warnings'].append('해당 보고기간의 연결·별도 재무자료가 없습니다.')
        value['status']='ready' if value['financials'] and not value['financials']['missing_accounts'] else 'partial'
    except (DartError,ValueError,TypeError,KeyError) as exc:
        value['status']='partial' if value['disclosures'] else 'error'
        value['warnings'].append(str(exc) if isinstance(exc,DartError) else 'DART 자료 형식을 확인하지 못했습니다.')
    return value


def research(stocks,key,*,client=None,codes=None,today=None,cancelled=lambda:False):
    today=today or datetime.now(timezone(timedelta(hours=9))).date()
    if client is None:
        with httpx.Client(trust_env=False,follow_redirects=False) as http:
            return research(stocks,key,client=DartClient(key,http=http,cached=True,cancelled=cancelled),today=today,cancelled=cancelled)
    if not isinstance(stocks,list) or not 1<=len(stocks)<=10 or any(not re.fullmatch(r'[0-9A-Z]{6}',s.get('code','')) for s in stocks):
        raise DartError('DART 조회 종목을 확인하세요.')
    if codes is None: codes=client.codes()
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows=list(pool.map(lambda stock:_stock(stock,client,codes,today),stocks))
    if cancelled(): raise DartError('DART 조회가 중단되었습니다.')
    sources={}
    for row in rows:
        for item in row['disclosures']:
            source_id=row['code']+'-dart-'+item['receipt_no']
            sources[source_id]=dict(id=source_id,code=row['code'],title=item['title'],url=item['url'],received_at=item['received_at'])
        f=row['financials']
        if f:
            source_id=row['code']+'-dart-'+f['receipt_no']
            sources[source_id]=dict(id=source_id,code=row['code'],title=f"{f['period_end']} 재무자료 ({f['fs_div']})",url=f['url'],received_at=f['received_at'])
    return dict(status='ready' if all(r['status']=='ready' for r in rows) else 'partial',stocks=rows,
                sources=list(sources.values()),
                fetched_at=datetime.now(timezone.utc).isoformat(),
                scope='최근 90일 공시 최대 20건과 최근 2년 정기공시 최대 20건에서 확인한 최신 보고기간. 공시 본문·주석 전체는 포함하지 않습니다.')
