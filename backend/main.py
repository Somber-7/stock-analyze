import sys
import os
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from backend.namuh.client import NamuhError
from backend.namuh.market import get_current_price
from backend.namuh.chart import get_daily_chart, get_minute_chart
from backend.namuh.portfolio import get_accounts, get_balance
from backend.namuh.stocks import ensure_fresh, search as search_stocks
from backend.namuh.us_market import get_quote
from backend.namuh.top100 import get_top100
from backend.trading.routes import router as paper_router, get_engine
from backend.trading.api import router as trading_router, get_service
from backend.watch.api import router as watch_router, get_watch
from backend.namuh.investors import get_investors
from backend.ai.api import router as ai_router
from backend.ai.operation_api import router as ai_operation_router, get_operation
from backend.briefing import router as briefing_router

@asynccontextmanager
async def lifespan(app):
    ensure_fresh()
    engine = get_engine()
    service = get_service()
    watch = get_watch()
    ai_operation = get_operation()
    engine.launch()
    service.launch()
    watch.launch()
    ai_operation.launch()
    try:
        yield
    finally:
        ai_operation.close()
        watch.close()
        service.close()
        engine.close()


app = FastAPI(title="Stock Analyze — NAMUH PLUG", lifespan=lifespan)
app.include_router(paper_router)
app.include_router(trading_router)
app.include_router(watch_router)
app.include_router(ai_router)
app.include_router(ai_operation_router)
app.include_router(briefing_router)


@app.exception_handler(NamuhError)
async def namuh_error_handler(request, exc):
    return JSONResponse(status_code=502, content={'detail': str(exc)})


@app.get('/api/health')
def health():
    return {'status': 'ok', 'broker': 'namuh'}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/stock/{code}/price")
def stock_price(code: str):
    return get_current_price(code)


@app.get('/api/stock/{code}/investors')
def stock_investors(code: str):
    try: return get_investors(code)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc


@app.get("/api/stock/{code}/chart")
def stock_chart(code: str, period: Literal['D', 'W', 'M', '1m', '5m'] = 'D',
                days: int = Query(250, ge=1, le=1000)):
    if period in ('1m', '5m'):
        return get_minute_chart(code, interval=1 if period == '1m' else 5)
    return get_daily_chart(code, days=days, period=period)


@app.get("/api/stocks/search")
def stocks_search(q: str = ""):
    return search_stocks(q)


@app.get('/api/accounts')
def accounts():
    return get_accounts()


@app.get('/api/market/top100')
def market_top100():
    return get_top100()


@app.get('/api/us-market/{code}')
def us_market_quote(code: Literal['DJI', 'SPY', 'QQQ', 'SOXX', 'NVDA', 'AMD', 'MU']):
    return get_quote(code)


@app.get("/api/portfolio")
def portfolio(account: str = ''):
    return get_balance(account)


# React 빌드 파일 서빙 - 반드시 API 라우트 뒤에 위치해야 함
def _get_dist_dir():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'dist')
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', 'dist')

_dist = _get_dist_dir()
if os.path.isdir(_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

    @app.get("/")
    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str = ""):
        if full_path.startswith('api/'):
            raise HTTPException(status_code=404, detail='API 경로를 찾을 수 없습니다.')
        return FileResponse(os.path.join(_dist, "index.html"))
