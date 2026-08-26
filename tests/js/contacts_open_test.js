// 링크로 들어왔을 때 담당자 상세가 실제로 열리는가. (node tests/js/contacts_open_test.js)
//
// 대시보드 '내 투자사 선호'에서 사람을 누르면 /contacts?contact=<id> 로 온다.
// 화면은 window.DEALFLOW_OPEN_CONTACT 에 그 번호를 적어 두고, contacts.js 가
// 그것을 보고 상세를 연다. 그런데 그 몇 줄이 **상세 패널과 다른 IIFE** 에 떨어져
// 있어서 loadContact 이라는 이름이 닿지 않았다 — ReferenceError 로 죽고, 화면에는
// 목록만 덩그러니 남았다(오류는 콘솔에만 있어 눈에 안 띈다).
//
// `<script>` 태그가 그려지는지만 보는 검사로는 못 잡는다. 그래서 여기서는
// **파일을 실제로 실행**한다. contacts.js 는 DOM 에 매여 있으므로 이 파일이 쓰는
// 만큼만 가짜 DOM 을 세워 두고 vm 으로 돌린다 — 이름이 안 닿으면 그 자리에서 터진다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "contacts.js");
const src = fs.readFileSync(SRC, "utf8");

// 가상의 담당자다 — 저장소가 공개라 실제 이름·번호를 두지 않는다.
const CONTACT = {
  id: 7, name: "홍길동", title: "심사역", firm: "가나벤처스",
  phone: "010-0000-0001", email: "hong@example.com",
  sectors: "헬스케어, 로보틱스", round_size: "10~30억",
  channel_kakao: 1, channel_email: 0
};
const TIMELINE = [{ kind: "deal_intro", date: "2026-08-03", month: "2026-08",
                    weekday: "월", week: 1, company_count: 3 }];

// --- 가짜 DOM (contacts.js 가 만지는 것만) ----------------------------------
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
  function el(id) { return nodes[id] || (nodes[id] = makeEl(id)); }

  // 표에 한 줄 — 눌러서 여는 길도 같이 본다.
  const rowNo = makeEl("rowno");
  const tr = makeEl("tr");
  tr.setAttribute("data-id", "7");
  tr.querySelector = function () { return rowNo; };

  const table = el("contacts-table");
  table.querySelectorAll = function (sel) {
    return sel.indexOf("tr.data-row") >= 0 ? [tr] : [];
  };
  table.querySelector = function () { return makeEl("tbody"); };

  const tabs = [makeEl("tab-info"), makeEl("tab-timeline")];
  tabs[0].setAttribute("data-tab", "info");
  tabs[1].setAttribute("data-tab", "timeline");
  const panels = [makeEl("panel-info"), makeEl("panel-timeline")];
  panels[0].setAttribute("data-panel", "info");
  panels[1].setAttribute("data-panel", "timeline");

  const document = {
    getElementById(id) { return nodes[id] || (nodes[id] = makeEl(id)); },
    querySelectorAll(sel) {
      if (sel === ".detail-tab") return tabs;
      if (sel === "[data-panel]") return panels;
      return [];
    },
    createElement(tag) { const e = makeEl(tag); e.tagName = tag.toUpperCase(); return e; }
  };
  // 상세 패널은 처음엔 닫혀 있다 — 열렸는지가 이 검사의 전부다.
  document.getElementById("detail-panel").hidden = true;

  return { document: document, nodes: nodes, el: el, tr: tr, tabs: tabs, panels: panels };
}

function run(setup) {
  const dom = makeDom();
  const calls = [];
  const win = {};
  const ctx = {
    document: dom.document,
    console: console,
    alert() {}, confirm() { return false; },
    MutationObserver: function (fn) { this.observe = function () {}; this.cb = fn; },
    fetch(url) {
      calls.push(url);
      return Promise.resolve({
        ok: true,
        json() { return Promise.resolve({ contact: CONTACT, timeline: TIMELINE.slice() }); }
      });
    }
  };
  ctx.window = win;
  Object.assign(win, ctx);
  if (setup) setup(win, dom);
  vm.runInNewContext(src, ctx, { filename: "contacts.js" });
  return { dom: dom, calls: calls, win: win };
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });

async function main() {
  // --- 대시보드에서 눌러 들어오면 상세가 열린다 ------------------------------
  {
    const { dom, calls } = run(function (win) { win.DEALFLOW_OPEN_CONTACT = 7; });
    assert.deepStrictEqual(calls, ["/api/contacts/7"],
      "번호를 받고도 담당자를 부르지 않았다 — 목록만 뜬다");

    await flush();
    const panel = dom.nodes["detail-panel"];
    assert.strictEqual(panel.hidden, false, "눌러서 들어왔는데 상세 패널이 안 열렸다");
    assert.ok(dom.nodes["detail-title"].textContent.indexOf("홍길동") >= 0,
      "패널은 열렸는데 누구 것인지 안 적혔다");
    assert.strictEqual(dom.nodes["f-firm"].value, "가나벤처스", "폼이 안 채워졌다");
    assert.strictEqual(dom.nodes["f-channel_kakao"].checked, true);
    assert.ok(dom.nodes["timeline"].innerHTML.indexOf("딜소개") >= 0,
      "활동 이력이 안 그려졌다");
  }

  // --- 번호가 없으면(그냥 /contacts) 아무 것도 열지 않는다 -------------------
  {
    const { dom, calls } = run(function (win) { win.DEALFLOW_OPEN_CONTACT = 0; });
    await flush();
    assert.deepStrictEqual(calls, [], "아무도 안 눌렀는데 담당자를 불러왔다");
    assert.strictEqual(dom.nodes["detail-panel"].hidden, true,
      "그냥 목록을 보러 왔는데 상세가 열려 있다");
  }

  // --- 표에서 줄을 눌러도 같은 함수로 열린다 ---------------------------------
  //
  // 두 길이 같은 loadContact 을 쓴다. 한쪽만 되는 상태가 바로 이 버그였다.
  {
    const { dom, calls } = run();
    const target = {
      tagName: "TD", classList: { contains() { return false; } },
      closest(sel) { return sel === "tr.data-row" ? dom.tr : null; }
    };
    dom.nodes["contacts-table"].fire("click", { target: target });
    assert.deepStrictEqual(calls, ["/api/contacts/7"], "줄을 눌렀는데 안 불러온다");
    await flush();
    assert.strictEqual(dom.nodes["detail-panel"].hidden, false,
      "줄을 눌렀는데 상세가 안 열린다");
  }

  // --- loadContact 이 부르는 자리에서 닿는 범위에 있는가 ----------------------
  //
  // 위 검사가 터지면 ReferenceError 만 남아 원인이 안 보인다. 원인은 늘 같다 —
  // 부르는 곳과 만든 곳이 서로 다른 IIFE 다. 그것을 이름 대고 말해 준다.
  {
    const blocks = src.split(/^\}\)\(\);\s*$/m);
    const caller = blocks.filter(function (b) {
      return b.indexOf("DEALFLOW_OPEN_CONTACT") >= 0;
    });
    assert.strictEqual(caller.length, 1, "DEALFLOW_OPEN_CONTACT 을 읽는 자리를 못 찾았다");
    const sameScope = /function\s+loadContact\s*\(/.test(caller[0]);
    const exported = /window\.loadContact\s*=/.test(src) &&
                     /window\.loadContact\s*\(/.test(caller[0]);
    assert.ok(sameScope || exported,
      "loadContact 을 부르는 자리에서 그 이름이 안 닿는다 — 다른 IIFE 안에 갇혀 있다.\n" +
      "  같은 IIFE 로 옮기거나(권장), 굳이 나눠야 한다면 window 로 내보내고 그 이름으로 불러라.");
  }

  console.log("contacts_open_test: 통과");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
