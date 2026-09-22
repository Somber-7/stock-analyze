from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from backend.config import base_dir
from backend.trading.api import get_service
from .api import Version, get_ai_settings, guard, parse
from .operation import AIOperation, OperationError
from .settings import SettingsError


@lru_cache(maxsize=1)
def get_operation():
    return AIOperation(Path(base_dir)/'.ai_operation.sqlite3', get_ai_settings(), get_service())


router = APIRouter(prefix='/api/ai/operation', dependencies=[Depends(guard)])
Service = Annotated[AIOperation, Depends(get_operation)]


class Configuration(Version):
    execution: Literal['suggest', 'paper', 'live']
    codes: list[Annotated[str, Field(pattern=r'^[0-9A-Z]{6}$')]] = Field(min_length=1, max_length=10)
    interval_minutes: int = Field(strict=True, ge=5, le=1440)
    objective: str = Field(min_length=1, max_length=2000)
    include_us: bool = Field(strict=True)
    include_web: bool = Field(default=False, strict=True)
    investment_horizon: Literal['unspecified', 'short', 'medium', 'long'] = 'unspecified'
    holding_purpose: str = Field(default='',max_length=500)
    max_position_pct: float | None = Field(default=None,strict=True,gt=0,le=100)
    review_drawdown_pct: float | None = Field(default=None,strict=True,gt=0,le=100)


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Control(Version):
    action: Literal['start', 'stop']
    live_acknowledged: bool = Field(default=False, strict=True)


class Execute(Version):
    code: str = Field(pattern=r'^[0-9A-Z]{6}$')
    live_acknowledged: bool = Field(default=False, strict=True)


def invoke(fn, *args, **kwargs):
    try: return fn(*args, **kwargs)
    except (OperationError, SettingsError) as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception:
        raise HTTPException(502, 'AI 운용 요청을 처리하지 못했습니다. 설정·시세·계좌 연결 상태를 확인하세요.') from None


@router.get('')
def snapshot(service: Service): return invoke(service.snapshot)


@router.get('/holdings')
def holdings(service: Service): return invoke(service.holdings)


@router.get('/runs/{run_id}/inputs')
def inputs(run_id: str, service: Service): return invoke(service.inputs, run_id)


@router.post('/runs/{run_id}/outcomes')
async def outcomes(run_id: str, request: Request, service: Service):
    await parse(request, Observation)
    return await run_in_threadpool(invoke, service.observe, run_id)


@router.post('/settings')
async def settings(request: Request, service: Service):
    body = await parse(request, Configuration)
    return await run_in_threadpool(invoke, service.configure, **body.model_dump())


@router.post('/analyze')
async def analyze(request: Request, service: Service):
    body = await parse(request, Version)
    return await run_in_threadpool(invoke, service.analyze, body.version)


@router.post('/control')
async def control(request: Request, service: Service):
    body = await parse(request, Control)
    return await run_in_threadpool(invoke, service.control, **body.model_dump())


@router.post('/runs/{run_id}/execute')
async def execute(run_id: str, request: Request, service: Service):
    body = await parse(request, Execute)
    return await run_in_threadpool(invoke, service.execute, run_id, **body.model_dump())
