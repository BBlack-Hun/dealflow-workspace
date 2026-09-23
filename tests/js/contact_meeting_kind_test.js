// 활동 이력에 **미팅 갈래 이름이 한글로** 서는가. (node tests/js/contact_meeting_kind_test.js)
//
// 미팅 한 칸(`meeting`)을 셋으로 갈랐다 — 요청·확정·완료
// (`app/services/meeting_kind.py`). 서버가 새 값을 실어 보내는데 화면의
// 이름표(`KIND_KO`)에 그 값이 없으면, 이력 줄에 **코드값이 그대로** 찍힌다
// (`meeting_request` · `meeting_done`). 조용히 틀리는 자리라 눈에 안 띈다 —
// 화면은 멀쩡히 그려지고 글자만 영어가 된다.
//
// 파이썬으로는 못 잰다. 이름표가 contacts.js 안에 있어서, 규칙을 여기 옮겨
// 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 실제로 돌리고**
// 그려진 글자를 읽는다(contacts_open_test.js 와 같은 방식).
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
  id: 7, name: "가상담당", title: "심사역", firm: "가상투자",
  channel_kakao: 1, channel_email: 0
};

// 서버가 주는 모양 그대로(`routers/contacts._activity_view`).
const TIMELINE = [
  { kind: "meeting_request", date: "2026-08-05", month: "2026-08", source: "import" },
  { kind: "meeting_set", date: "2026-09-03", month: "2026-09", source: "import" },
  { kind: "meeting_done", date: "2026-08-20", month: "2026-08", source: "import" },
  // 아직 안 가른 옛 줄. 그냥 `미팅` 이라고 선다.
  { kind: "meeting", date: "2026-07-11", month: "2026-07", source: "import" }
];

function makeEl(id) {
  const attrs = {};
  const el = {
    id: id, value: "", checked: false, textContent: "", innerHTML: "",
    hidden: false, className: "", tagName: "DIV", handlers: {},
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

function run() {
  const dom = makeDom();
  const ctx = {
    document: dom.document,
    console: console,
    alert() {}, confirm() { return false; },
    MutationObserver: function () { this.observe = function () {}; },
    fetch() {
      return Promise.resolve({
        ok: true,
        json() {
          return Promise.resolve({ contact: CONTACT, timeline: TIMELINE.slice() });
        }
      });
    }
  };
  const win = {};
  ctx.window = win;
  Object.assign(win, ctx);
  win.DEALFLOW_OPEN_CONTACT = 7;
  vm.createContext(ctx);
  vm.runInContext(modalSrc, ctx, { filename: "panel_modal.js" });
  vm.runInContext(src, ctx, { filename: "contacts.js" });
  return dom;
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });

async function main() {
  const dom = run();
  await flush();
  const html = dom.nodes["timeline"].innerHTML;

  // 코드값이 그대로 찍히면 안 된다.
  ["meeting_request", "meeting_set", "meeting_done"].forEach(function (code) {
    assert.ok(html.indexOf(">" + code + "<") < 0,
      "이력에 코드값 `" + code + "` 가 그대로 찍힌다 — contacts.js 의 KIND_KO 에 넣어라");
  });

  // 갈래마다 제 이름으로 선다.
  ["미팅 요청", "미팅 확정", "미팅 완료"].forEach(function (label) {
    assert.ok(html.indexOf(label) >= 0, "`" + label + "` 줄이 안 보인다");
  });

  // 아직 안 가른 옛 줄은 그냥 `미팅` 이다 — 없던 뜻을 지어내지 않는다.
  assert.ok(/>미팅</.test(html), "안 가른 옛 줄이 `미팅` 으로 안 선다");

  console.log("contact_meeting_kind_test: 통과");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
