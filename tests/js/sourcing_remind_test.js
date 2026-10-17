// 딜 소싱 제안의 [보낼 문구] · 이 달 딜 받음 제외 · 명단 다시 읽기.
// (node tests/js/sourcing_remind_test.js)
//
// 여기서 못 박는 것.
//   ① [월간 리마인드] 를 누르면 미리보기·발송이 `topic: sourcing_remind` 를
//      싣고, 처음 안내로 돌아오면 `sourcing_intro` 다
//   ② 리마인드는 **이 달 딜 받음**인 사람을 기본으로 뺀다 — 숨고, 체크가 꺼지고,
//      [전체선택]에도 안 걸린다. `이번 달 딜 받음 N명 제외` 를 말한다
//   ③ [이번 달 딜 받음 포함] 을 켜면 다시 고를 수 있고 `include_received` 가 실린다
//   ④ [딜 소싱 제안] 탭을 열면 명단을 다시 읽어(`/api/sourcing/state`) 담당 칩과
//      카드 값을 고친다 — 딜 소싱 메뉴에서 담당을 바꾼 것이 열어 둔 화면에도 선다
//
// 어느 글이 나가는지 · 누가 이 달 딜 받음인지는 서버가 정한다(파이썬 쪽
// `tests/test_sourcing_remind_manual.py`). 여기는 **화면이 그 값을 싣고 지키는가**만 본다.
// 이름은 전부 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const run = deals_.run;
const fakeFetch = deals_.fakeFetch;
const pickMode = deals_.pickMode;
const pickBucket = deals_.pickBucket;
const SOURCING = deals_.SOURCING;

const RECEIVED_NAME = "다소싱";            // _deals_dom.js 의 `data-received="1"`
const STATE_URL = "/api/sourcing/state";

function now(fn) { fn(); return 0; }

function setup(gets, opts) {
  const fetch = fakeFetch([], null, gets);
  const dom = run(null, Object.assign({ fetch: fetch, setTimeout: now }, opts || {}));
  pickMode(dom, "sourcing");
  return { dom: dom, fetch: fetch };
}

function pickTopic(dom, value) {
  const chip = dom.document.querySelector('#sourcing-topic .chip[data-value="' + value + '"]');
  assert.ok(chip, "[보낼 문구] 칩이 없다: " + value);
  chip.fire("click");
}

function card(dom, name) {
  return dom.sourcingCards.filter(function (c) {
    return c.querySelector(".contact-cb").getAttribute("data-name") === name;
  })[0];
}

function box(dom, name) { return card(dom, name).querySelector(".contact-cb"); }

function previews(fetch) {
  return fetch.calls.filter(function (c) { return c.url === "/api/deals/preview"; });
}

function selectAll(dom) { dom.document.getElementById("select-all-contacts").fire("click"); }

function checkedSourcing(dom) {
  return dom.sourcingCards.filter(function (c) { return c.querySelector(".contact-cb").checked; })
    .map(function (c) { return c.querySelector(".contact-cb").getAttribute("data-name"); })
    .sort();
}

// --- ① 고른 문구가 서버로 간다 ----------------------------------------------
{
  const t = setup();
  let last = previews(t.fetch).pop();
  assert.strictEqual(last.body.topic, "sourcing_intro", "처음 안내가 기본이어야 한다");

  pickTopic(t.dom, "sourcing_remind");
  last = previews(t.fetch).pop();
  assert.strictEqual(last.body.topic, "sourcing_remind",
                     "[월간 리마인드] 를 눌렀는데 미리보기가 리마인드를 안 물었다");
  assert.strictEqual(last.body.mode, "sourcing");

  pickTopic(t.dom, "sourcing_intro");
  last = previews(t.fetch).pop();
  assert.strictEqual(last.body.topic, "sourcing_intro", "처음 안내로 돌아오지 않는다");
  assert.strictEqual(card(t.dom, RECEIVED_NAME).hidden, false,
                     "처음 안내인데 이 달 딜 받음인 분이 빠졌다");
}

// --- ② 리마인드는 이 달 딜 받음을 뺀다 --------------------------------------
{
  const t = setup();
  selectAll(t.dom);                          // 처음 안내에서 셋 다 고른 채로
  assert.strictEqual(checkedSourcing(t.dom).length, SOURCING.length);

  pickTopic(t.dom, "sourcing_remind");
  assert.strictEqual(card(t.dom, RECEIVED_NAME).hidden, true,
                     "이 달 딜 받음인 분이 리마인드 목록에 그대로 보인다");
  assert.strictEqual(box(t.dom, RECEIVED_NAME).checked, false,
                     "숨기기만 하고 체크가 남았다 — 안 보이는 사람에게 나간다");
  assert.deepStrictEqual(previews(t.fetch).pop().body.contact_ids, [101, 102],
                         "뺀 사람이 미리보기 대상에 남았다");

  const note = t.dom.document.getElementById("received-note");
  assert.strictEqual(note.hidden, false, "몇 명을 뺐는지 말하지 않는다");
  assert.strictEqual(t.dom.document.getElementById("received-count").textContent,
                     "이번 달 딜 받음 1명 제외");

  // [전체선택] 을 다시 눌러도 뺀 사람에게는 안 걸린다.
  t.dom.document.getElementById("clear-all-contacts").fire("click");
  selectAll(t.dom);
  assert.deepStrictEqual(checkedSourcing(t.dom), ["가소싱", "나소싱"],
                         "[전체선택] 이 이 달 딜 받음인 분까지 골랐다");

  // 갈래로 좁히면 그 안의 수를 센다(M&A 갈래에는 딜 받음이 없다).
  pickBucket(t.dom, SOURCING[1][2]);
  assert.strictEqual(t.dom.document.getElementById("received-count").textContent,
                     "이번 달 딜 받음 0명 제외");
}

// --- ③ [이번 달 딜 받음 포함] -------------------------------------------------
{
  const confirms = [];
  const t = setup(null, { confirm: function (m) { confirms.push(m); return true; } });
  pickTopic(t.dom, "sourcing_remind");
  const include = t.dom.document.getElementById("include-received");
  include.checked = true;
  include.fire("change");

  assert.strictEqual(card(t.dom, RECEIVED_NAME).hidden, false, "포함을 켰는데 안 보인다");
  selectAll(t.dom);
  assert.deepStrictEqual(checkedSourcing(t.dom), ["가소싱", "나소싱", "다소싱"]);
  assert.ok(/1명 포함/.test(t.dom.document.getElementById("received-count").textContent),
            "포함을 켰는데 그 말을 안 한다");

  t.dom.document.getElementById("send-btn").fire("click");
  const sent = t.fetch.calls.filter(function (c) { return c.url === "/api/deals/send"; }).pop();
  assert.ok(sent, "발송 요청이 안 나갔다");
  assert.strictEqual(sent.body.topic, "sourcing_remind");
  assert.strictEqual(sent.body.include_received, true);
  assert.deepStrictEqual(sent.body.contact_ids.slice().sort(), [101, 102, 103]);
  assert.ok(/딜 소싱 리마인드/.test(confirms.pop()), "확인창이 무엇을 보내는지 말하지 않는다");

  // 포함을 다시 끄면 그 사람의 체크도 꺼진다.
  include.checked = false;
  include.fire("change");
  assert.strictEqual(box(t.dom, RECEIVED_NAME).checked, false);
}

// --- 탭을 바꾸면 처음 안내로 돌아간다 ---------------------------------------
{
  const t = setup();
  pickTopic(t.dom, "sourcing_remind");
  pickMode(t.dom, "deal");
  pickMode(t.dom, "sourcing");
  assert.strictEqual(previews(t.fetch).pop().body.topic, "sourcing_intro",
                     "다른 탭에 갔다 오면 [보낼 문구]가 처음 안내로 돌아와야 한다");
  assert.strictEqual(t.dom.document.getElementById("received-note").hidden, true);
}

// --- 링크로 바로 리마인드 ----------------------------------------------------
{
  const fetch = fakeFetch([]);
  const dom = run(null, { fetch: fetch, setTimeout: now,
                          search: "?mode=sourcing&topic=sourcing_remind" });
  assert.strictEqual(previews(fetch).pop().body.topic, "sourcing_remind");
}

// --- ④ 탭을 열면 명단을 다시 읽는다 ------------------------------------------
//
// 딜 소싱 메뉴에서 `가소싱` 의 담당을 `가담당 > 10/13 라담당` 으로 바꿨다 —
// 서버가 지금 담당 `라담당` 을 돌려준다. 열어 둔 화면에도 그 칩이 서야 한다.
{
  const state = {
    month: "2026-10", month_label: "10월",
    rows: [
      { id: 101, assignee: "라담당", received: true },
      { id: 102, assignee: "나담당", received: false },
      { id: 103, assignee: "가담당", received: false }
    ],
    assignees: [{ name: "가담당", count: 1 }, { name: "나담당", count: 1 },
                { name: "라담당", count: 1 }]
  };
  const gets = {};
  gets[STATE_URL] = state;
  const t = setup(gets);
  assert.ok(t.fetch.calls.some(function (c) { return c.url === STATE_URL; }),
            "[딜 소싱 제안] 탭을 열었는데 명단을 다시 읽지 않았다");

  assert.strictEqual(card(t.dom, "가소싱").getAttribute("data-assignee"), "라담당",
                     "새 담당이 카드에 안 섰다");
  const chip = t.dom.document.querySelector('#assignee-filter .chip[data-value="라담당"]');
  assert.ok(chip, "새 담당 칩이 안 섰다 — 딜 소싱에서 바꾼 담당이 안 보인다");
  chip.fire("click");
  const shown = t.dom.sourcingCards.filter(function (c) { return !c.hidden; })
    .map(function (c) { return c.querySelector(".contact-cb").getAttribute("data-name"); });
  assert.deepStrictEqual(shown, ["가소싱"], "새 담당 칩이 그 사람을 안 거른다");

  // 딜 받음도 다시 읽은 값이다 — 이제 가소싱이 받았고 다소싱은 아니다.
  t.dom.document.querySelector('#assignee-filter .chip[data-value=""]').fire("click");
  pickTopic(t.dom, "sourcing_remind");
  assert.strictEqual(card(t.dom, "가소싱").hidden, true);
  assert.strictEqual(card(t.dom, RECEIVED_NAME).hidden, false);
  assert.strictEqual(card(t.dom, "가소싱").querySelector(".received-tag").hidden, false);
}

// 고르던 담당이 사라지면 [전체]로 돌아간다 — 없는 칩이 켜진 채면 아무도 안 보인다.
{
  let state = {
    rows: SOURCING.map(function (s) { return { id: s[0], assignee: s[3], received: s[4] }; }),
    assignees: [{ name: "가담당", count: 2 }, { name: "나담당", count: 1 }]
  };
  const gets = {};
  gets[STATE_URL] = function () { return state; };
  const t = setup(gets);
  t.dom.document.querySelector('#assignee-filter .chip[data-value="나담당"]').fire("click");
  state = {
    rows: SOURCING.map(function (s) { return { id: s[0], assignee: "가담당", received: s[4] }; }),
    assignees: [{ name: "가담당", count: 3 }]
  };
  t.dom.root.fire("visibilitychange");     // 이 창으로 돌아왔다(문서까지 올라간다)
  assert.strictEqual(
    t.dom.document.querySelector('#assignee-filter .chip[data-value="나담당"]'), null,
    "없어진 담당 칩이 남았다");
  assert.strictEqual(
    t.dom.sourcingCards.filter(function (c) { return !c.hidden; }).length, SOURCING.length,
    "고르던 담당이 사라졌는데 [전체]로 안 돌아갔다");
}

// --- ⑤ 화면을 연 뒤에 `불참여` 가 된 분 — 처음 안내도 리마인드도 못 고른다 ----
//
// 딜 소싱 화면의 `참여` 칸이나 투자사 관리 현황의 `Series A 딜 소싱` 칸에서 X 로
// 두면 다시 읽을 때 `out` 이 선다(`/api/sourcing/state`). 리마인드의 `딜 받음`
// 과 달리 **켜는 칸이 없다** — 서버도 그 분께는 보내지 않는다(`OUT_NOTE`).
{
  const state = {
    rows: SOURCING.map(function (s) {
      return { id: s[0], assignee: s[3], received: s[4], out: s[0] === 101 };
    }),
    assignees: [{ name: "가담당", count: 1 }, { name: "나담당", count: 1 }]
  };
  const gets = {};
  gets[STATE_URL] = state;
  const t = setup(gets);
  const gone = card(t.dom, "가소싱");
  assert.strictEqual(gone.getAttribute("data-out"), "1", "다시 읽은 불참여가 카드에 안 섰다");
  assert.strictEqual(gone.hidden, true, "불참여인 분이 처음 안내 목록에 그대로 보인다");
  selectAll(t.dom);
  assert.deepStrictEqual(checkedSourcing(t.dom), ["나소싱", "다소싱"],
                         "[전체선택] 이 불참여인 분까지 골랐다");
  assert.deepStrictEqual(previews(t.fetch).pop().body.contact_ids.slice().sort(), [102, 103]);

  pickTopic(t.dom, "sourcing_remind");
  const include = t.dom.document.getElementById("include-received");
  include.checked = true;
  include.fire("change");
  assert.strictEqual(gone.hidden, true, "딜 받음 포함을 켰더니 불참여인 분이 돌아왔다");
  assert.strictEqual(box(t.dom, "가소싱").checked, false);
}

// --- ⑥ 화면을 연 뒤에 `참여 의사를 물어보는 중` 이 된 분 — 같이 빠지고 딱지가 다르다 ----
//
// 받는 것은 정확히 `참여` 인 분뿐이다(`sourcing_sync.takes_part`). 다시 읽은 줄의
// `out_label` 이 딱지 글자다 — 불참여와 사정이 달라 서버가 따로 짓는다.
{
  const LABEL = "참여 확인 전 · 참여 의사를 물어보는 중";
  const state = {
    rows: SOURCING.map(function (s) {
      return { id: s[0], assignee: s[3], received: s[4], out: s[0] === 102,
               out_label: s[0] === 102 ? LABEL : "" };
    }),
    assignees: [{ name: "가담당", count: 1 }, { name: "나담당", count: 1 }]
  };
  const gets = {};
  gets[STATE_URL] = state;
  const t = setup(gets);
  const asking = card(t.dom, "나소싱");
  assert.strictEqual(asking.getAttribute("data-out"), "1", "물어보는 중인 분이 고를 수 있게 남았다");
  assert.strictEqual(asking.hidden, true);
  const tag = asking.querySelector(".out-tag");
  assert.strictEqual(tag.hidden, false, "빠진 까닭 딱지가 안 섰다");
  assert.strictEqual(tag.textContent, LABEL, "불참여 딱지를 그대로 달았다 — 사정이 다르다");
  selectAll(t.dom);
  assert.ok(checkedSourcing(t.dom).indexOf("나소싱") === -1,
            "[전체선택] 이 물어보는 중인 분까지 골랐다");
}

console.log("ok - 딜 소싱 [보낼 문구] · 이 달 딜 받음 제외 · 명단 다시 읽기 · 불참여 · 확인 전 제외");
