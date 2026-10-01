# Orders agentic loop · 로컬 CI · 기본 이미지 검증

2026-09-30 AEST. `taehyoun/release1-orders`, HEAD `6519476` + 미커밋 변경.
**MCP agentic 및 로컬 CI/빌드는 통과했다. RAG 주장 검증은 3 PASS / 2 FAIL이며
전체 RAG 품질 통과로 보고하지 않는다.** [기계 판독 요약](SUMMARY.json).

## 재개 시 저장 상태

실제 파일과 JSON을 다시 읽어 이전 MCP 브라우저 **23 PASS / 0 FAIL**, RAG 브라우저
**11 PASS / 0 FAIL**, 두 REPORT.md, 계획서의 8–11단계 완료 기록이 저장된 것을 확인했다.
중단 때문에 빠진 결과 파일은 없었다. 이 통과 결과를 새 코드의 재실행으로 부풀리지 않았고
동일한 전체 브라우저/별도 MCP live 검사를 반복하지 않았다.

RUN의 runtime, compose, 키/계정, snapshot 3개, 작업 DB, PID, RAG 색인도 그대로 재사용했다.
prepare.py를 다시 실행하지 않았다. 기존 공용 기본 색인 경로에는 색인이 없었으며,
이번 실행은 이미 존재하는 RUN의 별도 색인을 조회했다. `/refresh`/삭제/재색인은 하지 않았다.

## 변경 범위

- 공용 `agentic-loop/main.py`: `--feature student-4` 선택, 증거/검토/로그 경로와 실패 종료 코드.
  기본 feature는 Student 1이다. 기존 MCP/RAG/AI 세 mode 파일과 prompt는 그대로다.
- `modes/orders_mode.py`: 실제 shared 로그인 + 서명 토큰 + MCP 경계 사례 6개;
  RAG 질문 5개의 전체 답변/검색 문장 수집 및 그 증거에 묶인 주장별 검토.
  토큰·비밀번호는 메모리에만 쓰며 로그에 넣지 않는다.
- `student-4/backend/app.py`: CI에서 기존 AI 호출도 끌 수 있도록 실제 `AI_ENABLED` 검사 추가.
  기본 true라 기존 동작을 유지하고 false면 DB/모델 호출 전 403이다. Compose/CI에도 반영했다.
- `student-4/.dockerignore`: 기본 이미지에 원본 DB/비밀 runtime 파일이 포함되지 않도록 제외.
  기본 Dockerfile 자체는 변경하지 않았다.
- `scripts/local_ci.py`, `image_check.py`: Python 3.11 CI와 기본 이미지의 격리 HTTP 통합 검사.
  `test_orders_agentic.py` 및 AI disabled 테스트, 사용법 `ORDERS_AGENTIC.md` 추가.

## 실제 명령과 새 결과

아래 명령에서 `PY=/private/tmp/retail-orders-mcp-venv/bin/python`,
`RUN=/private/tmp/orders-mcp-browser-validation`이며 `ORDERS_VALIDATION_RUN`도 같은 값이다.
명령은 저장소 루트에서 실행했다. 실제 값 대신 비밀 환경 변수를 인쇄하는 작업은 하지 않았다.

| 실행 | 결과 |
|---|---|
| `$PY ai-services/agentic-loop/main.py --mode mcp --feature student-4 --output-dir "$RUN/agentic-outputs"` | **6 PASS / 0 FAIL, exit 0**; 실제 shared/MCP/Orders DB 경로 |
| `$PY ai-services/agentic-loop/main.py --mode rag --feature student-4 --evidence-file "$RUN/orders-agentic-rag-1.json" --output-dir "$RUN/agentic-outputs"` | 실제 HTTP 5개 성공; **REVIEW_REQUIRED, exit 1**. 답변 정확성은 아직 미판정인 수집 단계 |
| 위 RAG 명령에 `--review-file "$RUN/orders-agentic-rag-review-1.json"` 추가 | 저장된 동일 응답의 근거 검토 **3 PASS / 2 FAIL, exit 1**. 모델 재호출 없음 |
| `AI_ENABLED=false MCP_ENABLED=false RAG_ENABLED=false $PY -m pytest student-4/tests/ -q` | 중간 Python 3.12 실행 **123 passed, 1 skipped (4.25s)** |
| `docker build -t student4-orders:release1-local student-4` | 기본 Python 3.11-slim Dockerfile 실제 build 성공. [이미지 ID](image-id.txt), [DB 미포함 확인](image-contents.log) |
| `ORDERS_VALIDATION_RUN="$RUN" $PY student-4/scripts/local_ci.py` | Python 3.11 **123 passed, 1 skipped (3.72s)**; pip check 성공; root/Student 4 Compose config 성공; 이미지 통합 **13 PASS / 0 FAIL** |
| 아래 최종 Python 3.11 테스트 명령 | 추가한 검토 계약/기존 mode 분기 테스트까지 **128 passed, 0 failed, 1 skipped (5.22s)** |
| `docker compose --env-file "$RUN/compose.env" -f "$RUN/compose.json" restart orders-backend` | AI flag 반영을 위해 검증 backend만 재시작. DB는 재시작하지 않음 |
| `$PY` + requests로 기존 검증 주문의 `/api/order-assistant` 호출 | 기본 enabled 유지: **HTTP 200, source=ollama, 답변 있음** ([결과](ai-default-enabled.json)) |
| `ORDERS_VALIDATION_RUN="$RUN" $PY student-4/scripts/audit.py` | 원본 DB 5개 해시 동일. 다른 프로젝트 및 원본 컨테이너 보존 |
| `git diff --check` | 성공 |

마지막 CI build job에도 AI/MCP/RAG false를 명시한 뒤, 같은 세 환경값을 설정해
root 및 Student 4 `docker compose config --quiet`를 다시 확인했고 둘 다 exit 0이었다.
최종 변경 파일 76개를 실제 키·비밀번호·검증 계정 값과 비교했으며 일치가 없었다.
변경 목록에 DB/runtime 파일이 없는 것과 결과 JSON/보고서/계획서 저장 상태도 확인했다.

최종 로컬 CI 명령(전체 빌드/통합을 반복하지 않고 변경된 판정 테스트만 포함해 pytest 재실행):

```sh
docker run --rm -v /Users/ashley/Desktop/retail-management:/repo:ro \
  -w /repo/student-4 -e AI_ENABLED=false -e MCP_ENABLED=false -e RAG_ENABLED=false \
  -e PYTHONDONTWRITEBYTECODE=1 student4-orders:release1-local sh -c \
  'python -m pip install -r tests/requirements.txt && python -m pip check && python -m pytest tests/ -v -p no:cacheprovider'
```

[최종 CI 원문](ci-python311-final.log), [이전 CI 원문](ci-python311.log),
[이미지 통합 결과](image-integration.json), [원본 DB 보존](preservation-results.json).
pytest의 외부 서비스는 mock, DB는 임시 SQLite다. AI 단위 테스트만 해당 테스트 안에서
명시적으로 enable하고 모델을 mock한다. skip 1개는 opt-in 실제 MCP live로, 변경하지 않은
도구의 동일 검사를 이번 단계에서 재실행하지 않았다. 별도 실제 MCP agentic 6개와 구분한다.

## MCP agentic 실제 결과

기존 Reviews 도구 3개 + Orders 조회 도구 등록 확인, 본인 주문 13/PENDING,
타 고객 직접 MCP 403에 해당하는 forbidden, 잘못된 ID invalid_input,
위조 토큰 unauthorized, Orders backend → 공용 MCP 결과까지 **6개 통과**.
주문/계정 생성이나 변경 없이 실제 서명 인증과 복사 DB를 사용했다.
[실행 로그](student-4-mcp-20260930-131619-459844.txt).

## RAG: 전체 답변과 근거의 대조

검증용 모델은 기존 `qwen2.5:0.5b`, 임베딩 `nomic-embed-text`를 유지했다.
학생별 검색 범위는 student-4다. 새로운 판정은 키워드나 confidence를 정답 기준으로 삼지 않는다.
아래 결과는 Codex가 실제 응답 전체·검색 문장·Orders 소스를 대조한 검토이며 자동 LLM 심사 결과가 아니다.
검토 JSON은 원본 증거의 SHA-256, 답변 인용, 근거 인용, 사례별 이유를 포함한다.
검증 코드는 검토의 결합/완결성과 상태 계약을 검사하며 의미 판정을 대신하지 않는다.

| 질문/주장 | 실제 답변과 검색 근거 대조 | 결과 |
|---|---|---|
| 지원 상태 세 가지 | 답변은 정확히 PENDING / CONFIRMED / CANCELLED. `order-statuses.md`의 exactly three 문장, DB schema CHECK, update API allowed_statuses와 일치. 다른 상태를 추가하지 않음 | **PASS** |
| CONFIRMED 취소 가능 여부 | 답변이 `regardless of its previous status, including CONFIRMED`를 명시. `order-cancellation.md`와 DB cancel_order의 이전 상태 조건 없는 UPDATE에 부합. 취소 불가/환불 보장 주장은 없음 | **PASS** |
| 취소 후 주문·항목 보존 | 답변이 `preserves the order and its items instead of deleting them`을 명시. 문서 및 UPDATE 구현에 부합. 새 이미지 HTTP 검사에서도 CONFIRMED 취소 뒤 주문 GET 200 및 전체 items의 전후 동일을 확인 | **PASS** |
| 관련 질문: CONFIRMED 주문의 정확한 배송일 | 관련 distance 0.2717/High이나 배송일 근거 없음. 답변에 `cannot establish a delivery date`가 있고 날짜·배송 약속을 발명하지는 않음. 하지만 문서 나열을 **success/High**로 반환하고 정보 부족 계약을 지키지 않음. 마지막 Source 목록도 scope 문서와 다르게 기재 | **FAIL** |
| 관련 질문: 취소 후 환불 입금까지 영업일 | 관련 distance 0.317/Medium이나 소요일 근거 없음. 답변이 환불 처리 미구현을 밝히고 기한·금액·자격을 발명하지는 않음. 하지만 **success/Medium**으로 문서를 재현하고 정보 부족 계약을 지키지 않음 | **FAIL** |

긍정 사례도 추가로 붙은 문서 설명 전체를 확인했다. 실제 구현의 상태/취소/조회 범위와
모순되는 배송·환불 정책은 이 5개 응답에서 관찰되지 않았다. 이는 모든 질문의 환각 부재를
보장하지 않는다. 취소/보존 답변이 장황한 문제도 여전하다.

[원본 질문·답변·검색 근거](orders-agentic-rag-1.json),
[주장별 검토 JSON](orders-agentic-rag-review-1.json),
[실제 수집 로그](student-4-rag-20260930-131754-545266.txt),
[검토 실패 로그](student-4-rag-20260930-132248-641437.txt).

기존 날씨 질문의 정보 부족 PASS를 이 관련 질문들에 재사용하지 않았다.
모델을 바꾸거나 질문을 골라 결과를 통과로 만들지 않았고, 다른 학생 공용 pipeline을
수정하지 않았다. **관련 있지만 답할 수 없는 질문을 명확한 정보 부족 상태로 반환하는 후속 수정과
동일 질문 재검증이 남는다.** 모델/prompt 또는 Orders 전용 응답 판정 개선 시 이 실패 증거를 유지해야 한다.

## 빌드·통합의 격리 및 보존

기본 이미지는 Linux ARM64 / Python 3.11.16이며 DB 파일이 포함되지 않았다.
`orders-image-validation` 프로젝트의 frontend/backend/DB 3개가 이미지 코드로 실제 HTTP 통신했다.
외부 포트 없음, Docker 내부 전용 network, RUN/image-data의 새 빈 DB를 사용했다.
원본 DB 복사도 필요 없었고 기존 RUN DB 복사본도 재생성하지 않았다. schema 중 CREATE/PRAGMA만
적용했으며 DROP 또는 init_db.py 시작 명령은 실행하지 않았다.
검사 종료 후 이 3개 임시 컨테이너/network만 정리했고 테스트 데이터는 RUN에 남겼다.

13개 검사는 서비스 연결, 주문 생성/항목·합계, CONFIRMED 변경, SHIPPED 거부, CONFIRMED 취소,
레코드·항목 보존, 없는 주문, AI/MCP/RAG disabled, frontend API 주소 및 shared origin 복귀다.
실제 DB·HTTP 통합이며 공용 AI를 Docker 안에서 실행하지 않았다.

기존 브라우저 검증 stack 및 호스트 shared/MCP/RAG/Ollama는 유지했다. 원본 로컬 DB 3개와
중지된 기존 컨테이너 DB 2개는 해시가 동일하고, 다른 프로젝트의 5001/5002/8080 서비스도
그대로다. 최신 audit에서 MCP 내부 callback은 4개(200 2개, 401 1개, 403 1개)를 확인했다.
Accept 없는 MCP GET probe 406은 도구 호출 결과와 구분하며 Docker→Ollama probe는 200이다.

## 남은 제출·통합 작업

- RAG 관련 미지원 질문 2개의 명확한 정보 부족 처리와 재검증. 기본 8B 모델은 이번에 미검증.
- 원격 GitHub Actions **미실행**. 로컬 Python 3.11 결과를 원격 run URL/Ubuntu 결과로 대체하지 않음.
- 전체 학생 root Compose 기동/전체 UI, Student 1 실제 Reviews DB 기반 agentic 사례는 미실행.
  기존 mode 3개 무수정과 기본 CLI 분기 보존은 단위 테스트로 확인했다.
- 팀 병합 버전의 통합 검증, Release 1 식별 commit/기여 로그 연결, 그룹 PDF·영상·시연 준비.

원격 조회, commit, push, PR 생성, merge는 하지 않았다. 재현 방법은
[ORDERS_AGENTIC.md](../../ORDERS_AGENTIC.md), 진행 상태는 루트 계획서를 참조한다.
