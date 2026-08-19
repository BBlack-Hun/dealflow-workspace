# dealflow DATA_MODEL — 엔티티·관계·상태전이

> 버전: v1.0 (2026-08-18) · DB: **SQLite** (단일 파일 `data/dealflow.db`) · ORM: SQLAlchemy 2.x
> 표기: PK=기본키, FK=외래키. 모든 테이블 공통 컬럼 `created_at`, `updated_at` (ISO8601 문자열) — 아래 표에서 생략.

---

## 1. 엔티티 관계도 (텍스트 ERD)

```
users ─┬─< message_templates         (단계별 오프닝/클로징, user_id NULL=팀 기본)
       ├─< checklist_routines ──< checklist_items
       ├─< vc_contacts ──< contact_activities   (내 투자사 담당자 + 월별 활동 이력)
       ├─< deal_batches ──< deal_batch_companies >── ir_companies (팀 공유 마스터, ir_drive_url 보유)
       │        │
       │        ├──< send_sequences (담당자×회차 후속 캐던스: 단계·다음예약일·상태)
       │        │         │
       │        └──< send_jobs ──< send_items >── vc_contacts   (send_items.sequence_id/stage)
       │                 ▲
       ├─< ir_requests ──┘ (kind=ir_delivery 잡 연결)     ir_requests >── ir_companies
       │        └──< meetings ──< notifications
       ├─< notifications
       └─< auth_otps / sessions

agent_devices  (발송 에이전트 등록, users 1:1)
schedule_rules (발송 주기·캐던스 창 설정 — 하드코딩 금지)
weekly_stats   (퇴사 삭제 후에도 남는 익명화 집계)
```

---

## 2. 테이블 정의

### 2.1 users — 사용자
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| phone | TEXT UNIQUE | 휴대폰 번호(로그인 ID), `01012345678` 정규화 저장 |
| name | TEXT | 이름 |
| role | TEXT | `user` \| `admin` |
| weekly_goal_sends | INTEGER | 주간 딜소개 발송 목표(달성률 계산용, 기본 30) |
| is_active | INTEGER | 1=재직, 0=삭제 진행 중(트랜잭션 안전용, 최종은 행 삭제) |

### 2.2 auth_otps / sessions — 인증
| 테이블 | 주요 필드 |
|---|---|
| auth_otps | id PK, phone, code(6자리), expires_at(+5분), attempts, used(0/1) |
| sessions | id PK(랜덤 토큰), user_id FK, expires_at(+14일), last_seen_at |

### 2.3 message_templates — 단계별 메시지 템플릿 (사용자별 개인화, 팀 기본값 제공)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users NULL | NULL = 팀 기본 템플릿(시드), 사용자 것이 있으면 우선 |
| kind | TEXT | `opening_first`(첫연락 오프닝) \| `opening_re`(재연락 오프닝) \| `closing_day1` \| `closing_remind` \| `closing_meeting` \| `ir_delivery`(IR 전달 안내) |
| body | TEXT | 치환 변수: `{담당자명}` `{직함}` `{투자사}` `{기업명}` `{ir_drive_url}` |
| is_active | INTEGER | |

시드 기본값(팀 템플릿):
| kind | body |
|---|---|
| opening_first | "안녕하세요 {담당자명} {직함}님, 카톡으로 스타트업 딜소개를 드리고 있는데 검토해보시면 좋을 기업들 공유드립니다." |
| opening_re | "{담당자명} {직함}님 안녕하세요, 이번 회차 소개드릴 기업들 공유드립니다." |
| closing_day1 | "관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다." |
| closing_remind | "지난번 공유드린 기업들 검토 중 궁금하신 점 있으시면 말씀 부탁드립니다." |
| closing_meeting | "다음주 또는 다다음주 20~30분 정도 간단히 미팅 가능하실지요?" |

### 2.4 vc_contacts — 투자사 담당자 (고객)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users | 담당 사용자(소유자) — RBAC: 본인 것만 CRUD |
| group_name | TEXT NULL | 시트 A '그룹' |
| name | TEXT | 담당자명 (시트 A "홍길동 대표님" → name=홍길동) |
| title | TEXT | 직함 (→ title=대표님/심사역 등, 임포트 시 분리 파싱) |
| firm | TEXT | 투자사명 (예: "가나벤처스") |
| round_size | TEXT NULL | 시트 A '투자분야/라운드사이즈' 중 라운드 사이즈 부분 |
| channel_kakao | INTEGER | 카톡 연결 여부 0/1 |
| channel_email | INTEGER | 메일 연결 여부 0/1 |
| email | TEXT NULL | |
| phone | TEXT NULL | |
| kakao_room_name | TEXT NULL | **카톡 채팅방 이름(에이전트 검색 키, 정확 일치)** |
| room_verified | TEXT | `unverified` \| `verified` \| `ambiguous`(복수 매칭) \| `not_found` |
| stages | TEXT | 투자 단계 태그 CSV: `Seed,SeriesA` |
| sectors | TEXT | 섹터 태그 CSV: `AI,헬스케어` |
| status | TEXT | `active`(활발) \| `no_response`(반응없음) \| `paused`(검토중단) |
| memo | TEXT | |

파생값(저장 안 함, 조회 시 집계): 최근 딜소개(마지막 sent send_item), 반응(최근 90일 ir_requests/meetings 수).

### 2.5 ir_companies — 딜 기업(스타트업, 팀 공유 마스터 데이터)

구글시트 B [IR 기업현황] 헤더(`NO, 기업명, 사업분야 대분류, 소분류, 기업구분(시리즈), 한줄 소개, 담당자, IR deck유무, 계약여부, 계약 월 기입, 핵심/TOP Deal, 투자유치상태, 비고`)를 계승 + 서비스 필드 추가.

| 필드 | 타입 | 시트 B 원천 | 설명 |
|---|---|---|---|
| id | INTEGER PK | NO | |
| name | TEXT | 기업명 | |
| sector_major | TEXT | 사업분야 대분류 | |
| sector_minor | TEXT NULL | 소분류 | |
| series | TEXT | 기업구분(시리즈) | Seed/A/B/Pre-IPO 등 |
| one_liner | TEXT NULL | 한줄 소개 | 예: "B2B 농산물 선도거래 'Presell'" |
| owner_user_id | FK users NULL | 담당자 | RBAC: 편집=관리자+담당자 |
| ir_drive_url | TEXT NULL | IR deck유무 → 링크로 승격 | **IR 자료 구글 드라이브 링크** (있으면 deck 보유로 간주) |
| contract_status | TEXT | 계약여부 | `yes` \| `no` \| `pending` |
| contract_month | TEXT NULL | 계약 월 기입 | `2026-07` |
| is_top_deal | INTEGER | 핵심/TOP Deal | 0/1 |
| funding_status | TEXT NULL | 투자유치상태 | 예: "Series A 진행 중" |
| note | TEXT NULL | 비고 | |
| revenue_recent | INTEGER NULL | (추가) | 최근 매출(백만 원) |
| funding_total | INTEGER NULL | (추가) | 누적 투자(백만 원) |
| raise_target | INTEGER NULL | (추가) | 유치 희망(백만 원) |
| pre_value | INTEGER NULL | (추가) | Pre Value(백만 원) |
| competitiveness | TEXT NULL | (추가) | 경쟁력 항목(요약 자동 조합 말미, 예: "상급 유통사 12곳 계약") |
| summary | TEXT NULL | (추가) | **딜 요약문**. 필드 자동 조합(`[분야] \| 한줄소개 \| 매출 N억 \| 누적투자금액 N억 \| N억 투자유치중 \| Pre Value 약 N억원 \| 경쟁력`) 결과를 캐시, 수동 수정본 우선 |
| summary_status | TEXT | (추가) | `done`(작성완료) \| `draft`(미작성) \| `insufficient`(정보부족) |
| introducible | INTEGER | (파생) | summary_status=done AND 필수필드(name·sector_major·series) 충족 |

> **파일 저장 없음(확정)**: IR 파일은 서버에 업로드하지 않는다. 사용자가 구글 드라이브에 수기 업로드 후 `ir_drive_url`만 등록하며, 발송 메시지 본문에 링크 텍스트로 포함된다.

### 2.6 contact_activities — 담당자 활동 이력 (시트 A 월별 기록 임포트 + 서비스 자동 기록)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| contact_id | FK vc_contacts | |
| month | TEXT NULL | `2026-06` (시트 A 6/7/8월 컬럼 임포트분) |
| kind | TEXT | `deal_intro`(1차 딜소개) \| `ir_request` \| `meeting` \| `memo` |
| content | TEXT | 예: "1차 딜소개 06.12 · 딜 3개", "IR 요청: 샘플애그, 샘플메디" |
| happened_at | TEXT NULL | 날짜 식별 가능 시 |
| source | TEXT | `import`(시트) \| `system`(발송·IR·미팅 자동 기록) |

### 2.7 deal_batches — 딜소개 회차
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users | |
| title | TEXT | 예: "9월 1회차(첫째 수요일)" |
| sent_date | TEXT NULL | D0 발송일(캐던스 기산점) |
| cycle_type | TEXT | `regular`(정기: 첫째·셋째 수요일) \| `weekly`(과거 매주 이력) \| `adhoc`(수시) |
| opening_template_id | FK message_templates NULL | 사용한 오프닝 |
| body_override | TEXT NULL | 회차 단위 수정본(치환 변수 포함 원본) |

### 2.7-1 schedule_rules — 발송 주기 규칙 (하드코딩 금지, 설정 테이블)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| key | TEXT UNIQUE | `deal_batch_cycle` \| `seq_remind_window` \| `seq_meeting_window` \| `followup_after_meeting_days` |
| value | TEXT | 예: `deal_batch_cycle` = `"monthly:wed:1,3"` (매월 1·3번째 수요일, 2026-09 시행) / `seq_remind_window` = `"6,7"` / `seq_meeting_window` = `"11,14"` / `followup_after_meeting_days` = `"10"` |
| effective_from | TEXT NULL | `2026-09-01` (그 이전엔 주 단위 이력과 혼재 허용) |

### 2.7-2 send_sequences — 딜소개 후속 시퀀스 (담당자 × 회차)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users | |
| contact_id | FK vc_contacts | |
| batch_id | FK deal_batches | 기업 세트(회차) |
| current_stage | INTEGER | 1=Day1 딜소개, 2=리마인드, 3=미팅요청 |
| next_send_at | TEXT NULL | 다음 단계 예약일(창 내 랜덤, 영업일 보정) |
| status | TEXT | 상태전이 §3.6 |
| stopped_reason | TEXT NULL | `responded` \| `ir_requested` \| `meeting` \| `manual` \| `superseded`(새 회차로 대체) |
| started_at / ended_at | TEXT NULL | |

### 2.8 deal_batch_companies — 회차-기업 (1~3개)
| 필드 | 타입 | 설명 |
|---|---|---|
| batch_id | FK deal_batches | 복합 PK |
| company_id | FK ir_companies | 복합 PK |
| position | INTEGER | 1~3 (문구 내 순서) |

### 2.9 send_jobs — 발송 잡 (에이전트 큐의 단위)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users | |
| kind | TEXT | `deal_intro`(딜소개) \| `ir_delivery`(IR 전달) |
| batch_id | FK NULL | kind=deal_intro일 때 |
| ir_request_id | FK NULL | kind=ir_delivery일 때 |
| status | TEXT | 상태전이 §3.1 |
| total / sent / failed | INTEGER | 진행 카운터 |
| started_at / finished_at | TEXT NULL | |

### 2.10 send_items — 발송 건 (담당자별 1건, 이력 원장)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| job_id | FK send_jobs | |
| contact_id | FK vc_contacts | |
| sequence_id | FK send_sequences NULL | 시퀀스 발송이면 연결 |
| stage | INTEGER NULL | 1=딜소개, 2=리마인드, 3=미팅요청 (ir_delivery는 NULL) |
| room_name | TEXT | 발송 시점 방 이름 **스냅샷** |
| message | TEXT | 치환 완료된 최종 문안 **스냅샷**(이후 수정과 무관하게 불변). ir_delivery는 본문에 `ir_drive_url` 링크 텍스트 포함 |
| status | TEXT | 상태전이 §3.2 |
| error | TEXT NULL | 실패 사유 |
| screenshot_path | TEXT NULL | 실패 시 에이전트 스크린샷 |
| retry_count | INTEGER | 자동 1회 + 수동 |
| sent_at | TEXT NULL | |

### 2.11 ir_requests — IR 요청
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users | |
| contact_id | FK vc_contacts | 요청한 투자사 담당자 |
| company_id | FK ir_companies | 요청 기업 |
| requested_at | TEXT | 요청일 |
| due_days | INTEGER | 기한 D+N (기본 3) |
| status | TEXT | 상태전이 §3.3 |
| delivered_at | TEXT NULL | |
| delivery_note | TEXT NULL | 전달 문구(수정본 스냅샷) |

### 2.12 meetings — 미팅
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users | |
| contact_id | FK vc_contacts | |
| company_id | FK ir_companies | 대상 기업 |
| ir_request_id | FK NULL | 출발점이 된 IR 요청 |
| status | TEXT | 상태전이 §3.4 |
| meeting_date | TEXT NULL | 확정/완료 일자 |
| next_action | TEXT NULL | 다음 액션 메모 |
| next_action_done | INTEGER | 1이면 D+10 알림 취소 |
| completed_at | TEXT NULL | 완료 전환 시각(D+10 기산점) |

### 2.13 checklist_routines / checklist_items — 루틴·오늘 할 일
| 테이블 | 주요 필드 |
|---|---|
| checklist_routines | id PK, user_id FK, title, type(`send`\|`mail`\|`call`\|`meeting`\|`ir`\|`etc`), weekdays(CSV `tue,thu`), is_active |
| checklist_items | id PK, user_id FK, routine_id FK NULL(수동 추가 시 NULL), date(YYYY-MM-DD), title, type, done(0/1), done_at, count(건수형), memo, carried_over(이월 표시 0/1) |

### 2.14 notifications — 알림(D+10 등)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users | 수신자(사용자 본인) |
| meeting_id | FK NULL | D+10 알림의 원천 |
| kind | TEXT | `meeting_followup` \| `seq_due`(후속 시퀀스 도래) \| `system` |
| channel | TEXT | `in_app`(MVP 기본) \| `sms` \| `kakao` — **#5 발송 채널은 결정 보류. 채널 어댑터(NotificationChannel)로 추상화, MVP는 in_app만 활성** |
| scheduled_at | TEXT | 예: 완료일+10일 09:30 |
| status | TEXT | 상태전이 §3.5 |
| message | TEXT | 발송 문안 |
| sent_at / error | TEXT NULL | |

### 2.15 agent_devices — 발송 에이전트 등록
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK users UNIQUE | 사용자당 1대 |
| token | TEXT UNIQUE | 에이전트 인증 토큰(발급형) |
| hostname | TEXT | Windows PC 이름 |
| last_poll_at | TEXT | 최근 폴링 시각(30초 내면 "연결됨" 배지) |
| agent_version | TEXT | |

### 2.16 weekly_stats — 익명화 가능 주간 집계 (관리자 화면 원천)
| 필드 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| user_id | FK NULL | **퇴사 삭제 시 NULL + user_label="퇴사자"로 익명화** |
| user_label | TEXT | 표시명(재직 중엔 이름 미러) |
| week | TEXT | ISO 주차 `2026-W34` |
| contacts_total | INTEGER | 연결 투자사 수 |
| sends / mails / irs / meetings_cnt | INTEGER | 발송·메일·IR·미팅 건수 |
| goal_rate | REAL | 주간 목표 달성률 |

> weekly_stats는 매주 월요일 스케줄러가 원장 테이블에서 집계·적재(멱등 upsert). 관리자 화면은 이 테이블만 읽는다 → 원문 접근 차단이 구조적으로 보장됨.

---

## 3. 상태 전이

### 3.1 send_jobs.status
```
draft ──[발송 목록 생성]──▶ queued ──[에이전트 수령]──▶ running ─┬─▶ done      (전건 종결)
  │                            │                                └─▶ done_with_errors (실패 포함 종결)
  └─[취소]─▶ canceled          └─[일시정지]─▶ paused ─[재개]─▶ queued
```

### 3.2 send_items.status
```
pending ──▶ sending ─┬─▶ sent
                     └─▶ failed ──[자동 1회/수동 재시도]──▶ pending
  (job 취소 시: pending → canceled)
```

### 3.3 ir_requests.status
```
pending(미전달) ──[IR 전달 성공]──▶ delivered(전달완료)
      │                                 
      └──[발송 실패]──▶ pending 유지(+error 표시)      delivered는 종결 상태
```

### 3.4 meetings.status
```
scheduling(조율중) ──▶ scheduled(일정확정) ──▶ completed(완료) ──(D+10 알림 예약)
      │                     │                      │
      └────────┴──▶ dropped(Drop)          completed→dropped 전환 시 알림 취소
```

### 3.5 notifications.status
```
scheduled ─┬─▶ sent      (in_app: 앱 내 배너·오늘 할 일 항목 생성 시점에 sent)
           ├─▶ failed ──▶ (외부 채널 실패 시 in_app 폴백 생성)
           └─▶ canceled   (미팅 상태 변경/next_action_done=1)
```

### 3.6 send_sequences.status
```
                    ┌─[사용자 응답 기록/IR 요청 생성/미팅 생성]─▶ stopped(reason: responded|ir_requested|meeting)
active(stage=1 발송됨)
  ─[예약일 도래]─▶ due(대기 목록 노출) ─[후속 발송 성공]─▶ active(stage+1)
  │                                      └─[발송 실패]─▶ due 유지(+error)
  ├─[stage=3 발송 후 7일 무응답]─▶ completed(전체 미응답 종료)
  ├─[새 회차 발송]─▶ stopped(superseded)
  └─[수동 중단]─▶ stopped(manual)   ← 24시간 내 [재개] 가능
```

---

## 4. 예시 레코드

```jsonc
// users
{ "id": 1, "phone": "01012345678", "name": "정훈", "role": "user", "weekly_goal_sends": 30 }
{ "id": 9, "phone": "01099998888", "name": "김리더", "role": "admin" }

// message_templates (사용자 개인화 오프닝 — 팀 기본을 복제 후 수정)
{ "id": 3, "user_id": 1, "kind": "opening_first", "is_active": 1,
  "body": "안녕하세요 {담당자명} {직함}님, 카톡으로 스타트업 딜소개를 드리고 있는 정훈입니다.\n검토해보시면 좋을 기업 3곳 공유드립니다." }
{ "id": 4, "user_id": null, "kind": "closing_day1", "is_active": 1,
  "body": "관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다." }

// schedule_rules
{ "key": "deal_batch_cycle", "value": "monthly:wed:1,3", "effective_from": "2026-09-01" }
{ "key": "seq_remind_window", "value": "6,7" }
{ "key": "seq_meeting_window", "value": "11,14" }

// vc_contacts (시트 A "홍길동 대표님 | 가나벤처스" 임포트 예)
{ "id": 12, "user_id": 1, "group_name": "A그룹", "name": "홍길동", "title": "대표님",
  "firm": "가나벤처스", "round_size": "라운드 30~100억",
  "channel_kakao": 1, "channel_email": 1, "email": "cho@lfinvest.kr",
  "kakao_room_name": "홍길동 대표님(가나벤처스)", "room_verified": "verified",
  "stages": "SeriesA,SeriesB", "sectors": "AI,SaaS", "status": "active",
  "memo": "AI 인프라 선호, 리드 가능" }

// contact_activities (시트 A 월별 기록 임포트)
{ "id": 201, "contact_id": 12, "month": "2026-06", "kind": "deal_intro",
  "content": "1차 딜소개 06.12 · 딜 3개", "happened_at": "2026-06-12", "source": "import" }
{ "id": 202, "contact_id": 12, "month": "2026-07", "kind": "ir_request",
  "content": "IR 요청: 샘플애그, 샘플메디", "source": "import" }

// ir_companies (시트 B "샘플애그 | B2B 농산물 선도거래 'Presell' | 매출 30.9억 | 누적투자 5.6억 | 핵심")
{ "id": 7, "name": "샘플애그", "sector_major": "애그테크", "sector_minor": "B2B 유통",
  "series": "SeriesA", "one_liner": "B2B 농산물 선도거래 'Presell'",
  "owner_user_id": 1, "ir_drive_url": "https://drive.google.com/file/d/1AbC.../view",
  "contract_status": "yes", "contract_month": "2026-07", "is_top_deal": 1,
  "funding_status": "Series A 진행 중", "note": "",
  "revenue_recent": 3090, "funding_total": 560, "raise_target": 5000, "pre_value": 20000,
  "summary": "[샘플애그] B2B 농산물 선도거래 플랫폼 'Presell'. 매출 30.9억, 누적투자 5.6억. Series A 50억 모집.",
  "summary_status": "done", "introducible": 1 }

// deal_batches + deal_batch_companies
{ "id": 21, "user_id": 1, "title": "9월 1회차(첫째 수요일)", "sent_date": "2026-09-02",
  "cycle_type": "regular", "opening_template_id": 3, "body_override": null }
[ { "batch_id": 21, "company_id": 7, "position": 1 },
  { "batch_id": 21, "company_id": 8, "position": 2 },
  { "batch_id": 21, "company_id": 11, "position": 3 } ]

// send_sequences (Day1 발송 성공 후 자동 생성 — 리마인드 예약)
{ "id": 61, "user_id": 1, "contact_id": 12, "batch_id": 21, "current_stage": 1,
  "next_send_at": "2026-09-08", "status": "active", "started_at": "2026-09-02" }

// send_jobs / send_items
{ "id": 55, "user_id": 1, "kind": "deal_intro", "batch_id": 21,
  "status": "running", "total": 28, "sent": 17, "failed": 1 }
{ "id": 901, "job_id": 55, "contact_id": 12, "sequence_id": 61, "stage": 1,
  "room_name": "홍길동 대표님(가나벤처스)",
  "message": "홍길동 대표님님 안녕하세요, 정훈입니다.\n이번 주 소개드릴 기업 3곳 공유드립니다.\n\n[1] [샘플애그] B2B 농산물 선도거래 플랫폼 'Presell'. ...\n\n[2] ...\n\n[3] ...\n\n검토 후 IR 자료 필요하시면 편하게 말씀 주세요!",
  "status": "sent", "sent_at": "2026-08-18T10:42:11" }
{ "id": 902, "job_id": 56, "contact_id": 12, "room_name": "홍길동 대표님(가나벤처스)",
  "message": "홍길동 대표님, 요청 주신 샘플애그 IR 자료 전달드립니다.\nB2B 농산물 선도거래 'Presell' · Series A 진행 중\nIR 자료: https://drive.google.com/file/d/1AbC.../view\n검토 후 미팅 원하시면 편하신 일정 말씀 부탁드립니다.",
  "status": "failed", "error": "채팅방 검색 결과 없음(room not found)",
  "screenshot_path": "agent_logs/902.png", "retry_count": 1 }

// ir_requests
{ "id": 31, "user_id": 1, "contact_id": 12, "company_id": 7,
  "requested_at": "2026-08-17", "due_days": 3, "status": "pending" }

// meetings
{ "id": 14, "user_id": 1, "contact_id": 12, "company_id": 7, "ir_request_id": 31,
  "status": "completed", "meeting_date": "2026-08-10", "completed_at": "2026-08-10T16:00:00",
  "next_action": "텀시트 논의 여부 확인", "next_action_done": 0 }

// notifications (위 미팅의 D+10 — 채널 결정 보류, MVP는 in_app)
{ "id": 71, "user_id": 1, "meeting_id": 14, "kind": "meeting_followup", "channel": "in_app",
  "scheduled_at": "2026-08-20T09:30:00", "status": "scheduled",
  "message": "[dealflow] 가나벤처스 홍길동 대표님 미팅(샘플애그) 후 10일 경과. 후속 연락을 진행하세요." }

// checklist_routines / checklist_items
{ "id": 5, "user_id": 1, "title": "딜소개+리마인드 카톡", "type": "send", "weekdays": "tue,thu", "is_active": 1 }
{ "id": 301, "user_id": 1, "routine_id": 5, "date": "2026-08-18", "title": "딜소개+리마인드 카톡",
  "type": "send", "done": 1, "done_at": "2026-08-18T10:55:00", "count": 28, "carried_over": 0 }

// agent_devices
{ "id": 1, "user_id": 1, "token": "agt_9f3k...", "hostname": "DESKTOP-JH-01",
  "last_poll_at": "2026-08-18T10:55:03", "agent_version": "0.1.0" }

// weekly_stats
{ "id": 88, "user_id": 1, "user_label": "정훈", "week": "2026-W34",
  "contacts_total": 42, "sends": 28, "mails": 15, "irs": 4, "meetings_cnt": 2, "goal_rate": 0.93 }
```

---

## 5. 삭제(퇴사) 시 데이터 처리 매트릭스

| 테이블 | 처리 |
|---|---|
| users, sessions, auth_otps, agent_devices | 행 삭제 |
| message_templates(user_id 있는 것), checklist_* , deal_batches(+batch_companies), send_sequences, send_jobs, send_items, notifications | **하드 삭제** (개인 원문. 팀 기본 템플릿 user_id=NULL은 보존) |
| vc_contacts, contact_activities, ir_requests, meetings | 하드 삭제 (개인 담당 고객 데이터. 팀 이관이 필요하면 삭제 전 관리자에게 CSV 내보내기 옵션 제공 — 원문 중 문안·메모 제외한 연락처 필드만) |
| ir_companies | **보존** (팀 공유 마스터 자산. owner_user_id만 NULL 처리) |
| weekly_stats | user_id=NULL, user_label="퇴사자"로 익명화 보존 |

---

## 6. 초기 데이터 임포트 (구글시트 → CSV 시딩)

`scripts/import_sheets.py --sheet-a a.csv --sheet-b b.csv --user <담당 user_id>`

| 시트 | 원본 컬럼 | 대상 |
|---|---|---|
| A(투자사/심사원) | 번호 | (무시) |
| | 그룹 | vc_contacts.group_name |
| | 이름("홍길동 대표님") | name+title 분리 파싱(마지막 어절=직함 휴리스틱, 실패 시 name에 전체) |
| | 투자사명 | firm |
| | 투자분야/라운드사이즈 | sectors(태그 분해) + round_size |
| | 1차 딜소개(날짜+딜 개수) | contact_activities(kind=deal_intro, source=import) |
| | IR 자료 요청(기업명 리스트) | contact_activities(kind=ir_request) — 기업명이 ir_companies와 일치하면 ir_requests 생성 옵션 |
| | 미팅 요청 | contact_activities(kind=meeting) |
| | 월별(6/7/8월) 활동 | contact_activities(month별 kind=memo) |
| | (헤더에 섞인 임시 로그인 문자열 등 비정형 행) | **무시**(스킵 리포트에 기록). 인증은 휴대폰 로그인으로 대체 |
| B(IR 기업현황) | NO~비고 13개 컬럼 | ir_companies (§2.5 매핑 그대로) |
| | IR deck유무 | `유` + 링크 파악 가능 시 ir_drive_url, 아니면 비고에 "deck 보유" 표기 후 링크는 서비스에서 수기 등록 |

- 멱등성: 기업명/(담당자명+투자사명) 기준 upsert. 재실행 시 중복 생성 없음.
- 임포트 결과 리포트: 생성/갱신/스킵 건수 + 스킵 행 목록 출력.
