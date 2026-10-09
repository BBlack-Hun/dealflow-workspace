// 스타트업 카톡방 매칭 — **누른 줄, 누른 글자 그대로. 저절로는 아무것도.**
// (node tests/js/startup_room_pick_test.js)
//
// 지킬 것:
//  1. [이 방으로 확정] 은 **그 줄의 번호**로, **누른 제목 글자 그대로** 보낸다.
//  2. 확정 전에 묻고, 아니라고 하면 아무것도 안 보낸다.
//  3. [방 후보 찾기] 는 줄 번호 없이 보낸다 — 찾을 줄은 서버가 고른다.
//  4. 직접 적기 [저장] 은 수정창과 같은 길(`PATCH /api/contacts/{id}`)로 그 줄의
//     칸 글자를 보낸다.
//  5. [방 연결 확인] 은 적어 둔 줄 번호들을 투자사 화면과 같은 길로 보낸다.
//  6. 서버가 거절하면 그 까닭을 그대로 적는다.
//
// 아이디·클래스가 실제 화면과 같은지는 파이썬 쪽이 본다
// (`tests/test_startup_room_pick.py`).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

// 전부 지어낸 값이다 — 저장소가 공개다.
const ROOM_A = "홍길동 대표님가나다랩스 , 강민준 팀장";
const ROOM_B = "가나다랩스 투자유치 공유방";

function row(id, rooms, typed) {
  return el("tr", { class: "room-pick-row", "data-id": String(id) }, [
    el("td", {}, rooms.map(function (r) {
      return el("li", { class: "room-cand" }, [
        el("button", { type: "button", class: "linkbtn room-confirm",
                       "data-id": String(id), "data-room": r })
      ]);
    })),
    el("td", {}, [
      el("input", { type: "text", class: "room-input room-direct", "data-id": String(id),
                    value: typed || "" }),
      el("button", { type: "button", class: "linkbtn room-direct-save", "data-id": String(id) })
    ])
  ]);
}

function build(opts) {
  opts = opts || {};
  dom_.resetHandlers();
  const table = el("table", { id: "room-pick-table" }, [
    el("tbody", {}, [row(11, [ROOM_A, ROOM_B]), row(12, [ROOM_B], "김철수 대표님 라마바")])
  ]);
  const root = el("div", { class: "layout" }, [
    el("button", { id: "room-search-btn", "data-count": String(opts.count == null ? 3 : opts.count) }),
    el("button", { id: "room-verify-btn", "data-ids": "12,13" }),
    el("p", { id: "room-pick-error" }),
    table
  ]);
  const document = dom_.makeDocument(root);
  const calls = [];
  const asked = [];
  const win = {
    location: { href: "", reloaded: 0, reload: function () { this.reloaded += 1; } },
    confirm: function (text) { asked.push(text); return opts.answer !== false; },
    alert: function () {}
  };
  const ctx = {
    document: document, console: console, window: win, JSON: JSON,
    fetch: function (url, o) {
      calls.push({ url: url, method: o.method, body: JSON.parse(o.body || "{}") });
      const reply = opts.reply ? opts.reply(url) : { ok: true, data: { job_id: 7, href: "/jobs/7", room_ready: true } };
      return Promise.resolve({ ok: reply.ok, json: function () { return Promise.resolve(reply.data); } });
    },
    navigator: {}, setTimeout: function () { return 0; }, clearTimeout: function () {}
  };
  win.document = document;
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  vm.runInNewContext(fs.readFileSync(path.join(JS, "startup_room_pick.js"), "utf8"),
                     ctx, { filename: "startup_room_pick.js" });
  return {
    root: root, win: win, calls: calls, asked: asked,
    byId: function (id) { return document.getElementById(id); },
    confirmBtn: function (id, room) {
      return root.querySelectorAll(".room-confirm").filter(function (b) {
        return b.getAttribute("data-id") === String(id) && b.getAttribute("data-room") === room;
      })[0];
    },
    saveBtn: function (id) {
      return root.querySelectorAll(".room-direct-save").filter(function (b) {
        return b.getAttribute("data-id") === String(id);
      })[0];
    },
    input: function (id) {
      return root.querySelectorAll(".room-direct").filter(function (b) {
        return b.getAttribute("data-id") === String(id);
      })[0];
    }
  };
}

function click(node) { node.fire("click", { target: node }); }
function flush() { return new Promise(function (r) { setImmediate(r); }); }

(async function main() {
  // ── 1. 확정은 그 줄 · 그 글자 그대로 ──────────────────────────────────
  {
    const s = build();
    click(s.confirmBtn(11, ROOM_B));
    await flush(); await flush();
    assert.strictEqual(s.calls.length, 1);
    assert.strictEqual(s.calls[0].url, "/api/startup-rooms/11/confirm");
    assert.strictEqual(s.calls[0].method, "POST");
    assert.deepStrictEqual(s.calls[0].body, { room: ROOM_B },
      "누른 제목이 아닌 글자가 갔다");
    assert.ok(s.asked[0].indexOf(ROOM_B) >= 0, "어느 방인지 묻지 않았다");
    assert.strictEqual(s.win.location.reloaded, 1, "확정 뒤 화면을 다시 받지 않았다");
  }

  // ── 2. 아니라고 하면 아무것도 안 보낸다 ────────────────────────────────
  {
    const s = build({ answer: false });
    click(s.confirmBtn(11, ROOM_A));
    click(s.byId("room-search-btn"));
    await flush();
    assert.strictEqual(s.calls.length, 0, "묻고 아니라는데 보냈다");
  }

  // ── 3. 찾기는 줄 번호 없이 — 서버가 고른다 ──────────────────────────────
  {
    const s = build();
    click(s.byId("room-search-btn"));
    await flush(); await flush();
    assert.strictEqual(s.calls.length, 1);
    assert.strictEqual(s.calls[0].url, "/api/startup-rooms/search");
    assert.deepStrictEqual(s.calls[0].body, {});
    assert.strictEqual(s.win.location.href, "/jobs/7", "진행 화면으로 가지 않았다");
  }
  {
    const s = build({ count: 0 });
    click(s.byId("room-search-btn"));
    await flush();
    assert.strictEqual(s.calls.length, 0, "찾을 곳이 0곳인데 보냈다");
  }

  // ── 4. 직접 적기 — 수정창과 같은 길 · 그 줄의 칸 글자 ──────────────────
  {
    const s = build();
    s.input(12).value = "김철수 대표님 라마바랩스";
    click(s.saveBtn(12));
    await flush(); await flush();
    assert.strictEqual(s.calls.length, 1);
    assert.strictEqual(s.calls[0].url, "/api/contacts/12");
    assert.strictEqual(s.calls[0].method, "PATCH");
    assert.deepStrictEqual(s.calls[0].body, { kakao_room_name: "김철수 대표님 라마바랩스" });
    assert.strictEqual(s.asked.length, 0, "직접 적기는 묻지 않는다(되돌릴 수 있다)");
  }

  // ── 5. 방 연결 확인 — 투자사 화면과 같은 길 ─────────────────────────────
  {
    const s = build();
    click(s.byId("room-verify-btn"));
    await flush(); await flush();
    assert.strictEqual(s.calls[0].url, "/api/contacts/verify-rooms");
    assert.deepStrictEqual(s.calls[0].body, { contact_ids: [12, 13] });
  }

  // ── 6. 서버가 거절하면 그 까닭 그대로 ───────────────────────────────────
  {
    const s = build({ reply: function () {
      return { ok: false, data: { detail: "카톡에서 찾은 후보가 아닙니다" } };
    } });
    click(s.confirmBtn(11, ROOM_A));
    await flush(); await flush();
    assert.strictEqual(s.byId("room-pick-error").textContent, "카톡에서 찾은 후보가 아닙니다");
    assert.strictEqual(s.win.location.reloaded, 0);
    assert.strictEqual(s.confirmBtn(11, ROOM_A).disabled, false, "다시 누를 수 없게 됐다");
  }

  console.log("startup_room_pick_test: ok");
})().catch(function (e) { console.error(e); process.exit(1); });
