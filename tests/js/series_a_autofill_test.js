// 딜 소싱 제안 › Series A 딜 공유의 [후보 자동 채우기] — 화면 쪽.
// (node tests/js/series_a_autofill_test.js)
//
// 여기서 못 박는 것.
//   ① 누르면 서버에서 새로 읽고(`/api/series-a-share/state`), 있던 체크를 지운 뒤
//      서버가 준 차례(`autofill.ids` — 투자유치 금액 높은 순)대로 체크한다.
//      그 차례가 곧 번호(`data-pick-order`)이고 미리보기의 `series_a_ids` 다
//   ② 금액이 빈 후보가 있으면 단추 옆에 그 수를 적는다(없으면 숨는다)
//   ③ 화면에 없는 번호(화면을 연 뒤에 생긴 줄)는 건너뛰고 번호가 비지 않는다
//   ④ IR 자료 전달에서는 단추 줄이 숨는다(`data-only="share"`)
//
// 차례를 정하는 규칙은 서버 한 곳이다(`series_a_share.autofill` — 파이썬 쪽
// `tests/test_series_a_share_autofill.py`). 이름은 전부 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const run = deals_.run;
const fakeFetch = deals_.fakeFetch;
const pickMode = deals_.pickMode;

const SHARE = "sourcing_deal_share";
const STATE = "/api/series-a-share/state";

function now(fn) { fn(); return 0; }
function pickTopic(dom, value) {
  dom.document.querySelector('#sourcing-topic .chip[data-value="' + value + '"]').fire("click");
}
function saCard(dom, id) {
  return dom.seriesACards.filter(function (c) {
    return c.querySelector(".sa-cb").value === String(id);
  })[0];
}
function checked(dom) {
  return dom.seriesACards
    .filter(function (c) { return c.querySelector(".sa-cb").checked; })
    .map(function (c) {
      return [parseInt(c.querySelector(".sa-cb").value, 10), c.getAttribute("data-pick-order")];
    })
    .sort(function (a, b) { return a[1] - b[1]; });
}
function calls(fetch, url) { return fetch.calls.filter(function (c) { return c.url === url; }); }
function lastPreview(fetch) { return calls(fetch, "/api/deals/preview").pop(); }

// --- ① 체크를 지우고 서버 차례대로 · ② 금액이 빈 곳 수 ----------------------------
{
  let state = { companies: [], autofill: { ids: [304, 302, 306], candidates: 3, blank: 1 } };
  const fetch = fakeFetch([], null, { [STATE]: function () { return state; } });
  const dom = run(null, { fetch: fetch, setTimeout: now });
  pickMode(dom, "sourcing");
  pickTopic(dom, SHARE);
  const note = dom.document.getElementById("sa-autofill-note");
  assert.strictEqual(note.hidden, false, "금액이 빈 후보가 있는데 말하지 않는다");
  assert.strictEqual(note.textContent, "후보 3곳 중 금액이 빈 곳 1곳");

  // 사람이 먼저 고른 것 — 누르면 지워진다.
  const cb301 = saCard(dom, 301).querySelector(".sa-cb");
  cb301.checked = true;
  cb301.fire("change");
  assert.deepStrictEqual(checked(dom), [[301, "1"]]);

  const before = calls(fetch, STATE).length;
  dom.document.getElementById("sa-autofill").fire("click");
  assert.strictEqual(calls(fetch, STATE).length, before + 1, "누를 때 서버에서 새로 읽지 않았다");
  assert.deepStrictEqual(checked(dom), [[304, "1"], [302, "2"], [306, "3"]],
                         "서버 차례대로 체크 · 번호가 서지 않았다");
  assert.deepStrictEqual(lastPreview(fetch).body.series_a_ids, [304, 302, 306],
                         "미리보기에 그 차례로 실리지 않았다");

  // 금액이 다 채워지면 말이 숨는다.
  state = { companies: [], autofill: { ids: [303], candidates: 1, blank: 0 } };
  dom.document.getElementById("sa-autofill").fire("click");
  assert.strictEqual(note.hidden, true);
  assert.deepStrictEqual(checked(dom), [[303, "1"]], "다시 누르면 앞의 체크를 지운다");
}

// --- ③ 화면에 없는 번호는 건너뛴다 ------------------------------------------------
{
  const fetch = fakeFetch([], null, {
    [STATE]: { companies: [], autofill: { ids: [999, 305, 301], candidates: 3, blank: 0 } } });
  const dom = run(null, { fetch: fetch, setTimeout: now });
  pickMode(dom, "sourcing");
  pickTopic(dom, SHARE);
  dom.document.getElementById("sa-autofill").fire("click");
  assert.deepStrictEqual(checked(dom), [[305, "1"], [301, "2"]]);
}

// --- ④ IR 자료 전달에서는 단추 줄이 숨는다 ----------------------------------------
{
  const dom = run(null, { fetch: fakeFetch([]), setTimeout: now });
  pickMode(dom, "sourcing");
  pickTopic(dom, SHARE);
  const line = dom.document.getElementById("sa-autofill-line");
  assert.strictEqual(line.hidden, false);
  pickMode(dom, "ir");
  assert.strictEqual(line.hidden, true, "자료 전달에서 단추가 보인다");
}

console.log("series_a_autofill_test: ok");
