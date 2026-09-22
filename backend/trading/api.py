from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from backend.config import base_dir
from backend.namuh.client import NamuhError
from backend.namuh.orders import OrderGateway
from backend.namuh.stocks import trading_names
from .live import TradingService, TradingError


@lru_cache(maxsize=1)
def get_service():
    from .routes import get_engine
    return TradingService(Path(base_dir) / '.live_trading.sqlite3', get_engine(), OrderGateway())


Service = Annotated[TradingService, Depends(get_service)]
Version = Annotated[int, Header(alias='X-Trading-Version')]
LiveMode = Annotated[Literal['live'], Header(alias='X-Trading-Mode')]
Positive = Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Settings(StrictModel):
    mode: Literal['paper', 'live']
    account: str = Field(max_length=30)
    live_acknowledged: bool = False


class LiveOrder(StrictModel):
    client_id: str = Field(min_length=1, max_length=100)
    code: str = Field(pattern=r'^[0-9A-Z]{6}$')
    side: Literal['buy', 'sell']
    quantity: Positive
    price: Positive


class LiveRule(LiveOrder):
    comparison: Literal['gte', 'lte']
    threshold: Positive


class Management(StrictModel):
    client_id: str = Field(min_length=1, max_length=100)
    action: Literal['modify', 'cancel']
    order_day: str = Field(pattern=r'^[0-9]{8}$')
    price: Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)] = 0


class Resolution(StrictModel):
    decision: Literal['not_sent', 'linked']
    broker_id: str | None = None
    acknowledged: bool


class Control(StrictModel):
    action: Literal['start', 'pause', 'emergency']


def invoke(method, *args, **kwargs):
    try:
        return method(*args, **kwargs)
    except TradingError as exc:
        raise HTTPException(400, str(exc)) from exc
    except NamuhError as exc:
        raise HTTPException(502, str(exc)) from exc


router = APIRouter(prefix='/api/trading')


@router.get('')
def state(service: Service):
    return trading_names(service.snapshot())


@router.post('/settings')
def settings(body: Settings, service: Service, version: Version):
    if body.mode == 'live' and not body.live_acknowledged:
        raise HTTPException(400, '실전 모드에서는 실제 계좌로 주문됨을 확인하세요.')
    return invoke(service.configure, expected_version=version,
                  **body.model_dump(exclude={'live_acknowledged'}))


@router.get('/live')
def live_history(service: Service, day: str | None = None):
    if day:
        try: datetime.strptime(day, '%Y%m%d')
        except ValueError: raise HTTPException(422, '조회일자는 YYYYMMDD 형식입니다.') from None
    return invoke(service.refresh, day)


@router.get('/capacity')
def capacity(service: Service, code: str, side: Literal['buy', 'sell'], price: int):
    return invoke(service.capacity, code, side, price)


@router.post('/orders')
def submit(body: LiveOrder, service: Service, version: Version, mode: LiveMode):
    return invoke(service.order, expected_version=version, **body.model_dump())


@router.post('/orders/{broker_id}')
def manage(broker_id: str, body: Management, service: Service, version: Version, mode: LiveMode):
    return invoke(service.manage, body.action, body.client_id, broker_id, body.price, version, order_day=body.order_day)


@router.post('/resolve/{op_id}')
def resolve(op_id: str, body: Resolution, service: Service, version: Version, mode: LiveMode):
    return invoke(service.resolve, op_id, body.decision, body.broker_id, body.acknowledged, version)


@router.post('/rules')
def add_rule(body: LiveRule, service: Service, version: Version, mode: LiveMode):
    return invoke(service.add_rule, expected_version=version, **body.model_dump())


@router.post('/rules/{rule_id}/cancel')
def cancel_rule(rule_id: str, service: Service, version: Version, mode: LiveMode):
    invoke(service.cancel_rule, rule_id, version)
    return service.snapshot()


@router.post('/control')
def control(body: Control, service: Service, version: Version, mode: LiveMode):
    if body.action == 'start': return invoke(service.start, version)
    if body.action == 'emergency': return invoke(service.emergency)
    return invoke(service.stop)
