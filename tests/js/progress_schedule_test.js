// 진행 화면의 **예약 발송** 자리. (node tests/js/progress_schedule_test.js)
//
// 규칙을 옮겨 적어 검사하면 두 벌이 되어 어긋나도 모른다. 그래서 진짜
// `progress.js` 를 가짜 화면 위에서 **그대로 실행**한다.
//
// 이 검사가 지키는 것은 여섯이다.
//   ① 걸어 둔 예약이 **눈에 보인다** — 문장은 **서버가 만든 것 그대로**다.
//      화면이 지으면 두 벌이 되고, 그러면 화면과 서버가 다른 시각을 말한다.
//   ② 09~19시 밖은 **누르기 전에** 막는다 — 서버로 보내지도 않는다.
//      (서버도 따로 막는다 — `tests/test_scheduled_send.py`. 화면만 막으면 뚫린다.)
//   ③ [예약] 은 고른 시각을 그대로 보낸다.
//   ④ [예약 취소] 는 한 번 묻고, 아니라고 하면 **아무것도 안 보낸다.**
//   ⑤ 큐에 서 있는데 발송기가 없으면 **막힌 것이 아니라 서 있는 것**이라고 적는다.
//   ⑥ 2초 폴링이 **사람이 고치고 있는 시각 칸을 덮어쓰지 않는다** — 덮어쓰면
//      시각을 아예 못 고친다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("../js/_dom.js");
const el = dom_.el;

const JOB_ID = 42;

// 서버가 내려주는 예약 한 덩이(`services/scheduled_send.py: describe`).
function booking(over) {
  return Object.assign({
    at: "2099-03-12T14:00:00+09:00", input: "2099-03-12T14:00",
    label: "3/12(목) 14:00", state: "waiting",
    sentence: "3/12(목) 14:00 에 55명에게 나갑니다",
    count: 55, earliest: 9, latest: 19
  }, over || {});
}

function payload(over) {
  return Object.assign({
    id: JOB_ID, status: "draft", total: 55,
    counts: { pending: 55, sending: 0, sent: 0, failed: 0, canceled: 0 },
    started_at: null, finished_at: null, items: [],
    scheduled: booking(), agent: { online: true }
  }, over || {});
}

// `progress.html` 이 그려 두는 자리들. 아이디가 화면과 같아야 하는데, 그것은
// 파이썬 쪽이 따로 본다(가짜 화면 위에서는 아이디를 바꿔도 통과하기 때문).
function buildDom() {
  dom_.resetHandlers();
  const root = el("div", { class: "layout" }, [
    el("div", { class: "counters" }, [
      el("span", { id: "c-pending" }), el("span", { id: "c-sending" }),
      el("span", { id: "c-sent" }), el("span", { id: "c-failed" })
    ]),
    el("div", { class: "progress-actions" }, [
      el("span", { id: "job-status-badge" }),
      el("button", { id: "start-btn" }),
      el("button", { id: "cancel-btn" }),
      el("button", { id: "retry-btn" }),
      el("button", { id: "resend-canceled-btn" }),
      el("button", { id: "resume-btn" })
    ]),
    el("div", { class: "warn-box", id: "draft-note" }),
    el("div", { class: "schedule-box", id: "schedule-box" }, [
      el("p", { id: "schedule-note" }),
      el("div", { class: "schedule-pick" }, [
        el("input", { type: "datetime-local", id: "schedule-at" }),
        el("button", { id: "schedule-btn" }),
        el("button", { id: "unschedule-btn" })
      ]),
      el("p", { id: "schedule-hint" })
    ]),
    el("div", { class: "warn-box", id: "standing-note" }),
    el("tbody", { id: "log-body" })
  ]);
  return { document: dom_.makeDocument(root), root: root };
}

// 다 끝난 약속(진짜 Promise 처럼 `.then` 이 이어진다 — `_deals_dom.js` 와 같은 방식).
function settled(value) {
  return {
    __settled: true,
    then: function (fn) {
      const next = fn(value);
      return (next && next.__settled) ? next : settled(next);
    },
    catch: function () { return this; }
  };
}

// 서버 대역. **GET 은 지금 상태를 돌려주고**, 나머지(POST·DELETE)는 적어 둔다.
function fakeServer(state) {
  const calls = [];
  const fn = function (url, init) {
    const method = (init && init.method) || "GET";
    calls.push({ url: url, method: method,
                 body: JSON.parse((init && init.body) || "{}") });
    const reply = method === "GET" ? state.now : (state.reply || {});
    return settled({ ok: state.ok !== false,
                     json: function () { return settled(reply); } });
  };
  fn.calls = calls;
  // 예약 뒤의 폴링이 무엇을 볼지 바꿔 끼울 수 있게.
  fn.writes = function () {
    return calls.filter(function (c) { return c.method !== "GET"; });
  };
  return fn;
}

function run(data, opts) {
  opts = opts || {};
  const dom = buildDom();
  const state = { now: data, ok: opts.ok, reply: opts.reply };
  const fetch = fakeServer(state);
  const ticks = [];
  const said = [];
  const asked = [];
  const win = { DEALFLOW_JOB_ID: JOB_ID, DEALFLOW_JOB_VERIFY: false };
  const ctx = {
    document: dom.document, console: console, window: win, fetch: fetch,
    setInterval: function (fn) { ticks.push(fn); return ticks.length; },
    clearInterval: function () {},
    alert: function (m) { said.push(String(m)); },
    // 되돌릴 수 없는 일에는 기본값이 **아니오**다.
    confirm: function (m) { asked.push(String(m)); return opts.confirm === true; }
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, "..", "..", "app", "static", "js",
                              "progress.js"), "utf8"),
    ctx, { filename: "progress.js" });
  return {
    dom: dom, fetch: fetch, said: said, asked: asked, state: state,
    // 2초 폴링 한 번.
    tick: function () { ticks.forEach(function (fn) { fn(); }); },
    id: function (name) { return dom.document.getElementById(name); }
  };
}

// ── ① 걸어 둔 예약이 눈에 보인다 (문장은 서버 것 그대로) ────────────────────

(function theBookingIsOnTheScreen() {
  const s = run(payload());

  assert.strictEqual(s.id("schedule-box").hidden, false,
    "아직 안 나간 회차에는 예약 자리가 보여야 한다");
  assert.strictEqual(s.id("schedule-note").textContent,
    "3/12(목) 14:00 에 55명에게 나갑니다",
    "서버가 만든 문장을 **그대로** 적어야 한다 — 화면이 지으면 두 벌이 된다");
  assert.strictEqual(s.id("schedule-at").value, "2099-03-12T14:00",
    "걸어 둔 시각이 칸에 채워져 있어야 다시 고칠 수 있다");
  assert.strictEqual(s.id("schedule-btn").textContent, "시각 변경",
    "이미 걸어 둔 예약 위에서는 [예약] 이 아니라 [시각 변경] 이다");
  assert.strictEqual(s.id("unschedule-btn").hidden, false,
    "걸어 둔 예약은 뗄 수 있어야 한다");
})();

(function withoutABookingItAsksForOne() {
  const s = run(payload({ scheduled: booking({ state: "none", at: "", input: "",
                                               label: "", sentence: "", count: 0 }) }));

  assert.strictEqual(s.id("schedule-note").textContent, "",
    "예약이 없으면 예약 이야기를 하지 않는다");
  assert.strictEqual(s.id("schedule-btn").textContent, "예약");
  assert.strictEqual(s.id("unschedule-btn").hidden, true,
    "뗄 예약이 없는데 [예약 취소] 가 보이면 안 된다");
  assert.ok(s.id("schedule-hint").textContent.indexOf("9:00~19:00") >= 0,
    "고를 수 있는 폭을 말해 준다 — 그 숫자는 **서버가 준 값**이다");
})();

(function aMissedBookingStillOffersTheButton() {
  // 지나 버린 예약. **저절로 안 나간다** — 사람이 누를 수 있어야 한다.
  const s = run(payload({ scheduled: booking({
    state: "expired",
    sentence: "예약 시각이 지났습니다 (3/12(목) 14:00 · 55명에게) — 저절로 "
      + "나가지 않습니다. 보내려면 [발송 시작] 을 누르세요" }) }));

  assert.ok(s.id("schedule-note").textContent.indexOf("예약 시각이 지났습니다") >= 0,
    "지난 예약은 지났다고 말해야 한다 — 조용히 기다리는 것처럼 보이면 안 된다");
  assert.strictEqual(s.id("start-btn").hidden, false,
    "지나 버린 예약도 사람이 누르면 나간다 — 단추가 사라지면 보낼 길이 없다");
  assert.strictEqual(s.id("unschedule-btn").hidden, false,
    "지난 예약도 뗄 수 있어야 한다 — 안 그러면 그 줄이 영영 붙어 있는다");
})();

(function pressingSendNowSaysThereIsABooking() {
  const s = run(payload(), { confirm: false });
  s.id("start-btn").fire("click");

  assert.strictEqual(s.asked.length, 1, "누르기 전에 물어야 한다");
  assert.ok(s.asked[0].indexOf("3/12(목) 14:00") >= 0,
    "예약을 걸어 둔 회차를 지금 보내려는 것이라면 **그 사실**을 말해야 한다");
  assert.ok(s.asked[0].indexOf("55명") >= 0, "몇 명에게 가는지 함께 말한다");
  assert.strictEqual(s.fetch.writes().length, 0,
    "아니라고 했는데 나가면 확인창은 장식일 뿐이다");
})();

// ── ② 09~19 밖은 누르기 전에 막는다 ─────────────────────────────────────────

(function theWindowIsGuardedBeforeAnythingIsSent() {
  const s = run(payload({ scheduled: booking({ state: "none", input: "" }) }));
  s.id("schedule-at").value = "2099-03-12T21:00";
  s.id("schedule-btn").fire("click");

  assert.strictEqual(s.fetch.writes().length, 0,
    "고를 수 없는 시각은 서버로 보내지도 않는다");
  assert.ok(s.said.length === 1 && s.said[0].indexOf("9:00~19:00") >= 0,
    "왜 안 되는지를 그 자리에서 말해야 한다: " + s.said.join(" / "));
})();

(function anEmptyTimeIsNotABooking() {
  const s = run(payload({ scheduled: booking({ state: "none", input: "" }) }));
  s.id("schedule-btn").fire("click");

  assert.strictEqual(s.fetch.writes().length, 0);
  assert.strictEqual(s.said.length, 1, "빈 칸으로 예약을 걸 수는 없다");
})();

// ── ③ [예약] 은 고른 시각을 그대로 보낸다 ───────────────────────────────────

(function bookingSendsTheChosenTime() {
  const s = run(payload({ scheduled: booking({ state: "none", input: "" }) }));
  s.id("schedule-at").value = "2099-03-12T16:30";
  s.id("schedule-btn").fire("click");

  const wrote = s.fetch.writes();
  assert.strictEqual(wrote.length, 1);
  assert.strictEqual(wrote[0].url, "/api/jobs/" + JOB_ID + "/schedule");
  assert.strictEqual(wrote[0].method, "POST");
  assert.deepStrictEqual(wrote[0].body, { at: "2099-03-12T16:30" },
    "고른 시각을 그대로 보낸다 — 화면이 손대면 화면과 서버가 다른 시각을 안다");
  assert.strictEqual(s.said.length, 0, "막힐 이유가 없는 값이다");
})();

(function aRefusedBookingSaysWhy() {
  const s = run(payload({ scheduled: booking({ state: "none", input: "" }) }),
                { ok: false, reply: { detail: "이미 지난 시각입니다" } });
  s.id("schedule-at").value = "2099-03-12T10:00";
  s.id("schedule-btn").fire("click");

  assert.ok(s.said.length === 1 && s.said[0].indexOf("이미 지난 시각입니다") >= 0,
    "서버가 막았으면 **서버가 말한 까닭**이 떠야 한다: " + s.said.join(" / "));
})();

// ── ④ [예약 취소] 는 묻는다 ─────────────────────────────────────────────────

(function droppingABookingAsksFirst() {
  const s = run(payload(), { confirm: false });
  s.id("unschedule-btn").fire("click");

  assert.strictEqual(s.asked.length, 1, "한 번 물어야 한다");
  assert.strictEqual(s.fetch.writes().length, 0,
    "아니라고 했으면 아무것도 안 보낸다");
})();

(function droppingABookingCallsDelete() {
  const s = run(payload(), { confirm: true });
  s.id("unschedule-btn").fire("click");

  const wrote = s.fetch.writes();
  assert.strictEqual(wrote.length, 1);
  assert.strictEqual(wrote[0].url, "/api/jobs/" + JOB_ID + "/schedule");
  assert.strictEqual(wrote[0].method, "DELETE");
})();

// ── ⑤ 서 있는 것과 막힌 것 ──────────────────────────────────────────────────

(function aQueuedJobWithNoSenderIsStandingNotStuck() {
  const s = run(payload({ status: "queued", scheduled: booking({ state: "released" }),
                          agent: { online: false } }));

  assert.strictEqual(s.id("standing-note").hidden, false,
    "발송기가 없으면 왜 안 나가는지 화면이 말해야 한다");
  const text = s.id("standing-note").textContent;
  assert.ok(text.indexOf("막힌 것이 아닙니다") >= 0 && text.indexOf("기다립니다") >= 0,
    "막힌 것이 아니라 **서 있는 것**이라고 말해야 한다: " + text);
  assert.strictEqual(s.id("schedule-box").hidden, true,
    "이미 나간 회차에는 예약을 걸 자리가 없다 — 그쪽은 [중단] 이 맡는다");
})();

(function aQueuedJobWithASenderSaysNothingExtra() {
  const s = run(payload({ status: "queued", agent: { online: true } }));
  assert.strictEqual(s.id("standing-note").hidden, true,
    "발송기가 붙어 있으면 굳이 말할 것이 없다");
})();

// ── ⑥ 폴링이 고치고 있는 칸을 덮어쓰지 않는다 ───────────────────────────────

(function pollingDoesNotFightTheTypist() {
  const s = run(payload());
  // 사람이 시각을 고쳐 놓았다. 아직 [시각 변경] 을 누르지 않았다.
  s.id("schedule-at").value = "2099-03-12T16:30";
  s.tick();

  assert.strictEqual(s.id("schedule-at").value, "2099-03-12T16:30",
    "2초마다 값이 되돌아가면 시각을 아예 못 고친다");
})();

console.log("ok");
