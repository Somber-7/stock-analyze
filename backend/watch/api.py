from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.config import base_dir
from backend.namuh.market import get_current_price
from backend.namuh.stocks import search
from .service import WatchService


def resolve(code): return next((s for s in search(code) if s['code'] == code), None)


@lru_cache(maxsize=1)
def get_watch(): return WatchService(Path(base_dir)/'.watchlist.sqlite3', get_current_price, resolve)


def guard(request: Request, x_watch_action: Annotated[str | None, Header()] = None):
    if request.method != 'GET' and x_watch_action != 'manage':
        raise HTTPException(422, '관심종목 관리 요청을 확인하세요.')


router = APIRouter(prefix='/api/watch', dependencies=[Depends(guard)])
Service = Annotated[WatchService, Depends(get_watch)]


class Stock(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(pattern=r'^[0-9A-Z]{6}$')


class Alert(Stock):
    comparison: Literal['gte', 'lte']
    threshold: int = Field(strict=True, gt=0, le=1_000_000_000)
    client_id: str = Field(min_length=1, max_length=100)


class Ack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[str] = Field(max_length=1000)


def invoke(fn, *args):
    try: return fn(*args)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc


@router.get('')
def snapshot(service: Service): return service.snapshot(viewed=True)


@router.post('/items')
def add(body: Stock, service: Service): return invoke(service.add, body.code)


@router.post('/items/{code}/remove')
def remove(code: str, service: Service):
    service.remove(code)
    return {'ok': True}


@router.post('/alerts')
def alert(body: Alert, service: Service):
    return invoke(service.add_alert, body.code, body.comparison, body.threshold, body.client_id)


@router.post('/alerts/{alert_id}/cancel')
def cancel(alert_id: str, service: Service):
    invoke(service.cancel_alert, alert_id)
    return {'ok': True}


@router.get('/notifications')
def notifications(service: Service): return service.notifications()[:1000]


@router.post('/notifications/ack')
def acknowledge(body: Ack, service: Service):
    service.acknowledge(body.ids)
    return {'ok': True}
