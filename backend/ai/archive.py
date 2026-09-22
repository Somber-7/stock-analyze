"""Immutable local evidence records and compact model inputs."""
import copy
import hashlib
import json
import math


PRIVATE_FIELDS = {'account','account_id','account_no','act_no','acct_no','cust_no','binding',
                  'comparison_scope','api_key','key','secret','app_key','app_secret','access_token',
                  'authorization','token','credentials','tavily_key','dart_key'}


def sanitize(value):
    if isinstance(value,dict):
        return {k:sanitize(v) for k,v in value.items() if isinstance(k,str) and k.lower() not in PRIVATE_FIELDS}
    if isinstance(value,(list,tuple)): return [sanitize(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value): return None
    if value is None or isinstance(value,(str,int,float,bool)): return value
    return None


def build_snapshot(config, context, instructions):
    record = dict(schema_version=1,config=sanitize(config),context=sanitize(context),instructions=instructions)
    encoded=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    record['sha256']=hashlib.sha256(encoded.encode()).hexdigest()
    return record


def model_context(context):
    result=copy.deepcopy(context)
    for stock in result.get('stocks',[]): stock.pop('raw_daily',None)
    if isinstance(result.get('benchmark'),dict): result['benchmark'].pop('daily',None)
    web=result.get('web_research')
    if isinstance(web,dict):
        for search in web.get('searches',[]): search.pop('sources',None)
        unique={}
        for source in web.get('sources',[]): unique.setdefault(source['id'],source)
        web['sources']=list(unique.values())
    return result
