# Orders MCP 브라우저·Docker 통합 검증

- 실행일: 2026-09-29 Australia/Sydney (최종 확인 18:33 AEST)
- 브랜치: `taehyoun/release1-orders`
- 기준 HEAD: `65194764d70136097bf1ddf1d3ef9e1500d5d9e7` + 미커밋 구현
- Python: 호스트 3.12.10, Docker 3.11; MCP SDK 1.30.0
- 브라우저: Playwright 1.63.0 + 실제 설치된 Chrome 154.0.8037.58, 독립 headless 세션
- 결과: 최종 브라우저 실행 **23/23 PASS**. 이는 준비 상태 확인을 포함한 검사 수이며 별개의 23개 단위 테스트라는 의미는 아니다.

## 재개 지점과 데이터 보존

재개 당시 RUN에는 `prepare.py`만 있었다. `runtime.json`, snapshot, 작업용 DB,
`compose.json`, 실행 로그와 검증 이미지/컨테이너는 아직 없었다. 기존 준비 단계를
중복 실행하거나 runtime을 삭제하지 않고 누락된 준비부터 수행했다.

RUN: `/private/tmp/orders-mcp-browser-validation` (디렉터리 0700).
`runtime.json`, `compose.env`, `login.txt`는 0600이며 저장소 밖에만 있다.
비밀키·로그인 비밀번호·세션 쿠키 값·Bearer 토큰은 결과나 Git에 포함하지 않았다.

Orders와 Customer의 **중지된 기존 컨테이너 DB**를 읽어 snapshot을 만들고,
그 snapshot에서 별도의 작업 DB를 생성했다. 상품 DB는 로컬 파일에서 SQLite backup으로
복사했다. 시작 당시 복사본 행 수는 Orders 12, Customer 14, Products 10이었다.
원본 컨테이너를 시작하거나 원본 DB를 초기화하지 않았다.

검증용 DB 서버는 `serve_db.py`에서 DB 경로만 복사본으로 지정하고 API를 실행한다.
`init_db.py`, DROP schema, `down -v`는 사용하지 않았다. 검증용 계정과 주문만
작업 DB에 추가했다. 원본 로컬 DB 3개 및 중지 컨테이너 DB 2개의 전후 SHA-256은
모두 일치했다. [보존 결과](preservation-results.json) 참조.

## 실제 실행 구조

- 별도 Compose 프로젝트: `orders-mcp-validation`, 기존 프로젝트/컨테이너는 유지.
- 검증 이미지: `orders-mcp-validation:local`. 의존성만 빌드하고 코드 폴더는 읽기 전용 mount.
  원본 DB나 비밀키를 이미지에 COPY하지 않았다.
- Docker: Orders frontend 3004, backend 5004, DB 6004;
  Customer backend 5003, DB 6003; Product backend 5102, DB 6002.
- 호스트: shared 5000, MCP 8100, 기존 Ollama 11434.
- 다른 프로젝트가 이미 사용하는 5001·5002·8080은 변경하지 않았다.
- 컨테이너 포트는 localhost에만 게시했다. MCP는 Docker에서 접근하도록 호스트에서
  `0.0.0.0:8100`으로 실행하며, shared는 `127.0.0.1:5000`이다.

브라우저의 실제 요청은 `3004 → 5000`에서 세션 쿠키로 토큰을 발급받고,
`3004 → 5004`로 Bearer 토큰을 전달했다. 이후 Orders 컨테이너가
`http://host.docker.internal:8100/mcp`에 연결하고, 호스트 MCP가
`http://localhost:5004/api/internal/mcp/orders/<id>/status`를 호출했다.
내부 조회 API의 200/403 응답이 Docker 로그에 기록됐다.

Docker 내부에서 MCP HTTP 연결도 확인했다. 단순 GET은 MCP Accept 헤더가 없어
406을 반환했으나 이는 연결 실패가 아니다. 실제 SDK의 도구 호출은 200으로 성공했다.
Docker에서 호스트 Ollama `/api/tags`는 200이었다.

## 완료한 검증

| 항목 | 실제 결과 |
|---|---|
| 홈페이지 → 로그인 → My Orders | 실제 Customer 비밀번호 검증, shared 로그인 성공, Orders 화면 이동 |
| 세션·CORS | HttpOnly 세션 쿠키 존재; 토큰 응답 ACAO `http://localhost:3004`, credentials `true`; Chrome에서 응답 접근 성공 |
| 정상 MCP 조회 | 고객 15의 주문 13: 200, 화면 `Order #13: PENDING · Source: MCP (get_order_status)` |
| 타 고객 주문 | 고객 15가 고객 16의 주문 14 조회: 403, 주문 상태 노출 없음 |
| 인증 위조 | 위조 Bearer와 임의 고객 헤더: 401 |
| 실제 토큰 만료 | 시간/서명 mock 없이 123초 이상 경과 후 재사용: 401, `Authentication expired. Please try again.` |
| 만료 후 재시도 | 화면 버튼이 새 토큰 발급 후 200으로 성공 |
| MCP 장애 | 이번 검증용 MCP 프로세스만 중단: 503과 `Shared MCP server is unavailable.` 화면 표시 |
| MCP 복구 | 같은 설정·키로 MCP 재시작 후 200 |
| 기존 주문 상세 | 주문 13 상세 modal 정상 |
| 기존 주문 생성 | 실제 shared Shop → Order Now → Place Order, 주문 15 생성 |
| 직원 상태 변경 | 실제 직원 로그인 → Orders admin → 주문 15 Confirm 성공 |
| 고객 취소 | Orders 화면에서 주문 15 취소 성공; 테스트 복사본의 주문만 변경 |
| 관리자 복귀 | `http://localhost:3004/admin` → `http://localhost:5000/staff_dashboard` 성공 |
| 기존 AI | 실제 `qwen2.5:0.5b` 모델 응답; HTTP 200, `source: ollama` (mock/fallback 아님) |
| 회귀 단위 테스트 | `MCP_ENABLED=false .../python -m pytest student-4/tests/ -q`: **47 passed, 1 skipped, 4.76s** |

[브라우저 결과 JSON](browser-results.json), [정상 화면](mcp-success.png),
[장애 화면](mcp-outage.png).

## 실패·수정·검증 한계

1. 최초 데이터 준비 시 실제 Student 3 로그인 응답이 flat 형식임을 확인했다.
   검증 스크립트는 중첩 형식을 가정해 KeyError로 중단됐다. shared의 `/login`도
   같은 가정이 있어 실제 로그인이 막힐 수 있었다. shared가 flat/nested 응답을
   모두 받고 양의 정수 customer_id를 검사하도록 최소 수정했다.
   두 형식에 대한 토큰 발급 회귀 테스트를 추가했다. 생성했던 계정은 재사용했다.
2. 첫 Chrome 시도는 외부 리소스가 포함된 페이지 이동 중 timeout으로 중단됐다.
   이 날짜의 실행 스크립트는 localhost/127.0.0.1 외의 모든 브라우저 URL을 차단했다.
   2026-09-30 재검증에서는 외부 image/font/stylesheet만 차단하는 명시적 정책으로 좁혔다.
   로그인·DB·MCP·Ollama 요청에는 mock이나 브라우저 응답 대체를 사용하지 않았다.
3. 원본 DB를 직접 변경하는 시연, 기본 root Compose 전체 기동, 다른 학생 전체 화면,
   GitHub CI 실행, 공용 agentic loop, RAG는 이번에 실행하지 않았다.
   기존 Release 0 CRUD·AI 경로의 전체 인증 개편도 수행하지 않았다.
4. 새 원본 Dockerfile 전체 build 검증이 아니라 의존성 전용 검증 이미지와 현재 코드 mount로
   실제 네트워크/브라우저 통합을 확인했다.

초기 실패 기록은 RUN의 `browser-attempt-*.json`에 남아 있다. 최종 실행에는 실패가 없다.

## 직접 확인할 URL과 순서

검증 서비스는 실행 상태로 남겨 두었다. 컴퓨터 재시작/임시 디렉터리 정리 전까지의
로컬 검증 환경이며 production 기동 구성으로 간주하지 않는다.

1. `/private/tmp/orders-mcp-browser-validation/login.txt`에서 테스트 고객 로그인 정보를
   로컬로 확인한다. 이 파일을 Git에 추가하거나 공유하지 않는다.
2. `http://localhost:5000/` → **Log in** → 테스트 고객 로그인 → **My Orders**.
   Orders 주소는 `http://localhost:3004/?customer_id=15`다.
3. **Check order status**에 `13` → **Check with MCP**:
   `PENDING`, `Source: MCP (get_order_status)` 기대.
4. `14` 조회: 접근 거절 기대. `15`는 이번 검증에서 취소했으므로 `CANCELLED` 기대.
5. AI Order Assistant에서 주문 `13`과 상태 질문 → **Ask AI**:
   정상 모델 응답 시 화면의 응답 출처가 AI로 표시된다.
6. 별도 브라우저/시크릿 창에서 `http://localhost:5000/staff-login`으로 직원 로그인
   (`login.txt`의 직원 항목). **View all orders** → **Staff Dashboard**:
   origin 5000의 실제 dashboard로 돌아가야 한다.

로그인 정보·runtime·snapshot을 다시 생성할 필요가 없다. `prepare.py`를 재실행하지 않는다.
검증 환경 상태 확인/중지는 아래 명령으로 **검증 프로젝트에만** 적용한다.

```sh
docker compose --env-file /private/tmp/orders-mcp-browser-validation/compose.env -f /private/tmp/orders-mcp-browser-validation/compose.json ps
# 중지할 때 (데이터/컨테이너 삭제 없음)
docker compose --env-file /private/tmp/orders-mcp-browser-validation/compose.env -f /private/tmp/orders-mcp-browser-validation/compose.json stop
/private/tmp/retail-orders-mcp-venv/bin/python /private/tmp/orders-mcp-browser-validation/host_servers.py shared stop
/private/tmp/retail-orders-mcp-venv/bin/python /private/tmp/orders-mcp-browser-validation/host_servers.py mcp stop
```

중지 후에는 같은 Compose 파일로 `up -d`하고, 빈 포트를 확인한 후 `host_servers.py shared`,
`host_servers.py mcp`로 재사용할 수 있다. `docker compose config`의 전체 출력은 비밀키가
치환될 수 있으므로 필요하면 `config --quiet`만 사용한다.
