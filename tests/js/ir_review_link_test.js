// 딜 진행 관리의 `미팅 후기` 에서 투자사명을 누르면 **딜 제안 관리의
// `미팅 후기`** 로 넘어간다 — 그 담당자가 골라진 채로.
//
// 링크를 그리는 것은 화면(`app/templates/ir.html`)이고, 그 주소를 읽어
// 방식·담당자를 세팅하는 것은 여기 검사하는 `deals.js` 다. 주소가 맞아도
// 저쪽이 안 읽으면 빈 화면이 열리므로, **주소를 받은 쪽**을 본다.
// (`전달한 자료` 의 이름이 여는 `?mode=meeting` 과 같은 길이다 —
//  `tests/js/ir_sent_meeting_link_test.js`.)
//
//   node tests/js/ir_review_link_test.js
"use strict";
const assert = require("assert");
const deals_ = require("./_deals_dom.js");

// ── 1) 담당자가 골라진 채로, 미팅 후기 탭이 켜진 채로 열린다 ────────────────
{
  const dom = deals_.run(null, { search: "?mode=review&contacts=2" });

  assert.deepStrictEqual(deals_.checkedNames(dom), ["나담당"],
    "링크로 넘어온 담당자가 안 골라졌다: " + deals_.checkedNames(dom));

  const active = Array.prototype.slice
    .call(dom.document.querySelectorAll(".mode-tab"))
    .filter(function (b) { return b.classList.contains("active"); })
    .map(function (b) { return b.getAttribute("data-mode"); });
  assert.deepStrictEqual(active, ["review"],
    "미팅 후기 방식으로 안 열렸다: " + active);

  // 미팅 후기는 **기업 목록 없이 문구만** 나간다(`MODES_WITH_COMPANIES` 에
  // 없다). 기업 칸이 흐려져 있어야 "여기서 뭘 골라야 하나" 를 묻지 않는다.
  assert.ok(dom.companyPanel.classList.contains("dimmed"),
    "미팅 후기인데 기업 칸이 그대로 살아 있다");
}

// ── 2) 기업은 안 실려 온다 ────────────────────────────────────────────────
//
// 골라진 기업이 남아 있으면 거기서 탭을 딜 소개로 바꿨을 때 그것이 그대로 나간다.
{
  const dom = deals_.run(null, { search: "?mode=review&contacts=2" });
  const picked = dom.companyCards.filter(function (card) {
    return card.querySelector(".company-cb").checked;
  });
  assert.strictEqual(picked.length, 0, "미팅 후기인데 기업이 골라져 있다");
}

// ── 3) ★ 남의 담당자는 여전히 못 고른다 ────────────────────────────────────
//
// 발송 화면의 대상은 `내 담당` 보다 좁다 — 딜 소개 명단에 있고 카톡방 연결까지
// 끝난 사람만 선다. 주소에 번호를 실어 보내는 길이 하나 더 생겼다고 그 좁힘이
// 풀리면, 연결도 안 된 곳으로 문구가 나간다. 되돌릴 수 없는 일이라 못박는다.
{
  const dom = deals_.run(null, { search: "?mode=review&contacts=99" });

  assert.deepStrictEqual(deals_.checkedNames(dom), [],
    "목록 밖 번호로 사람이 골라졌다: " + deals_.checkedNames(dom));
  dom.blockedCbs.forEach(function (cb) {
    assert.ok(!cb.checked,
      "목록 밖 체크박스가 켜졌다: " + cb.getAttribute("data-name"));
  });

  // 못 골랐으면 **말한다** — 조용히 비워 두면 화면이 준비된 척을 한다.
  const warn = dom.document.getElementById("send-warnings");
  assert.ok(!warn.hidden, "못 고른 담당자를 두고 아무 말이 없다");
  assert.ok(/담당자 1명/.test(warn.innerHTML), warn.innerHTML);
}

// ── 4) ★ 여는 것으로는 **아무것도 안 나간다** ─────────────────────────────
//
// 이 저장소는 발송 앞에 사람을 세운다. 넘어온 주소가 곧 발송이 되면 투자사명을
// 누르는 것만으로 카톡이 나간다 — 되돌릴 수 없다.
{
  const fetch = deals_.fakeFetch([deals_.previewReply([])]);
  deals_.run(null, {
    fetch: fetch,
    search: "?mode=review&contacts=2",
    setTimeout: function (fn) { return fn && fn(); }   // 미리보기를 곧바로 부른다
  });
  const sent = fetch.calls.filter(function (c) {
    return String(c.url).indexOf("/api/deals/send") >= 0;
  });
  assert.strictEqual(sent.length, 0,
    "화면을 여는 것만으로 발송이 불렸다: " + JSON.stringify(fetch.calls));
  // 부른 것은 **미리보기**뿐이다 — 보여 주고 사람을 기다리는 자리다.
  assert.ok(fetch.calls.some(function (c) {
    return String(c.url).indexOf("/api/deals/preview") >= 0;
  }), "미리보기조차 안 불렀다: " + JSON.stringify(fetch.calls));
}

console.log("ir_review_link_test.js OK");
