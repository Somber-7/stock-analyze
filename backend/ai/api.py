from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from backend.config import base_dir
from .settings import AISettings, SettingsError


@lru_cache(maxsize=1)
def get_ai_settings(): return AISettings(Path(base_dir)/'.ai_settings.enc')


def guard(request: Request, x_ai_action: Annotated[str | None, Header()] = None):
    if request.method != 'GET' and x_ai_action != 'manage':
        raise HTTPException(422, 'AI 설정 요청을 확인하세요.')


router = APIRouter(prefix='/api/ai', dependencies=[Depends(guard)])
Service = Annotated[AISettings, Depends(get_ai_settings)]
Provider = Literal['openai', 'anthropic', 'gemini']


class Version(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(strict=True, ge=0)


class Update(Version):
    provider: Provider
    model: str = Field(max_length=160)
    api_key: SecretStr | None = None


class TavilyUpdate(Version):
    api_key: SecretStr | None = None


class DartUpdate(TavilyUpdate):
    enabled: bool = Field(strict=True)


async def parse(request, schema):
    # FastAPI's default validation output echoes invalid inputs, including secrets.
    try: return schema.model_validate(await request.json())
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, 'AI 설정 입력 형식을 확인하세요.') from None


def invoke(fn, *args):
    try: return fn(*args)
    except SettingsError as exc: raise HTTPException(400, str(exc)) from None


@router.get('/settings')
def snapshot(service: Service): return invoke(service.snapshot)


@router.post('/settings')
async def save(request: Request, service: Service):
    body = await parse(request, Update)
    return invoke(service.save, body.provider, body.model,
                  body.api_key.get_secret_value() if body.api_key is not None else None, body.version)


@router.post('/import-openai')
async def import_openai(request: Request, service: Service):
    body = await parse(request, Version)
    return invoke(service.import_openai, Path(base_dir)/'Api_Key.txt', body.version)


@router.post('/tools/tavily/settings')
async def save_tavily(request: Request, service: Service):
    body = await parse(request, TavilyUpdate)
    return invoke(service.save_tavily,
                  body.api_key.get_secret_value() if body.api_key is not None else None, body.version)


@router.post('/tools/tavily/delete-key')
async def delete_tavily(request: Request, service: Service):
    body = await parse(request, Version)
    return invoke(service.delete_tavily, body.version)


@router.post('/tools/tavily/check')
async def check_tavily(request: Request, service: Service):
    from starlette.concurrency import run_in_threadpool
    body = await parse(request, Version)
    return await run_in_threadpool(invoke, service.check_tavily, body.version)


@router.post('/{provider}/delete-key')
async def delete(provider: Provider, request: Request, service: Service):
    body = await parse(request, Version)
    return invoke(service.delete, provider, body.version)


@router.post('/tools/dart/settings')
async def save_dart(request: Request, service: Service):
    body = await parse(request, DartUpdate)
    return invoke(service.save_dart, body.api_key.get_secret_value() if body.api_key is not None else None, body.enabled, body.version)


@router.post('/tools/dart/delete-key')
async def delete_dart(request: Request, service: Service):
    body = await parse(request, Version)
    return invoke(service.delete_dart, body.version)


@router.post('/tools/dart/check')
async def check_dart(request: Request, service: Service):
    from starlette.concurrency import run_in_threadpool
    body = await parse(request, Version)
    return await run_in_threadpool(invoke, service.check_dart, body.version)


@router.post('/{provider}/check')
async def check(provider: Provider, request: Request, service: Service):
    from starlette.concurrency import run_in_threadpool
    from .providers import ProviderError
    body = await parse(request, Version)
    try: return await run_in_threadpool(invoke, service.check, provider, body.version)
    except ProviderError as exc: raise HTTPException(502, str(exc)) from None
