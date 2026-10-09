// 스타트업 안내 카톡 — **고른 곳만, 보이는 곳만, 서버가 채운 글 그대로.**
// (node tests/js/startup_msg_test.js)
//
// 지킬 것:
//  1. 단추에 **몇 곳**인지 적힌다 — 고르기 전에는 눌리지 않는다.
//  2. 거르개(계약여부 · 검색)로 감춘 줄은 **체크가 풀린다** — 안 보이는 기업에
//     나가면 안 된다.
//  3. 못 고르는 줄(체크상자가 없는 줄)은 [전체 선택] 으로도 안 잡힌다.
//  4. [대기 목록 만들기] 가 보내는 것이 고른 줄 · 문구 · N일 그대로다.
//  5. 미리보기는 서버가 준 글을 **글자 그대로** 적는다(HTML 로 안 넣는다).
//
// 아이디·클래스가 실제 화면과 같은지는 파이썬 쪽이 본다
// (`tests/test_startup_outreach.py`).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

// 전부 지어낸 값이다 — 저장소가 공개다.
function row(id, contract, search, sendable) {
  const kids = [el("td", {}, sendable
    ? [el("input", { type: "checkbox", class: "msg-pick", value: String(id) })]
    : [])];
  return el("tr", { class: "msg-row", "data-id": String(id),
                    "data-contract": contract, "data-search": search }, kids);
}

function build(fetchImpl) {
  dom_.resetHandlers();
  const body = el("textarea", { id: "msg-body", "data-topic": "startup_msg_quote" });
  body.value = "안녕하세요 {대표명} 대표님.";
  const table = el("table", { id: "msg-table" }, [
    el("tbody", {}, [
      row(11, "미계약", "가나다랩스 홍길동", true),
      row(12, "계약검토중", "라마바랩스", true),
      row(13, "미계약", "사아자랩스 김철수", false)      // 최근 받음 — 못 고른다
    ])
  ]);
  const sendBtn = el("button", { id: "msg-send-btn", "data-days": "30" });
  const root = el("div", { class: "layout" }, [
    body, table,
    el("input", { type: "checkbox", id: "msg-all" }),
    el("select", { id: "msg-contract" }),
    el("input", { type: "search", id: "msg-search" }),
    el("input", { type: "text", id: "msg-title", value: "검사 회차" }),
    el("input", { type: "datetime-local", id: "msg-when" }),
    el("button", { id: "msg-preview-btn" }),
    sendBtn,
    el("p", { id: "msg-error" }),
    el("section", { id: "msg-preview" }, [
      el("span", { id: "msg-preview-note" }), el("div", { id: "msg-preview-list" })
    ])
  ]);
  const document = dom_.makeDocument(root);
  const calls = [];
  const win = { location: { search: "", href: "", reload: function () {} },
                confirm: function () { return true; } };
  const ctx = {
    document: document, console: console, window: win, JSON: JSON,
    fetch: function (url, opts) {
      calls.push({ url: url, body: JSON.parse(opts.body || "{}") });
      const data = fetchImpl ? fetchImpl(url) : {};
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve(data); } });
    },
    navigator: {}, setTimeout: function () { return 0; }, clearTimeout: function () {}
  };
  win.document = document;
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  vm.runInNewContext(fs.readFileSync(path.join(JS, "startup_msg.js"), "utf8"),
                     ctx, { filename: "startup_msg.js" });
  const pick = function (id) {
    return root.querySelectorAll(".msg-pick").filter(function (cb) {
      return cb.value === String(id);
    })[0];
  };
  return { root: root, document: document, win: win, calls: calls, sendBtn: sendBtn,
           pick: pick, rows: root.querySelectorAll("tr.msg-row"),
           byId: function (id) { return document.getElementById(id); } };
}

function check(s, id) {
  const cb = s.pick(id);
  cb.checked = true;
  cb.fire("change", { target: cb });
}

function flush() { return new Promise(function (r) { setImmediate(r); }); }

(async function main() {
  // ── 1. 단추에 몇 곳인지 ──────────────────────────────────────────────
  {
    const s = build();
    assert.strictEqual(s.sendBtn.disabled, true, "아무것도 안 골랐는데 눌린다");
    assert.strictEqual(s.sendBtn.textContent, "0곳 대기 목록 만들기");
    check(s, 11); check(s, 12);
    assert.strictEqual(s.sendBtn.textContent, "2곳 대기 목록 만들기");
    assert.strictEqual(s.sendBtn.disabled, false);
  }

  // ── 2. 감춘 줄은 체크가 풀린다 ─────────────────────────────────────────
  {
    const s = build();
    check(s, 11); check(s, 12);
    const sel = s.byId("msg-contract");
    sel.value = "미계약";
    sel.fire("change", { target: sel });
    assert.strictEqual(s.rows[1].hidden, true, "계약여부로 안 걸러졌다");
    assert.strictEqual(s.pick(12).checked, false,
      "감춘 줄의 체크가 남았다 — 안 보이는 기업에 나간다");
    assert.strictEqual(s.sendBtn.textContent, "1곳 대기 목록 만들기");

    sel.value = "";
    sel.fire("change", { target: sel });
    const q = s.byId("msg-search");
    q.value = "라마바";
    q.fire("input", { target: q });
    assert.strictEqual(s.rows[0].hidden, true, "검색으로 안 걸러졌다");
    assert.strictEqual(s.rows[1].hidden, false);
    assert.strictEqual(s.pick(11).checked, false);
  }

  // ── 3. [전체 선택] 은 고를 수 있는 줄만 ────────────────────────────────
  {
    const s = build();
    const all = s.byId("msg-all");
    all.checked = true;
    all.fire("change", { target: all });
    assert.strictEqual(s.sendBtn.textContent, "2곳 대기 목록 만들기",
      "못 고르는 줄까지 세었다");
  }

  // ── 4. 보내는 것이 고른 그대로 ─────────────────────────────────────────
  {
    const s = build(function () { return { job_id: 9, href: "/jobs/9" }; });
    check(s, 12);
    s.sendBtn.fire("click", { target: s.sendBtn });
    await flush(); await flush();
    assert.strictEqual(s.calls.length, 1);
    assert.strictEqual(s.calls[0].url, "/api/startup-msg/send");
    assert.deepStrictEqual(s.calls[0].body, {
      topic: "startup_msg_quote", body: "안녕하세요 {대표명} 대표님.",
      contact_ids: [12], days: 30, title: "검사 회차", scheduled_at: ""
    });
    assert.strictEqual(s.win.location.href, "/jobs/9", "진행 화면으로 안 갔다");
  }

  // ── 5. 미리보기는 서버가 준 글자 그대로 ───────────────────────────────
  {
    const msg = "안녕하세요 대표님.\n<b>굵게</b> 가 아니라 글자다";
    const s = build(function () {
      return { sample: false, previews: [{ contact_id: 11, firm: "가나다랩스",
                                          name: "홍길동", room: "방", message: msg }] };
    });
    check(s, 11);
    const btn = s.byId("msg-preview-btn");
    btn.fire("click", { target: btn });
    await flush(); await flush();
    assert.strictEqual(s.calls[0].url, "/api/startup-msg/preview");
    assert.deepStrictEqual(s.calls[0].body.contact_ids, [11]);
    const list = s.byId("msg-preview-list");
    assert.strictEqual(list.children.length, 1);
    const pre = list.children[0].children[1];
    assert.strictEqual(pre.textContent, msg, "서버가 준 글이 바뀌었다");
    assert.strictEqual(s.byId("msg-preview").hidden, false);
  }

  // ── 6. 표가 없는 화면에서는 아무 일도 하지 않는다 ──────────────────────
  {
    dom_.resetHandlers();
    const root = el("div", { class: "layout" });
    const ctx = {
      document: dom_.makeDocument(root), console: console,
      window: { location: { search: "", href: "" } }, navigator: {}
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "..", "app",
      "static", "js", "startup_msg.js"), "utf8"), ctx, { filename: "startup_msg.js" });
  }

  console.log("ok");
}()).catch(function (e) { console.error(e); process.exit(1); });
