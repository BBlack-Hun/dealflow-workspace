# dealflow ROADMAP — 스프린트별 개발 순서

> 버전: v1.0 (2026-08-18) · 전제: 개발은 macOS, 운영·실기 검증은 Windows PC(카카오톡 로그인 상태).
> 각 스프린트는 개발 에이전트가 그대로 착수할 수 있는 태스크 단위로 쪼갠다. 스프린트 기간은 산정하지 않고 **완료 조건(DoD)** 으로 관리한다.
> 확정 사항: 카카오 공식 API 미채택, **Windows 카카오톡 UI 자동화(텍스트 전송 전용)**. IR 자료는 구글 드라이브 링크. 자동화 #5 발송 채널은 **결정 보류(TODO)**.

---

## Sprint 1 — ★ Windows 발송 에이전트로 카톡 딜소개 문구 자동 발송 "최소 동작"

> 목표: "웹 화면에서 발송 목록을 만들면, Windows 에이전트가 카카오톡 채팅방들에 문구를 자동 전송하고 결과가 화면에 보인다." 이 한 문장이 끝까지 동작하면 성공. 로그인·체크리스트·미팅 등은 전부 다음 스프린트로 미룬다.

| # | 태스크 | 산출물 | 참조 |
|---|---|---|---|
| 1.1 | 프로젝트 골격: FastAPI 앱 팩토리, SQLAlchemy(SQLite WAL)+Alembic, Jinja2, Pretendard 로컬 번들, 공통 레이아웃(사이드바 메뉴 6개·에이전트 상태 배지) | `app/` 골격, `static/fonts/` | TECH_SPEC §2.2~2.3, FEATURE_SPEC §0 |
| 1.2 | 최소 모델: users(임시 단일 사용자 하드코딩 세션), vc_contacts, ir_companies, message_templates, deal_batches(+companies), send_jobs, send_items, agent_devices | `models.py`, Alembic 초기 마이그레이션 | DATA_MODEL §2 |
| 1.3 | 시드 스크립트: 팀 기본 템플릿(오프닝 2종+클로징 3종) + 데모 담당자 3명·기업 3개 | `scripts/seed_demo.py` | DATA_MODEL §2.3 |
| 1.4 | 문구 조합 서비스: 오프닝(첫연락/재연락 자동 선택)+기업 요약 자동 생성(`[분야] \| 한줄소개 \| 매출 N억 \| …` 빈 값 세그먼트 생략)+클로징, `{담당자명}` 등 치환, 3,000자 경고 | `services/message_composer.py` + 단위 테스트 | FEATURE_SPEC §5 조합 규칙 |
| 1.5 | 딜소개 보내기 화면(최소판): 기업 3개 선택 → 대상 담당자 체크 → 담당자별 미리보기 → [발송 목록 생성] → send_job(queued) 생성(문안 스냅샷) | `routers/deals.py`, 템플릿 | FEATURE_SPEC §5 ①~⑥ |
| 1.6 | 에이전트 큐 API: poll(원자적 클레임)/item result/job status/heartbeat, Bearer 토큰 | `routers/agent_api.py` | TECH_SPEC §4 |
| 1.7 | 에이전트 골격 + **MockSender**: 폴링 루프, Sender 인터페이스, 랜덤 지연, 결과 보고 — macOS에서 E2E 왕복 확인 | `agent/main.py`, `sender/base.py`, `sender/mock.py` | TECH_SPEC §3, §5.1 |
| 1.8 | **KakaoDesktopSender**(Windows): 카톡 창 탐색→Ctrl+F 방 검색→방 제목 정확 일치 검증→클립보드 붙여넣기→Enter→창 닫기. selectors.yaml 외부화, 실패 스크린샷 | `sender/kakao_windows.py` | TECH_SPEC §5.2 |
| 1.9 | 발송 진행 화면: 대기/발송중/성공/실패 카운터(2초 폴링), 건별 로그, [중단], 실패 [재시도] | 템플릿+JS | FEATURE_SPEC §5 ⑦~⑧ |
| 1.10 | **Windows 실기 검증**: 실제 카톡 테스트 방 3개에 장문(URL 포함) 발송, 방 이름 불일치 시 skip 확인, ESC/FAILSAFE 중단 확인, 감독 오버레이 | 검증 체크리스트 결과 | TECH_SPEC §3, §5.5 |

**DoD**: Windows PC에서 `run_server.bat`+`run_agent.bat` 실행 → 브라우저에서 기업 3개·담당자 3명 선택·발송 → 실제 카톡방 3곳에 치환된 문구 도착, 화면에 3/3 성공 표시. 방 이름이 틀린 1건은 오발송 없이 failed 처리.

---

## Sprint 2 — 실데이터 ·  핵심 화면 (내 투자사 / 딜 기업 DB / IR 전달)

| # | 태스크 | 참조 |
|---|---|---|
| 2.1 | 구글시트 임포트: `scripts/import_sheets.py` (시트 A→vc_contacts+contact_activities, 시트 B→ir_companies, 이름/직함 분리 파싱, 멱등 upsert, 스킵 리포트) + 관리자 화면 [시트 임포트] | DATA_MODEL §6 |
| 2.2 | 내 투자사 화면: **7컬럼 고정 한 페이지 레이아웃(가로 스크롤 0)**, 우측 상세 패널, 활동 이력 타임라인 | FEATURE_SPEC §3 |
| 2.3 | **공통 필터 드롭다운 컴포넌트**(고유값+건수, 다중 선택 AND/OR, 칩, URL 쿼리 유지) → 내 투자사·딜 기업 DB 적용 | FEATURE_SPEC §8 |
| 2.4 | 딜 기업 DB 화면: 시트 B 전 필드 CRUD, 딜 요약문 편집기(자동 생성 캐시+수동 우선), **ir_drive_url 등록**(URL 검증·공유 권한 안내), RBAC(편집=admin+담당자) | FEATURE_SPEC §4 |
| 2.5 | [방 연결 확인]: verify_room 에이전트 명령 + 배지(●/○/⚠), 발송 대상 선택 시 경고 연동 | TECH_SPEC §5.3 |
| 2.6 | IR·미팅 관리(요청 트래커 절반): IR 요청 CRUD, D+N 기한 배지, [IR 전달] 모달(문구 자동 생성+**드라이브 링크 삽입**)→ir_delivery 잡 발송, 전달완료 전이 | FEATURE_SPEC §2 플로우 A |
| 2.7 | Windows 실기 검증: 임포트된 실데이터 일부(테스트 동의 방)로 딜소개+IR 전달 발송, 링크 클릭 동작 확인 | |

**DoD**: 실제 시트 CSV 2개가 서비스에 들어오고, 1280px 화면에서 내 투자사 표가 가로 스크롤 없이 필터와 함께 동작하며, IR 요청 1건을 [IR 전달] 버튼으로 링크 포함 카톡 전송까지 완료.

---

## Sprint 3 — 후속 캐던스(시퀀스) + 정기 회차 스케줄러

| # | 태스크 | 참조 |
|---|---|---|
| 3.1 | send_sequences·schedule_rules 모델 + 상태 머신(§3.6), Day1 성공 시 시퀀스 생성·리마인드 예약(6~7 창 랜덤, 영업일 보정) | DATA_MODEL §2.7-1/2, §3.6 |
| 3.2 | APScheduler: 매일 09:00 due 산출→대기 목록+오늘 할 일 항목, **매월 1·3번째 수요일 회차 초안 생성**(effective_from 2026-09-01, 규칙은 schedule_rules에서 로드 — 하드코딩 금지), 잡 타임아웃 감시 | TECH_SPEC §2.2 |
| 3.3 | 후속 단계 문안 조합(리마인드·미팅요청: 짧은 오프닝+단계 클로징) + [후속 발송 시작] 일괄 발송 | FEATURE_SPEC §5 캐던스 |
| 3.4 | 시퀀스 관리 UI: '진행 중 시퀀스' 표(단계·다음 예약일·상태), [응답 옴]/[중단]/[재개], IR 요청·미팅 생성 시 자동 중단 훅 | FEATURE_SPEC §5 하단 탭 |
| 3.5 | 미팅 파이프라인: meetings CRUD·상태 전이, 완료 시 D+10 notifications 예약(발생 로직만) | FEATURE_SPEC §2 플로우 B |
| 3.6 | **알림 채널 어댑터**: NotificationChannel 인터페이스 + InAppChannel(배너·오늘 할 일 항목). **TODO(결정 보류): SMS vs 카톡 채널 확정 후 SmsChannel/KakaoChannel 장착** | TECH_SPEC §6.1 |
| 3.7 | Windows 실기 검증: 시퀀스 예약→도래→[후속 발송 시작] 전체 사이클(시계 조작 테스트 포함) | |

**DoD**: Day1 발송 → (시간 조작) 6일 후 리마인드가 대기 목록에 뜨고 일괄 발송됨 → [응답 옴] 클릭 시 미팅요청 단계가 취소됨. 9월 첫째 수요일에 회차 초안이 자동 생성됨.

---

## Sprint 4 — 로그인·오늘 할 일·관리자·운영 마감

| # | 태스크 | 참조 |
|---|---|---|
| 4.1 | 휴대폰 OTP 로그인: auth_otps/sessions, CoolSMS 연동(ConsoleProvider로 개발), 화이트리스트, 잠금 정책, 세션 쿠키 | TECH_SPEC §7.1 |
| 4.2 | RBAC 마감: user 본인 필터 전면 적용, admin 라우터 분리(집계·마스터·계정만), 원문 403 테스트 | TECH_SPEC §7.2 |
| 4.3 | 오늘 할 일: 루틴 CRUD·요일 자동 생성·이월·주간 요약 카드, 후속/회차/알림 자동 항목 통합 | FEATURE_SPEC §1 |
| 4.4 | 팀 현황(관리자): weekly_stats 주간 집계 잡, 사용자별 표+팀 합계, CSV/Markdown 내보내기 | FEATURE_SPEC §6 |
| 4.5 | 퇴사 삭제: 2단계 확인→하드 삭제+익명화 트랜잭션(+연락처 CSV 내보내기 옵션), secure_delete·VACUUM | TECH_SPEC §7.3, DATA_MODEL §5 |
| 4.6 | 운영 패키징: run_server.bat/run_agent.bat, 일일 DB 백업, .env 정리, 온보딩 문서(카톡 로그인·발신번호 등록·드라이브 권한 체크리스트) | TECH_SPEC §9 |
| 4.7 | 리스크 가드 마감: 발송 상한·야간 경고·반자동 모드 스위치·최초 실행 리스크 고지 화면 | TECH_SPEC §1.5, §8 |

**DoD**: 7명 실사용자 등록 → 휴대폰 로그인 → 각자 본인 데이터만 보임 → 관리자는 집계·마스터만 → 테스트 계정 삭제 시 개인 데이터가 DB에서 사라지고 주간 집계는 "퇴사자"로 남음.

---

## 이후 백로그 (우선순위 낮음 / 결정 대기)

- **[결정 대기] 자동화 #5 발송 채널**: SMS(CoolSMS) vs 카톡(에이전트 경유 "나와의 채팅") — 채널 확정 시 어댑터 1개 구현으로 완료.
- 발송 진행 SSE 실시간화(현재 2초 폴링), 시퀀스 성과 리포트(단계별 응답률), 카카오 알림톡 채널(비즈니스 채널 개설 시), Postgres 이전(Alembic 경로 확보됨), 이메일 발송 자동화, PyInstaller 단일 exe 패키징.

## 스프린트 공통 원칙

1. 모든 스프린트에 **Windows 실기 검증 태스크 포함** — MockSender 통과 ≠ 완료.
2. 카톡 발송 관련 수치(지연·상한·창 범위)는 코드 상수 금지, `agent/config.yaml`·`schedule_rules`로.
3. 발송 문안은 항상 스냅샷 저장(이력 불변) — 디버깅과 오발송 분쟁 대비의 기준.
4. 오발송 방지가 성능보다 우선: 방 제목 정확 일치 검증 실패 시 무조건 skip.
