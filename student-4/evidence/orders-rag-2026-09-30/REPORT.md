# Orders RAG 구현·실제 검증 — 2026-09-30

브랜치 `taehyoun/release1-orders`, 기준 HEAD `6519476` 위의 미커밋 작업이다.
MCP 선행 범위는 [같은 날 새 실행](../orders-mcp-2026-09-30/REPORT.md)으로 통과한 뒤
추가 개선을 멈췄다. 이 보고서는 그 이후 RAG 구현과 새 검증 결과를 기록한다.
최종 RAG 브라우저 실행 완료: **12:58:49 AEST**.

## 구현 및 실제 흐름

- 공개 지식 문서 4개: 상태, 취소, 조회 방법, 답변 범위. 각 문서에 구현 파일을 명시했다.
  Orders DB 행·고객 정보는 색인하지 않는다. CONFIRMED도 취소 가능하고 레코드를 보존하는
  실제 동작을 문서화했으며 배송·환불 기능을 만들어 설명하지 않았다.
- UI → Docker Orders `POST /api/rag/answer` → 호스트 공용 RAG `POST /answer` →
  Chroma 검색 → 실제 Ollama 답변. backend가 `feature: student-4`를 고정한다.
  공용 loader/retrieval/generation 코드와 Student 1 문서는 수정하지 않았다.
- backend는 입력·답변 자료형·출처 feature를 검증한다. 정상 답변/출처/confidence,
  정보 부족(200), 장애(503), 잘못된 upstream 응답(502), disabled(403)를 구분한다.
- 기존 Orders 화면에 Orders guide를 추가했다. 답변, 번호가 붙은 source/chunk ID,
  confidence 및 정보 부족/장애 표시가 있으며 장애에 이전 출처가 남지 않는다.
  화면 문구는 textContent로 표시한다. 개인 주문 상태는 기존 MCP로 조회한다.
- Compose와 CI에 실제 코드가 읽는 RAG 설정을 추가했다. RAG 기본값은 disabled이며
  공용 MCP/RAG는 Docker 밖에 유지한다. 기존 주문·AI·MCP 코드는 이번 RAG 단계에서 재작성하지 않았다.

## 새 실행 명령과 결과

명령은 저장소 루트 기준이다. Python은 `/private/tmp/retail-orders-mcp-venv/bin/python`이다.

| 실제 실행 명령 | 결과 |
|---|---|
| `RAG_ENABLED=false MCP_ENABLED=false /private/tmp/retail-orders-mcp-venv/bin/python -m pytest student-4/tests/ -q` | **105 passed, 0 failed, 1 skipped (3.48s)**. RAG 27개 추가 포함. skip은 별도 live 테스트 |
| `RUN_ORDERS_MCP_LIVE=1 /private/tmp/retail-orders-mcp-venv/bin/python -m pytest student-4/tests/test_orders_mcp_live.py -v` | **1 passed, 0 failed, 0 skipped (6.73s)**. SDK alias deprecation warning 5개 |
| `ORDERS_VALIDATION_RUN=/private/tmp/orders-mcp-browser-validation /private/tmp/retail-orders-mcp-venv/bin/python student-4/scripts/host_servers.py rag` | 기존 shared RAG를 별도 RUN 색인/로그로 기동 |
| `docker compose --env-file /private/tmp/orders-mcp-browser-validation/compose.env -f /private/tmp/orders-mcp-browser-validation/compose.json up -d --no-deps orders-backend` | 기존 runtime을 유지하며 RAG 환경값을 반영한 Orders backend만 재생성; DB 서비스 재생성 없음 |
| 같은 Compose 옵션의 `restart orders-frontend` | 템플릿 및 최종 RAG 배치 수정 반영 |
| `ORDERS_VALIDATION_RUN=/private/tmp/orders-mcp-browser-validation /private/tmp/retail-orders-mcp-venv/bin/python student-4/scripts/rag_check.py` | 최종 화면 수정 후 **11 PASS, 0 FAIL, 0 skip, exit 0** |
| `ORDERS_VALIDATION_RUN=/private/tmp/orders-mcp-browser-validation /private/tmp/retail-orders-mcp-venv/bin/python student-4/scripts/audit.py` | 최종 브라우저 실행 후 원본 로컬 DB 3개 + 기존 컨테이너 DB 2개 SHA-256 모두 동일 |
| `docker compose config --quiet`, `docker compose -f student-4/docker-compose.yml config --quiet`, `git diff --check` | 모두 exit 0 |

회귀 테스트의 RAG HTTP/embedding/Chroma는 mock이다. 별도 MCP live는 실제 SDK·MCP·Orders
HTTP·임시 DB를 실행하며 Student 1 Reviews DB는 fixture다. RAG 브라우저 검사는 실제
Chrome·Docker backend·호스트 RAG·Chroma·Ollama를 사용한다. 세 종류의 검증을 구분한다.
마지막 CSS 배치 수정 후에는 RAG 브라우저 전체를 재실행했으며 위 회귀/live 결과는 그 직전의
동일 Python 코드에 대한 실행이다.

## 실제 RAG 검증 내용

검증 모델: `qwen2.5:0.5b`, 임베딩: `nomic-embed-text`. 기존 공용 기본 모델은 변경하지 않았다.
독립 색인/로그는 RUN 안에만 있다. `/refresh` 결과 문서 10 chunks, DB 0 chunks였다.
Reviews DB는 이 환경에서 사용할 수 없어 DB 자료는 미검증이며 문서 검색은 실제로 확인했다.

- student-4 검색 결과는 공개 Orders 문서 4개만 반환했다. 기존 student-1 문서도 검색됐다.
- 상태 질문: PENDING / CONFIRMED / CANCELLED가 답변에 있었고, 실제 파일을 가리키는
  출처와 `High` confidence가 화면에도 표시됐다. 첫 문서 distance는 0.1887이었다.
- 취소 질문: CONFIRMED도 CANCELLED로 변경하며 주문/항목을 보존한다는 문서 내용이
  실제 답변에 포함됐다. 자동 검사는 성공·취소 관련 응답 여부를 확인했고, 답변 원문을
  구현/문서와 추가 대조했다. 취소 API를 RAG가 실행한 것은 아니다.
- 날씨 질문: `insufficient_context`, 출처 없음, `Insufficient` 및 정보 부족 화면.
- 검증용 RAG만 중단: 503, unavailable 화면, 출처/confidence 제거. 재기동 후 정상 답변 복구.
- 브라우저 context는 외부 **image/font/stylesheet만 차단**한다. 로컬 로그인/API/MCP/Ollama 및
  fetch/XHR는 차단하거나 mock으로 대체하지 않는다. RAG 검사는 공개 문서 UI에 직접 접속하며,
  실제 홈페이지 로그인·쿠키/CORS 검사는 앞선 같은 날 MCP 브라우저 23 PASS 기록에 있다.

[최종 결과 JSON](rag-results.json), [정상 화면](rag-success.png),
[정보 부족 화면](rag-insufficient.png), [장애 화면](rag-outage.png),
[원본 DB 보존](preservation-results.json).

## 실패·제약·미실행

첫 RAG 실행은 API 답변이 정상이어도 Playwright `inner_text()`의 줄바꿈 정규화 때문에
화면 원문 비교가 실패했다. **6 PASS, 2 FAIL 기록**(실패 검사와 예외 각각 1건), exit 1이며
[원본 실패 결과](initial-ui-assertion-failure.json)를 보존했다. 검사에 `text_content()`를 사용해
실제 DOM 텍스트와 응답을 비교하도록 수정한 뒤 재실행했다. 최종 결과는 11 PASS다.

검증용 소형 모델의 취소 답변은 관련 문서를 길게 재현하여 공용 프롬프트의 80단어 요구를
지키지 않았다. 상태 답변은 문장별 인용 번호를 생략하여 공용 RAG가 관련 출처 전체를
첨부했다. 출처 목록이 모든 문장을 개별 검증했다는 뜻은 아니며, confidence는 검색 거리의
범주이지 정답 확률이 아니다. 공용 기능 보존을 위해 이 단계에서 모델/공용 pipeline을 바꾸지 않았다.

원본 DB에 쓰기, 전체 root Compose build/up, 다른 학생 전체 UI, Reviews 실제 DB 색인,
공용 agentic loop, 원격 GitHub CI, 전체 Release 1 통합/영상은 미실행이다.
마지막 Orders backend 재생성으로 현재 audit의 내부 MCP callback 로그 수는 0이다.
앞선 MCP 브라우저의 실제 호출 증거와 구분한다. MCP GET probe 406은 Accept 없는 요청 결과이며
도구 호출 실패로 해석하지 않는다. Docker→Ollama probe는 200이다.

기존 runtime/키/계정/snapshot/작업 DB를 재생성하지 않았고 prepare.py를 다시 실행하지 않았다.
원본 컨테이너는 중지 상태를 유지했으며 다른 프로젝트의 5001/5002/8080 서비스도 그대로다.
실제 키·비밀번호 내용은 출력하지 않았으며 변경 파일을 실제 비밀값과 비교해 일치가 없는 것을
확인했다. 저장소에는 DB/runtime 파일을 추가하지 않았다. commit/push/PR/merge도 하지 않았다.

## 직접 재현

검증용 서비스는 실행 중이다. `http://localhost:5000/` → Log in → My Orders → **Orders guide**.
계정은 저장소 밖 RUN의 `login.txt`를 로컬로 확인한다. 위 상태/취소/날씨 질문을 입력하면 된다.
실행·중지 절차는 [스크립트 README](../../scripts/README.md), 설정/계약은
[ORDERS_RAG.md](../../ORDERS_RAG.md)를 참조한다. 다음 계획 단계는 공용 agentic loop와
전체 CI/통합 검증이며 이번 구현의 통과 결과로 대신하지 않는다.
