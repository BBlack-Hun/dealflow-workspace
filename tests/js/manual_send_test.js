// 손으로 보낸 것 적기 — 브라우저 쪽. (node tests/js/manual_send_test.js)
//
// 이 칸이 하는 일은 **위 ①② 에서 고른 것을 그대로 서버로 보내는 것**이다.
// 여기서 다시 고르게 하면 고르는 목록이 두 벌이 되고, 둘 중 한쪽만 발송 대상
// 규칙(멈춘 사람 빼기 · 방 연결)을 따라가는 날이 온다.
//
// 못 박아야 하는 것이 넷이다.
//
//   1. **확인 전에는 아무 것도 안 적는다.** 서버를 `confirm: false` 로 먼저
//      부르고, 사람이 [확인] 을 눌러야 `confirm: true` 가 나간다. 취소하면
//      두 번째 부름이 아예 없다 — 있으면 확인창은 장식일 뿐이다.
//   2. **고른 기업과 사람이 그대로 실린다** — 기업은 고른 차례까지.
//      기업이 안 실리면 다음 회차에 LLM 이 같은 기업을 또 추천한다.
//   3. **날짜가 무엇을 뜻하는지 미리 말한다.** 오늘이면 리마인드가 잡히고
//      지난 날이면 기록만 남는다 — 적고 나서 알면 이미 늦다.
//   4. **되돌리기도 두 걸음이다.**
//
// 규칙을 옮겨 적어 검사하면 두 벌이 되어 어긋나도 모른다. 그래서
// `manual_send.js` 를 실제 화면 위에서 **그대로 실행**한다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const run = deals_.run;
const fakeFetch = deals_.fakeFetch;
const toggleCompany = deals_.toggleCompany;
const boxes = deals_.boxes;

const TODAY = "2026-09-15";
const LONG_AGO = "2026-09-01";

function open(opts) {
  opts = opts || {};
  opts.manual = true;
  return run(opts.people, opts);
}

function pickPeople(dom, names) {
  boxes(dom).forEach(function (cb) {
    if (names.indexOf(cb.getAttribute("data-name")) >= 0) {
      cb.checked = true;
      cb.fire("change");
    }
  });
}

function el(dom, id) { return dom.document.getElementById(id); }

// 적으러 간 부름만. 적고 나면 목록을 다시 받아 오는 GET 이 한 번 더 가는데,
// 그것까지 세면 "몇 번 불렀나" 가 어긋난다.
function posts(fetch) {
  return fetch.calls.filter(function (c) {
    return String(c.url) === "/api/deals/manual-sends" &&
           c.body.contact_ids !== undefined;
  });
}

// ── 1) 고른 사람이 없으면 단추가 안 눌린다 ──────────────────────────────────
{
  const dom = open();
  assert.strictEqual(el(dom, "manual-btn").disabled, true,
    "아무도 안 골랐는데 기록 단추가 눌린다");

  pickPeople(dom, ["가담당", "나담당"]);
  assert.strictEqual(el(dom, "manual-btn").disabled, false);
  assert.ok(el(dom, "manual-btn").textContent.indexOf("2명") >= 0,
    "몇 명이 걸린 일인지 단추가 말하지 않는다 — 80명과 8명은 다른 일이다");
}

// ── 2) ★ 확인 전에는 아무 것도 안 적는다 ────────────────────────────────────
{
  const asked = [];
  const fetch = fakeFetch([
    { ok: true, d: { plan: { total: 2, adding: 2, already: 0, day: TODAY,
                             kind_label: "딜 소개", companies: [], company_count: 0,
                             will_remind: true } } }
  ]);
  const dom = open({
    fetch: fetch,
    confirm: function (text) { asked.push(text); return false; }   // 취소
  });
  pickPeople(dom, ["가담당", "나담당"]);
  el(dom, "manual-btn").fire("click");

  const sent = posts(fetch);
  assert.strictEqual(sent.length, 1, "취소했는데 서버를 두 번 불렀다");
  assert.strictEqual(sent[0].body.confirm, false,
    "세어 보기도 전에 `confirm: true` 로 나갔다");
  assert.strictEqual(asked.length, 1, "확인창을 안 띄우고 지나갔다");
  assert.ok(asked[0].indexOf("리마인드가 함께 잡힙니다") >= 0,
    "리마인드가 서는지를 확인창이 말하지 않는다 — 이 기능의 절반이다");
}

// ── 3) ★ 고른 기업과 사람이 그대로, 고른 차례대로 실린다 ────────────────────
{
  const fetch = fakeFetch([
    { ok: true, d: { plan: { total: 2, adding: 2, already: 0, day: TODAY,
                             kind_label: "딜 소개", companies: ["마바로보", "가나애그"],
                             company_count: 2, will_remind: true } } },
    { ok: true, d: { added: 2, note: "2줄 적음 · 리마인드 2건 잡힘",
                     batch_key: "ms-1" } }
  ]);
  const dom = open({ fetch: fetch, confirm: function () { return true; } });

  // 3번째를 먼저, 1번째를 나중에 — 고른 차례가 곧 소개 차례다.
  toggleCompany(dom, "마바로보");
  toggleCompany(dom, "가나애그");
  pickPeople(dom, ["가담당", "다담당"]);
  el(dom, "manual-btn").fire("click");

  const sent = posts(fetch);
  assert.strictEqual(sent.length, 2, "확인했는데 참으로 적는 부름이 안 나갔다");
  assert.strictEqual(sent[1].body.confirm, true);
  assert.deepStrictEqual(sent[1].body.company_ids, [203, 201],
    "고른 차례가 사라졌다 — 소개 차례가 그 차례다");
  assert.deepStrictEqual(sent[1].body.contact_ids, [1, 3]);
  assert.strictEqual(sent[1].body.kind, "deal_intro");
  assert.strictEqual(sent[1].body.day, TODAY);
  // 결과 한 줄은 **서버가 지은 것을 그대로** 띄운다 — 두 벌이 되면 어긋나도 모른다.
  assert.strictEqual(el(dom, "manual-state").textContent,
    "2줄 적음 · 리마인드 2건 잡힘");
}

// ── 4) 기업을 안 골랐으면 [개수만] 칸이 열린다 ──────────────────────────────
//
// `핵심 딜 8개사` 처럼 이름 없이 개수만 적힌 회차가 시트에 실제로 있다.
{
  const fetch = fakeFetch([
    { ok: true, d: { plan: { total: 1, adding: 1, already: 0, day: TODAY,
                             kind_label: "딜 소개", companies: [], company_count: 8,
                             will_remind: true } } },
    { ok: true, d: { added: 1, note: "1줄 적음", batch_key: "ms-2" } }
  ]);
  const dom = open({ fetch: fetch, confirm: function () { return true; } });
  assert.strictEqual(el(dom, "manual-count").disabled, false,
    "기업을 안 골랐는데 [개수만] 칸이 잠겨 있다");

  el(dom, "manual-count").value = "8";
  pickPeople(dom, ["가담당"]);
  el(dom, "manual-btn").fire("click");
  assert.strictEqual(posts(fetch)[1].body.company_count, 8);

  // 기업을 고르면 그 칸은 잠긴다 — 고른 개수가 곧 답이다.
  toggleCompany(dom, "가나애그");
  assert.strictEqual(el(dom, "manual-count").disabled, true);
  assert.strictEqual(el(dom, "manual-count").value, "");
}

// ── 5) 미팅 요청은 기업을 안 적는다 ─────────────────────────────────────────
{
  const fetch = fakeFetch([
    { ok: true, d: { plan: { total: 1, adding: 1, already: 0, day: TODAY,
                             kind_label: "미팅 요청", companies: [],
                             company_count: 0, will_remind: true } } },
    { ok: true, d: { added: 1, note: "1줄 적음", batch_key: "ms-3" } }
  ]);
  const dom = open({ fetch: fetch, confirm: function () { return true; } });
  toggleCompany(dom, "가나애그");
  pickPeople(dom, ["가담당"]);
  el(dom, "manual-kind").value = "meeting_ask";
  el(dom, "manual-kind").fire("change");

  assert.strictEqual(el(dom, "manual-count").hidden, true,
    "미팅 요청인데 [개수만] 칸이 서 있다");
  el(dom, "manual-btn").fire("click");
  assert.deepStrictEqual(posts(fetch)[1].body.company_ids, [],
    "미팅 요청에 기업이 실렸다 — 나가는 카톡이 담당자당 한 통이다");
}

// ── 6) ★ 날짜가 무엇을 뜻하는지 **미리** 말한다 ─────────────────────────────
{
  const dom = open();
  const note = el(dom, "manual-note");
  assert.ok(note.textContent.indexOf("오늘 날짜입니다") >= 0,
    "오늘 날짜인데 리마인드가 잡힌다는 말이 없다");

  el(dom, "manual-day").value = LONG_AGO;
  el(dom, "manual-day").fire("change");
  assert.ok(note.textContent.indexOf("지난 날짜입니다") >= 0,
    "지난 날짜인데 기록만 남는다는 말이 없다 — 적고 나서 알면 늦다");
  // 서버가 준 안내문은 **지우지 않는다** — 규칙의 원문이 그 글자다.
  assert.ok(note.textContent.indexOf("리마인드가 잡힙니다") >= 0);
}

// ── 7) ★ 되돌리기도 두 걸음이다 ─────────────────────────────────────────────
{
  const batches = { batches: [
    { batch_key: "ms-9", kind_label: "딜 소개", day: TODAY, rows: 80,
      company_count: 8, undone: 0, is_undone: false },
    { batch_key: "ms-8", kind_label: "딜 소개", day: LONG_AGO, rows: 12,
      company_count: 0, undone: 12, is_undone: true }
  ] };
  // 목록은 GET 이라 가짜 서버의 POST 갈래를 안 지난다 — 여기서만 따로 받는다.
  const undoCalls = [];
  function settled(value) {
    return { __settled: true,
             then: function (fn) {
               const next = fn(value);
               return (next && next.__settled) ? next : settled(next);
             },
             catch: function () { return this; } };
  }
  const fetch = function (url, init) {
    if (!init || init.method !== "POST") {
      if (String(url).indexOf("/api/deals/manual-sends") === 0) {
        return settled({ ok: true, json: function () { return settled(batches); } });
      }
      return { then: function () { return this; }, catch: function () { return this; } };
    }
    undoCalls.push({ url: url, body: JSON.parse(init.body || "{}") });
    const plan = { rows: 80, kind_label: "딜 소개", day: TODAY };
    return settled({ ok: true,
                     json: function () { return settled({ plan: plan, undone: 80 }); } });
  };
  let asked = "";
  const dom = open({ fetch: fetch,
                     confirm: function (t) { asked = t; return true; } });

  const box = el(dom, "manual-batches");
  box.open = true;
  box.fire("toggle");

  const list = el(dom, "manual-batch-list");
  assert.strictEqual(list.children.length, 2, "적은 판 목록이 안 그려졌다");
  // **되돌린 판도 남는다** — 사라지면 되돌렸는지 안 적었는지를 알 수 없다.
  assert.ok(list.children[1].classList.contains("undone"));
  assert.strictEqual(list.children[1].querySelector("button"), null,
    "이미 되돌린 판에 [되돌리기] 가 또 서 있다");

  list.children[0].querySelector("button").fire("click");
  assert.strictEqual(undoCalls.length, 2, "되돌리기가 한 걸음으로 끝났다");
  assert.strictEqual(undoCalls[0].body.confirm, false);
  assert.strictEqual(undoCalls[1].body.confirm, true);
  assert.ok(asked.indexOf("80줄") >= 0, "몇 줄이 되돌아가는지 안 묻는다");
  assert.ok(asked.indexOf("숨깁니다") >= 0,
    "지우는 것이 아니라 숨기는 것임을 확인창이 말하지 않는다");
}

console.log("manual_send_test.js OK");
