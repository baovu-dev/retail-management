# MCP 범위 마무리 — 2026-09-30

브랜치 `taehyoun/release1-orders`, 기준 HEAD `6519476` + 미커밋 작업.
아래는 9월 30일 재개 후 새로 실행한 결과이며 과거 결과를 재사용하지 않았다.

| 실행 명령 (저장소 루트) | 새 결과 |
|---|---|
| `MCP_ENABLED=false /private/tmp/retail-orders-mcp-venv/bin/python -m pytest student-4/tests/ -q` | 78 passed, 1 skipped, 2.36s; skip은 별도 live 테스트 |
| `RUN_ORDERS_MCP_LIVE=1 /private/tmp/retail-orders-mcp-venv/bin/python -m pytest student-4/tests/test_orders_mcp_live.py -v` | 1 passed, 3.11s; 기존 SDK alias deprecation warning 5개 |
| `ORDERS_VALIDATION_RUN=/private/tmp/orders-mcp-browser-validation /private/tmp/retail-orders-mcp-venv/bin/python student-4/scripts/host_servers.py mcp stop` 및 같은 명령의 `mcp` | 실행 명령/PID 확인 후 검증용 MCP만 최신 코드로 재시작 |
| `ORDERS_VALIDATION_RUN=/private/tmp/orders-mcp-browser-validation /private/tmp/retail-orders-mcp-venv/bin/python student-4/scripts/browser_check.py` | **23 PASS, 0 FAIL, 종료 코드 0** |
| `ORDERS_VALIDATION_RUN=/private/tmp/orders-mcp-browser-validation /private/tmp/retail-orders-mcp-venv/bin/python student-4/scripts/audit.py` | 원본 로컬 DB 3개 + 기존 컨테이너 DB 2개 해시 동일; Docker→호스트 연결 확인 |

사용자 수정 `student4_orders.py`를 보존했다. 정확한 int 주문 ID·범위, dict 응답,
응답 주문 ID·문자열 상태와 허용된 상태를 검사하며 정상 반환은 ID/상태만 포함한다.
정상 상태 3개와 잘못된 응답 자료형/주문 ID 사례를 테스트했다.
live 테스트는 `expected.issubset(names)`를 사용하여 다른 학생 도구의 추가를 허용한다.

저장소의 browser_check.py는 validation_checks.py를 실제 import한다. 정상·복구·새 토큰
재시도 모두 요청 주문 ID, 예상 PENDING, MCP 출처/도구명, 화면 문구를 확인한다.
record()로 쌓인 FAIL이 하나라도 있으면 마지막에 종료 코드 1, 예외도 1이다.
고객·직원 두 브라우저 context 모두 route_resource를 적용한다. **외부 image/font/stylesheet만
차단**하며 로컬 요청 및 fetch/XHR/API는 차단하거나 mock 응답으로 바꾸지 않는다.
9월 29일의 더 넓은 비로컬 URL 차단과 구분하여 이전 보고서 설명도 정정했다.

실제 Chrome 로그인·쿠키/CORS·MCP·타 고객 거절·위조·123초 토큰 만료·새 토큰 재시도,
MCP 중단 503/복구, 기존 주문/직원/AI 흐름을 확인했다. 새 테스트 주문은 복사 DB의 17번이다.
최신 코드에서 실제 Ollama source도 확인했다. [결과](browser-results.json),
[원본 보존](preservation-results.json), [정상 화면](mcp-success.png), [장애 화면](mcp-outage.png).

기존 runtime/키/계정/snapshot은 재생성하지 않았다. 저장소에는 재사용 스크립트와 실행법만
추가했으며 실제 값과 DB는 RUN에 유지한다. 스크립트 사용법은 `student-4/scripts/README.md`.

이번 범위의 실패는 없다. 기본 root Compose 전체 build/up, 원격 CI, 다른 학생 전체 UI,
공용 agentic loop는 미실행이다. **요청한 MCP 범위를 통과했으므로 추가 MCP 개선을 멈추고
Orders RAG 8–11단계로 진행한다.** commit/push/PR/merge 없음.
