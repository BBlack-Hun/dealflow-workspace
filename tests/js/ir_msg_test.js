// IR 기업현황 탭 — 💬 스타트업으로 카톡보내기 · 카톡방 찾기·확인 (11/11 · 이름은 i248).
// (node tests/js/ir_msg_test.js)
//
// 지킬 것:
//  1. 고르면 단추 · 여는 줄에 **몇 곳**인지 적히고, 처음 하나를 고르면 칸이 한 번 펴진다.
//     [대표 카톡방 맞추기] 링크는 고른 기업으로 연다.
//  2. [전체] 는 **보이는 줄만** 고르고, 거르개로 감춘 줄의 체크는 풀린다.
//  3. 미리보기는 서버에 묻고 **서버가 준 글자 그대로** 적는다(HTML 로 안 넣는다).
//     빠지는 곳은 까닭과 함께 적는다.
//  4. [대기 목록 만들기] 는 미리보기의 `ready_ids` **만** 싣는다 — 고른 것 전부가 아니다.
//  5. 미리보기 뒤에 고른 기업 · 문구 · 글이 바뀌면 다시 잠긴다.
//  6. 문구를 바꾸면 글 · 회차명 · 문구 표시가 함께 바뀐다(화면을 다시 받지 않는다).
//  7. [카톡방 찾기·확인] 은 고른 기업을 그대로 보낸다 — 진행 화면을 못 보면 맞추기 화면으로.
//  8. 묻고 아니라고 하면 아무것도 안 보낸다.
//
// 아이디 · 클래스가 실제 화면과 같은지는 파이썬 쪽이 본다(`tests/test_ir_outreach.py`).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

// 전부 지어낸 값이다 — 저장소가 공개다.
function row(id) {
  return el("tr", { "data-id": String(id) }, [
    el("td", { class: "stick stick-lead" }, [
      el("input", { type: "checkbox", class: "irm-pick", value: String(id) })
    ]),
    el("td", { class: "co-name" })
  ]);
}

function build(opts) {
  opts = opts || {};
  dom_.resetHandlers();
  const table = el("table", { id: "co-table" }, [
    el("thead", {}, [el("tr", {}, [el("th", {}, [
      el("input", { type: "checkbox", id: "irm-pick-all" })])])]),
    el("tbody", {}, [row(11), row(12), row(13)])
  ]);
  const body = el("textarea", { id: "irm-body", "data-topic": "startup_msg_progress" });
  body.value = "안녕하세요 {대표명} 대표님.";
  const panel = el("div", { id: "irm-panel", "data-sender": opts.sender == null ? "윤서아" : opts.sender,
                            "data-rooms-href": "/deals/startup-ir/rooms" }, [
    el("button", { id: "irm-room-check-btn" }),
    el("a", { id: "irm-rooms-link", href: "/deals/startup-ir/rooms" }),
    el("button", { class: "chip irm-topic active", "data-topic": "startup_msg_progress",
                   "data-body": "안녕하세요 {대표명} 대표님.", "data-title": "11월 2주 · 진행 문의" }),
    el("button", { class: "chip irm-topic", "data-topic": "startup_msg_quote",
                   "data-body": "견적서를 공유 드렸습니다.", "data-title": "11월 2주 · 견적서" }),
    body,
    el("input", { type: "number", id: "irm-days", value: "30" }),
    el("input", { type: "text", id: "irm-title", value: "11월 2주 · 진행 문의" }),
    el("input", { type: "datetime-local", id: "irm-when" }),
    el("button", { id: "irm-preview-btn" }),
    el("button", { id: "irm-send-btn" }),
    el("p", { id: "irm-error" }),
    el("section", { id: "irm-preview" }, [
      el("span", { id: "irm-preview-note" }),
      el("div", { id: "irm-preview-list" }),
      el("ul", { id: "irm-skipped-list" })
    ])
  ]);
  const fold = el("details", { id: "irm-fold" }, [el("span", { id: "irm-count" }), panel]);
  fold.open = false;
  const root = el("div", { class: "layout" }, [fold, table]);
  const document = dom_.makeDocument(root);
  const calls = [];
  const asked = [];
  const alerts = [];
  const win = {
    location: { search: "", href: "" },
    confirm: function (text) { asked.push(text); return opts.answer !== false; },
    alert: function (text) { alerts.push(text); }
  };
  const ctx = {
    document: document, console: console, window: win, JSON: JSON,
    fetch: function (url, o) {
      calls.push({ url: url, body: JSON.parse(o.body || "{}") });
      const reply = opts.reply ? opts.reply(url) : { ok: true, data: {} };
      return Promise.resolve({ ok: reply.ok, json: function () { return Promise.resolve(reply.data); } });
    },
    navigator: {}, setTimeout: function () { return 0; }, clearTimeout: function () {}
  };
  win.document = document;
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  vm.runInNewContext(fs.readFileSync(path.join(JS, "ir_msg.js"), "utf8"), ctx, { filename: "ir_msg.js" });
  return {
    root: root, win: win, calls: calls, asked: asked, alerts: alerts, fold: fold,
    byId: function (id) { return document.getElementById(id); },
    pick: function (id) {
      return root.querySelectorAll(".irm-pick").filter(function (cb) { return cb.value === String(id); })[0];
    },
    tr: function (id) {
      return root.querySelectorAll("tr").filter(function (t) { return t.getAttribute("data-id") === String(id); })[0];
    }
  };
}

function check(s, id, on) {
  const cb = s.pick(id);
  cb.checked = on !== false;
  cb.fire("change", { target: cb });
}
function click(node) { node.fire("click", { target: node }); }
function flush() { return new Promise(function (r) { setImmediate(r); }); }

const PREVIEW = {
  sample: false, sender: "윤서아", ready_ids: [11],
  previews: [{ company_id: 11, firm: "가나다랩스", name: "홍길동", room: "홍길동 대표 가나다랩스",
               last_date: "", message: "안녕하세요 홍길동 대표님.\n<b>굵게</b> 가 아니라 글자다" }],
  skipped: [{ company_id: 12, firm: "라마바랩스", group: "no_room", reason: "확인 안 됨", last_date: "" }]
};

(async function main() {
  // ── 1. 몇 곳인지 · 칸이 한 번 펴진다 · 맞추기 링크 ──────────────────────
  {
    const s = build();
    assert.strictEqual(s.byId("irm-room-check-btn").disabled, true, "아무것도 안 골랐는데 눌린다");
    assert.strictEqual(s.byId("irm-send-btn").disabled, true);
    assert.strictEqual(s.byId("irm-count").textContent, "0곳 선택");
    check(s, 11); check(s, 13);
    assert.strictEqual(s.byId("irm-count").textContent, "2곳 선택");
    assert.strictEqual(s.byId("irm-room-check-btn").textContent, "카톡방 찾기·확인 (2곳)");
    assert.strictEqual(s.byId("irm-room-check-btn").disabled, false);
    assert.strictEqual(s.byId("irm-preview-btn").textContent, "미리보기 (2곳)");
    assert.strictEqual(s.fold.open, true, "처음 고를 때 칸이 안 펴졌다");
    assert.strictEqual(s.byId("irm-rooms-link").getAttribute("href"),
                       "/deals/startup-ir/rooms?ids=11,13");
    // 사람이 접으면 그대로 둔다.
    s.fold.open = false;
    check(s, 12);
    assert.strictEqual(s.fold.open, false, "접어 둔 칸을 또 폈다");
  }

  // ── 2. [전체] 는 보이는 줄만 · 감춘 줄의 체크는 풀린다 ──────────────────
  {
    const s = build();
    s.tr(12).hidden = true;
    const all = s.byId("irm-pick-all");
    all.checked = true;
    all.fire("change", { target: all });
    assert.strictEqual(s.pick(12).checked, false, "감춘 줄까지 골랐다");
    assert.strictEqual(s.byId("irm-count").textContent, "2곳 선택");
    // 거르개가 줄을 감추면 companies.js 가 refresh 를 부른다.
    s.tr(11).hidden = true;
    s.win.DealflowIrMsg.refresh();
    assert.strictEqual(s.pick(11).checked, false, "감춘 줄의 체크가 남았다 — 안 보이는 기업에 나간다");
    assert.strictEqual(s.byId("irm-count").textContent, "1곳 선택");
  }

  // ── 3 · 4. 미리보기는 서버 글자 그대로 · 보내는 것은 ready_ids 만 ─────────
  {
    const s = build({ reply: function (url) {
      return url === "/api/ir-msg/preview" ? { ok: true, data: PREVIEW }
        : { ok: true, data: { job_id: 9, href: "/jobs/9" } };
    } });
    check(s, 11); check(s, 12);
    click(s.byId("irm-preview-btn"));
    await flush(); await flush();
    assert.strictEqual(s.calls[0].url, "/api/ir-msg/preview");
    assert.deepStrictEqual(s.calls[0].body, {
      topic: "startup_msg_progress", body: "안녕하세요 {대표명} 대표님.",
      company_ids: [11, 12], days: 30 });
    const list = s.byId("irm-preview-list");
    assert.strictEqual(list.children.length, 1);
    assert.strictEqual(list.children[1 - 1].children[1].textContent, PREVIEW.previews[0].message,
                       "서버가 준 글이 바뀌었다");
    const skipped = s.byId("irm-skipped-list");
    assert.strictEqual(skipped.children.length, 1);
    assert.ok(skipped.children[0].textContent.indexOf("확인 안 됨") >= 0, "빠지는 까닭이 없다");
    assert.ok(s.byId("irm-preview-note").textContent.indexOf("2곳 중 1곳") >= 0);
    const send = s.byId("irm-send-btn");
    assert.strictEqual(send.textContent, "1곳 대기 목록 만들기");
    assert.strictEqual(send.disabled, false);

    click(send);
    await flush(); await flush();
    assert.ok(s.asked[0].indexOf("윤서아 계정 PC") >= 0, "어느 PC 에서 나가는지 묻지 않았다");
    assert.strictEqual(s.calls[1].url, "/api/ir-msg/send");
    assert.deepStrictEqual(s.calls[1].body, {
      topic: "startup_msg_progress", body: "안녕하세요 {대표명} 대표님.",
      company_ids: [11], days: 30, title: "11월 2주 · 진행 문의", scheduled_at: "" },
      "미리보기에서 빠진 곳까지 실었다");
    assert.strictEqual(s.win.location.href, "/jobs/9", "진행 화면으로 안 갔다");
  }

  // ── 5. 미리보기 뒤에 바뀌면 다시 잠긴다 ──────────────────────────────────
  {
    const s = build({ reply: function () { return { ok: true, data: PREVIEW }; } });
    check(s, 11);
    const send = s.byId("irm-send-btn");
    for (const change of [
      function () { check(s, 13); },
      function () { const b = s.byId("irm-body"); b.value = "다른 글"; b.fire("input", { target: b }); },
      function () { const d = s.byId("irm-days"); d.value = "0"; d.fire("change", { target: d }); }
    ]) {
      click(s.byId("irm-preview-btn"));
      await flush(); await flush();
      assert.strictEqual(send.disabled, false);
      change();
      assert.strictEqual(send.disabled, true, "미리보기 뒤에 바뀌었는데 그대로 보낸다");
      assert.strictEqual(send.textContent, "미리보기를 먼저 보세요");
    }
  }

  // ── 6. 문구를 바꾸면 글 · 회차명 · 표시가 함께 ───────────────────────────
  {
    const s = build();
    const quote = s.root.querySelectorAll(".irm-topic")[1];
    click(quote);
    assert.strictEqual(s.byId("irm-body").value, "견적서를 공유 드렸습니다.");
    assert.strictEqual(s.byId("irm-body").getAttribute("data-topic"), "startup_msg_quote");
    assert.strictEqual(s.byId("irm-title").value, "11월 2주 · 견적서");
    assert.ok(quote.classList.contains("active"));
    assert.ok(!s.root.querySelectorAll(".irm-topic")[0].classList.contains("active"));
  }

  // ── 7. [카톡방 찾기·확인] — 고른 그대로 · 못 보면 맞추기 화면으로 ──────────
  {
    const s = build({ reply: function () {
      return { ok: true, data: { job_id: 4, total: 2, sender: "윤서아", href: "",
                                 rooms_href: "/deals/startup-ir/rooms?ids=11,12" } };
    } });
    check(s, 11); check(s, 12);
    click(s.byId("irm-room-check-btn"));
    await flush(); await flush();
    assert.strictEqual(s.calls[0].url, "/api/ir-rooms/check");
    assert.deepStrictEqual(s.calls[0].body, { company_ids: [11, 12] });
    assert.ok(s.asked[0].indexOf("그 이름 그대로") >= 0 && s.asked[0].indexOf("회사명으로") >= 0,
              "한 번에 무엇을 하는지(대조 · 찾기) 묻지 않았다");
    assert.ok(s.alerts[0].indexOf("윤서아 계정 PC") >= 0);
    assert.strictEqual(s.win.location.href, "/deals/startup-ir/rooms?ids=11,12");
  }
  {
    const s = build({ reply: function () {
      return { ok: true, data: { job_id: 4, total: 1, href: "/jobs/4", rooms_href: "x" } };
    } });
    check(s, 11);
    click(s.byId("irm-room-check-btn"));
    await flush(); await flush();
    assert.strictEqual(s.win.location.href, "/jobs/4", "볼 수 있는데 진행 화면으로 안 갔다");
    assert.strictEqual(s.alerts.length, 0);
  }

  // ── 8. 아니라고 하면 아무것도 안 보낸다 · 서버 거절은 그대로 적는다 ────────
  {
    const s = build({ answer: false });
    check(s, 11);
    click(s.byId("irm-room-check-btn"));
    await flush();
    assert.strictEqual(s.calls.length, 0, "묻고 아니라는데 보냈다");
  }
  {
    const s = build({ reply: function () {
      return { ok: false, data: { detail: "찾을 곳이 없습니다" } };
    } });
    check(s, 11);
    click(s.byId("irm-room-check-btn"));
    await flush(); await flush();
    assert.strictEqual(s.byId("irm-error").textContent, "찾을 곳이 없습니다");
    assert.strictEqual(s.win.location.href, "");
  }

  // ── 칸이 없는 화면(보내는 계정이 없다)에서는 아무 일도 하지 않는다 ─────────
  {
    dom_.resetHandlers();
    const root = el("div", {}, [el("table", { id: "co-table" })]);
    const win = { location: { search: "", href: "" } };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "..", "app", "static", "js",
      "ir_msg.js"), "utf8"), { document: dom_.makeDocument(root), window: win, console: console },
      { filename: "ir_msg.js" });
    assert.strictEqual(win.DealflowIrMsg, undefined);
  }

  console.log("ir_msg_test: ok");
})().catch(function (e) { console.error(e); process.exit(1); });
