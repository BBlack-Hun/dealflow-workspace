# dealflow TECH_SPEC — 카카오 자동화 판정·아키텍처·보안

> 버전: v1.0 (2026-08-18) · 상위: `docs/PRD.md` · 기능: `docs/FEATURE_SPEC.md` · 데이터: `docs/DATA_MODEL.md`
> §1~§2는 2026-08 시점 웹 조사(카카오디벨로퍼스·카카오비즈니스 가이드·데브톡·발송대행사 문서)에 근거한 판정이다.

---

## 1. ★ 카카오톡 발송/파일 첨부 자동화 — 조사 결과와 확정 판정

### 1.1 요구사항 재확인

우리가 필요한 것은 다음이다.

- (A) **기존에 이미 존재하는 임의의 1:1 카톡 채팅방**(투자사 담당자)에 **자유 문구**(사전 승인 없는 딜소개 텍스트)를 보낸다. 후속 캐던스(리마인드·미팅요청)와 IR 전달 메시지도 동일 메커니즘.
- (B) IR 자료 전달 — **확정: 파일 첨부 자동화는 하지 않는다.** IR 자료는 사용자가 구글 드라이브에 수기 업로드하고 링크를 서비스에 등록, 발송 메시지 **본문에 드라이브 링크 텍스트를 포함**해 전송한다. 따라서 자동화 요구는 (A) 텍스트 전송 하나로 수렴한다(에이전트 단순화·안정성 향상).

### 1.2 카카오 공식 경로 조사 결과 (전부 요구사항 미충족 → **미채택**)

| 경로 | 조사 결과 | (A) 자유 문구 | (B) 파일 첨부 | 미채택 사유 |
|---|---|---|---|---|
| **알림톡** (비즈메시지) | 사업자 비즈니스 채널 필수. **템플릿 사전 심사·승인**된 정보성 메시지만 발송 가능. 이미지도 템플릿에 고정된 1장만 | ✕ (승인 템플릿 고정) | ✕ (문서 파일 첨부 개념 자체가 없음) | 매 회차 바뀌는 딜소개 자유 문구가 원천적으로 불가. 딜소개는 광고성으로 분류될 소지도 큼(알림톡은 정보성 한정) |
| **친구톡/브랜드 메시지** (비즈메시지) | 수신자가 **우리 카카오 채널을 친구 추가한 경우에만** 발송 가능. 광고성 메시지 규제: (광고) 표기·수신거부 안내 필수, 야간(20:50~익일 08:00) 발송 금지. 건당 과금 | △ (자유 문구는 되나 위 제약) | ✕ (이미지/캐러셀만, 문서 첨부 불가) | 투자사 담당자들에게 채널 친구 추가를 요구해야 하고, 기존 1:1 대화방이 아닌 채널방으로 감. 파일 전달 불가 |
| **카카오 로그인 메시지 API** — 나에게 보내기 | 검수 없이 사용 가능, 발송 제한 사실상 없음. 단 **본인 계정에게만** | ✕ (수신자가 본인뿐) | ✕ | 발송 대상이 될 수 없음 (내부 알림용으로만 활용 가치, 그마저 SMS로 대체) |
| **카카오 로그인 메시지 API** — 친구에게 보내기 | **수신자도 동일 앱에 카카오 로그인 + 이용 동의**해야 하고 발신자와 카카오톡 친구여야 함. 일일 쿼터 제한(예: 일 30건 수준), 권한 심사 필요. 정해진 메시지 템플릿(피드/텍스트 등) 형식 | △ (텍스트 가능하나 쿼터·동의 장벽) | ✕ (파일 첨부 미지원) | 외부 투자사 담당자 수십 명에게 "우리 앱에 카카오 로그인해서 동의해달라"는 것은 비현실적. 쿼터도 부족 |

**결론: 카카오 공식 API 어느 경로로도 "임의 기존 채팅방에 자유 문구 발송"은 불가능하다. 공식 API는 전부 미채택으로 확정한다.** (하이브리드 검토도 하지 않는다 — 확정 지시)

### 1.3 채택안(확정) — Windows 데스크톱 카카오톡 UI 자동화 (텍스트 전송 전용)

- 사용자의 **Windows PC에 로그인된 카카오톡 데스크톱 앱**을 Python **pywinauto**(+pyautogui 보조, pyperclip 클립보드)로 제어한다.
- 텍스트: 메인 창 친구/채팅 검색(Ctrl+F) → 방 이름 검색 → 방 열기 → 입력창에 클립보드 붙여넣기(Ctrl+V) → Enter. **긴 자유 문구 전송 가능 확인됨**(커뮤니티 구현 사례 다수). URL(드라이브 링크)도 일반 텍스트로 포함하면 되므로 별도 처리 불요.
- 파일 첨부 자동화는 **하지 않는다**(§1.1-B 확정). 참고: 기술적으로는 클립보드 CF_HDROP 붙여넣기로 가능하지만, UI 대화상자 처리 등 불안정 요소가 커서 드라이브 링크 방식으로 대체 확정.
- 제약: **Windows 전용**(pywinauto는 Win32/UIA 백엔드). 카카오톡 창이 떠 있고 로그인 상태여야 하며, 발송 중 사용자가 키보드·마우스를 쓰면 간섭 가능(§5.5 완화).

### 1.4 자동화 6종 최종 판정표

| # | 자동화 | 공식 API | UI 자동화 필요? | 판정 | 비고/우회책 |
|---|---|---|---|---|---|
| 1 | 카톡 딜소개 자유 문구 발송 + 후속 캐던스(Day1→6/7→11/14) | ✕ 불가(1.2) → **미채택** | **필요(텍스트 전송)** | **UI 자동화 채택** + 스케줄러(캐던스 예약) | 실패 시 폴백: 반자동 모드(§8) |
| 2 | IR 자료 전달 | ✕ 파일 첨부 전 경로 불가 → **미채택** | 텍스트 전송만 필요 | **드라이브 링크 포함 메시지 자동 발송**(#1과 동일 메커니즘) | 파일 첨부 자동화는 하지 않기로 확정. IR은 드라이브 링크로 관리 |
| 3 | 컬럼 필터 드롭다운 | 해당 없음 | 불필요 | 웹앱 자체 구현 (가능) | vanilla JS |
| 4 | 시트 한 페이지 표시 | 해당 없음 | 불필요 | 웹앱 CSS (가능) | FEATURE_SPEC §3 |
| 5 | 미팅 D+10 알림 | (채널 후보: SMS API·알림톡) | 불필요 | **발생 로직만 구현, 발송 채널 결정 보류** — NotificationChannel 어댑터로 추상화, MVP는 앱 내 알림 | 채널 확정 시 어댑터만 추가(§6) |
| 6 | 휴대폰 로그인/퇴사 삭제 | SMS API 활용(OTP) | 불필요 | 자체 구현 (가능) | OTP 발송은 CoolSMS(§6) |

### 1.5 UI 자동화의 리스크 고지 (솔직한 한계)

| 리스크 | 내용 | 완화책 |
|---|---|---|
| **카카오 운영정책 위반 소지** | 카카오톡 운영정책은 자동화 프로그램(매크로 등)을 통한 서비스 이용을 금지 → **계정 이용 제한(제재) 가능성**. 본 도구의 최대 리스크 | 사람 유사 패턴(건당 랜덤 3~7초 지연), 1회 발송 상한 60건, **수동 트리거만**(무인 스케줄 발송 금지), 사용자 감독 모드 기본, 사용자에게 최초 실행 시 리스크 고지·동의 화면 |
| UI 변경으로 스크립트 파손 | 카카오톡 업데이트 시 컨트롤 구조 변경 가능 | 셀렉터(창 제목·컨트롤 경로·단축키)를 `agent/selectors.yaml`로 외부화, 실패 시 스크린샷 저장 후 **즉시 전체 중단**(오발송 방지 우선), 자동 업데이트 끄고 검증된 버전 유지 권장 |
| 오발송 | 방 이름 오매칭·검색 결과 오클릭 | 발송 전 [방 연결 확인] 검증 절차(§5.4), 방 이름 **정확 일치**만 허용, 열린 방 제목 재확인 후 전송, 불일치 시 skip+실패 처리 |
| 사용 중 간섭 | 발송 중 사용자가 PC 조작 | 발송 중 오버레이 안내 "PC 조작을 멈춰주세요", 비상 중단(ESC 2회/마우스 좌상단 코너=pyautogui FAILSAFE) |

---

## 2. 전체 아키텍처

### 2.1 구성도

```
[개발: macOS] ─ 코드 작성·MockSender 테스트 ─▶ (git) ─▶ [운영: 사용자 Windows PC 1대]

┌──────────────────────────── Windows PC (운영) ────────────────────────────┐
│                                                                           │
│  ┌─ 웹앱 서버 (FastAPI + Uvicorn, :8000) ──────────────┐                  │
│  │  Jinja2 SSR + vanilla JS + Pretendard(로컬 번들)     │   브라우저(Edge) │
│  │  SQLite WAL (data/dealflow.db)                       │◀── 사용자 UI    │
│  │  APScheduler: 후속 캐던스 도래 산출(매일 09:00),     │                  │
│  │   정기 회차 생성(매월 1·3번째 수요일), D+10 알림 생성,│                  │
│  │   주간 집계, 큐 타임아웃 감시                        │                  │
│  │  발송 큐 API: /api/agent/*                           │                  │
│  └───────────────▲──────────────────────────────────────┘                  │
│                  │ HTTP 폴링(5초, Bearer 토큰)                             │
│  ┌───────────────┴─────────────────────────┐    ┌──────────────────┐      │
│  │ 발송 에이전트 (Python, pywinauto)        │───▶│ 카카오톡 데스크톱 │      │
│  │  큐 수령 → 카톡 창 제어(텍스트 전송)     │    │ (로그인 상태)     │      │
│  │  → 결과 보고 · 실패 스크린샷             │    └──────────────────┘      │
│  └─────────────────────────────────────────┘                              │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
        │
        ├──▶ CoolSMS(SOLAPI) REST API   (로그인 OTP 인증번호 — 확정)
        └──▶ NotificationChannel 어댑터 (D+10 알림 — 채널 보류: MVP=in_app,
             추후 SmsChannel/KakaoChannel 장착)
   ※ IR 자료는 서버에 저장하지 않음 — 구글 드라이브(사용자 수기 업로드)의 링크만 DB에 보관
```

- **MVP 배치**: 웹앱 서버와 발송 에이전트를 **같은 Windows PC에서** 실행(사용자 1~수 명, localhost 또는 사내망 IP 접속). 서버를 사내 공용 머신에 두는 경우에도 에이전트는 각 사용자의 카톡이 로그인된 PC에서 돌며 HTTP로만 통신하므로 구조 변경 없음.
- 웹앱과 에이전트는 **DB를 공유하지 않는다**. 에이전트는 오직 HTTP API로만 통신 → 분리 배포·격차 해소의 핵심.

### 2.2 기술 스택 (확정)

| 레이어 | 선택 | 이유 |
|---|---|---|
| 언어 | Python 3.12 | 확정 사항 |
| 웹 | FastAPI + Uvicorn + Jinja2 SSR | 로컬 실행 간편, 무거운 SPA 지양(확정), API·화면 동시 제공 |
| 프론트 | HTML/CSS/vanilla JS + Pretendard 로컬 번들 | 필터·미리보기 정도의 상호작용에 충분 |
| DB | **SQLite 확정**(WAL 모드) + SQLAlchemy 2.x | 규모 확정: 사용자 7명 · 담당자 ~150명 · 발송 이력 수만 건 수준 → SQLite로 충분. WAL로 웹/스케줄러 동시 접근 안전. **Postgres 이전 경로**: SQLAlchemy ORM만 사용(raw SQL 금지)·JSON 컬럼 회피·마이그레이션은 Alembic → 필요 시 DSN 교체+`alembic upgrade`로 이전 가능하게 설계 |
| 스케줄러 | APScheduler (웹앱 프로세스 내) | 잡: ① 매일 09:00 후속 캐던스 도래 산출(due 전환+대기 목록), ② 매월 1·3번째 수요일 정기 회차 초안 생성(schedule_rules 기반, 2026-09~), ③ 미팅 D+10 알림 생성, ④ 매주 월요일 weekly_stats 집계, ⑤ 30분 주기 잡 타임아웃 감시 |
| 알림 채널 | NotificationChannel 어댑터 (`InAppChannel` 기본 / `SmsChannel`·`KakaoChannel` 후보) | #5 채널 결정 보류 대응 — 어댑터만 추가하면 전환 |
| 에이전트 | pywinauto(uia 백엔드) + pyperclip + pyautogui(FAILSAFE·보조) + requests | §1.3 (텍스트 전송 전용) |
| SMS | CoolSMS(SOLAPI) Python SDK — 로그인 OTP 용도 확정 | §6 |
| 패키징 | 서버: `run_server.bat`(venv+uvicorn) / 에이전트: `run_agent.bat`, 후순위로 PyInstaller 단일 exe | Windows 사용자가 더블클릭 실행 |

### 2.3 저장소 구조 (모노레포)

```
dealflow/
├─ app/                      # FastAPI 웹앱
│  ├─ main.py                # 앱 팩토리, 라우터 등록, APScheduler 기동
│  ├─ db.py, models.py       # SQLAlchemy
│  ├─ auth.py                # OTP·세션·role 가드
│  ├─ routers/               # checklist, contacts, companies, deals, sequences, ir, meetings, admin, agent_api
│  ├─ services/              # message_composer.py(오프닝/요약 자동 생성·치환·단계별 조합),
│  │                         # cadence.py(시퀀스 예약·중단·영업일 보정), stats.py,
│  │                         # notify.py(NotificationChannel 어댑터), sms.py(OTP)
│  ├─ scheduler.py           # 캐던스 도래·정기 회차 생성·D+10 알림·주간 집계·잡 타임아웃
│  ├─ templates/  static/    # Jinja2 · CSS/JS/fonts(Pretendard)
├─ agent/                    # Windows 발송 에이전트 (웹앱과 독립 실행)
│  ├─ main.py                # 폴링 루프
│  ├─ sender/base.py         # Sender 인터페이스 (플랫폼 격차 해소 지점)
│  ├─ sender/kakao_windows.py# pywinauto 구현 (Windows 전용 import 격리)
│  ├─ sender/mock.py         # MockSender (macOS 개발·테스트용)
│  ├─ selectors.yaml         # 카톡 UI 셀렉터·단축키·타이밍 외부화
│  └─ config.yaml            # 서버 URL, 토큰, 지연 범위, 상한
├─ data/  agent_logs/        # IR 파일 저장소 없음(드라이브 링크만 DB 보관)
├─ scripts/ run_server.bat  run_agent.bat  bootstrap.py  purge_demo.py  add_user.py  import_sheets.py
└─ docs/
```

---

## 3. 플랫폼 격차 해소 (개발 macOS ↔ 실행 Windows)

| 격차 | 해소 방안 |
|---|---|
| pywinauto는 macOS에서 import 불가 | `sender/base.py`의 `Sender` 추상 인터페이스(`verify_room(name)`, `send_text(room, text)`)로 격리. Windows 전용 import는 `kakao_windows.py` 안에서만. 에이전트 기동 시 `platform.system()`으로 구현 선택(macOS→MockSender) |
| macOS에서 발송 흐름 테스트 불가 | **MockSender**: 발송을 파일 로그로 기록하고 성공/실패/지연을 시나리오로 흉내(설정으로 실패율 주입). 웹앱~큐~에이전트 왕복 전체를 macOS에서 E2E 테스트 가능 |
| 실제 카톡 제어 검증 | 스프린트마다 **Windows 실기 검증 태스크**를 명시(ROADMAP). 검증 대상: 방 검색, 장문(URL 포함) 붙여넣기, 한글 IME 간섭 없음(클립보드 방식이라 IME 무관) |
| 서버·에이전트 간 결합 | HTTP API만 사용(코드 공유는 스키마 상수 정도). 에이전트는 서버 없이도 기동 후 재시도 폴링 |

## 4. 발송 큐 프로토콜 (웹앱 ↔ 에이전트)

```
에이전트 → 서버 (모두 Authorization: Bearer <agent_token>)

GET  /api/agent/poll                 5초 주기. 응답: 실행할 job 1개(send_items 배열 포함) 또는 204
POST /api/agent/items/{id}/result   {status: sent|failed, error?, screenshot_b64?}
POST /api/agent/jobs/{id}/status    {status: running|done|done_with_errors, counters}
POST /api/agent/heartbeat           30초 주기 → agent_devices.last_poll_at 갱신(UI 연결 배지)
POST /api/agent/verify_room         {room_name} → {verified|not_found|ambiguous} (내 투자사 [방 연결 확인])
```

- 잡 수령은 **원자적 클레임**(status queued→running를 UPDATE ... WHERE status='queued'로 선점) — 중복 실행 방지.
- 서버 스케줄러가 30분 이상 running인 잡을 감시 → 에이전트 사망 판정 시 pending 건 유지한 채 paused 전환(재개 가능).
- 진행 화면은 서버 DB를 2초 폴링(SSE는 후순위 개선).

## 5. 발송 에이전트 상세 설계

### 5.1 메인 루프
```
기동 → config 로드 → Sender 선택 → 서버 연결 확인
loop:
  heartbeat(30s) / poll(5s)
  job 수령 시:
    for item in send_items(pending only):
      사용자 감독 오버레이 표시(§5.5)
      sender.send_text(room_name, message)   # 드라이브 링크도 본문 텍스트로 포함됨
      결과 보고 → 랜덤 지연 uniform(3, 7)초
    job 완료 보고
  ESC 2회/코너 FAILSAFE → 현재 건 중단 보고 후 루프 정지
```

### 5.2 텍스트 발송 시퀀스 (kakao_windows.py)
```
1. 카카오톡 메인 창 탐색(Desktop(backend="uia").window(title_re="카카오톡.*")) → 최소화 해제·전면화
2. Ctrl+F(검색) → pyperclip.copy(room_name) → Ctrl+V → 결과 대기(0.8s)
3. Enter로 최상위 결과 열기 → 열린 채팅창 핸들 획득
4. ★검증: 채팅창 타이틀 == room_name 정확 일치 확인. 불일치 → 창 닫고 failed(사유: room_mismatch)
5. pyperclip.copy(message) → 입력창 클릭 → Ctrl+V → 스크린 안정 대기(0.5s) → Enter
6. 채팅창 닫기(Esc)
```

> 파일 첨부 시퀀스는 없다(확정: IR 자료는 드라이브 링크를 본문에 포함 → §5.2로 충분).

### 5.3 방 연결 확인 (verify_room)
- 검색 결과 목록에서 room_name 정확 일치 항목 수 카운트: 1개=verified, 0개=not_found, 2개 이상=ambiguous.
- 채팅방을 열지 않고 검색 결과만 읽음(발송 없음) → 내 투자사 화면 배지(●/○/⚠)에 반영.

### 5.5 속도 제한·상한 (계정 보호 — config.yaml 기본값)
- 건당 지연 3~7초 랜덤, 10건마다 30~60초 휴지, 1잡 상한 60건, 1일 상한 120건(에이전트가 로컬 카운트).

### 5.5 사용자 감독 모드 (기본 ON)
- 발송 시작 시 화면 우하단 오버레이(항상 위): "카톡 자동 발송 중 (17/28) — PC 조작을 멈춰주세요 · [일시정지] [중단]".
- 목적: (a) 간섭 방지, (b) 사용자가 지켜보는 반자동 성격 유지 → 오발송 즉시 인지, ToS 리스크 완화.

### 5.6 로그
- `agent_logs/agent.log`(회전), 실패 스크린샷 `agent_logs/{item_id}.png`(서버에도 b64 업로드), 건별 소요 시간 기록.

## 6. 알림·SMS — 채널 어댑터와 한국 SMS API 비교

### 6.1 D+10 알림 채널 (자동화 #5) — **발송 채널 결정 보류**
- 발생 조건·스케줄·대상 산출(미팅 완료일+10일 → notifications 큐 생성)은 정상 구현한다.
- 발송 채널(SMS vs 카톡)은 사용자가 고민 중 → `NotificationChannel` 인터페이스(`send(notification) -> result`)로 추상화:
  - `InAppChannel` — **MVP 기본**: 앱 내 배너 + 오늘 할 일 항목 생성.
  - `SmsChannel` — CoolSMS 어댑터(코드 준비, 비활성).
  - `KakaoChannel` — 발송 에이전트 큐를 통해 "나와의 채팅" 또는 지정 방으로 전송(후보, 미구현).
- 채널 확정 시 settings에서 어댑터만 교체. ROADMAP에 TODO로 명시.

### 6.2 한국 SMS API 비교 (로그인 OTP 용도 — 확정 채택 필요)

| 서비스 | 장점 | 단점 | 판정 |
|---|---|---|---|
| **CoolSMS (SOLAPI)** | 개발 문서·공식 Python SDK 우수, 자동충전·잔액 관리 쉬움, 알림톡 발송도 동일 API로 확장 가능 | 단가가 최저가군보다 높음(SMS 건당 ~20원대) | **채택(OTP용)** — 소량(월 수백 건)이라 단가보다 개발 속도·안정성 우선 |
| 알리고 | 국내 최저가(단문 8.4원) | SDK 없이 raw REST, 문서 간소 | 비용 민감해지면 교체 후보(SmsProvider 어댑터로 교체 용이) |
| 네이버 SENS | 월 50건 무료, 네이버클라우드 통합, 알림톡 지원 | NCP 계정·서명 생성 등 초기 셋업 부담 | 미채택 |

- 발신번호 사전 등록(통신사 규정) 필요 — 회사 대표번호 또는 사용자 번호 등록 절차를 온보딩 문서에 포함.
- OTP·알림 문안은 정보성(수신자=사용자 본인)이므로 광고 규제 무관.
- `services/sms.py`에 `SmsProvider` 인터페이스 + `CoolsmsProvider` / `ConsoleProvider`(개발용, 콘솔 출력) — macOS 개발 시 실제 발송 없이 테스트.

## 7. 보안·계정

### 7.1 휴대폰 번호 로그인 (OTP)
```
[로그인 화면] 번호 입력 → 서버: 화이트리스트(users.phone) 확인
 → 6자리 OTP 생성(auth_otps, 5분 유효) → CoolSMS 발송
 → 사용자 입력 → 검증(5회 실패 시 10분 잠금, OTP는 해시 저장)
 → sessions 토큰 발급 → HttpOnly+SameSite=Lax 쿠키(14일)
```
- 미등록 번호는 OTP 자체를 발송하지 않음(오류 메시지는 "등록되지 않은 번호"로 통일 — 번호 존재 여부 탐지 방지 위해 발송 여부와 무관하게 동일 응답 시간).
- 관리자 계정 생성: 초기 `scripts/create_admin.py`로 시드, 이후 관리자 화면에서 사용자 등록.

### 7.2 권한 가드 (RBAC)

| 데이터 | user | admin |
|---|---|---|
| 본인 담당 데이터(vc_contacts·ir_requests·meetings·checklist·deal_batches·send_*·sequences) | 본인 것만 CRUD(쿼리 강제 user_id 필터) | ✕ 원문 접근 403 (집계만) |
| IR 기업 DB(ir_companies) — 팀 마스터 | 전원 조회, 편집=본인이 담당자(owner)인 기업 + 생성 | **전체 편집**(마스터 데이터 관리) + CSV 임포트 |
| 팀 현황(weekly_stats)·사용자 계정 관리·schedule_rules·팀 기본 템플릿 | ✕ | ○ |
| 개인 원문(체크리스트 원문·오프닝 문구·발송 메시지 원문·개인 메모) | 본인만 | ✕ (구조적 차단: 관리자 화면은 집계 테이블만 조회, DATA_MODEL §2.16) |

- 모든 라우터에 세션 의존성. 에이전트 API는 세션과 별개의 Bearer 토큰(사용자별 발급, 웹 화면에서 재발급/폐기).

### 7.3 퇴사 삭제 절차
```
관리자 [사용자 삭제] → 확인 모달(이름 재입력) 
 → (선택) 연락처 CSV 내보내기(문안·메모 제외)
 → 트랜잭션: DATA_MODEL §5 매트릭스대로 하드 삭제 + weekly_stats 익명화
 → 에이전트 토큰 폐기 → 완료 리포트(삭제 건수 요약)
```
- SQLite `PRAGMA secure_delete=ON` + 삭제 후 `VACUUM` — 파일 레벨 잔존 최소화.
- IR 기업 DB(ir_companies)는 팀 공유 마스터 자산으로 보존(owner_user_id만 NULL 처리). IR 파일 자체는 구글 드라이브(팀 계정)에 있으므로 서비스 삭제 범위 밖.

### 7.4 기타
- 서버는 사내망 바인드(`127.0.0.1` 기본, 팀 공유 시 사내 IP). 외부 공개 금지 전제 — HTTPS 미적용 대신 네트워크 경계로 보호(문서에 명시).
- 백업: 서버 기동 시 `data/backup/dealflow-YYYYMMDD.db` 일 1회 복사(7일 보관).
- 비밀값(coolsms 키, agent 토큰 서명키)은 `.env` — 저장소 커밋 금지.

## 8. 리스크와 폴백 전략

| 시나리오 | 폴백 |
|---|---|
| 카카오 제재 우려 고조 / 계정 경고 수신 | **반자동 모드**(에이전트 설정): 방 열기·문구 클립보드 적재까지 자동, **Enter 전송은 사람이** 직접. 건당 2~3초로 여전히 수작업 대비 10배 이상 빠름 |
| 카톡 UI 대격변으로 에이전트 장기 불능 | selectors.yaml 갱신으로 1차 대응. 불가 시 반자동 모드 + "발송 문안 전체 복사" 버튼(웹앱)으로 순수 수동 지원 |
| 드라이브 링크 접근 불가 신고(권한 미설정) | IR 전달 화면의 공유 권한 안내 강화 + 링크 등록 시 "링크가 있는 모든 사용자" 설정 체크리스트 |
| SMS(OTP) 단가·장애 | SmsProvider 어댑터 교체(알리고), 장애 시 관리자 화면에서 임시 로그인 코드 발급(백도어 아님 — 관리자 수동 전달) |
| 후속 캐던스 과밀(같은 날 회차+후속 겹침) | 대기 목록에서 우선순위 표시(회차 우선), 1일 상한(120건) 초과분은 다음 영업일 자동 이월 |

## 9. 로컬 실행법

### 개발 (macOS)
```bash
cd dealflow
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # fastapi uvicorn jinja2 sqlalchemy apscheduler ...
python scripts/bootstrap.py             # 팀 기본 문구 + 관리자 (데모는 DEALFLOW_SEED_DEMO=1)
python scripts/import_sheets.py --sheet-a a.csv --sheet-b b.csv --user 1  # 구글시트 CSV 임포트
uvicorn app.main:app --reload            # http://127.0.0.1:8000
# 별도 터미널: MockSender 에이전트
python -m agent.main --config agent/config.dev.yaml   # sender=mock
```

### 운영 (Windows PC)
```bat
:: 1) Python 3.12 설치, 카카오톡 데스크톱 로그인 상태 확인
:: 2) 서버
scripts\run_server.bat        :: venv 생성·의존성 설치·uvicorn 기동 (:8000)
:: 3) 에이전트 (관리자 권한 불필요, 단 카톡과 같은 세션에서)
scripts\run_agent.bat         :: agent\config.yaml: server_url, token(웹 화면에서 발급) 기입
:: 4) 브라우저에서 http://127.0.0.1:8000 → 휴대폰 로그인
```
- requirements를 `requirements.txt`(공통)와 `agent/requirements-win.txt`(pywinauto·pywin32)로 분리 — macOS 설치 실패 방지.
