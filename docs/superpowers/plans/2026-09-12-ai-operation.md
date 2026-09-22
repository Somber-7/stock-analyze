# AI Operation Implementation Plan

**Goal:** 기존 AI 키 설정을 실제 분석, 매매 제안, 선택적 모의/실전 자동 운용에 연결한다.
**Architecture:** 생성 어댑터와 데이터 수집을 분리하고 기존 PaperEngine/TradingService를 주문 경계로 유지한다. 실행 기록은 별도 SQLite에 저장한다.
**Tech Stack:** Python/FastAPI/httpx/SQLite, React/Vite/Electron.
**Spec:** docs/superpowers/specs/2026-09-12-ai-operation-design.md

## Constraints
실제 주문 테스트 금지. API 키·계좌번호는 생성 입력/로그/실행 결과에 포함하지 않는다. 기존 주문 금액 한도 제거를 유지한다. 기존 사용자 상태 파일을 초기화하지 않는다.

## Tasks
- [x] 생성 어댑터: `generate(provider,key,model,context,objective,*,http=None)` → `{analysis:{summary,risks,decisions},usage:{input_tokens,output_tokens}}`. 각 decision은 code,target_quantity,rationale. HTTP 가짜 transport 테스트를 먼저 실행하고 구현한다. 고정 공식 URL, 리디렉션/재시도 금지, 일반화한 오류만 표시한다.
- [x] 실행 서비스: `AIOperation(path,settings,trading,context_loader,generate_fn)`로 주입 가능한 경계. SQLite analysis 이력과 execution 상태를 저장. 최초 red 테스트: 분석 주문 0회, 중복 실행 주문 1회, 정지 후 지연 응답 주문 0회. 이후 구현하고 버전 변경/미체결/오류/재시작 회귀를 추가한다.
- [x] UI: 아래 API 계약으로 검색·보유종목 선택, 분석 이력, 설정, 시작/정지, 개별 제안 실행을 구현한다. 버튼 잠금, 한국어 오류, 늦은 네트워크 응답 처리 및 기존 테마를 검증한다.
- [x] 통합: main lifespan/router, AISettings 서버 전용 credential accessor, ignore, 문서, 버전 1.9.0. 전체 unittest discover/lint/build, 브라우저 가짜 서비스 QA, PyInstaller/Electron 배포 검증.

## UI API contract
All mutation requests: `X-AI-Action: manage`, JSON body. Base `/api/ai/operation`.
GET: `{version,config:{execution,codes,interval_minutes,objective,include_us},running,busy,next_run_at,error,mode,engine_running,connection:{provider,model,has_key},symbols:[{code,name}],holdings:[{code,name,quantity}],runs:[Run]}`. holdings comes from separate GET `/holdings` -> `[{code,name,quantity}]` (avoid polling real balance).
POST `/settings`: `{version,execution:'suggest'|'paper'|'live',codes:[code],interval_minutes,objective,include_us}` → state.
POST `/analyze`: `{version}` → returns quickly state; background analysis status busy; GET polls results. No orders, including while configured live.
POST `/control`: `{version,action:'start'|'stop',live_acknowledged:false}` → state. start schedules first cycle soon; requires existing matching trading engine running for paper/live.
POST `/runs/{id}/execute`: `{version,code,live_acknowledged:false}` → state. Execute one proposal, current mode engine must be running, live explicit acknowledgment.
Run: `{id,created_at,completed_at,status:'analyzing'|'ready'|'error'|'interrupted',source:'manual'|'auto',mode,provider,model,summary,risks,warnings,error,usage:{input_tokens,output_tokens},decisions:[{code,name,current_quantity,target_quantity,quantity,side:'buy'|'sell'|'hold',reference_price,rationale,execution:{status,message,order_id}|null}]}`.
Status symbol names from cached stock master. Analysis may take minutes, UI poll every3s, no repeat analyze while busy. Show analysis data sent to selected AI, API usage billing, 5minute proposal validity and 3% price refresh requirement. Explicit live ack checkbox for start/execute. Navigation callback to settings and existing orders screen. No auto-start or generation on mount.
