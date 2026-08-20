# dealflow

VC 투자영업(딜소싱) 워크스페이스. 웹에서 딜소개 발송 목록을 만들면
**사용자 PC의 에이전트가 카카오톡으로 자동 전송**한다.

```
   서버 (도커)                        각 팀원 PC
 ┌────────────────┐                ┌──────────────┐
 │ 웹앱 · DB · 큐  │◀── HTTP 폴링 ──│ 발송 에이전트  │──▶ 카카오톡
 │ 무엇을 보낼지    │                │ 실제 전송      │
 └────────────────┘                └──────────────┘
```

> 카톡방은 각자 계정에 있으므로 발송은 반드시 **본인 PC**에서 실행된다.
> 서버는 문구 생성·대상 선정·이력 관리를 담당한다.

---

## 빠른 시작 (개발/데모)

```bash
docker compose up -d                    # 웹앱 :8889
open http://localhost:8889

docker compose --profile demo up -d     # (선택) 가짜 발송기까지 — 실발송 테스트 중에는 켜지 말 것
```

컨테이너 기동 시 마이그레이션 + 부트스트랩(팀 기본 문구 + 관리자 계정)이 자동 적용된다.
가상 담당자·기업까지 넣어 둘러보려면 `DEALFLOW_SEED_DEMO=1` 로 띄운다.
`딜소개 보내기`에서 기업·담당자를 고르고 **발송 목록 생성**을 누르면 큐에 등록되고,
연결된 에이전트가 처리해 성공/실패가 화면에 반영된다.

로그인은 **휴대폰번호(숫자만) + 비밀번호**다. 팀원 계정은 관리자가 만든다.

```bash
docker exec dealflow-public-web-1 python scripts/add_user.py --list
docker exec dealflow-public-web-1 python scripts/add_user.py --name 홍길동 --phone 010-1234-5678
```

계정마다 에이전트 토큰이 따로 발급된다. **사용자 1명 = 에이전트 1대**가 원칙이라
같은 토큰을 두 PC 에 넣으면 발송 잡이 어느 기기로 갈지 예측할 수 없다.

개발 중 쌓인 가상 데이터·테스트 발송 이력은 이걸로 지운다(기본은 미리보기).

```bash
docker exec dealflow-public-web-1 python scripts/purge_demo.py         # 무엇이 지워지는지
docker exec dealflow-public-web-1 python scripts/purge_demo.py --yes   # 실행
```

### 테스트

```bash
docker exec dealflow-public-web-1 python -m pytest -q
```

---

## 구글시트 임포트

시트를 **CSV로 내려받아**(파일 → 다운로드 → 쉼표로 구분된 값) 넣는다.
시트 1개 = 사용자 1명이므로 `--user-id` 가 필수다.

```bash
# 미리보기(DB 변경 없음) — 스킵 리포트를 먼저 확인
docker exec dealflow-public-web-1 python scripts/import_sheets.py \
  --sheet-a /tmp/a.csv --user-id 1 --dry-run

# 실제 반영 (재실행해도 중복이 생기지 않음)
docker exec dealflow-public-web-1 python scripts/import_sheets.py \
  --sheet-a /tmp/a.csv --sheet-b /tmp/b.csv --user-id 1
```

- 시트 A: 담당자 + **월별 3열 세트(딜소개/IR 요청/미팅)** → `contact_activities` 행으로 정규화.
  달이 갈수록 열이 늘어나는 시트의 한계를 여기서 푼다. 헤더 행·컬럼 위치는 자동 탐지한다.
- 시트 B: IR 기업현황 → 딜 기업 DB.
- 카톡방 이름은 `이름 + 직함 + 투자사 + 고정 접미사` 로 자동 생성되며,
  **이미 값이 있으면 덮어쓰지 않는다**(수기로 맞춘 방 제목을 되돌리면 발송이 skip 된다).
- 자세한 구조 근거: [docs/SHEET_FINDINGS.md](docs/SHEET_FINDINGS.md)

---

## 투자사 현황 업로드 · 엑셀 내려받기

팀원이 각자 관리하는 '투자사 관리 현황' 시트를 화면에서 직접 올린다.
`내 투자사 → 현황 업로드` 에서 `.xlsx` 또는 `.csv` 를 고르면
**미리보기**로 무엇이 생기고 바뀌는지 먼저 보여주고, 확인한 뒤에만 반영한다
(담당자 명단은 곧 발송 대상이라 잘못 덮으면 그대로 오발송이 된다).

- 읽는 기준은 **헤더 이름**이다 — `이름`·`투자사명` 이 있는 행을 찾는다. 컬럼 순서는 상관없다.
- 엑셀이면 시트를 고를 수 있다(구글 시트를 내려받으면 여러 장이 딸려 온다).
- 이미 확인해 둔 카톡방 이름은 **덮어쓰지 않는다**.
- 내려받은 표를 그대로 되올리면 막는다 — 내보내기의 `IR 요청(누적)` 류 컬럼을
  임포트 파서가 월별 활동으로 읽어 이력이 뻥튀기되기 때문이다.

표가 있는 화면에는 **엑셀 내려받기**가 있다 (`내 투자사` · `딜 기업 DB` · `발송 진행`).
머리행 고정 + 자동 필터가 걸린 채로 나온다.

---

## 환경변수

| 이름 | 기본값 | 용도 |
|---|---|---|
| `DEALFLOW_TEST_ROOM` | (없음) | 값이 있으면 **모든 발송이 이 방 하나로만** 나간다(오발송 방지) |
| `DEALFLOW_ROOM_SUFFIX` | `Deal 공유 우리브이씨 Asset` | 카톡방 이름 끝에 붙는 고정 문구. 조직마다 다르므로 `.env` 로 실제 값을 준다 |
| `DEALFLOW_SEED_DEMO` | `0` | `1` 이면 가상 담당자·기업까지 넣는다(둘러보기용) |
| `DEALFLOW_INITIAL_PASSWORD` | `dealflow123` | 새 계정의 초기 비밀번호(첫 로그인 후 변경 요구) |

`.env` 는 `.gitignore` 대상이다 — 실제 값은 저장소에 올라가지 않는다.

---

## 회차 리허설

회차 당일에 처음 해 보면 늦다. 전날 한 번 끝까지 걸어 본다.

```bash
docker exec dealflow-public-web-1 python scripts/rehearsal.py --check      # 지금 상태
docker exec dealflow-public-web-1 python scripts/rehearsal.py --setup      # 리허설 대상 만들기
docker exec dealflow-public-web-1 python scripts/rehearsal.py --teardown   # 흔적 지우기
```

`--setup` 은 리허설용 담당자 1명과 기업 2개를 만든다. 담당자의 카톡방은
`DEALFLOW_TEST_ROOM`(대개 '나와의 채팅')이라 **발송 프로그램이 실제로 움직여도
나에게만** 온다. `DEALFLOW_TEST_ROOM` 이 비어 있으면 아예 실행되지 않는다.

걸어 볼 순서:

1. `회차 준비 점검` 에서 막힌 것이 없는지
2. `딜 제안 관리` 에서 리허설 기업·담당자를 골라 발송
3. `발송 진행` 에서 성공 확인 — **카톡에 실제로 도착하는지**
4. `후속 관리` 에 리마인드가 잡혔는지
5. `IR·미팅 관리` 에서 요청 기록 → **[자료 보내기]** → 요청이 닫히는지
6. 미팅 등록 → 완료 → 결과 문의 날짜가 잡히는지

같은 흐름을 코드로도 검사한다: `tests/test_end_to_end.py`.
화면은 따로 테스트하지만 **이어지는 지점**에서 깨진 적이 여러 번 있어서다.

---

## 방 연결 확인

카톡방 제목이 실제와 한 글자라도 다르면 그 담당자에게는 **발송이 되지 않는다**(오발송은 없다).
실운영 전 [내 투자사] → **[방 연결 확인]** 으로 전원 대조한다.

- 서버가 확인 잡(`kind=verify_room`)을 큐에 넣고, 에이전트가 **검색만** 해서 결과를 돌려준다(전송 없음).
- 결과는 배지로: `● 확인됨` / `○ 미확인` / `⚠ 방 없음 · 복수 매칭`.
- 확인 잡은 **최신 에이전트만** 받아간다. 예전에 내려받은 에이전트를 쓰고 있다면
  [에이전트 설치](/setup)에서 **다시 받아** 실행해야 확인이 동작한다.

---

## 발송 방식 (Sender)

같은 큐·재시도·이력 경로를 공유하며 구현체만 교체된다.

| sender | 대상 | 상태 |
|---|---|---|
| `kakao_mac` | macOS 카카오톡 | ✅ 실발송 검증 완료 |
| `kakao_windows` | Windows 카카오톡 | ✅ 실발송 검증 완료 |
| `telegram` | 운영자 본인 텔레그램 | ✅ 문구 실물 확인용 |
| `mock` | 가짜(로그만) | ✅ 개발/도커 기본값 |

### macOS 에이전트 실행

접근성 권한 필요: 시스템 설정 → 개인정보 보호 및 보안 → **손쉬운 사용**

```bash
python3 -m venv .venv-agent
.venv-agent/bin/pip install requests pyyaml pyobjc-framework-Quartz

DEALFLOW_SENDER=kakao_mac \
DEALFLOW_SERVER_URL=http://127.0.0.1:8889 \
DEALFLOW_AGENT_TOKEN=agt_demo_token_sprint1 \
.venv-agent/bin/python -m agent.main --config agent/config.yaml
```


> ⚠️ **에이전트 코드를 고쳤으면 반드시 `docker compose up -d --build`** 로 이미지를 다시 만드세요.
> `/download/agent` 는 **컨테이너 안의 파일**을 묶어 내려주므로, 이미지가 낡으면
> 고치기 전 코드가 담긴 zip 이 배포됩니다(실제로 겪은 문제).
> 받은 zip 의 `BUILD_INFO.txt` 에 파일 지문이 들어 있으니 서버와 대조할 수 있습니다.

### Windows 에이전트 배포

`dist/dealflow-agent-windows.zip` 를 Windows PC로 복사 →
`setup.bat` (최초 1회) → `run_agent.bat`.
자세한 절차와 체크리스트는 [docs/WINDOWS_TEST.md](docs/WINDOWS_TEST.md).

---

## 오발송 방지 (양보 불가)

1. 방을 연 뒤 **창 제목이 대상과 정확히 일치**해야만 전송한다. 불일치면 전송하지 않는다.
2. 본문을 넣은 뒤 **실제로 입력됐는지 확인**하고 전송한다.
3. 전송 후 **입력창이 비워졌는지 확인**한다. (거짓 성공 보고 방지)
4. 발송 간격·상한은 코드가 아닌 `agent/config.yaml` 로 관리한다.

---

## 문서

| 파일 | 내용 |
|---|---|
| [docs/PRD.md](docs/PRD.md) | 제품 요구사항 |
| [docs/FEATURE_SPEC.md](docs/FEATURE_SPEC.md) | 화면·기능 상세 |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | 엔티티·상태 전이 |
| [docs/TECH_SPEC.md](docs/TECH_SPEC.md) | 아키텍처·카카오 자동화 판정 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 스프린트 계획 |
| [docs/SHEET_FINDINGS.md](docs/SHEET_FINDINGS.md) | 실제 구글시트 분석 결과 |
| [docs/WINDOWS_TEST.md](docs/WINDOWS_TEST.md) | Windows 발송 테스트 절차 |
| [docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md) | 브랜치·커밋·PR 규칙 |

---

## 진행 상황

**Sprint 1 완료** — 딜소개 문구 조합 → 발송 목록 생성 → 에이전트 전송 → 결과 표시

- [x] 웹앱 골격, 발송 큐 API(사용자별 격리), 발송 진행 화면
- [x] 문구 조합 엔진(오프닝/기업요약/클로징, 존칭 정규화)
- [x] 투자 성향 매칭(분야·단계·라운드) 발송 전 경고
- [x] macOS 카카오톡 실발송 검증
- [x] Windows 카카오톡 실기 검증

**Sprint 2 진행 중** — 실데이터 · 핵심 화면

- [x] 구글시트 임포트(시트 A/B CSV, 월별 3열 세트 → 활동 이력 정규화, 멱등 upsert)
- [x] 내 투자사 화면 — 7컬럼 한 페이지 표(가로 스크롤 0) + 우측 상세·활동 타임라인 + CRUD
- [x] 공통 컬럼 필터 드롭다운(고유값+건수, 다중 선택, 칩, URL 유지)
- [x] 방 연결 확인(verify_room 잡 + ●/○/⚠ 배지)
- [x] 개발용 사용자 전환(기기별 계정 분리 테스트용 — 인증 아님)
- [ ] 딜 기업 DB 화면(2.4) · IR·미팅 관리(2.6)
- [ ] Windows 실기 검증(2.7): 실데이터 일부로 방 연결 확인 + 딜소개 발송

- [ ] Sprint 3: 후속 캐던스(D+6/7, D+11/14), 월 2회 정기 회차 스케줄러
- [ ] Sprint 4: 로그인(휴대폰번호 + 비밀번호), RBAC, 팀 현황, 퇴사 삭제

---

## 주의

카카오 운영정책상 자동화는 계정 제재 소지가 있다.
발송 간격·상한을 임의로 낮추지 말고, 테스트는 반드시 **나와의 채팅** 등 안전한 방으로 한다.

---

## 데모 데이터 안내

이 저장소의 담당자·기업 정보(`scripts/bootstrap.py`, 테스트, 문서 예시)는 **모두 가상 데이터**다.
실제 투자사·포트폴리오 기업 정보는 코드에 포함하지 않으며 DB에만 존재한다
(`.env`, `*.db` 는 `.gitignore` 로 제외).
