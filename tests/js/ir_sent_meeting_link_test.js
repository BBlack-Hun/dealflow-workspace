// IR 진행 관리의 `전달한 자료` 에서 투자사명을 누르면 **딜 제안 관리의
// `미팅 요청`** 으로 넘어간다 — 그 담당자가 골라진 채로.
//
// 링크를 그리는 것은 화면(`app/templates/ir.html`)이고, 그 주소를 읽어
// 방식·담당자를 세팅하는 것은 여기 검사하는 `deals.js` 다. 주소가 맞아도
// 저쪽이 안 읽으면 빈 화면이 열리므로, **주소를 받은 쪽**을 본다.
//
//   node tests/js/ir_sent_meeting_link_test.js
"use strict";
const assert = require("assert");
const deals_ = require("./_deals_dom.js");

// ── 1) 담당자가 골라진 채로, 미팅 요청 탭이 켜진 채로 열린다 ────────────────
{
  const dom = deals_.run(null, { search: "?mode=meeting&contacts=2" });

  assert.deepStrictEqual(deals_.checkedNames(dom), ["나담당"],
    "링크로 넘어온 담당자가 안 골라졌다: " + deals_.checkedNames(dom));

  const active = Array.prototype.slice
    .call(dom.document.querySelectorAll(".mode-tab"))
    .filter(function (b) { return b.classList.contains("active"); })
    .map(function (b) { return b.getAttribute("data-mode"); });
  assert.deepStrictEqual(active, ["meeting"],
    "미팅 요청 방식으로 안 열렸다: " + active);

  // 미팅 요청은 **기업 목록 없이 문구만** 나간다. 기업 칸이 흐려져 있어야
  // "여기서 뭘 골라야 하나" 를 묻지 않는다(`MODES_WITH_COMPANIES` 와 짝).
  assert.ok(dom.companyPanel.classList.contains("dimmed"),
    "미팅 요청인데 기업 칸이 그대로 살아 있다");
}

// ── 2) 기업은 안 실려 온다 — 실려 와도 고른 것이 남지 않아야 하나? ──────────
//
// 안 싣기로 했으니 여기서는 **아무 기업도 안 골라진 채**로 열리는지만 본다.
// 골라진 기업이 남아 있으면 거기서 탭을 딜 소개로 바꿨을 때 그것이 그대로 나간다.
{
  const dom = deals_.run(null, { search: "?mode=meeting&contacts=2" });
  const picked = dom.companyCards.filter(function (card) {
    return card.querySelector(".company-cb").checked;
  });
  assert.strictEqual(picked.length, 0, "미팅 요청인데 기업이 골라져 있다");
}

// ── 3) ★ 남의 담당자는 여전히 못 고른다 ────────────────────────────────────
//
// 발송 화면의 대상은 `내 담당` 보다 좁다 — 딜 소개 명단에 있고 카톡방 연결까지
// 끝난 사람만 선다. 주소에 번호를 실어 보내는 길이 생겼다고 그 좁힘이 풀리면,
// 연결도 안 된 곳으로 문구가 나간다. 되돌릴 수 없는 일이라 못박는다.
//
// `99` 는 목록 **밖**(연결이 안 끝나 접혀 있는 칸)의 체크박스다.
{
  const dom = deals_.run(null, { search: "?mode=meeting&contacts=99" });

  assert.deepStrictEqual(deals_.checkedNames(dom), [],
    "목록 밖 번호로 사람이 골라졌다: " + deals_.checkedNames(dom));
  dom.blockedCbs.forEach(function (cb) {
    assert.ok(!cb.checked,
      "목록 밖 체크박스가 켜졌다: " + cb.getAttribute("data-name"));
  });
}

// ── 4) 못 골랐으면 **말한다** ──────────────────────────────────────────────
//
// 조용히 아무도 안 골라 두면 화면은 준비된 척을 하고, 사람은 왜 비었는지 모른 채
// 이름을 찾아 헤맨다. 담당이 넘어간 뒤의 줄에서 넘어오면 실제로 그렇게 된다.
{
  const dom = deals_.run(null, { search: "?mode=meeting&contacts=99" });
  const warn = dom.document.getElementById("send-warnings");

  assert.ok(!warn.hidden, "못 고른 담당자를 두고 아무 말이 없다");
  assert.ok(/담당자 1명/.test(warn.innerHTML),
    "몇 명을 못 골랐는지 안 적었다: " + warn.innerHTML);
}

// ── 5) 다 골랐으면 아무 말도 안 한다 ───────────────────────────────────────
{
  const dom = deals_.run(null, { search: "?mode=meeting&contacts=1,3" });
  const warn = dom.document.getElementById("send-warnings");

  assert.deepStrictEqual(deals_.checkedNames(dom), ["가담당", "다담당"],
    deals_.checkedNames(dom).join(","));
  assert.ok(warn.hidden, "다 골랐는데 경고가 떴다: " + warn.innerHTML);
}

// ── 6) ★ 그 말이 **한 박자 뒤에 사라지지 않는다** ─────────────────────────
//
// 화면을 열면 곧바로 미리보기를 부르고, 그 응답이 경고 칸을 통째로 다시 쓴다.
// 못 골랐다는 말을 그 칸에 그냥 적어 두면 응답이 오는 순간 지워져, 사람 눈에는
// 아무 말도 없었던 것과 같다 — 실제로 그랬다(브라우저에서 확인).
{
  const fetch = deals_.fakeFetch([deals_.previewReply([])]);
  const dom = deals_.run(null, {
    fetch: fetch,
    search: "?mode=meeting&contacts=99",
    setTimeout: function (fn) { return fn && fn(); }   // 미리보기를 곧바로 부른다
  });
  const warn = dom.document.getElementById("send-warnings");

  assert.ok(!warn.hidden,
    "미리보기가 오자 못 고른 담당자 얘기가 사라졌다: " + warn.innerHTML);
  assert.ok(/담당자 1명/.test(warn.innerHTML), warn.innerHTML);
}

// ── 7) 사람이 방식을 직접 바꾸면 그 말은 지운다 ────────────────────────────
{
  const dom = deals_.run(null, { search: "?mode=meeting&contacts=99" });
  deals_.pickMode(dom, "remind");
  const warn = dom.document.getElementById("send-warnings");

  assert.ok(warn.hidden, "탭을 바꿨는데 넘어올 때의 경고가 남아 있다: " + warn.innerHTML);
}

console.log("ir_sent_meeting_link_test.js OK");
