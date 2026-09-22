"""Conservative, deterministic validation for public company search evidence."""
import hashlib
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REPORT_WORDS = ('사업보고서', '반기보고서', '분기보고서', '감사보고서', '재무제표', '매출액', '영업이익')
BUSINESS_ANCHORS = ('주가', '주식', '종목', '코스닥', '코스피', '기업', '회사', '매출', '실적', '수주', '공시', '계약', '사업')
SHELL_PHRASES = ('본문선택', '첨부파일 선택', 'pdf 저장', '다운로드', '최종문서가 아니므로', '투자판단에 유의',
                 '문서 목차', '회사의 개요', '사업의 내용', '재무에 관한 사항', '열기')


# Search excerpts are untrusted. Articles do not address the model or name the
# output schema, so these phrases drop the source instead of relying on the prompt.
INSTRUCTION_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r'\b(?:ignore|disregard|forget|override)\b.{0,40}\b(?:instructions?|prompts?|rules?|directions?)\b',
    r'\b(?:system\s+prompt|developer\s+message)\b',
    r'\byou\s+are\s+(?:now\s+)?(?:an?\s+)?(?:ai|assistant|language\s+model|chatgpt|claude|gemini)\b',
    r'</?\s*(?:system|assistant|user|instructions?)\s*>',
    r'(?:^|\n)\s*(?:system|assistant)\s*:',
    r'(?:이전|위의?|앞의|기존|모든)\s*(?:지시|지침|명령|규칙|프롬프트)[^\n]{0,20}(?:무시|잊|따르지)',
    r'시스템\s*프롬프트',
    r'(?:AI|에이아이|인공지능|모델|어시스턴트)\s*(?:는|은|에게|야|여)[^\n]{0,30}(?:지시|명령|출력|응답)\s*(?:하라|하세요|해라|할\s*것)',
    r'(?<![A-Za-z0-9_])(?:target_quantity|source_ids|decision_basis|review_conditions|market_view)(?![A-Za-z0-9_])',
))


def instruction_like(text):
    text=unicodedata.normalize('NFKC', text if isinstance(text,str) else '')
    return any(pattern.search(text) for pattern in INSTRUCTION_PATTERNS)


def normalized(value):
    text=unicodedata.normalize('NFKC', value if isinstance(value,str) else '').casefold()
    return ''.join(ch for ch in text if ch.isalnum())


def searchable(value):
    text=unicodedata.normalize('NFKC',value if isinstance(value,str) else '').casefold()
    return re.sub(r'\s+',' ',re.sub(r'[^0-9a-z가-힣]+',' ',text)).strip()


def _name_pattern(value, *, start=False):
    term=searchable(value)
    if not term: return None
    prefix=r'^' if start else r'(?<![0-9a-z가-힣])'
    particle=r'(?:에서|으로|는|은|이|가|을|를|의|에|와|과|로|도|만)?'
    return re.compile(prefix+re.escape(term)+particle+r'(?![0-9a-z가-힣])')


def name_match(text, value, *, start=False):
    pattern=_name_pattern(value,start=start)
    return bool(pattern and pattern.search(searchable(text)))


def code_match(text, code):
    value=unicodedata.normalize('NFKC',code if isinstance(code,str) else '').casefold()
    return bool(value and re.search(r'(?<![0-9a-z])'+re.escape(value)+r'(?![0-9a-z])',
                                    unicodedata.normalize('NFKC',text if isinstance(text,str) else '').casefold()))


def canonical_url(url):
    parts=urlsplit(url)
    query=urlencode(sorted(parse_qsl(parts.query,keep_blank_values=True)))
    return urlunsplit((parts.scheme.lower(),(parts.hostname or '').lower(),parts.path or '/',query,''))


def source_id(code, kind, url):
    digest=hashlib.sha256(canonical_url(url).encode()).hexdigest()[:12]
    return f'{code}-{kind}-{digest}'


def clean_excerpt(content):
    # Keep article prose, excluding recommendation lists and publisher navigation.
    content=re.split(r'(?:^|\n|(?<=[.!?])\s+)[#*\s]*(?:관련\s*종목|관련\s*기사|많이\s*본\s*뉴스|인기\s*기사|저작권자|무단\s*전재)', content, maxsplit=1)[0]
    result,seen=[],set()
    for line in content.splitlines():
        line=line.strip()
        if re.match(r'^[-*\d.)\s]*!?\[.*\]\(https?://',line): continue
        line=re.sub(r'!\[[^\]]*\]\([^)]*\)','',line)
        line=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',line).strip()
        marker=normalized(line)
        if marker and marker not in seen:
            seen.add(marker);result.append(line)
    return '\n'.join(result)


def duplicate_source(source, previous):
    for other in previous:
        if canonical_url(source['url'])==canonical_url(other['url']): return True
        if source['kind']!='news' or other['kind']!='news': continue
        body,old=normalized(source['content']),normalized(other['content'])
        title=normalized(source['title'].split('|')[0])
        old_title=normalized(other['title'].split('|')[0])
        # Same prose or near-identical syndicated title/body. Different financial
        # figures must not be discarded just because the headline was reused.
        if len(body)>=40 and body==old: return True
        numbers=re.findall(r'\d[\d,.]*',source['content'])
        old_numbers=re.findall(r'\d[\d,.]*',other['content'])
        if (len(title)>=12 and title==old_title and numbers==old_numbers
                and SequenceMatcher(None,body,old,autojunk=False).ratio()>=0.7): return True
    return False


def _date_from_title(title):
    matches=re.findall(r'(?<!\d)(20\d{2})[.\-/년 ]\s*(0?[1-9]|1[0-2])(?:[.\-/월 ]\s*([0-3]?\d))?',title)
    if not matches: return None
    year,month,day=matches[-1]
    try: return date(int(year),int(month),int(day) if day else 1)
    except ValueError: return None


def validate_source(*, name, code, aliases, kind, title, content, published, today):
    content=clean_excerpt(content)
    if instruction_like(title+'\n'+content): return 'instruction_like'
    combined_text=title+' '+content
    combined=normalized(combined_text)
    name_term=normalized(name)
    matched_code=code_match(combined_text,code)
    matched_alias=any(name_match(combined_text,alias) for alias in aliases)
    matched_name=name_match(combined_text,name)
    if not (matched_name or matched_code or matched_alias):
        return 'identity_mismatch'
    if kind=='news' and len(normalized(content))<12: return 'thin_news'
    if kind=='news' and len(name_term)<=2 and not matched_code and not matched_alias:
        if not any(normalized(anchor) in combined for anchor in BUSINESS_ANCHORS):
            return 'identity_mismatch'
    if kind=='reports':
        first_line=content.splitlines()[0] if content.splitlines() else ''
        title_match=name_match(title,name) or code_match(title,code) or any(name_match(title,alias) for alias in aliases)
        heading_match=name_match(first_line,name,start=True) or code_match(first_line.split(' ',1)[0],code) or any(name_match(first_line,alias,start=True) for alias in aliases)
        if not (title_match or heading_match):
            return 'identity_mismatch'
        lower=unicodedata.normalize('NFKC',content).casefold()
        cleaned=lower
        for phrase in SHELL_PHRASES: cleaned=cleaned.replace(phrase,' ')
        body=normalized(cleaned)
        has_financial_term=any(normalized(word) in body for word in REPORT_WORDS)
        has_amount=bool(re.search(r'\d[\d,]*(?:\.\d+)?\s*(?:조원|억원|백만원|천원|원|%)',cleaned))
        words={normalized(word) for word in re.findall(r'[가-힣A-Za-z0-9]+',cleaned) if len(normalized(word))>=2}
        narrative=len(body)>=180 and len(words)>=12
        if not ((has_financial_term and has_amount) or narrative):
            return 'thin_report'
    stamp=None
    if published:
        try: stamp=datetime.fromisoformat(published).astimezone(timezone.utc).date()
        except (ValueError,TypeError): stamp=None
    if stamp is None and kind=='reports': stamp=_date_from_title(title)
    if stamp is None: return 'undated'
    if stamp>today+timedelta(days=1): return 'future'
    max_age=timedelta(days=45 if kind=='news' else 550)
    if today-stamp>max_age: return 'stale'
    return None


def empty_diagnostics():
    return {'rejected':Counter(), 'missing':[]}
