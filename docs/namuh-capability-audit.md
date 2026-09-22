# 나무 API 지원 범위 점검 (2026-09-11)

공식 가이드 메뉴의 API 220개에 대해 설명, 요청·응답 명세를 수집하고 기존 기능과 대조했습니다. 전체 API를 실제 실행한 것은 아닙니다. 주문 API는 실행하지 않았습니다.

## 적용 범위

| 기능 | 나무 공식 자료 | 결정 |
|---|---|---|
| 국내 계좌·잔고·예수금·평가손익 | 계좌목록 / 국내주식 잔고 | 유지 |
| 국내 종목 검색 | 공식 m_new_stock.mst / m_new_stock.h | 외부 목록을 나무 자료로 교체 |
| 국내 현재가·일/주/월/분봉 | currentPrice / period | 유지 |
| 시가총액 TOP 100 | 종목 마스터의 전일 시총 + 개별 현재가 | 1.3.0에서 조합 구현. 전일 순위 고정, 현재가 순차 갱신 |
| 거래량·거래대금 전체 시장 순위 | 전용 순위 API 확인 못함 | 외부 의존성 제거, 이번 범위에서 제외 |
| 종목별 투자자 | currentInvestor 제공 | 전체 시장 순위와 다름. 이번 범위에는 추가하지 않음 |
| 미국 참고 | symbolIndexFxPeriod / current | 다우, SPY·QQQ·SOXX ETF, NVDA·AMD·MU만 표시 |

## 실제 확인

- 국내 종목 파일 237바이트 레코드, CP949 한글명 오프셋 7~47: 공식 헤더와 실제 파일 검증.
- 다우 .DJI: 지수 응답과 날짜 확인.
- .IXIC / .SPX / .SOX: 나무 서버가 00902로 거부. 해당 코드를 지원된다고 단정하거나 화면에 넣지 않음.
- SPY / QQQ / SOXX / NVDA / AMD / MU: 이름·가격·거래일자 실제 응답 확인. ETF는 지수 수치와 구분 표시.
- 미국 화면은 조회 전용. 국내 투자에 관한 자동 예측·매매 기능 없음.

## 공식 출처

- [API 가이드](https://www.nhplug.com/apiservice)
- [종목정보파일](https://www.nhplug.com/apiservice-category)
- [국내주식 헤더](https://www.nhplug.com/instruments/m_new_stock.h)
- [전체 요청·응답 저장본](namuh-full-api-reference.json)

## 전체 API 목록

| 분류 | API | 경로 |
|---|---|---|
| OAuth 인증 | [접근토큰발급](https://www.nhplug.com/apiservice?group_id=be078217-0bf2-4bd3-8a6f-7d20e1dff90b&api_id=dba721ee-1584-4fde-8164-92c028dc760c) | `/oauth2/token` |
| OAuth 인증 | [접근토큰폐기](https://www.nhplug.com/apiservice?group_id=be078217-0bf2-4bd3-8a6f-7d20e1dff90b&api_id=efc6cd4d-e6cb-48e9-a6d3-79879ef1af7d) | `/oauth2/revoke` |
| OAuth 인증 | [실시간(Websocket) 세션해제](https://www.nhplug.com/apiservice?group_id=be078217-0bf2-4bd3-8a6f-7d20e1dff90b&api_id=db25c92a-84c1-45c3-b9ae-c30118c94642) | `/websocket/close/session` |
| 공통_조회 | [공통_계좌_조회_목록조회](https://www.nhplug.com/apiservice?group_id=13dc0d8c-a6b7-4f71-b3de-9e5d8812823f&api_id=60ede1bb-ae2e-4a93-8a96-4980478a45c7) | `/n2/acctinfo` |
| 공통_조회 | [공통_계좌_조회_종합거래내역](https://www.nhplug.com/apiservice?group_id=13dc0d8c-a6b7-4f71-b3de-9e5d8812823f&api_id=799c0f84-b180-49a6-bfdb-35bc6fe3a1d7) | `/common/inquiry/v1/totalTransaction` |
| 공통_조회 | [공통_계좌_조회_입출금내역](https://www.nhplug.com/apiservice?group_id=13dc0d8c-a6b7-4f71-b3de-9e5d8812823f&api_id=d69bc72b-a057-45ff-902c-b21b9f5765a3) | `/common/inquiry/v1/depositWithdrawal` |
| 통보_실시간 (Websocket) | [체결통보(국내주식/파생)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=9fd60e6c-d2df-4d65-a4f7-430e3198bf74) | `/websocket/d2/krstock` |
| 통보_실시간 (Websocket) | [체결통보(국내야간파생)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=1117972d-a78f-43f4-8f8e-e28cdbdf251f) | `/websocket/dv` |
| 통보_실시간 (Websocket) | [체결통보(해외주식)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=97851391-1442-4462-88e1-634484b63014) | `/websocket/d0` |
| 통보_실시간 (Websocket) | [체결통보(해외파생)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=36da7837-f224-4eb3-ba8c-d8e82bfd7ea8) | `/websocket/dk` |
| 통보_실시간 (Websocket) | [체결통보(장내채권/금현물)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=d8c9a66a-fa5b-4dac-9924-48afd33bb73c) | `/websocket/de/krbond` |
| 통보_실시간 (Websocket) | [주문내역통보(국내주식/파생)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=2aa32c6c-4535-4c64-ab50-e09c54a4f426) | `/websocket/d3/krstock` |
| 통보_실시간 (Websocket) | [주문내역통보(국내야간파생)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=c12d4d2e-f9b5-4096-a26c-1d2e10f8150e) | `/websocket/dn` |
| 통보_실시간 (Websocket) | [주문내역통보(해외주식)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=a933319c-675f-42f5-9f6f-82a8016b2303) | `/websocket/d1` |
| 통보_실시간 (Websocket) | [주문내역통보(해외파생)](https://www.nhplug.com/apiservice?group_id=c84d3355-00b5-4e19-a903-3d65c0ccd201&api_id=0021dd36-9d88-4056-a8b9-b535b35c8628) | `/websocket/dj` |
| 국내주식_주문 | [국내_주식_주문_현금매수](https://www.nhplug.com/apiservice?group_id=7b327f4e-a528-4bc8-9974-4331d00ffdd8&api_id=524f73cb-e915-426d-bdbb-8092373aa3cb) | `/krstock/order/v1/cashBuy` |
| 국내주식_주문 | [국내_주식_주문_현금매도](https://www.nhplug.com/apiservice?group_id=7b327f4e-a528-4bc8-9974-4331d00ffdd8&api_id=000603d3-7e54-4771-8f6e-1554cc61aae7) | `/krstock/order/v1/cashSell` |
| 국내주식_주문 | [국내_주식_주문_신용매수](https://www.nhplug.com/apiservice?group_id=7b327f4e-a528-4bc8-9974-4331d00ffdd8&api_id=d11a4115-6fbb-4ef5-a465-db0aaa8d8520) | `/krstock/order/v1/creditBuy` |
| 국내주식_주문 | [국내_주식_주문_신용매도](https://www.nhplug.com/apiservice?group_id=7b327f4e-a528-4bc8-9974-4331d00ffdd8&api_id=56d2c5bd-4204-4be2-9887-076f9f67811b) | `/krstock/order/v1/creditSell` |
| 국내주식_주문 | [국내_주식_주문_정정](https://www.nhplug.com/apiservice?group_id=7b327f4e-a528-4bc8-9974-4331d00ffdd8&api_id=782dc965-9350-419f-94bb-7076f7f567ec) | `/krstock/order/v1/modify` |
| 국내주식_주문 | [국내_주식_주문_취소](https://www.nhplug.com/apiservice?group_id=7b327f4e-a528-4bc8-9974-4331d00ffdd8&api_id=b94fadb3-9cb6-47ff-92be-fa1b720e4b93) | `/krstock/order/v1/cancel` |
| 국내주식_주문 | [국내_주식_주문_예약](https://www.nhplug.com/apiservice?group_id=7b327f4e-a528-4bc8-9974-4331d00ffdd8&api_id=bddf74fb-593a-4fa6-a4a2-b35abc0ceb3b) | `/krstock/order/v1/reservedOrder` |
| 국내주식_주문 | [국내_주식_주문_예약취소](https://www.nhplug.com/apiservice?group_id=7b327f4e-a528-4bc8-9974-4331d00ffdd8&api_id=510abcae-44d3-4d25-b214-a2b8a5fe9a7c) | `/krstock/order/v1/reservedCancel` |
| 국내주식_조회 | [국내_주식_조회_체결](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=ac080b4d-1c7a-4ae8-af9d-afab86520910) | `/krstock/inquiry/v1/dailyOrderExecution` |
| 국내주식_조회 | [국내_주식_조회_잔고](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=29b936b9-dbcd-45a9-8b1b-aa56e7e6f7df) | `/krstock/inquiry/v1/balance` |
| 국내주식_조회 | [국내_주식_조회_매수가능수량](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=4eae7a1c-5247-4866-9dc8-85eddb2f19a4) | `/krstock/inquiry/v1/buyableQuantity` |
| 국내주식_조회 | [국내_주식_조회_매도가능수량](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=d124d08d-c9d1-49d7-a7ea-3bd3215dfb3e) | `/krstock/inquiry/v1/sellableQuantity` |
| 국내주식_조회 | [국내_주식_조회_예약주문](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=027a625d-a6d9-43da-8886-83dbff72ec47) | `/krstock/inquiry/v1/reservedInquiry` |
| 국내주식_조회 | [국내_주식_조회_실현손익](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=59bba8ac-7ad1-43a7-b6ba-fdeeef0533ce) | `/krstock/inquiry/v1/realizedPnl` |
| 국내주식_조회 | [국내_주식_조회_자산현황](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=b44fe112-508f-4e96-b7b8-bd88dffef94d) | `/krstock/inquiry/v1/assetStatus` |
| 국내주식_조회 | [국내_주식_조회_실현손익추이](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=4bf63793-a235-4e9e-b99c-19ebcb7a3cb1) | `/krstock/inquiry/v1/dailyPnl` |
| 국내주식_조회 | [국내_주식_조회_종목별실현손익](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=bbe6352c-7810-499e-a58e-fbe0c5b86ccd) | `/krstock/inquiry/v1/tradingPnl` |
| 국내주식_조회 | [국내_주식_조회_통합증거금](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=40091b5d-6647-4d20-a5c7-5cb17d6678b8) | `/krstock/inquiry/v1/integratedMargin` |
| 국내주식_조회 | [국내_주식_조회_권리보유](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=e19b923a-58c0-4f9e-9b33-0c251fc128c6) | `/krstock/inquiry/v1/rightsHeld` |
| 국내주식_조회 | [국내_주식_조회_권리예정](https://www.nhplug.com/apiservice?group_id=5ebbc5cb-8234-41c4-bc95-86a51e42116a&api_id=55d708ec-2f06-47c9-af4f-598bbefece70) | `/krstock/inquiry/v1/rightsScheduled` |
| 국내주식_시세 | [국내_주식_시세_현재가](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=c9e382f1-d510-43dc-82ab-3739b8b79f66) | `/krstock/quote/v1/currentPrice` |
| 국내주식_시세 | [국내_주식_시세_체결추이](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=7ba51fdc-a9f9-442c-a274-5b2e7eacfece) | `/krstock/quote/v1/currentExecution` |
| 국내주식_시세 | [국내_주식_시세_일자별](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=58bbd690-a6ba-45b4-a44d-d57545b10a44) | `/krstock/quote/v1/currentDaily` |
| 국내주식_시세 | [국내_주식_시세_투자자](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=ed3bf111-1032-4da9-ada7-b5d0dafe59ee) | `/krstock/quote/v1/currentInvestor` |
| 국내주식_시세 | [국내_주식_시세_기간별](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=fde9e26d-3433-4fc1-ba73-e0e35b7b1998) | `/krstock/quote/v1/period` |
| 국내주식_시세 | [국내_주식_시세_시간외현재가](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=1810d91e-ed8f-4009-87da-861fd24985be) | `/krstock/quote/v1/afterHoursCurrent` |
| 국내주식_시세 | [국내_주식_시세_시간외일자별주가](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=0e8255c6-e209-41e4-8ac6-44b11de8426f) | `/krstock/quote/v1/currentAfterHoursDaily` |
| 국내주식_시세 | [국내_주식_시세_시간외시간별체결](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=9725778f-5427-4f32-8832-3c01c421eea8) | `/krstock/quote/v1/currentAfterHoursExecution` |
| 국내주식_시세 | [국내_주식_시세_시간외시간별예상](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=43fbae8a-9677-459f-9093-5df325d5bf6e) | `/krstock/quote/v1/afterHoursExpected` |
| 국내주식_시세 | [국내_주식_시세_ETF현재가](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=f931e4e1-0abe-4d94-8ab2-279e1a07c139) | `/krstock/quote/v1/etfCurrent` |
| 국내주식_시세 | [국내_주식_시세_ETF구성종목](https://www.nhplug.com/apiservice?group_id=c8314560-6cc8-456f-8a9b-b6bd0271cea3&api_id=ac018767-aec0-4dab-8d7d-7d0cfc970605) | `/krstock/quote/v1/etfComponents` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_호가(KRX)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=21314676-b3d2-4e84-a9cd-ad68ed5b560b) | `/websocket/ob` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_호가(NXT)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=4dc562ea-e3a1-4847-8d49-6b6f5c27e3a9) | `/websocket/nb` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_호가(통합)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=a6628495-c511-4031-9978-cf233e976721) | `/websocket/mb` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_체결가(KRX)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=69e81be5-3eeb-46c7-beba-fd2e22813a36) | `/websocket/oc` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_체결가(NXT)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=c991faa5-2942-4f63-87f6-1d3ca5b98487) | `/websocket/nc` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_체결가(통합)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=ae0e9a6e-034e-4b8b-9eb3-5dfda9b9d29a) | `/websocket/mc` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_예상체결(KRX)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=284a6497-5f82-4b74-a4d3-c8c5ccd6a612) | `/websocket/oa` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_예상체결(NXT)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=21efe222-5f96-43dc-8042-a3e47137fb4e) | `/websocket/na` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_예상체결(통합)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=16394230-d41f-4816-813a-89a0d6dc6169) | `/websocket/ma` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_회원사(KRX)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=728244e4-b201-41ac-805f-3c948a9310c3) | `/websocket/t1` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_회원사(NXT)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=5f5714cf-5949-46cb-824f-c4033546b950) | `/websocket/ng` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_회원사(통합)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=df3175b1-6f18-4833-badf-aa1d73a02730) | `/websocket/mg` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_프로그램매매(KRX)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=c8661746-859e-4c51-afcb-9b7ad8ee9d89) | `/websocket/t8` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_프로그램매매(NXT)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=2c358237-e2d8-40e4-bcd3-c4be0cdca241) | `/websocket/nn` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_프로그램매매(통합)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=131ca358-13a8-42ee-806f-eb5a8d44f310) | `/websocket/mn` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_시간외호가(KRX)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=bebf9d9a-9e75-436d-88b7-247cdc803558) | `/websocket/e5` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_시간외체결가(KRX)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=a99207a0-98e4-4918-9d51-0c2117ede40d) | `/websocket/e2` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_시간외예상체결(KRX)](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=d76fd76a-acac-4e5d-ad70-51b615c49a72) | `/websocket/e4` |
| 국내주식_실시간 (Websocket) | [국내_주식_실시간_채권지수체결가](https://www.nhplug.com/apiservice?group_id=25f1cdd9-6731-4941-97d4-72139a4d4a8e&api_id=4f8025f9-2782-4fff-ac18-1b5305355939) | `/websocket/uB` |
| 국내파생_주문 | [국내_파생_주문_주간](https://www.nhplug.com/apiservice?group_id=a33d392b-2ca1-4c3c-ab1b-f369a65f8ca1&api_id=de44ae47-ee32-4c66-8c63-3f255221cf95) | `/krfuture/order/v1/day` |
| 국내파생_주문 | [국내_파생_주문_야간](https://www.nhplug.com/apiservice?group_id=a33d392b-2ca1-4c3c-ab1b-f369a65f8ca1&api_id=89dc34d0-b499-4eb7-8925-c7557c260fbe) | `/krfuture/order/v1/night` |
| 국내파생_주문 | [국내_파생_주문_주간정정](https://www.nhplug.com/apiservice?group_id=a33d392b-2ca1-4c3c-ab1b-f369a65f8ca1&api_id=c25e90e0-fc93-48a0-8eed-0935d783a5a0) | `/krfuture/order/v1/dayModify` |
| 국내파생_주문 | [국내_파생_주문_야간정정](https://www.nhplug.com/apiservice?group_id=a33d392b-2ca1-4c3c-ab1b-f369a65f8ca1&api_id=a1c45cbe-8247-4fe0-a3e4-63c58a4af6f2) | `/krfuture/order/v1/nightModify` |
| 국내파생_주문 | [국내_파생_주문_주간취소](https://www.nhplug.com/apiservice?group_id=a33d392b-2ca1-4c3c-ab1b-f369a65f8ca1&api_id=273d7f5f-f210-460d-ac75-cb42c9724e88) | `/krfuture/order/v1/dayCancel` |
| 국내파생_주문 | [국내_파생_주문_야간취소](https://www.nhplug.com/apiservice?group_id=a33d392b-2ca1-4c3c-ab1b-f369a65f8ca1&api_id=bf904ffe-22b0-4dc0-b9da-c0e5ffd1ffe9) | `/krfuture/order/v1/nightCancel` |
| 국내파생_조회 | [국내_파생_조회_잔고](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=60553fec-a7af-4149-b931-57095930af17) | `/krfuture/inquiry/v1/balance` |
| 국내파생_조회 | [국내_파생_조회_주문가능수량](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=4dd450ef-0ab5-4718-8b2d-c84eccbd627e) | `/krfuture/inquiry/v1/orderable` |
| 국내파생_조회 | [국내_파생_조회_증거금](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=90e08191-4045-4b30-9571-792d63edb68d) | `/krfuture/inquiry/v1/margin` |
| 국내파생_조회 | [국내_파생_조회_야간체결](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=d7218ee2-ffbb-404d-80d6-f3a96f3063bc) | `/krfuture/inquiry/v1/nightOrderExecutionHistory` |
| 국내파생_조회 | [국내_파생_조회_체결](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=b26c288e-b8d2-403f-9c1d-c0f30a2f3bae) | `/krfuture/inquiry/v1/orderExecutionHistory` |
| 국내파생_조회 | [국내_파생_조회_야간잔고](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=368dbd96-a347-4c4d-b7ea-93fc9ede4009) | `/krfuture/inquiry/v1/nightBalance` |
| 국내파생_조회 | [국내_파생_조회_야간주문가능수량](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=658da4de-96de-488c-a9a0-190777df6d30) | `/krfuture/inquiry/v1/nightOrderable` |
| 국내파생_조회 | [국내_파생_조회_야간증거금](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=c3e50abd-b058-4658-9220-fa63a27c12a0) | `/krfuture/inquiry/v1/nightMargin` |
| 국내파생_조회 | [국내_파생_조회_평가손익](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=93222e01-330b-4d84-ac52-171c96f5bf8a) | `/krfuture/inquiry/v1/evalPnl` |
| 국내파생_조회 | [국내_파생_조회_기준일체결내역](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=24195cec-1a2b-4b05-9625-0c225c320249) | `/krfuture/inquiry/v1/executionHistory` |
| 국내파생_조회 | [국내_파생_조회_약정수수료](https://www.nhplug.com/apiservice?group_id=8a716ea0-2c80-4383-9f77-936283ea65bd&api_id=e07fae3a-00d0-42d1-acc8-4b05e15b6574) | `/krfuture/inquiry/v1/commission` |
| 국내파생_시세 | [국내_파생_시세_주간](https://www.nhplug.com/apiservice?group_id=be41e939-ccd3-4f88-b8bc-33f7daaa4eea&api_id=dad25671-4774-470c-8a85-7e043c7445e9) | `/krfuture/quote/v1/day` |
| 국내파생_시세 | [국내_파생_시세_야간](https://www.nhplug.com/apiservice?group_id=be41e939-ccd3-4f88-b8bc-33f7daaa4eea&api_id=b126247e-55bc-444f-9550-05a656935cd7) | `/krfuture/quote/v1/night` |
| 국내파생_시세 | [국내_파생_시세_기간별주간](https://www.nhplug.com/apiservice?group_id=be41e939-ccd3-4f88-b8bc-33f7daaa4eea&api_id=a26919f4-fd20-452d-85c0-2f0d5e7252eb) | `/krfuture/quote/v1/dayPeriod` |
| 국내파생_시세 | [국내_파생_시세_기간별야간](https://www.nhplug.com/apiservice?group_id=be41e939-ccd3-4f88-b8bc-33f7daaa4eea&api_id=5f82705f-6ab7-42bb-a02f-02f098fcadab) | `/krfuture/quote/v1/nightPeriod` |
| 국내파생_시세 | [국내_파생_시세_체결추이](https://www.nhplug.com/apiservice?group_id=be41e939-ccd3-4f88-b8bc-33f7daaa4eea&api_id=b7461db8-cf05-4be1-8430-37003510c49a) | `/krfuture/quote/v1/intradayExpectedTrend` |
| 국내파생_시세 | [국내_파생_시세_일자별거래](https://www.nhplug.com/apiservice?group_id=be41e939-ccd3-4f88-b8bc-33f7daaa4eea&api_id=f65c769a-6fc8-4d52-a056-b63aa206218f) | `/krfuture/quote/v1/daily` |
| 국내파생_시세 | [국내_파생_시세_시간대별투자자](https://www.nhplug.com/apiservice?group_id=be41e939-ccd3-4f88-b8bc-33f7daaa4eea&api_id=b8d07e2e-ab88-4ab0-9fb6-4652a741f41e) | `/krfuture/quote/v1/tradingStatus` |
| 국내파생_시세 | [국내_파생_시세_시간대별프로그램매매](https://www.nhplug.com/apiservice?group_id=be41e939-ccd3-4f88-b8bc-33f7daaa4eea&api_id=10ebb85e-07e3-4b00-a938-860e6363150b) | `/krfuture/quote/v1/timeProgramTrading` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물호가(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=3ac3047f-857c-434e-930c-c3e8c2b8d116) | `/websocket/f1` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물호가(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=b431601d-a20c-48b2-8884-6530fc348b30) | `/websocket/fH` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물호가(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=65199c84-46ee-4cf4-9e98-9b1841b46e17) | `/websocket/hH` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물체결가(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=53524c0a-67e1-4df2-9c11-de860bec38b0) | `/websocket/f8` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물체결가(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=736aa12a-12ba-4696-806e-07ba8d436b4b) | `/websocket/fC` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물체결가(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=bad9a68f-a206-4f07-9bb2-52ef1fd0f0ad) | `/websocket/hC` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물예상체결(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=1bebf2f8-8897-4821-a46f-98d5da41ca15) | `/websocket/fE` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물예상체결(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=de14d05e-21d9-4404-bd2e-0de76aacca45) | `/websocket/fP` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수선물예상체결(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=36651583-03d1-4902-8f99-487c7bb69bbc) | `/websocket/hE` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션호가(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=5ff241e4-daa7-408f-917b-49ce5dd90962) | `/websocket/o1` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션호가(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=a8797196-ab30-430c-8421-f9ffe5d13cb6) | `/websocket/xH` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션호가(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=662667e5-111f-4d1c-95cc-5c9d9edbd3f9) | `/websocket/rH` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션체결가(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=89738fec-6d1e-487a-844d-5c9eb45fd9b0) | `/websocket/o2` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션체결가(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=6701aab5-ef44-4575-9d05-0c3f41308fe7) | `/websocket/xC` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션체결가(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=639af12b-a9a7-4def-aa4d-af028d8f0dad) | `/websocket/rC` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션예상체결(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=fb3b9c56-d448-4bca-a658-998ab9052ebc) | `/websocket/oE` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션예상체결(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=337667a7-cae3-4dc3-9be9-1829be78b74e) | `/websocket/xP` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_지수옵션예상체결(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=e5c40de7-000f-4e57-90b4-c1e16d0a8bec) | `/websocket/rE` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_상품선물호가](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=715fef91-8415-4c1a-aff3-99f072db9387) | `/websocket/pH` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_상품선물체결가](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=b7e9c622-ca89-4cda-a568-1b8c10eb6049) | `/websocket/pC` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_상품선물예상체결](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=421b2e78-5c61-4dbb-80e4-07d364912ae9) | `/websocket/pE` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_주식선물호가](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=62dc8c34-ee88-41dc-b016-2c33b37d8f39) | `/websocket/vH` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_주식선물체결가](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=343cb1b7-4e4d-42ca-b6fd-f08d1c06b331) | `/websocket/vC` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_주식선물예상체결](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=b662f992-ebab-4016-ad81-6371e49e3bf2) | `/websocket/vE` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_주식옵션호가](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=5c4dd0cb-0f2f-4f75-94da-6376e4473bb3) | `/websocket/v1` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_주식옵션체결가](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=3d62efaa-c1b2-46d6-ab24-16188373fd13) | `/websocket/v2` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물호가(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=383fc33c-288a-481e-9091-538a0d676a0a) | `/websocket/1a` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물호가(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=34bed992-c454-4526-9557-537588a9e5fa) | `/websocket/2a` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물호가(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=c1de9106-1c78-49a2-b254-2a5c49c1de49) | `/websocket/4a` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물체결가(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=1b0f5f9b-07be-49e0-8b8e-e1944b054868) | `/websocket/1c` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물체결가(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=9afca033-c877-4604-8a8d-8b08df8b6131) | `/websocket/2c` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물체결가(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=ed99363a-773d-4606-aeca-8813713ec670) | `/websocket/4c` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물예상체결(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=dfca0fd6-11b0-47cb-b3e4-8c6efc7717c1) | `/websocket/1b` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물예상체결(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=ba454cce-e99b-4946-ac10-a8a4406f4cc5) | `/websocket/2b` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간선물예상체결(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=775f6afe-8988-4fcf-98af-ac0fb922c0f9) | `/websocket/4b` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션호가(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=97390d4f-8198-4238-a4e9-bc32aa15f727) | `/websocket/5a` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션호가(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=778fe2c8-cad1-42d6-b0aa-6dee1236205e) | `/websocket/7a` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션호가(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=6212008a-1557-42c5-aeea-a31e8ecba3ec) | `/websocket/6a` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션체결가(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=5dc6a5a4-95d4-4b9f-9804-ed8b3194a1df) | `/websocket/5c` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션체결가(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=09675b28-7ff0-4a8a-8f30-708ddc29c874) | `/websocket/7c` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션체결가(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=c64a50c7-6db8-4926-8f51-92fd653a98e4) | `/websocket/6c` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션예상체결(KP200)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=71c179fc-cfce-481e-aec1-e5b36778be7c) | `/websocket/5b` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션예상체결(KQ150)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=b8008127-fc79-4317-af7e-aab84d0f14ff) | `/websocket/7b` |
| 국내파생_실시간 (Websocket) | [국내_파생_실시간_야간옵션예상체결(미니)](https://www.nhplug.com/apiservice?group_id=d4e010c7-3235-45af-b143-adf0d9df6e1e&api_id=ef68ee4e-c698-4357-b71d-c4c932dd84a1) | `/websocket/6b` |
| 해외주식_주문 | [해외_주식_주문_매수](https://www.nhplug.com/apiservice?group_id=4775f634-2df5-4930-a198-18c5335f2538&api_id=3dbb5c2d-2486-47a7-8693-1b23622a486e) | `/gbstock/order/v1/buy` |
| 해외주식_주문 | [해외_주식_주문_매도](https://www.nhplug.com/apiservice?group_id=4775f634-2df5-4930-a198-18c5335f2538&api_id=d4f01aaa-0ad3-48ea-b044-fc27198feb82) | `/gbstock/order/v1/sell` |
| 해외주식_주문 | [해외_주식_주문_정정](https://www.nhplug.com/apiservice?group_id=4775f634-2df5-4930-a198-18c5335f2538&api_id=f5510c53-3af0-4d9c-8256-daff386f5147) | `/gbstock/order/v1/modify` |
| 해외주식_주문 | [해외_주식_주문_취소](https://www.nhplug.com/apiservice?group_id=4775f634-2df5-4930-a198-18c5335f2538&api_id=b7e79493-1894-4d6d-a37c-6fdc3360008e) | `/gbstock/order/v1/cancel` |
| 해외주식_주문 | [해외_주식_주문_예약](https://www.nhplug.com/apiservice?group_id=4775f634-2df5-4930-a198-18c5335f2538&api_id=3878b303-f1c2-4cc9-94fe-9c0ed20e4eba) | `/gbstock/order/v1/reservedSubmit` |
| 해외주식_주문 | [해외_주식_주문_예약취소](https://www.nhplug.com/apiservice?group_id=4775f634-2df5-4930-a198-18c5335f2538&api_id=ff5e5d5d-b6c5-4fce-b032-4543da1d4b82) | `/gbstock/order/v1/reservedCancel` |
| 해외주식_조회 | [해외_주식_조회_주문가능수량](https://www.nhplug.com/apiservice?group_id=aeab423a-0de9-469e-af35-036020aef53b&api_id=5b14eafd-df72-4ac3-be71-a799ee2c31ce) | `/gbstock/inquiry/v1/buyableAmount` |
| 해외주식_조회 | [해외_주식_조회_체결](https://www.nhplug.com/apiservice?group_id=aeab423a-0de9-469e-af35-036020aef53b&api_id=ae395aa3-fa1e-430e-a087-eb9ebae0a7bf) | `/gbstock/inquiry/v1/unexecuted` |
| 해외주식_조회 | [해외_주식_조회_잔고](https://www.nhplug.com/apiservice?group_id=aeab423a-0de9-469e-af35-036020aef53b&api_id=a96709e0-23ce-4252-9dd2-fb0f9eed2cb3) | `/gbstock/inquiry/v1/balance` |
| 해외주식_조회 | [해외_주식_조회_예약주문](https://www.nhplug.com/apiservice?group_id=aeab423a-0de9-469e-af35-036020aef53b&api_id=6547465c-0104-4c00-8153-9594f922f506) | `/gbstock/inquiry/v1/reservedInquiry` |
| 해외주식_조회 | [해외_주식_조회_일별거래내역](https://www.nhplug.com/apiservice?group_id=aeab423a-0de9-469e-af35-036020aef53b&api_id=fade3a9b-24f1-4adf-afbf-1ae2ae627425) | `/gbstock/inquiry/v1/dailyTransaction` |
| 해외주식_조회 | [해외_주식_조회_기간손익](https://www.nhplug.com/apiservice?group_id=aeab423a-0de9-469e-af35-036020aef53b&api_id=e17bcb0e-f498-467b-a59a-c89bdf3e91b2) | `/gbstock/inquiry/v1/periodPnl` |
| 해외주식_조회 | [해외_주식_조회_기간손익상세](https://www.nhplug.com/apiservice?group_id=aeab423a-0de9-469e-af35-036020aef53b&api_id=1e2ddc5b-5134-4886-97ea-5d8a96f78f30) | `/gbstock/inquiry/v1/periodPnlDetail` |
| 해외주식_조회 | [해외_주식_조회_증거금](https://www.nhplug.com/apiservice?group_id=aeab423a-0de9-469e-af35-036020aef53b&api_id=d576f091-42ec-44f8-a632-49d073666c09) | `/gbstock/inquiry/v1/margin` |
| 해외주식_시세 | [해외_주식_시세_현재가](https://www.nhplug.com/apiservice?group_id=8f861cae-7e6c-4caa-b580-a5bd4d7835c3&api_id=336f0dc3-36cc-4174-bafa-34aedd4db0a0) | `/gbstock/quote/v1/current` |
| 해외주식_시세 | [해외_주식_시세_체결추이](https://www.nhplug.com/apiservice?group_id=8f861cae-7e6c-4caa-b580-a5bd4d7835c3&api_id=9e10f6ec-3395-4128-b9ee-03f4182a81cf) | `/gbstock/quote/v1/executionTrend` |
| 해외주식_시세 | [해외_주식_시세_기간별](https://www.nhplug.com/apiservice?group_id=8f861cae-7e6c-4caa-b580-a5bd4d7835c3&api_id=fe421967-6333-4c50-a6e8-52a04e823956) | `/gbstock/quote/v1/period` |
| 해외주식_시세 | [해외_주식_시세_종목지수환율](https://www.nhplug.com/apiservice?group_id=8f861cae-7e6c-4caa-b580-a5bd4d7835c3&api_id=22ec86d2-705d-4b6f-9116-eb4e667865cd) | `/gbstock/quote/v1/symbolIndexFxPeriod` |
| 해외주식_실시간 (Websocket) | [해외_주식_실시간_호가](https://www.nhplug.com/apiservice?group_id=cc9092d7-f18d-4f28-9fae-6c5625b0c9f1&api_id=898ec749-e7e4-440d-8711-409306af5dd8) | `/websocket/RH` |
| 해외주식_실시간 (Websocket) | [해외_주식_실시간_호가(지연)](https://www.nhplug.com/apiservice?group_id=cc9092d7-f18d-4f28-9fae-6c5625b0c9f1&api_id=62d7c64c-a967-4e71-ba5e-c37d934538a4) | `/websocket/rh` |
| 해외주식_실시간 (Websocket) | [해외_주식_실시간_체결가](https://www.nhplug.com/apiservice?group_id=cc9092d7-f18d-4f28-9fae-6c5625b0c9f1&api_id=05100316-df43-48f4-ba1f-f3ef5d26c6bf) | `/websocket/RC` |
| 해외주식_실시간 (Websocket) | [해외_주식_실시간_체결가(지연)](https://www.nhplug.com/apiservice?group_id=cc9092d7-f18d-4f28-9fae-6c5625b0c9f1&api_id=0ee42fb9-d059-448d-9557-c82527897ceb) | `/websocket/rc` |
| 해외파생_주문 | [해외_파생_주문_매수매도](https://www.nhplug.com/apiservice?group_id=53c953b4-dcb4-490c-9a5d-18768fddc34e&api_id=8759ab9e-afae-46f4-b7d5-e16b5a3d282d) | `/gbfuture/order/v1/buy` |
| 해외파생_주문 | [해외_파생_주문_정정](https://www.nhplug.com/apiservice?group_id=53c953b4-dcb4-490c-9a5d-18768fddc34e&api_id=1fc31c2e-cc4a-45a0-892a-926c82f4a3da) | `/gbfuture/order/v1/modify` |
| 해외파생_주문 | [해외_파생_주문_취소](https://www.nhplug.com/apiservice?group_id=53c953b4-dcb4-490c-9a5d-18768fddc34e&api_id=9332415f-57c2-4cc7-b86b-3962b20cd565) | `/gbfuture/order/v1/cancel` |
| 해외파생_조회 | [해외_파생_조회_체결](https://www.nhplug.com/apiservice?group_id=18b268f5-e63b-4224-ac6e-415794b4bc8c&api_id=d4a8a80a-c06f-4d22-a346-4e8da3fe33e6) | `/gbfuture/inquiry/v1/todayOrderHistory` |
| 해외파생_조회 | [해외_파생_조회_주문가능](https://www.nhplug.com/apiservice?group_id=18b268f5-e63b-4224-ac6e-415794b4bc8c&api_id=8128ddbf-216b-4ab9-b359-7810d8f4cd37) | `/gbfuture/inquiry/v1/orderable` |
| 해외파생_조회 | [해외_파생_조회_손익](https://www.nhplug.com/apiservice?group_id=18b268f5-e63b-4224-ac6e-415794b4bc8c&api_id=1a15236c-5c77-4891-ba4c-89cb36bd5eea) | `/gbfuture/inquiry/v1/pnl` |
| 해외파생_조회 | [해외_파생_조회_예수금](https://www.nhplug.com/apiservice?group_id=18b268f5-e63b-4224-ac6e-415794b4bc8c&api_id=fe8f118d-1e9f-4db9-b451-053172171eb2) | `/gbfuture/inquiry/v1/deposit` |
| 해외파생_조회 | [해외_파생_조회_증거금](https://www.nhplug.com/apiservice?group_id=18b268f5-e63b-4224-ac6e-415794b4bc8c&api_id=f41a40d4-004f-4f89-a5b7-bc89512d0b87) | `/gbfuture/inquiry/v1/margin` |
| 해외파생_시세 | [해외_파생_시세_현재가](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=8a2b85b1-7111-40ba-9441-cf4f95fb0249) | `/gbfuture/quote/v1/current` |
| 해외파생_시세 | [해외_파생_시세_종목상세](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=3c527900-4314-44cc-9808-ce0bf1185917) | `/gbfuture/quote/v1/symbolDetail` |
| 해외파생_시세 | [해외_파생_시세_호가](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=c7a5e7fe-35bc-4465-a0a2-79655def1ab0) | `/gbfuture/quote/v1/quote` |
| 해외파생_시세 | [해외_파생_시세_분봉](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=4bfc25be-f740-4b77-a897-c88496d89956) | `/gbfuture/quote/v1/minute` |
| 해외파생_시세 | [해외_파생_시세_틱봉](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=fd277974-63f3-4977-bc9c-60f87eb9cc5e) | `/gbfuture/quote/v1/executionTrendTick` |
| 해외파생_시세 | [해외_파생_시세_일봉](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=8dea7f3d-cd49-4957-abf2-3ef480b70dc0) | `/gbfuture/quote/v1/executionTrendDaily` |
| 해외파생_시세 | [해외_파생_시세_주봉](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=b4d544b4-3c48-4e9a-9e48-139bb31f7a5e) | `/gbfuture/quote/v1/executionTrendWeekly` |
| 해외파생_시세 | [해외_파생_시세_월봉](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=f7d48f79-6eaf-4daf-8d19-49c602316b88) | `/gbfuture/quote/v1/executionTrendMonthly` |
| 해외파생_시세 | [해외_파생_시세_상품정보](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=6a1b28a1-522c-4186-bbfe-ca1df2354920) | `/gbfuture/quote/v1/productInfo` |
| 해외파생_시세 | [해외_파생_시세_장운영정보](https://www.nhplug.com/apiservice?group_id=53a9522c-e33f-44bc-a1e6-f138766d0dcf&api_id=e57c0a6c-f0e9-4f4e-a8ae-5d3d52a1a4fb) | `/gbfuture/quote/v1/marketOperationInfo` |
| 해외파생_실시간 (Websocket) | [해외_파생_실시간_호가](https://www.nhplug.com/apiservice?group_id=9378c2df-f0a7-4002-84fd-d2919f4c37cb&api_id=27dfe435-7f86-4aaf-bbd2-a698eeceeb06) | `/websocket/FH` |
| 해외파생_실시간 (Websocket) | [해외_파생_실시간_호가(지연)](https://www.nhplug.com/apiservice?group_id=9378c2df-f0a7-4002-84fd-d2919f4c37cb&api_id=a2fd06a0-2870-4de7-9c83-d9fab95c8636) | `/websocket/fh` |
| 해외파생_실시간 (Websocket) | [해외_파생_실시간_체결가](https://www.nhplug.com/apiservice?group_id=9378c2df-f0a7-4002-84fd-d2919f4c37cb&api_id=f0b28a3b-8c89-4b18-964a-5186739e6d97) | `/websocket/FC` |
| 해외파생_실시간 (Websocket) | [해외_파생_실시간_체결가(지연)](https://www.nhplug.com/apiservice?group_id=9378c2df-f0a7-4002-84fd-d2919f4c37cb&api_id=a4411f0e-a61d-4fa9-8366-2000030354df) | `/websocket/fc` |
| 장내채권_주문 | [국내_채권_주문_매수](https://www.nhplug.com/apiservice?group_id=75fefeda-72b6-40e5-8e7f-a087211b5fed&api_id=4750def0-a511-46c1-bd58-640ff68d1be6) | `/krbond/order/v1/bondBuy` |
| 장내채권_주문 | [국내_채권_주문_매도](https://www.nhplug.com/apiservice?group_id=75fefeda-72b6-40e5-8e7f-a087211b5fed&api_id=9d9588c7-8be1-483e-8ca5-32f7e172a853) | `/krbond/order/v1/bondSell` |
| 장내채권_주문 | [국내_채권_주문_정정](https://www.nhplug.com/apiservice?group_id=75fefeda-72b6-40e5-8e7f-a087211b5fed&api_id=1f48c966-b96d-45f6-a6d0-1568282c4d23) | `/krbond/order/v1/bondModify` |
| 장내채권_주문 | [국내_채권_주문_취소](https://www.nhplug.com/apiservice?group_id=75fefeda-72b6-40e5-8e7f-a087211b5fed&api_id=b04841db-4f6c-4ed3-8e28-4c956e130a54) | `/krbond/order/v1/bondCancel` |
| 장내채권_주문 | [국내_채권_주문_대용매도](https://www.nhplug.com/apiservice?group_id=75fefeda-72b6-40e5-8e7f-a087211b5fed&api_id=c0793c20-9afb-47a4-9d2c-e32f6b5f5a9a) | `/krbond/order/v1/bondSubstituteSell` |
| 장내채권_조회 | [국내_채권_조회_주문가능수량](https://www.nhplug.com/apiservice?group_id=b7854914-d365-4775-9b40-d35f78809f75&api_id=0e0c1ecb-3edb-4cfb-912f-b6bcfafee413) | `/krbond/inquiry/v1/bondOrderableQuantity` |
| 장내채권_조회 | [국내_채권_조회_체결](https://www.nhplug.com/apiservice?group_id=b7854914-d365-4775-9b40-d35f78809f75&api_id=341cbcf8-b969-4e10-80ef-98a3d608ed23) | `/krbond/inquiry/v1/bondModifiableOrder` |
| 장내채권_조회 | [국내_채권_조회_잔고](https://www.nhplug.com/apiservice?group_id=b7854914-d365-4775-9b40-d35f78809f75&api_id=e871a8d0-8a92-4beb-a2a6-7a856b7946b5) | `/krbond/inquiry/v1/bondBalance` |
| 장내채권_조회 | [국내_채권_조회_대용잔고](https://www.nhplug.com/apiservice?group_id=b7854914-d365-4775-9b40-d35f78809f75&api_id=63c266fa-9acd-4a9b-befc-65a19d60e639) | `/krbond/inquiry/v1/bondSubstituteBalance` |
| 장내채권_시세 | [국내_채권_시세_현재가](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=5b05ce83-6570-45e0-bff5-bcd4a04815db) | `/krbond/quote/v1/bondCurrent` |
| 장내채권_시세 | [국내_채권_시세_상세정보](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=9559aae5-1a79-4ecb-b432-b0a956b1f8a9) | `/krbond/quote/v1/bondDetail` |
| 장내채권_시세 | [국내_채권_시세_매매현황](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=132532d4-d1ca-471f-98cf-8a2b8d1c371f) | `/krbond/quote/v1/bondTradingStatus` |
| 장내채권_시세 | [국내_채권_시세_일자별](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=59478f65-8954-43fd-88bb-2f7f4d2277cb) | `/krbond/quote/v1/bondDaily` |
| 장내채권_시세 | [국내_채권_시세_발행현황](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=524b61d2-cc5c-4986-8e9d-c50770083b13) | `/krbond/quote/v1/bondIssuance` |
| 장내채권_시세 | [국내_채권_시세_민평단가](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=02c6fcaa-60cc-4e45-9f52-19398d675ef9) | `/krbond/quote/v1/bondFairValue` |
| 장내채권_시세 | [국내_채권_시세_물가연동채권](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=39785c5c-0a4a-4d81-b118-51f061fd2e6b) | `/krbond/quote/v1/inflationBond` |
| 장내채권_시세 | [국내_채권_시세_수익률추이](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=4e39d5d6-9f96-4366-a085-a616e315dd7e) | `/krbond/quote/v1/yieldTrend` |
| 장내채권_시세 | [국내_채권_시세_금리스프레드일별수익률](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=91aee39c-c9c6-47f6-96ff-015123f9a1ac) | `/krbond/quote/v1/rateSpreadDailyYield` |
| 장내채권_시세 | [국내_채권_시세_유형별수익률비교](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=ad3f56e0-a36d-4880-8f03-bdadacfbc592) | `/krbond/quote/v1/yieldComparisonByType` |
| 장내채권_시세 | [국내_채권_시세_시가평가수익률민평](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=7068d893-2a50-42a1-87e3-6f299b099076) | `/krbond/quote/v1/fairValueYield` |
| 장내채권_시세 | [국내_채권_시세_소액채권발행현황](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=aad597b2-21fd-4ef8-86f8-52dca7e476ec) | `/krbond/quote/v1/smallBondIssuance` |
| 장내채권_시세 | [국내_채권_시세_소액채권호가매매현황](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=198c9614-887d-421a-b46d-45baafa4a582) | `/krbond/quote/v1/smallBondQuoteTrading` |
| 장내채권_시세 | [국내_채권_시세_소액채권시간대별현재가](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=83a3d250-58d9-463b-b2da-d297b164e80a) | `/krbond/quote/v1/smallBondTimeCurrent` |
| 장내채권_시세 | [국내_채권_시세_소액채권신고수익률](https://www.nhplug.com/apiservice?group_id=046b5bcd-5bc6-42c5-95e7-826b9f7e9a94&api_id=f3d4e20e-89c7-48e4-b51e-d3f6121ecd55) | `/krbond/quote/v1/smallBondReportedYield` |
| 장내채권_실시간 (Websocket) | [국내_채권_실시간_호가(소액채권)](https://www.nhplug.com/apiservice?group_id=cf0b28db-bd0b-446d-ab7b-9a6fbee5412b&api_id=57d3db19-6088-4de3-b76f-636057bae4d6) | `/websocket/c1` |
| 장내채권_실시간 (Websocket) | [국내_채권_실시간_호가(전환사채)](https://www.nhplug.com/apiservice?group_id=cf0b28db-bd0b-446d-ab7b-9a6fbee5412b&api_id=98ce7e0a-1768-4d86-a25d-3e85149a8ce7) | `/websocket/c3` |
| 장내채권_실시간 (Websocket) | [국내_채권_실시간_체결가(소액채권)](https://www.nhplug.com/apiservice?group_id=cf0b28db-bd0b-446d-ab7b-9a6fbee5412b&api_id=312392fc-d7c4-4ca4-9f78-9aa3adffa6b9) | `/websocket/c2` |
| 장내채권_실시간 (Websocket) | [국내_채권_실시간_체결가(전환사채)](https://www.nhplug.com/apiservice?group_id=cf0b28db-bd0b-446d-ab7b-9a6fbee5412b&api_id=22c53fbf-7c64-40e4-b628-c514e29549d5) | `/websocket/c4` |
| 금현물_주문 | [국내_금현물_주문_매수](https://www.nhplug.com/apiservice?group_id=23368197-7ee1-4e78-91e1-c2eed9b70db2&api_id=117c39a7-d5fe-463f-a847-c517b9a41e85) | `/krgold/order/v1/goldBuy` |
| 금현물_주문 | [국내_금현물_주문_매도](https://www.nhplug.com/apiservice?group_id=23368197-7ee1-4e78-91e1-c2eed9b70db2&api_id=9a76b415-d199-4b1d-af86-0af38b293b88) | `/krgold/order/v1/goldSell` |
| 금현물_주문 | [국내_금현물_주문_정정](https://www.nhplug.com/apiservice?group_id=23368197-7ee1-4e78-91e1-c2eed9b70db2&api_id=3840f0ff-8548-4860-ba50-624eb25f01fb) | `/krgold/order/v1/goldModify` |
| 금현물_주문 | [국내_금현물_주문_취소](https://www.nhplug.com/apiservice?group_id=23368197-7ee1-4e78-91e1-c2eed9b70db2&api_id=19ecf8ae-feab-4648-b595-5d8d72d3a031) | `/krgold/order/v1/goldCancel` |
| 금현물_조회 | [국내_금현물_조회_주문가능수량](https://www.nhplug.com/apiservice?group_id=0fb4d875-bb8c-498d-a798-47dfb280ecc3&api_id=893aae98-c46c-4fa5-9e34-a7182e83e656) | `/krgold/inquiry/v1/goldOrderableQuantity` |
| 금현물_조회 | [국내_금현물_조회_체결](https://www.nhplug.com/apiservice?group_id=0fb4d875-bb8c-498d-a798-47dfb280ecc3&api_id=3f1268a2-90b5-44d6-a1a4-df8428d6a59e) | `/krgold/inquiry/v1/goldExecution` |
| 금현물_조회 | [국내_금현물_조회_잔고](https://www.nhplug.com/apiservice?group_id=0fb4d875-bb8c-498d-a798-47dfb280ecc3&api_id=8958679b-b4c5-46f6-9dc4-0959c9a1f171) | `/krgold/inquiry/v1/goldDepositAndBalance` |
| 금현물_시세 | [국내_금현물_시세_현재가](https://www.nhplug.com/apiservice?group_id=632f32f0-0efc-4e66-a5c8-c12cb9cdfcdb&api_id=0bc91c32-27fd-4b9b-96c3-6d1bd8e58eeb) | `/krgold/quote/v1/goldCurrent` |
| 금현물_시세 | [국내_금현물_시세_일별투자매매현황](https://www.nhplug.com/apiservice?group_id=632f32f0-0efc-4e66-a5c8-c12cb9cdfcdb&api_id=bf40e172-6e35-4f6a-ba7b-f21c4d1b2d79) | `/krgold/quote/v1/goldDailyInvestorTrade` |
| 금현물_시세 | [국내_금현물_시세_일별추이](https://www.nhplug.com/apiservice?group_id=632f32f0-0efc-4e66-a5c8-c12cb9cdfcdb&api_id=2a90f1ea-48c9-4ecf-89fc-b361778e7024) | `/krgold/quote/v1/goldDailyTrend` |
| 금현물_시세 | [국내_금현물_시세_변동거래](https://www.nhplug.com/apiservice?group_id=632f32f0-0efc-4e66-a5c8-c12cb9cdfcdb&api_id=2c041b86-321e-4d80-93c6-c186dce100de) | `/krgold/quote/v1/goldVolatilityTrade` |
| 금현물_실시간 (Websocket) | [국내_금현물_실시간_호가](https://www.nhplug.com/apiservice?group_id=2cfb0684-ec58-4b06-b272-46b66b514551&api_id=4aa18db9-759e-4118-ac74-b4b4c3fc893f) | `/websocket/g5` |
| 금현물_실시간 (Websocket) | [국내_금현물_실시간_체결가](https://www.nhplug.com/apiservice?group_id=2cfb0684-ec58-4b06-b272-46b66b514551&api_id=4427c947-272b-4298-9714-5c484f07fadb) | `/websocket/g4` |
| 금현물_실시간 (Websocket) | [국내_금현물_실시간_예상체결](https://www.nhplug.com/apiservice?group_id=2cfb0684-ec58-4b06-b272-46b66b514551&api_id=33c43f83-b0ec-4abc-87cb-f8ea5f3042f3) | `/websocket/gE` |
