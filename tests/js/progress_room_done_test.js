// 진행 화면 — **방 찾기 · 확인이 끝나면 한 번 알린다** (사용자 11/13: "방 찾기 완료 시 alert").
// (node tests/js/progress_room_done_test.js)
//
// 진짜 `progress.js` 를 가짜 화면 위에서 그대로 돌린다(`progress_schedule_test.js` 와 같은 틀).
// 지키는 것:
//   ① 열어 둔 동안 **진행 중 → 끝남**으로 바뀔 때만, 한 번 — 글은 서버가 준 그대로다.
//   ② 이미 끝난 회차를 **새로 열면** 아무것도 안 뜬다.
//   ③ **발송 회차**(서버가 `room_done` 을 안 싣는다)에는 아무것도 안 뜬다.
//   ④ 고를 화면이 있으면(`room-pick-link`) 알림창 대신 **갈지 묻고**, [확인] 이면 그리로 간다.
//      [취소] 여도 링크를 강조해 둔다. 고를 화면이 없는 갈래(투자사 방 연결 확인)는 알림창.
//   ⑤ 회사명으로 찾은 줄은 상태 칸에 서버가 준 결과 말(찾음 · 여럿 …)을 적는다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

const JOB_ID = 77;
const PICK_HREF = "/deals/startup-ir/rooms?ids=11,12";
const DONE_TEXT = "방 찾기가 끝났습니다 — 찾음 1 · 여럿 1 · 못 찾음 0";

function payload(over) {
  return Object.assign({
    id: JOB_ID, status: "queued", total: 2,
    counts: { pending: 2, sending: 0, sent: 0, failed: 0, canceled: 0 },
    items: [], scheduled: { state: "none" }, agent: { online: true }, room_done: null
  }, over || {});
}

function done(over) {
  return payload(Object.assign({
    status: "done_with_errors",
    counts: { pending: 0, sending: 0, sent: 1, failed: 1, canceled: 0 },
    room_done: { sentence: DONE_TEXT, pick: true }
  }, over || {}));
}

function run(first, opts) {
  opts = opts || {};
  dom_.resetHandlers();
  const kids = [
    el("span", { id: "c-pending" }), el("span", { id: "c-sending" }),
    el("span", { id: "c-sent" }), el("span", { id: "c-failed" }),
    el("span", { id: "job-status-badge" }),
    el("button", { id: "cancel-btn" }),
    el("tbody", { id: "log-body" })
  ];
  if (opts.link !== false) {
    kids.push(el("a", { id: "room-pick-link", href: PICK_HREF,
                        "data-label": "대표 카톡방 맞추기", class: "linkbtn" }));
  }
  const root = el("div", { class: "layout" }, kids);
  const document = dom_.makeDocument(root);
  const state = { now: first };
  const said = [], asked = [], ticks = [];
  const settled = function (value) {
    return { then: function (fn) { const next = fn(value); return next && next.then ? next : settled(next); },
             catch: function () { return this; } };
  };
  const win = { DEALFLOW_JOB_ID: JOB_ID, DEALFLOW_JOB_VERIFY: true,
                location: { href: "/jobs/" + JOB_ID } };
  const ctx = {
    document: document, console: console, window: win,
    fetch: function () { return settled({ ok: true, json: function () { return settled(state.now); } }); },
    setInterval: function (fn) { ticks.push(fn); return ticks.length; },
    clearInterval: function () {},
    alert: function (m) { said.push(String(m)); },
    confirm: function (m) { asked.push(String(m)); return opts.confirm === true; }
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, "..", "..", "app", "static", "js", "progress.js"), "utf8"),
    ctx, { filename: "progress.js" });
  return {
    said: said, asked: asked, win: win, document: document,
    // 서버 상태를 바꾸고 2초 폴링 한 번.
    next: function (data) { state.now = data; ticks.forEach(function (fn) { fn(); }); },
    link: function () { return document.getElementById("room-pick-link"); }
  };
}

// ── ① · ④ 진행 중 → 끝남, 고를 화면이 있으면 묻고 간다 ────────────────────
(function 끝나면_한_번_묻고_확인이면_간다() {
  const s = run(payload(), { confirm: true });
  assert.strictEqual(s.asked.length + s.said.length, 0, "진행 중인데 벌써 떴다");
  s.next(payload({ status: "running" }));
  assert.strictEqual(s.asked.length + s.said.length, 0, "아직 안 끝났다");
  s.next(done());
  assert.strictEqual(s.said.length, 0, "고를 화면이 있으면 알림창을 두 번 띄우지 않고 묻는 창 하나다");
  assert.strictEqual(s.asked.length, 1, "끝났는데 안 물었다");
  assert.ok(s.asked[0].indexOf(DONE_TEXT) === 0, "서버가 준 글 그대로여야 한다: " + s.asked[0]);
  assert.ok(s.asked[0].indexOf("대표 카톡방 맞추기") >= 0, "어느 화면으로 가는지 말해야 한다");
  assert.strictEqual(s.win.location.href, PICK_HREF, "[확인] 인데 고르는 화면으로 안 갔다");
  assert.ok(s.link().classList.contains("primary-btn"), "링크를 강조하지 않았다");

  // 끝난 뒤 한 번 더 물어도(폴링이 남아 있어도) 또 뜨지 않는다.
  s.next(done());
  assert.strictEqual(s.asked.length, 1, "한 번만 떠야 한다");
}());

(function 취소면_머물고_링크만_강조한다() {
  const s = run(payload(), { confirm: false });
  s.next(done());
  assert.strictEqual(s.asked.length, 1);
  assert.strictEqual(s.win.location.href, "/jobs/" + JOB_ID, "[취소] 인데 화면을 옮겼다");
  assert.ok(s.link().classList.contains("primary-btn"), "[취소] 여도 갈 길은 눈에 띄어야 한다");
}());

// ── ② 이미 끝난 회차를 새로 열면 안 뜬다 ───────────────────────────────────
(function 이미_끝난_회차는_조용하다() {
  const s = run(done(), { confirm: true });
  s.next(done());
  assert.strictEqual(s.asked.length + s.said.length, 0,
    "끝난 회차를 열 때마다 뜨면 진행 화면을 다시 볼 때마다 창을 닫아야 한다");
  assert.strictEqual(s.win.location.href, "/jobs/" + JOB_ID);
}());

// ── ③ 발송 회차에는 안 뜬다 ────────────────────────────────────────────────
(function 발송_회차는_조용하다() {
  const s = run(payload(), { confirm: true });
  s.next(done({ room_done: null }));
  assert.strictEqual(s.asked.length + s.said.length, 0, "발송 회차에 방 찾기 알림이 떴다");
}());

// ── ④ 고를 화면이 없는 갈래 — 알림창 하나 ─────────────────────────────────
(function 투자사_방_연결_확인은_알림창이다() {
  const text = "방 연결 확인이 끝났습니다 — 확인됨 3 · 불일치 1";
  const s = run(payload(), { link: false, confirm: true });
  s.next(done({ room_done: { sentence: text, pick: false } }));
  assert.deepStrictEqual(s.said, [text]);
  assert.strictEqual(s.asked.length, 0, "고를 화면이 없는데 갈지 물었다");
}());

(function 다시_돌리면_다시_알린다() {
  // [불일치 재확인] 으로 회차가 다시 돌고 또 끝났다 — 새로 끝난 것이다.
  const s = run(payload(), { link: false });
  const text = "방 연결 확인이 끝났습니다 — 확인됨 1 · 불일치 0";
  s.next(done({ room_done: { sentence: text, pick: false } }));
  s.next(payload({ status: "queued" }));
  s.next(done({ room_done: { sentence: text, pick: false } }));
  assert.strictEqual(s.said.length, 2);
}());

// ── ⑤ 상태 칸의 결과 말 ────────────────────────────────────────────────────
(function 회사명으로_찾은_줄은_결과_말을_적는다() {
  const s = run(done({ items: [
    { id: 1, contact_name: "", room_name: "", status: "failed", result: "여럿(후보 2)",
      retry_count: 0, error: "후보 2개 — 맞추기 화면에서 고르세요" },
    { id: 2, contact_name: "", room_name: "", status: "sent", result: null, retry_count: 0 }
  ] }));
  const html = s.document.getElementById("log-body").innerHTML;
  assert.ok(html.indexOf("여럿(후보 2)") >= 0, "결과 말이 안 섰다: " + html);
  assert.ok(html.indexOf("확인됨") >= 0, "결과 말이 없는 줄은 예전 말 그대로다");
}());

console.log("ok");
