from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.config import base_dir
from backend.namuh.market import get_current_price
from backend.namuh.stocks import trading_names
from .paper import PaperEngine, PaperError


@lru_cache(maxsize=1)
def get_engine():
    return PaperEngine(Path(base_dir) / '.paper_trading.sqlite3', get_current_price)


def paper_mutation(request: Request, x_paper_mode: Annotated[str | None, Header()] = None):
    if request.method != 'GET' and x_paper_mode != 'paper':
        raise HTTPException(422, '모의매매 요청만 허용됩니다.')


router = APIRouter(prefix='/api/paper', dependencies=[Depends(paper_mutation)])
Engine = Annotated[PaperEngine, Depends(get_engine)]
Version = Annotated[int, Header(alias='X-Paper-Version')]
PositiveInt = Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]


class PaperRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['paper'] = 'paper'


class Order(PaperRequest):
    client_id: str = Field(min_length=1, max_length=100)
    code: str = Field(pattern=r'^[0-9A-Z]{6}$')
    side: Literal['buy', 'sell']
    quantity: PositiveInt
    limit_price: PositiveInt


class Rule(Order):
    comparison: Literal['gte', 'lte']
    threshold: PositiveInt


class Modify(PaperRequest):
    limit_price: PositiveInt


class Control(PaperRequest):
    action: Literal['start', 'pause', 'emergency']


def call(method, *args, **kwargs):
    try:
        return method(*args, **kwargs)
    except PaperError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('')
def snapshot(engine: Engine):
    return trading_names(engine.snapshot())


@router.post('/orders')
def submit(body: Order, engine: Engine, version: Version):
    return call(engine.submit, expected_version=version, **body.model_dump(exclude={'mode'}))


@router.post('/orders/{order_id}/cancel')
def cancel(order_id: str, engine: Engine, version: Version):
    return call(engine.cancel, order_id, expected_version=version)


@router.post('/orders/{order_id}/modify')
def modify(order_id: str, body: Modify, engine: Engine, version: Version):
    return call(engine.modify, order_id, body.limit_price, expected_version=version)


@router.post('/rules')
def add_rule(body: Rule, engine: Engine, version: Version):
    return call(engine.add_rule, expected_version=version, **body.model_dump(exclude={'mode'}))


@router.post('/rules/{rule_id}/cancel')
def cancel_rule(rule_id: str, engine: Engine, version: Version):
    return call(engine.cancel_rule, rule_id, expected_version=version)


@router.post('/control')
def control(body: Control, engine: Engine, version: Version):
    if body.action == 'start':
        call(engine.start, expected_version=version)
    else:
        call(engine.stop, emergency=body.action == 'emergency', expected_version=version)
    return engine.snapshot()
