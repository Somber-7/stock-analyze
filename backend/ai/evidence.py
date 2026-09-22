"""Calculated report evidence; no forecasts, trade rules or network requests."""
import math
import re


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


def financial_evidence(financials):
    result=[]
    for account in (financials or {}).get('accounts',[]):
        pairs=[(account.get('period_basis'),'amount','comparison_amount')]
        if account.get('period_basis')=='3개월': pairs.append(('누적','ytd_amount','comparison_ytd_amount'))
        for period,current_key,previous_key in pairs:
            current,previous=account.get(current_key),account.get(previous_key)
            comparable=(number(current) and number(previous) and bool(account.get('currency'))
                        and bool(account.get('period_name')) and bool(account.get('comparison_name')))
            delta=current-previous if comparable else None
            result.append(dict(name=account['name'],period_basis=period,current=current,previous=previous,
                status='comparable' if comparable else 'comparison_missing',change=delta,
                change_pct=round(delta/previous*100,4) if comparable and previous>0 and current>=0 else None,
                direction=('increase' if delta>0 else 'decrease' if delta<0 else 'unchanged') if comparable else None))
    return result


def enrich_context(context):
    portfolio=context.get('portfolio',{})
    total=portfolio.get('total_assets')
    def weight(value):
        return round(value/total*100,4) if number(value) and number(total) and total>0 else None
    stocks=context.get('stocks',[])
    selected={s['code'] for s in stocks}
    unselected=[p.get('eval_amount') for p in portfolio.get('holdings',[]) if p['code'] not in selected]
    selected_values=[s.get('holding_eval_amount') for s in stocks]
    portfolio['allocation']=dict(cash_weight_pct=weight(portfolio.get('cash_balance')),
        selected_stock_weight_pct=weight(sum(selected_values)) if all(number(v) for v in selected_values) else None,
        unselected_stock_weight_pct=weight(sum(unselected)) if all(number(v) for v in unselected) else None)
    for stock in stocks:
        points=[]
        prices=stock.get('price_basis') or {}
        close=prices.get('daily_close')
        if (number(close) and close>0 and prices.get('daily_date')
                and not (stock.get('data_quality') or {}).get('requires_defer')):
            for window in (20,60):
                level=(stock.get('metrics') or {}).get(f'sma_{window}')
                if not number(level) or level<=0: continue
                direction='below' if close>=level else 'above'
                condition='하회' if direction=='below' else '상회'
                points.append(dict(window=window,level=level,direction=direction,data_date=prices['daily_date'],
                    text=f'종가의 {window}봉 이동평균 {condition} 전환 시 재검토 · 이번 기준 {level:,.2f}원'))
        stock['review_points']=points
    for stock in context.get('dart_research',{}).get('stocks',[]):
        financials=stock.get('financials')
        if financials: financials['comparisons']=financial_evidence(financials)
    return context


_ACCOUNTS=re.compile(r'영업(?:활동\s*)?\s*현금흐름|매출액?|영업(?:이익|손익|손실)|(?:당기)?순(?:이익|손익|손실)')
_UP=re.compile(r'개선|증가|늘었|흑자\s*전환|흑자로\s*전환')
_DOWN=re.compile(r'악화|감소|줄었|적자\s*전환|적자로\s*전환')
_QUALIFIED=re.compile(r'미확인|(?:확인|단정)(?:할\s*수\s*없|되지\s*않|하지\s*못)|(?:개선|악화|증가|감소)(?:되지|하지)\s*않|(?:근거|자료|증거)(?:가|는|도)?\s*(?:부족|없)|확인(?:이|은|도)?\s*필요|확인해야|없이|불명|비교(?:할\s*수\s*없|\s*불가)|여부|기대|전망|예상|가정|한다면|되면|될\s*때|되는지|됐는지|되었는지|지속될지')
# Reject only a directly attributable account comparison. An unknown intervening
# subject/phrase is ambiguous, not evidence of a financial contradiction.
_DIRECT_PREFIX=re.compile(r'(?:\s|은|는|이|가|의|도|누적|연결|별도|상반기|반기|분기|전년|전기|동기|비교기간|비교|기간|대비|보다|크게|소폭|대폭|다소|약|금액|규모|유출|유입|손실|적자|[0-9.,+%()\-]|억|조|만|천|원)*\Z')
_ASSERTED=re.compile(r'^\s*(?:(?:했|됐|되었|하였)(?:다|습니다|음)|(?:이|가)?\s*확인(?:됐|되었|된다|됨)|한\s*(?:상태|것으로\s*확인)|된\s*(?:상태|것으로\s*확인))')


class FinancialComparisonError(ValueError):
    def __init__(self, account, reason):
        super().__init__(reason)
        self.issue=dict(account=account,reason=reason)


def _account_name(term):
    if '현금흐름' in term: return '영업활동 현금흐름'
    if '매출' in term: return '매출액'
    return '영업이익' if term.startswith('영업') else '당기순이익'


def _check_text(text, facts):
    # A bounded guard for explicit income/cash-flow comparisons. This is not a
    # general language fact checker; keep qualified/future conditions separate.
    for clause in re.split(r'[。;\n]|(?<=[다요])[.]|반면|그러나|하지만|이며|이고|했고|됐고|었고|였고',text or ''):
        matches=list(_ACCOUNTS.finditer(clause))
        for index,match in enumerate(matches):
            end=matches[index+1].start() if index+1<len(matches) else len(clause)
            predicate=clause[match.end():end]
            # Enumerated subjects share the final predicate (매출·영업이익 및 현금흐름은 증가).
            if index+1<len(matches) and re.fullmatch(r'[\s·,/및과와누적연결반기]*',predicate):
                predicate=clause[matches[-1].end():]
            # Do not attach another subject's predicate to the financial account.
            predicate=re.split(r'(?:주가|가격|차입금|부채|자산|거래량|수급)(?:은|는|이|가)',predicate,maxsplit=1)[0]
            if _QUALIFIED.search(predicate): continue
            up,down=bool(_UP.search(predicate)),bool(_DOWN.search(predicate))
            if not up and not down: continue
            if up and down: continue
            action=(_UP if up else _DOWN).search(predicate)
            prefix=predicate[:action.start()]
            if not _DIRECT_PREFIX.fullmatch(prefix): continue
            if not _ASSERTED.search(predicate[action.end():]): continue
            name=_account_name(match.group())
            relevant=[f for f in facts if f['name']==name]
            # An explicit cumulative claim must have a cumulative comparison.
            start=matches[index-1].end() if index else 0
            period_text=clause[start:match.end()]
            if '3개월' in period_text: relevant=[f for f in relevant if f['period_basis']=='3개월']
            elif '누적' in period_text or '반기' in period_text:
                relevant=[f for f in relevant if f['period_basis']=='누적']
            valid=[f for f in relevant if f['status']=='comparable']
            if not valid: raise FinancialComparisonError(name,'재무 비교값이 없는 항목을 개선·악화로 단정했습니다.')
            profit_transition=re.search(r'흑자(?:로)?\s*전환',predicate)
            loss_transition=re.search(r'적자(?:로)?\s*전환',predicate)
            if profit_transition and not any(f['previous']<=0<f['current'] for f in valid):
                raise FinancialComparisonError(name,'재무 비교값에 흑자 전환이 없습니다.')
            if loss_transition and not any(f['previous']>=0>f['current'] for f in valid):
                raise FinancialComparisonError(name,'재무 비교값에 적자 전환이 없습니다.')
            # 손실 증가는 손익 금액의 감소. 손실 개선은 금액의 증가.
            if ('손실' in match.group() or re.search(r'유출|손실|적자',prefix)) and re.search(r'증가|늘었|감소|줄었',predicate): up,down=down,up
            expected='increase' if up and not down else 'decrease' if down and not up else None
            if expected and not any(f['direction']==expected for f in valid):
                raise FinancialComparisonError(name,'재무 비교값과 개선·악화 방향이 일치하지 않습니다.')


def validate_financial_claims(analysis, context):
    by_code={s['code']:financial_evidence(s.get('financials')) for s in context.get('dart_research',{}).get('stocks',[])}
    def check(text,code,field):
        try: _check_text(text,by_code.get(code,[]))
        except FinancialComparisonError as exc:
            exc.issue.update(code=code,field=field,text=text[:600])
            raise
    for decision in analysis.get('decisions',[]):
        for key in ('headline','rationale'):
            check(decision.get(key,''),decision['code'],key)
    for field,text in [('summary',analysis.get('summary','')),*[(f'risks[{i}]',value) for i,value in enumerate(analysis.get('risks',[]))]]:
        # Validate named-company sentences; ambiguous cross-company prose remains
        # governed by the structured input and generation instructions.
        for clause in re.split(r'(?<=[다요])[.]|\n',text):
            targets=[s for s in context.get('stocks',[]) if s.get('name') and s['name'] in clause]
            if len(targets)==1: check(clause,targets[0]['code'],field)
