# Windows 발송 테스트 가이드

> 개발은 macOS, 실제 운영은 Windows PC. 이 문서는 **Windows 카카오톡 실발송**을
> 검증하는 절차다. (ROADMAP task 1.8 / 1.10)

## 구조 다시 확인

서버(웹앱)와 발송 에이전트는 **분리**되어 있고 HTTP로만 통신한다.
따라서 **서버는 Mac에 그대로 두고, 에이전트만 Windows PC에서 돌리면** 된다.

```
  Mac (개발 PC)                     Windows PC (테스트)
 ┌──────────────────┐              ┌────────────────────┐
 │ 도커 웹앱 :8889   │◀──HTTP 폴링──│ 발송 에이전트        │
 │ DB · 발송 큐      │              │  → 카카오톡 조작     │
 └──────────────────┘              └────────────────────┘
   192.168.0.122                    같은 네트워크(같은 공유기)
```

---

## A. 준비 (Mac 쪽)

1. 웹앱이 떠 있어야 한다.
   ```bash
   cd dealflow && docker compose up -d
   ```
2. 포트가 `0.0.0.0:8889` 로 열려 있는지 확인 (`docker ps`). LAN에서 접근 가능해야 한다.
3. **Mac 방화벽**이 켜져 있으면 8889 인바운드를 허용해야 한다.
   시스템 설정 → 네트워크 → 방화벽 → 옵션.
4. Mac의 LAN IP 확인:
   ```bash
   ipconfig getifaddr en0        # 예: 192.168.0.122
   ```
5. Windows PC 브라우저에서 `http://<MacIP>:8889` 가 열리는지 먼저 확인.
   **안 열리면 그 다음 단계는 의미 없다** — 방화벽/같은 네트워크 여부부터 해결.

> 사무실 네트워크가 분리돼 있어 접근이 안 되면, 서버를 사내 서버/클라우드에 올린 뒤
> 그 주소를 쓰면 된다(배포 스프린트 참고).

---

## B. Windows PC 준비

1. **카카오톡 PC 버전 설치 + 로그인** (테스트할 계정으로)
2. **테스트용 채팅방 준비** — 실제 투자사 방으로 테스트하지 말 것.
   "나와의 채팅" 또는 본인만 있는 방을 쓴다. 방 제목을 정확히 메모해 둔다.
3. **Python 3.10+ 설치** (python.org, 설치 시 "Add to PATH" 체크)
4. 프로젝트 폴더 복사 (USB / 압축 / git 등 무엇이든)
5. 의존성 설치:
   ```bat
   cd dealflow
   python -m venv .venv-agent
   .venv-agent\Scripts\pip install -r requirements-agent-windows.txt
   ```

---

## C. 에이전트 실행

```bat
set DEALFLOW_SENDER=kakao_windows
set DEALFLOW_SERVER_URL=http://192.168.0.122:8889
set DEALFLOW_AGENT_TOKEN=agt_demo_token_sprint1
set DEALFLOW_POLL_INTERVAL=3
.venv-agent\Scripts\python -m agent.main --config agent\config.yaml
```

정상이면 로그에 다음이 찍힌다:
```
agent starting; server=http://192.168.0.122:8889 sender=kakao_windows
using KakaoDesktopSender (Windows)
```
웹 화면 하단 상태바도 **"발송 에이전트 연결됨"** 으로 바뀐다.

---

## D. 발송 테스트

1. Windows 브라우저에서 `http://<MacIP>:8889` 접속
2. **딜소개 보내기** → 기업 선택 → **테스트 방으로 만든 담당자**만 체크
3. 미리보기 확인 → **발송 목록 생성**
4. 카카오톡 창이 자동으로 움직이며 발송된다. **발송 중에는 PC를 건드리지 말 것.**
5. 카톡에 실제로 도착했는지 눈으로 확인

---

## E. 확인해야 할 체크리스트

macOS 실기 검증에서 실제로 걸렸던 항목들이다. Windows에서도 같은 함정이 있을 수 있다.

- [ ] **방 이름 정확 일치** — 시트에서 만든 이름과 실제 카톡방 제목이 같은가?
      (Mac에서 확인된 실제 방: `홍길동 대표님 Deal 공유 우리브이씨 Asset` — 투자사명이 없는 형태도 있음)
- [ ] **Ctrl+V 붙여넣기가 실제로 먹는가?** — macOS에서는 Cmd+V가 **안 먹어서**
      AX value 직접 설정으로 우회했다. Windows에서 안 되면 `_input_text` 검증이
      `input_not_filled` 로 잡아준다(전송은 안 됨).
- [ ] **검색 → Enter 로 방이 열리는가?** — macOS에서는 Enter/AXPress로 안 열려
      **실제 더블클릭**이 필요했다.
- [ ] **오발송 방지 동작** — 일부러 존재하지 않는 방 이름으로 1건 만들어
      `room_mismatch` 로 실패하고 **아무 방에도 안 보내는지** 확인 (가장 중요)
- [ ] **전송 검증** — 발송 후 입력창이 비워지는지(`send_not_confirmed` 안 뜨는지)
- [ ] 여러 건 연속 발송 시 지연(3~7초)이 지켜지는지

---

## F. 문제 생기면

- 로그: `agent_logs/` 아래 파일과 콘솔 출력
- 실패 사유는 웹 발송 진행 화면의 건별 로그에도 남는다
- 타이밍 문제(창이 늦게 뜸)면 `agent/config.yaml` 의 대기시간을 늘린다
  (`after_open_room`, `after_message_paste` 등 — 코드 수정 불필요)

---

## G. Windows PC가 없다면

| 방법 | 평가 |
|---|---|
| 팀원의 실제 Windows PC | ✅ **가장 권장** — 실제 운영 환경과 동일 |
| Mac에 Windows VM (Parallels 등) | △ 가능하나 Apple Silicon은 ARM Windows라 카톡(x86) 호환성 이슈 가능 |
| 클라우드 Windows(EC2 등) | ✗ 낯선 IP 로그인으로 카카오 보안 확인이 걸릴 수 있어 비권장 |

당장 Windows가 없으면 **macOS 에이전트(`kakao_mac`)로 기능 검증을 계속하고**,
Windows 검증은 팀원 PC가 확보될 때 이 문서대로 진행하면 된다.
로직(큐·문구·오발송 방지)은 두 센더가 공유하므로 대부분의 버그는 Mac에서 먼저 잡힌다.


---

## 실기 검증 결과 (2026-08, Windows 11 + 카카오톡 PC)

**결론: 실제 방으로 전송 성공.** 도달 과정에서 세 단계로 막혔고, 각각 원인이 달랐다.

| 증상 | 원인 | 해결 |
|---|---|---|
| `room_mismatch` | 카톡이 포커스를 못 얻은 상태로 Ctrl+F 를 눌러 **브라우저 검색창**에 방 이름이 입력됨. 방은 열리지 않음 | 포커스 확인 후에만 키 입력 (`_focus_verified`) |
| `focus_failed` | Windows 가 백그라운드 프로세스의 `SetForegroundWindow` 를 차단 | `_force_foreground()` — SW_RESTORE + AttachThreadInput + ALT 키 |
| — | — | ✅ 전송 성공 |

### 배운 것

1. **UI 자동화에서 포커스는 안전 문제다.** 포커스 없이 키를 누르면 그 키는 사라지는 게
   아니라 *다른 앱으로 간다*. 확인 없이 진행하면 엉뚱한 곳에 입력되고, 심하면 오발송이 된다.
   → 포커스가 확인되지 않으면 **아무 키도 누르지 않는다**.
2. **`set_focus()` 성공 != 창이 앞에 왔음.** 반드시 포그라운드 창 제목을 다시 읽어 확인한다.
3. **원격 진단이 필요하다.** 사용자 PC 는 접속할 수 없으므로 에이전트가 창 목록·포그라운드
   창·로그를 서버로 올린다(`POST /api/agent/diagnostics` → `data/agent_reports.log`).
   이 데이터가 없었으면 세 단계 모두 추측으로 헤맸을 것이다.

### 운영 시 주의

- 카카오톡을 **최소화하지 말고** 화면에 띄워둘 것
- 발송 중에는 **다른 창을 클릭하지 말 것** (포커스를 뺏으면 그 건이 실패 처리됨)
- 실패해도 오발송은 없다 — 방 제목 정확 일치 검사가 통과해야만 전송된다
