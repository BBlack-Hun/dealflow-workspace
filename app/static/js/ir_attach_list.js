// [보낼 자료] 목록과 [문구 복사] — **두 화면이 같은 한 벌을 쓴다.**
//
// 딜 제안 관리(`deals.js`)와 IR 진행 관리의 [자료 보내기] 창(`ir_send.js`)이
// 똑같은 목록을 그리고 똑같은 복사 단추를 단다. 한쪽에 베껴 두면 번호를 적는
// 규칙이 두 벌이 되어, 고칠 때 한쪽만 고쳐진다 — 화면과 문구의 번호가 갈렸던
// 사고가 이 저장소에서 실제로 났다.
//
// 그리는 값은 **전부 서버 미리보기 응답**에서 온다(`/api/deals/preview` 의
// `previews[].attachments`). 여기서 세거나 짓는 것은 하나도 없다.
//
// ## 번호는 **화면이 셀 수 있는 값이 아니다**
//
// 자료를 붙이는 사람에게 알맹이는 **몇 번 기업인지**다 — 번호 차례대로 붙여야
// 하는데 화면에 안 적혀 있으면 어느 것이 몇 번인지 알 수가 없다.
//
// 그런데 그 번호는 **고른 차례가 아니다.** 딜 소개에서 붙은 번호이고
// (`app/services/deal_numbers.py`), 투자사가 "2번 주세요" 라고 답한 그 번호다.
// 담당자마다 다르다 — 같은 기업이 A 담당자에겐 2번, B 담당자에겐 5번일 수
// 있다. 그래서 **문구를 만든 그 함수**가 목록의 번호도 함께 낸다
// (`numbered_companies`). 화면이 따로 세면 목록은 `1`, 문구는 `2번 기업 …` 이
// 되어 어느 쪽이 맞는지 알 수 없다.
//
// 차례는 **여전히 고른 차례**다. 서버가 고른 차례로 실어 주고(`company_ids`),
// 문구도 그 차례로 짚는다 — 번호가 오름차순이 아닐 수 있다는 뜻이다
// ("3번 기업 다라헬스, 2번 기업 가나애그").
//
// 지난 회차에 없던 기업은 번호가 없다(`no` 가 `null`). **지어내지 않는다** —
// 문구도 그 기업만 이름으로 나가므로, 목록에는 번호 대신 `번호 없음` 이라고
// 적는다. 자리를 그냥 비우면 화면이 덜 그려진 것으로 읽힌다.
//
// ## 자료는 **파일 이름**으로 적는다 (링크가 아니다)
//
// 예전에는 구글 드라이브 링크라 `[자료 열기]` 로 열 수 있었다. 이제 그 칸에는
// **파일명**이 들어간다(0056) — 파일은 각자 PC 의 자료 폴더에 있어서 브라우저가
// 열 수 있는 자리가 아니다. `href` 를 억지로 만들면 깨진 링크나 (브라우저가
// 조용히 막는) `file://` 이 되어, 눌러도 아무 일이 없는 자리가 된다.
//
// 그래서 **이름을 그대로 보여 준다.** 자동 첨부를 켠 사람은 그 이름이 폴더에
// 있는지 눈으로 맞춰 보고, 켜지 않은 사람은 그 이름으로 파일을 찾아 PC 카톡에
// 붙인다. 어느 쪽이든 필요한 것은 **이름 그 자체**다.
"use strict";
(function () {
  var COPY_LABEL = "문구 복사";

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  // 미리보기 한 통(`preview`)의 자료 목록을 `list` 에 그리고, 번호가 왜 그렇게
  // 적혔는지를 `note` 에 적는다. 둘 다 화면이 넘겨준다 — 아이디로 찾지 않는
  // 것은 이 함수가 두 화면에서 돌기 때문이다(같은 아이디를 쓰지만 다른 페이지다).
  function renderList(list, note, preview) {
    if (!list) return;
    list.innerHTML = "";
    if (note) { note.hidden = true; note.textContent = ""; }
    var items = (preview && preview.attachments) || [];
    // 아직 아무도 안 고른 **기본 문구**에는 번호가 없다 — 번호는 담당자를
    // 알아야 나온다. 그것을 "지난 회차에 없는 기업" 과 같은 말로 적으면,
    // 있는 번호를 없다고 읽는다.
    var sample = !!(preview && preview.sample);
    var missing = 0;
    items.forEach(function (a) {
      var li = document.createElement("li");
      var badge;
      if (sample) badge = "";
      else if (a.no) badge = '<b class="ir-no">' + escapeHtml(String(a.no)) + '번</b> ';
      else { badge = '<span class="ir-no none">번호 없음</span> '; missing += 1; }
      // 이름·파일명은 **한 덩어리**로 싼다. 줄이 `flex` 라 안 싸면 글자와 파일명이
      // 각각 따로 서서 사이의 `—` 가 엉뚱한 자리로 밀린다.
      li.innerHTML = badge + '<span class="ir-body">' + (a.file
        ? escapeHtml(a.name) + " — <code>" + escapeHtml(a.file) + "</code>"
        : escapeHtml(a.name) +
          ' <span class="warn-text">— 첨부할 자료가 없습니다</span>') + '</span>';
      list.appendChild(li);
    });
    if (!list.children.length) {
      list.innerHTML = '<li class="muted">보낼 기업을 고르세요.</li>';
    }
    // 번호가 왜 그렇게 적혔는지 말해 준다. 안 적으면 "번호 없음" 을 고장으로
    // 읽거나, 담당자를 바꿔도 번호가 그대로인 줄 안다.
    if (note && items.length) {
      if (sample) {
        note.textContent = "담당자를 고르면 그 담당자가 받은 번호가 나옵니다.";
        note.hidden = false;
      } else if (missing) {
        note.textContent = "‘번호 없음’ 은 지난 딜 소개 목록에 없던 기업입니다 — "
          + "문구에도 번호 없이 이름만 나갑니다.";
        note.hidden = false;
      } else {
        note.textContent = "번호는 " + ((preview && preview.name) || "")
          + " 님이 받은 딜 소개 번호입니다 — 담당자를 바꾸면 번호도 바뀝니다.";
        note.hidden = false;
      }
    }
  }

  // 미리보기 문구를 클립보드로 — **문구를 사람이 손으로 보낼 때 쓴다.**
  //
  // 담는 것은 넘겨받은 칸의 값 그대로다(`ta.value` — 발송할 때 서버로 가는
  // 바로 그 문장이다). 머리말("○○ 심사역 · 💬 방이름 · 재연락")이나
  // "3통으로 나갑니다" 같은 안내는 **화면의 것**이라 섞이면 그것까지 붙는다.
  //
  // `navigator.clipboard` 는 https 나 localhost 가 아니면 **아예 없다.** 눌렀는데
  // 아무 일도 안 나면 복사된 줄 알고 빈 것을 붙여 넣는다. 그래서 세 겹으로 둔다:
  // 클립보드 → 옛 방식(`execCommand`) → 그마저 안 되면 **골라 두고 그렇게 말해
  // 준다**(llm_brief.js 가 쓰는 그 방식이다 — 복사 단추는 한 가지로만 둔다).
  function copyText(ta, btn) {
    function say(label) {
      btn.textContent = label;
      // 눌렀다는 것이 보여야 한다. 잠깐 뒤 원래 글자로 돌아온다.
      setTimeout(function () { btn.textContent = COPY_LABEL; }, 2000);
    }
    function fallback() {
      if (ta.focus) ta.focus();
      if (ta.select) ta.select();
      var ok = false;
      try { ok = !!(document.execCommand && document.execCommand("copy")); }
      catch (e) { ok = false; }
      say(ok ? "복사했습니다" : "Ctrl/⌘+C 로 복사하세요");
    }
    if (typeof navigator !== "undefined" && navigator.clipboard
        && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(ta.value).then(function () {
        say("복사했습니다");
      }, fallback);
    } else {
      fallback();
    }
  }

  // 브라우저에서는 `window` 가 곧 전역이라 `window.IrAttach` 로 닿는다.
  // 검사 하네스(`tests/js/_deals_dom.js`)는 `vm` 이라 전역과 `window` 가 다른
  // 물건인데, 쓰는 쪽도 `window.IrAttach` 로 읽으므로 양쪽에서 같이 돈다.
  var host = (typeof window !== "undefined") ? window : this;
  host.IrAttach = { renderList: renderList, copyText: copyText,
                    COPY_LABEL: COPY_LABEL, escapeHtml: escapeHtml };
}());
