"""Bounded Tavily retrieval of public company information; no account/model inputs."""
import copy
import hashlib
import ipaddress
import json
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl

import httpx

from .research_filter import clean_excerpt, duplicate_source, empty_diagnostics, source_id, validate_source

REPORT_DOMAINS = ('dart.fss.or.kr', 'kind.krx.co.kr')


class SearchError(ValueError): pass


def now(): return datetime.now(timezone.utc).isoformat()


class SearchCache:
    def __init__(self, ttl=900):
        self.ttl, self.entries, self.lock = ttl, OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if not entry: return None
            if time.monotonic()-entry[0] >= self.ttl:
                del self.entries[key]
                return None
            self.entries.move_to_end(key)
            value = copy.deepcopy(entry[1])
            value.update(cached=True, usage_credits=0)
            return value

    def put(self, key, value):
        with self.lock:
            self.entries[key] = (time.monotonic(), copy.deepcopy(value))
            self.entries.move_to_end(key)
            while len(self.entries) > 256: self.entries.popitem(last=False)


_cache = SearchCache()


def safe_url(value):
    if not isinstance(value, str) or len(value)>2048 or any(ord(c)<33 for c in value): return None
    try:
        parts=urlsplit(value)
        host=parts.hostname or ''
        if parts.scheme not in ('http','https') or parts.username or parts.password or parts.port not in (None,80,443): return None
        if not re.fullmatch(r'[A-Za-z0-9.-]+',host) or '.' not in host or host.endswith(('.local','.localhost','.internal')): return None
        try:
            if not ipaddress.ip_address(host).is_global: return None
        except ValueError: pass
        if any(name.lower() in ('api_key','apikey','access_token','token','secret','password') for name,_ in parse_qsl(parts.query)): return None
        return urlunsplit(parts._replace(fragment=''))
    except ValueError: return None


def published_at(value):
    if not isinstance(value,str) or len(value)>100: return None
    try: stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:
        try: stamp=parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError): return None
    return stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()


def _query(http, key, code, name, aliases, kind, alternate, cache, cancelled, deadline, fatal, today):
    if cancelled() or time.monotonic()>deadline or fatal.is_set(): raise SearchError('웹 검색이 중단되었습니다. 설정과 실행 상태를 확인하세요.')
    if kind=='news':
        query=(f'"{name}" {code} 공시 수주 실적 기업 뉴스' if alternate else f'"{name}" {code} 최근 주요 뉴스 실적')
    else:
        query=(f'"{name}" {code} site:dart.fss.or.kr 사업보고서 재무제표' if alternate else f'"{name}" {code} 사업보고서 분기보고서 재무제표 실적')
    body=dict(query=query,topic='news' if kind=='news' else 'general',search_depth='basic',max_results=3,
              time_range='month' if kind=='news' else 'year',include_answer=False,include_raw_content=False,
              include_images=False,include_usage=True,include_published_date=True,auto_parameters=False,
              language='ko',filter_by_language=True)
    if kind=='reports': body['include_domains']=list(REPORT_DOMAINS)
    if kind=='reports': body['country']='south korea'
    cache_key=hashlib.sha256((key+json.dumps(body,sort_keys=True)).encode()).hexdigest()
    cached=cache.get(cache_key) if cache else None
    if cached: return cached
    result=dict(code=code,kind=kind,query=query,alternate=alternate,fetched_at=now(),cached=False,status='error',sources=[],usage_credits=None,error='',rejected={})
    try:
        with http.stream('POST','https://api.tavily.com/search',headers={'Authorization':'Bearer '+key},
                         json=body,timeout=20,follow_redirects=False) as response:
            if response.status_code in (401,403):
                fatal.set()
                raise SearchError('Tavily 인증에 실패했습니다. 웹 검색 설정의 API 키를 확인하세요.')
            if response.status_code in (429,432,433): raise SearchError('Tavily 요청 또는 사용 한도에 도달했습니다.')
            if response.status_code!=200: raise SearchError('Tavily 검색 요청에 실패했습니다.')
            raw=bytearray()
            for chunk in response.iter_bytes():
                if cancelled() or time.monotonic()>deadline: raise SearchError('웹 검색이 중단되었거나 제한 시간을 초과했습니다.')
                if len(raw)+len(chunk)>1024*1024: raise SearchError('Tavily 응답 크기가 허용 범위를 초과했습니다.')
                raw.extend(chunk)
        payload=json.loads(raw)
        rows=payload.get('results')
        if not isinstance(rows,list): raise SearchError('Tavily 검색 응답 형식을 확인할 수 없습니다.')
        rejected={}
        for row in rows[:20]:
            if not isinstance(row,dict): continue
            url=safe_url(row.get('url'))
            title,content=row.get('title'),row.get('content')
            reason=None
            if not url or not isinstance(title,str) or not isinstance(content,str) or not content.strip(): reason='malformed'
            elif key in url or key in title or key in content: reason='secret_echo'
            elif kind=='reports' and not any(urlsplit(url).hostname==d or urlsplit(url).hostname.endswith('.'+d) for d in REPORT_DOMAINS): reason='unapproved_domain'
            else:
                title=title[:180]
                content=clean_excerpt(content[:900])
                normalized_date=published_at(row.get('published_date'))
                reason=validate_source(name=name,code=code,aliases=aliases,kind=kind,title=title,content=content,
                                       published=normalized_date,today=today)
            if reason:
                rejected[reason]=rejected.get(reason,0)+1
                continue
            source=dict(id=source_id(code,kind,url),code=code,kind=kind,url=url,title=title,
                content=content,published_at=published_at(row.get('published_date')),fetched_at=result['fetched_at'])
            if duplicate_source(source,result['sources']):
                rejected['duplicate']=rejected.get('duplicate',0)+1
                continue
            result['sources'].append(source)
            if len(result['sources'])>=3: break
        credits=(payload.get('usage') or {}).get('credits')
        result.update(status='ready' if result['sources'] else 'empty',
                      usage_credits=credits if type(credits) is int and credits>=0 else None,rejected=rejected)
        if cache: cache.put(cache_key,result)
    except SearchError as exc: result['error']=str(exc)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, UnicodeError):
        result['error']='Tavily 검색 응답을 가져오지 못했습니다.'
    return result


def research(stocks, key, *, http=None, cache=None, cancelled=lambda:False, today=None):
    if not isinstance(key,str) or not re.fullmatch(r'tvly-[A-Za-z0-9_-]{15,507}',key):
        raise SearchError('설정에서 Tavily API 키를 저장하세요.')
    if not isinstance(stocks,list) or not 1<=len(stocks)<=10: raise SearchError('웹 검색할 종목을 확인하세요.')
    jobs=[]
    for row in stocks:
        code,name=row.get('code'),row.get('name')
        if not isinstance(code,str) or not re.fullmatch(r'[0-9A-Z]{6}',code) or not isinstance(name,str): raise SearchError('웹 검색할 종목을 확인하세요.')
        name=re.sub(r'[^가-힣A-Za-z0-9 .&()-]','',name)[:80].strip()
        if not name: raise SearchError('웹 검색할 종목명을 확인하세요.')
        aliases=row.get('aliases',())
        if not isinstance(aliases,(list,tuple)) or any(not isinstance(a,str) for a in aliases): aliases=()
        kinds=('news',) if row.get('has_dart_financials') is True else ('news','reports')
        jobs.extend((code,name,tuple(aliases[:5]),kind) for kind in kinds)
    if http is None:
        with httpx.Client(timeout=20,trust_env=False,follow_redirects=False) as client:
            return research(stocks,key,http=client,cache=cache or _cache,cancelled=cancelled,today=today)
    today=today or datetime.now(timezone.utc).date()
    deadline,fatal=time.monotonic()+60,threading.Event()
    with ThreadPoolExecutor(max_workers=3) as pool:
        searches=list(pool.map(lambda job:_query(http,key,*job,False,cache,cancelled,deadline,fatal,today),jobs))
        retry_jobs=[job for job,search in zip(jobs,searches) if search['status']=='empty']
        if retry_jobs and not fatal.is_set() and not cancelled() and time.monotonic()<=deadline:
            searches.extend(pool.map(lambda job:_query(http,key,*job,True,cache,cancelled,deadline,fatal,today),retry_jobs))
    errors=[s for s in searches if s['status']=='error']
    if fatal.is_set() or len(errors)==len(searches):
        raise SearchError(errors[0]['error'] if errors else 'Tavily 검색을 완료하지 못했습니다.')
    if cancelled(): raise SearchError('웹 검색이 중단되었습니다.')
    sources=[]
    seen_by_target={}
    rejected=empty_diagnostics()['rejected']
    for search in searches:
        rejected.update(search.get('rejected',{}))
        target=(search['code'],search['kind'])
        seen=seen_by_target.setdefault(target,[])
        for source in search['sources']:
            if duplicate_source(source,seen):
                rejected['duplicate']+=1
                continue
            seen.append(source)
            sources.append(source)
    credits=[s['usage_credits'] for s in searches]
    ready_targets={(s['code'],s['kind']) for s in searches if s['sources']}
    all_targets={(code,kind) for code,_,_,kind in jobs}
    missing=[{'code':code,'kind':kind,'reason':'error' if all(s['status']=='error' for s in searches if (s['code'],s['kind'])==(code,kind)) else 'no_relevant_sources'}
             for code,kind in sorted(all_targets-ready_targets)]
    status='ready' if ready_targets==all_targets else 'partial' if ready_targets or errors else 'empty'
    return dict(status=status,
                fetched_at=now(),searches=searches,sources=sources,
                diagnostics={'rejected':dict(rejected),'missing':missing},
                usage_credits=sum(credits) if all(c is not None for c in credits) else None,
                requested_queries=sum(not s['cached'] for s in searches),cached_queries=sum(s['cached'] for s in searches))
