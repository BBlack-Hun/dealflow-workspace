// 진행 화면 — **찾은 방 후보를 눌러 방 이름에 넣고 그 분만 다시 확인** (사용자 11/13).
// (node tests/js/progress_room_pick_test.js)
//
// 진짜 `progress.js` 를 가짜 화면 위에서 그대로 돌린다(`progress_room_done_test.js` 와 같은 틀).
// 지키는 것:
//   ① 서버가 `room_pick.rooms` 를 실은 건에만, 다루는 사람(`DEALFLOW_JOB_PICK`)에게만 단추.
//   ② 누르면 확인 창(제목을 그대로 보여 준다) → [확인] 이면 그 건 주소로 그 제목을 보낸다.
//      [취소] 면 아무것도 안 보낸다.
//   ③ 고른 건은 단추 대신 넣은 이름과 새 확인 회차 링크.
//   ④ 서버가 막으면(덮지 않음 · 남의 줄) 그 까닭을 알린다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

const JOB_ID = 77;
const LONG = "홍길동 심사역님 가나다벤처스 · 라마바파트너스 공동 투자 검토방 (2026 하반기 \"딜\" 공유)";

function payload(items) {
  return {
    id: JOB_ID, status: "done_with_errors", total: items.length,
    counts: { pending: 0, sending: 0, sent: 0, failed: items.length, canceled: 0 },
    items: items, scheduled: { state: "none" }, agent: { online: true }, room_done: null
  };
}

function failed(id, pick) {
  return { id: id, contact_name: "홍길동", room_name: "", status: "failed", retry_count: 0,
           error: "찾은 방이 여럿입니다 — 찾은 방: …", room_pick: pick };
}

function run(first, opts) {
  opts = opts || {};
  dom_.resetHandlers();
  const root = el("div", { class: "layout" }, [
    el("span", { id: "c-pending" }), el("span", { id: "c-sending" }),
    el("span", { id: "c-sent" }), el("span", { id: "c-failed" }),
    el("span", { id: "job-status-badge" }), el("tbody", { id: "log-body" })
  ]);
  const document = dom_.makeDocument(root);
  const state = { now: first };
  const said = [], asked = [], posts = [];
  const settled = function (value) {
    return { then: function (fn) { const next = fn(value); return next && next.then ? next : settled(next); },
             catch: function () { return this; } };
  };
  const answer = opts.answer || { ok: true, body: { ok: true, job_id: 91, href: "/jobs/91" } };
  const ctx = {
    document: document, console: console,
    window: { DEALFLOW_JOB_ID: JOB_ID, DEALFLOW_JOB_VERIFY: true,
              DEALFLOW_JOB_PICK: opts.pick !== false, location: { href: "/jobs/" + JOB_ID } },
    fetch: function (url, init) {
      if (init && init.method === "POST") {
        posts.push({ url: url, body: JSON.parse(init.body) });
        if (answer.ok && opts.after) state.now = opts.after;
        return settled({ ok: answer.ok, json: function () { return settled(answer.body); } });
      }
      return settled({ ok: true, json: function () { return settled(state.now); } });
    },
    setInterval: function () { return 1; },
    clearInterval: function () {},
    alert: function (m) { said.push(String(m)); },
    confirm: function (m) { asked.push(String(m)); return opts.confirm !== false; }
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, "..", "..", "app", "static", "js", "progress.js"), "utf8"),
    ctx, { filename: "progress.js" });
  return {
    said: said, asked: asked, posts: posts, document: document,
    html: function () { return document.getElementById("log-body").innerHTML; },
    button: function (id) { return document.getElementById(id); }
  };
}

const ROOMS = [LONG, "홍길동 이사님 사아파트너스"];

// ── ① 단추는 후보가 실린 건 · 다루는 사람에게만 ─────────────────────────────
(function 후보가_실린_건에_제목마다_단추() {
  const s = run(payload([
    failed(5, { rooms: ROOMS, picked: "", job_id: null, note: "" }),
    failed(6, null),
    { id: 7, contact_name: "김서연", room_name: "김서연 방", status: "sent", retry_count: 0,
      room_pick: null }
  ]));
  const html = s.html();
  assert.ok(s.button("room-pick-5-0") && s.button("room-pick-5-1"), "제목마다 단추가 서야 한다: " + html);
  assert.ok(s.button("room-pick-5-0").classList.contains("room-pick"));
  assert.ok(!s.button("room-pick-6-0") && !s.button("room-pick-7-0"),
    "후보가 없는 건 · 확인됨 건에는 단추가 없다");
  // 제목은 잘리지 않고 글자가 그대로(따옴표는 HTML 로 풀어서) 선다.
  assert.ok(html.indexOf("공동 투자 검토방 (2026 하반기 &quot;딜&quot; 공유)") >= 0, html);
  assert.ok(html.indexOf("찾은 방이 여럿입니다") >= 0, "사유 글은 그대로 위에 있다");
}());

(function 조회만_하는_화면에는_단추가_없다() {
  const s = run(payload([failed(5, { rooms: ROOMS, picked: "", job_id: null, note: "" })]),
                { pick: false });
  assert.ok(!s.button("room-pick-5-0"), "조회만 하는 사람에게 단추가 섰다");
}());

// ── ② 누르면 묻고 · 그 건 주소로 그 제목을 ───────────────────────────────────
(function 누르면_묻고_그_제목을_보낸다() {
  const after = payload([failed(5, { rooms: [], picked: LONG, job_id: 91, note: "" })]);
  const s = run(payload([failed(5, { rooms: ROOMS, picked: "", job_id: null, note: "" })]),
                { after: after });
  s.button("room-pick-5-0").fire("click");
  assert.strictEqual(s.asked.length, 1);
  assert.ok(s.asked[0].indexOf("이 방 이름으로 넣고 이 분만 다시 확인할까요?") === 0, s.asked[0]);
  assert.ok(s.asked[0].indexOf(LONG) >= 0, "확인 창에 넣을 제목이 통째로 보여야 한다");
  assert.deepStrictEqual(s.posts, [{ url: "/api/jobs/77/items/5/room-pick", body: { title: LONG } }]);
  assert.strictEqual(s.said.length, 0, "잘 됐으면 알림창 없이 그 자리에 링크가 선다");

  // ③ 다시 그린 줄 — 단추 대신 넣은 이름과 새 회차 링크.
  const html = s.html();
  assert.ok(!s.button("room-pick-5-0"), "고른 뒤에도 단추가 남았다");
  assert.ok(html.indexOf('href="/jobs/91"') >= 0 && html.indexOf("이 분만 다시 확인") >= 0, html);
  assert.ok(html.indexOf("넣은 방 이름") >= 0);
}());

(function 취소면_아무것도_안_보낸다() {
  const s = run(payload([failed(5, { rooms: ROOMS, picked: "", job_id: null, note: "" })]),
                { confirm: false });
  s.button("room-pick-5-1").fire("click");
  assert.strictEqual(s.asked.length, 1);
  assert.strictEqual(s.posts.length, 0, "[취소] 인데 보냈다");
}());

// ── ④ 서버가 막으면 까닭을 알린다 ─────────────────────────────────────────────
(function 막히면_까닭을_알린다() {
  const why = "찾는 사이 방 이름이 바뀌어 덮지 않았습니다(지금: '사람이 넣은 방')";
  const s = run(payload([failed(5, { rooms: ROOMS, picked: "", job_id: null, note: "" })]),
                { answer: { ok: false, body: { detail: why } } });
  s.button("room-pick-5-0").fire("click");
  assert.strictEqual(s.posts.length, 1);
  assert.strictEqual(s.said.length, 1);
  assert.ok(s.said[0].indexOf(why) >= 0, s.said[0]);
}());

(function 다시_확인을_못_세웠으면_그_말을_남긴다() {
  const note = "방 이름은 넣었지만 다시 확인을 세우지 못했습니다 — 동명이인인데 방 이름까지 같아";
  const after = payload([failed(5, { rooms: [], picked: ROOMS[1], job_id: null, note: note })]);
  const s = run(payload([failed(5, { rooms: ROOMS, picked: "", job_id: null, note: "" })]),
                { after: after, answer: { ok: true, body: { ok: true, job_id: null, note: note } } });
  s.button("room-pick-5-1").fire("click");
  assert.deepStrictEqual(s.said, [note]);
  const html = s.html();
  assert.ok(html.indexOf(note) >= 0 && html.indexOf('href="/jobs/') < 0, html);
}());

console.log("ok");
