// 담당자 상세의 활동 이력에서 **손으로 적은 한 줄**을 되돌린다.
// (node tests/js/contact_manual_undo_test.js)
//
// 못 박아야 하는 것이 넷이다.
//
//   1. **단추는 서버가 되돌릴 수 있다고 한 줄에만 선다**(`undoable` —
//      `manual_send.undoable`). 시트에서 온 줄에 서면 다음 가져오기 때 그
//      줄이 또 들어온다.
//   2. **두 걸음이다.** 먼저 `confirm: false` 로 무엇이 되돌아가는지 받아
//      묻고, 사람이 [확인] 을 눌러야 `confirm: true` 가 나간다. 취소하면 두
//      번째 부름이 아예 없다.
//   3. **그 담당자 줄만 실린다**(`contact_id`) — 묶음째 되돌리면 같은 날 함께
//      적은 79명이 다 사라진다.
//   4. **되돌린 뒤 창을 닫으면 표를 다시 받는다.** 표의 `최근 딜소개` 는 서버가
//      그 줄을 읽어 만든 값이라 안 그러면 옛것으로 남는다.
//
// 규칙을 파이썬으로 옮겨 적으면 두 벌이 되어 어긋나도 모른다 — contacts.js 를
// 가짜 화면 위에서 **그대로 실행**한다(contact_meeting_kind_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const src = fs.readFileSync(path.join(JS, "contacts.js"), "utf8");
const modalSrc = fs.readFileSync(path.join(JS, "panel_modal.js"), "utf8");

// 가상의 담당자다 — 저장소가 공개라 실제 이름·번호를 두지 않는다.
const CONTACT = {
  id: 7, name: "홍길동", title: "심사역", firm: "가나다벤처스",
  channel_kakao: 1, channel_email: 0
};
const KEY = "ms-2026-10-12-abcdef123456";

// 서버가 주는 모양 그대로(`routers/contacts._activity_view`).
const MANUAL = { kind: "deal_intro", date: "2026-10-12", month: "2026-10",
                 source: "manual", content: "딜 소개 — 손으로 보냄",
                 batch_key: KEY, undoable: true };
const IMPORTED = { kind: "deal_intro", date: "2026-09-02", month: "2026-09",
                   source: "import", content: "시트 줄",
                   batch_key: "", undoable: false };

function makeEl(id) {
  const attrs = {};
  const el = {
    id: id, value: "", checked: false, textContent: "", innerHTML: "",
    hidden: false, className: "", tagName: "DIV", handlers: {}, disabled: false,
    classList: {
      _on: new Set(),
      toggle(c, on) { if (on) this._on.add(c); else this._on.delete(c); },
      contains(c) { return this._on.has(c); },
      add(c) { this._on.add(c); }, remove(c) { this._on.delete(c); }
    },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    setAttribute(k, v) { attrs[k] = v; },
    hasAttribute(k) { return k in attrs; },
    addEventListener(type, fn) { (el.handlers[type] = el.handlers[type] || []).push(fn); },
    fire(type, ev) { (el.handlers[type] || []).forEach(function (fn) { fn(ev); }); },
    querySelector() { return makeEl("*"); },
    querySelectorAll() { return []; },
    closest() { return null; }
  };
  return el;
}

function makeDom() {
  const nodes = {};
  const table = nodes["contacts-table"] = makeEl("contacts-table");
  table.querySelectorAll = function () { return []; };
  table.querySelector = function () { return makeEl("tbody"); };

  const tabs = [makeEl("tab-info"), makeEl("tab-timeline")];
  tabs[0].setAttribute("data-tab", "info");
  tabs[1].setAttribute("data-tab", "timeline");
  const panels = [makeEl("panel-info"), makeEl("panel-timeline")];
  panels[0].setAttribute("data-panel", "info");
  panels[1].setAttribute("data-panel", "timeline");

  const document = {
    getElementById(id) { return nodes[id] || (nodes[id] = makeEl(id)); },
    querySelector(sel) {
      return sel && sel.charAt(0) === "#" ? this.getElementById(sel.slice(1)) : null;
    },
    addEventListener() {},
    querySelectorAll(sel) {
      if (sel === ".detail-tab") return tabs;
      if (sel === "[data-panel]") return panels;
      return [];
    },
    createElement(tag) { const e = makeEl(tag); e.tagName = tag.toUpperCase(); return e; }
  };
  document.getElementById("detail-panel").hidden = true;
  document.getElementById("detail-backdrop").hidden = true;
  return { document: document, nodes: nodes };
}

// `answers` — 확인창이 차례로 내놓을 답. 다 쓰면 `false`.
function run(answers) {
  const dom = makeDom();
  const state = { posts: [], asked: [], reloaded: 0, undone: false };
  const ok = function (body) {
    return Promise.resolve({ ok: true, json() { return Promise.resolve(body); } });
  };
  const ctx = {
    document: dom.document,
    console: console,
    alert(t) { throw new Error("알림이 떴다: " + t); },
    confirm(t) { state.asked.push(t); return answers.length ? answers.shift() : false; },
    MutationObserver: function () { this.observe = function () {}; },
    fetch(url, init) {
      if (init && init.method === "POST") {
        const body = JSON.parse(init.body || "{}");
        state.posts.push({ url: String(url), body: body });
        if (!body.confirm) {
          return ok({ ok: false, confirmed: false, undone: 0,
                      plan: { rows: 1, kind: "deal_intro", kind_label: "딜 소개",
                              day: "2026-10-12", sequences: 1 } });
        }
        state.undone = true;
        return ok({ ok: true, confirmed: true, undone: 1, sequences: 1,
                    note: "1줄을 되돌렸습니다 · 리마인드 1건을 거뒀습니다" });
      }
      // 되돌린 뒤에는 그 줄이 이력에서 빠진다(서버가 숨긴다).
      const timeline = state.undone ? [IMPORTED] : [MANUAL, IMPORTED];
      return ok({ contact: CONTACT, timeline: timeline });
    }
  };
  const win = {};
  ctx.window = win;
  Object.assign(win, ctx);
  win.location = { pathname: "/contacts", search: "",
                    reload() { state.reloaded += 1; } };
  win.DEALFLOW_OPEN_CONTACT = 7;
  vm.createContext(ctx);
  vm.runInContext(modalSrc, ctx, { filename: "panel_modal.js" });
  vm.runInContext(src, ctx, { filename: "contacts.js" });
  return { dom: dom, state: state };
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });
async function settle() { for (let i = 0; i < 6; i += 1) await flush(); }

// 목록에 붙은 단추를 누른다. 단추는 `innerHTML` 로 그려지므로 화면은 목록에
// 한 번 붙여 둔 손잡이로 받는다 — 여기서도 그 손잡이로 누른다.
function clickUndo(dom) {
  const btn = makeEl("tl-undo");
  btn.setAttribute("data-batch", KEY);
  dom.nodes["timeline"].fire("click", {
    target: { closest(sel) { return sel === ".tl-undo" ? btn : null; } }
  });
  return btn;
}

function undoButtons(html) {
  return html.split('class="linkbtn tl-undo"').length - 1;
}

async function main() {
  // ── 1) 단추는 손으로 적은 줄에만 ───────────────────────────────────────
  {
    const t = run([]);
    await settle();
    const html = t.dom.nodes["timeline"].innerHTML;
    assert.strictEqual(undoButtons(html), 1,
      "되돌리기 단추가 손으로 적은 줄 하나에만 서야 한다 — 지금 " + undoButtons(html));
    assert.ok(html.indexOf('data-batch="' + KEY + '"') >= 0,
      "단추에 그 줄의 묶음 표시가 안 실렸다 — 어느 판을 되돌릴지 모른다");
  }

  // ── 2) 취소하면 두 번째 부름이 없다 ────────────────────────────────────
  {
    const t = run([false]);
    await settle();
    const btn = clickUndo(t.dom);
    await settle();
    assert.strictEqual(t.state.posts.length, 1, "취소했는데 되돌리기가 나갔다");
    assert.strictEqual(t.state.posts[0].body.confirm, false);
    assert.strictEqual(btn.disabled, false, "취소한 뒤 단추가 잠긴 채로 남았다");
  }

  // ── 3) 확인하면 그 담당자 줄만 되돌리고, 닫을 때 표를 다시 받는다 ─────
  {
    const t = run([true]);
    await settle();
    clickUndo(t.dom);
    await settle();
    const posts = t.state.posts;
    assert.strictEqual(posts.length, 2, "되돌리기가 두 걸음이 아니다");
    assert.deepStrictEqual(posts.map(function (p) { return p.body.confirm; }),
                           [false, true]);
    posts.forEach(function (p) {
      assert.strictEqual(p.url, "/api/deals/manual-sends/" + KEY + "/undo",
        "묶음 되돌리기와 다른 길로 갔다 — 권한 판정이 두 벌이 된다");
      assert.strictEqual(p.body.contact_id, 7,
        "그 담당자만 실리지 않았다 — 같은 판의 다른 사람까지 되돌아간다");
    });
    const asked = t.state.asked[0] || "";
    assert.ok(asked.indexOf("리마인드") >= 0,
      "리마인드를 함께 거두는지 확인창이 말하지 않는다");
    assert.ok(asked.indexOf("다른 담당자 줄은 그대로") >= 0,
      "같은 판의 다른 사람은 그대로라는 말이 없다 — 묶음째 사라질까 겁낸다");

    // 이력이 다시 그려져 그 줄이 빠졌다.
    assert.strictEqual(undoButtons(t.dom.nodes["timeline"].innerHTML), 0,
      "되돌린 줄이 이력에 그대로 남아 있다");
    assert.ok(t.dom.nodes["detail-msg"].textContent.indexOf("리마인드 1건") >= 0,
      "서버가 지은 결과 글이 창에 안 떴다");

    assert.strictEqual(t.state.reloaded, 0, "되돌리자마자 창이 닫혀 버렸다");
    t.dom.nodes["detail-close"].fire("click");
    assert.strictEqual(t.state.reloaded, 1,
      "되돌린 뒤 창을 닫아도 표를 다시 받지 않는다 — `최근 딜소개` 가 옛것으로 남는다");
  }

  // ── 4) 아무것도 안 되돌렸으면 닫아도 다시 받지 않는다 ─────────────────
  {
    const t = run([]);
    await settle();
    t.dom.nodes["detail-close"].fire("click");
    assert.strictEqual(t.state.reloaded, 0, "한 일이 없는데 화면을 다시 받았다");
  }

  console.log("contact_manual_undo_test: 통과");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
