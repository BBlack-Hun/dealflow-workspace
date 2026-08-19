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
docker compose up -d          # 웹앱 :8889 + mock 에이전트
open http://localhost:8889
```

컨테이너 기동 시 마이그레이션 + 데모 시드가 자동 적용된다.
`딜소개 보내기`에서 기업·담당자를 고르고 **발송 목록 생성**을 누르면
mock 에이전트가 처리해 성공/실패가 화면에 반영된다.

### 테스트

```bash
docker exec dealflow-web-1 python -m pytest -q
```

---

## 발송 방식 (Sender)

같은 큐·재시도·이력 경로를 공유하며 구현체만 교체된다.

| sender | 대상 | 상태 |
|---|---|---|
| `kakao_mac` | macOS 카카오톡 | ✅ 실발송 검증 완료 |
| `kakao_windows` | Windows 카카오톡 | ⏳ 실기 검증 필요 |
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

---

## 진행 상황

**Sprint 1 완료** — 딜소개 문구 조합 → 발송 목록 생성 → 에이전트 전송 → 결과 표시

- [x] 웹앱 골격, 발송 큐 API(사용자별 격리), 발송 진행 화면
- [x] 문구 조합 엔진(오프닝/기업요약/클로징, 존칭 정규화)
- [x] 투자 성향 매칭(분야·단계·라운드) 발송 전 경고
- [x] macOS 카카오톡 실발송 검증
- [ ] Windows 카카오톡 실기 검증
- [ ] **Sprint 2**: 구글시트 임포트(126명), 방 연결 확인, 한 페이지 표, 필터, IR 전달
- [ ] Sprint 3: 후속 캐던스(D+6/7, D+11/14), 월 2회 정기 회차 스케줄러
- [ ] Sprint 4: 휴대폰 로그인, RBAC, 팀 현황, 퇴사 삭제

---

## 주의

카카오 운영정책상 자동화는 계정 제재 소지가 있다.
발송 간격·상한을 임의로 낮추지 말고, 테스트는 반드시 **나와의 채팅** 등 안전한 방으로 한다.

---

## 데모 데이터 안내

이 저장소의 담당자·기업 정보(`scripts/seed_demo.py`, 테스트, 문서 예시)는 **모두 가상 데이터**다.
실제 투자사·포트폴리오 기업 정보는 코드에 포함하지 않으며 DB에만 존재한다
(`.env`, `*.db` 는 `.gitignore` 로 제외).
