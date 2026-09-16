// 줄 하나를 **새로** 넣는 자리 — 화면 쪽. (node tests/js/startup_add_row_test.js)
//
// 서버 쪽(누가 넣을 수 있나 · 어느 명단에 들어가나 · 무엇이 필수인가 · 로그)은
// `tests/test_startup_add_row.py` 가 본다. 여기서만 잴 수 있는 것이 넷이다.
//
//  · **필수 칸이 명단마다 다르다.** 이 파일(`contacts.js`)은 화면 둘이 같이
//    쓰는데 `if (!body.name)` 한 줄이 박혀 있었다 — 스타트업 명단에서는
//    성함이 비어 있는 줄이 흔해서, 그대로 두면 기업명을 채우고도 `담당자명을
//    입력하세요` 에 막혀 **한 줄도 못 넣는다.**
//  · **지금 보고 있는 탭을 실어 보내는가.** 안 실으면 그 줄은 `직접 추가` 로
//    밀려 방금 보던 화면 어느 탭에도 안 뜬다 — 넣어 놓고도 안 들어간 줄 안다.
//  · **막을 때 정말 안 보내는가.** 안내만 띄우고 요청이 나가면 반쪽짜리 줄이
//    생기고, 화면은 실패했다고 말한다.
//  · **고칠 때는 안 막는가.** 표에서 칸 하나만 눌러 고치는 일이 잦은데
//    (메모·카톡방 이름) 거기서 필수 칸을 물으면 메모 한 줄 고치는 데 이름이
//    필요해진다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const src = fs.readFileSync(path.join(JS, "contacts.js"), "utf8");
const modalSrc = fs.readFileSync(path.join(JS, "panel_modal.js"), "utf8");

// 서버가 내려 주는 값(`routers/pages.py` 의 `add_row`). 이름은 전부 지어낸
// 것이다 — 저장소가 공개다.
const STARTUP = {
  sheet: "샘플 스타트업(9)", label: "기업",
  required: "firm", required_label: "기업명", hint: ""
};
const VC = {
  sheet: "", label: "담당자",
  required: "name", required_label: "담당자명",
  hint: "투자사명을 넣으면 카톡방 이름이 자동 생성됩니다(비워둘 경우)."
};

const CONTACT = { id: 7, name: "홍길동", title: "심사역", firm: "가나벤처스" };

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

function run(config) {
  const dom = makeDom();
  const sent = [];
  const win = {};
  const ctx = {
    document: dom.document,
    console: console,
    alert() {}, confirm() { return true; },
    MutationObserver: function (fn) { this.observe = function () {}; this.cb = fn; },
    fetch(url, opts) {
      sent.push({ url: url, opts: opts || {} });
      return Promise.resolve({
        ok: true,
        json() { return Promise.resolve({ contact: CONTACT, timeline: [] }); }
      });
    }
  };
  ctx.window = win;
  Object.assign(win, ctx);
  // 저장하면 화면을 다시 받는다 — 자리를 적어 두는 길까지 그대로 지난다.
  win.location = { pathname: "/startup", search: "", reload() { win.reloaded = true; } };
  win.sessionStorage = {
    _v: {},
    setItem(k, v) { this._v[k] = v; },
    getItem(k) { return k in this._v ? this._v[k] : null; },
    removeItem(k) { delete this._v[k]; }
  };
  win.pageYOffset = 0;
  win.scrollTo = function () {};
  // `undefined` 를 넣으면 **설정이 아예 없는 화면**이 된다(단추가 안 서는 곳).
  if (config !== undefined) win.DEALFLOW_ADD_ROW = config;
  vm.createContext(ctx);
  vm.runInContext(modalSrc, ctx, { filename: "panel_modal.js" });
  vm.runInContext(src, ctx, { filename: "contacts.js" });
  return { dom: dom, sent: sent, win: win };
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });

function add(t) { t.dom.nodes["add-btn"].fire("click"); }
function save(t) { t.dom.nodes["save-btn"].fire("click"); }
function put(t, id, value) { t.dom.nodes["f-" + id].value = value; }
function msg(t) { return t.dom.nodes["detail-msg"].textContent; }
function body(one) { return JSON.parse(one.opts.body); }

async function main() {
  // ── 1. 스타트업 — 창 제목도 필수 칸도 **그 화면의 말**이다 ────────────────
  {
    const t = run(STARTUP);
    add(t);
    assert.strictEqual(t.dom.nodes["detail-title"].textContent, "기업 추가",
      "스타트업에서 기업을 넣는데 창에는 다른 말이 떠 있다");
    assert.strictEqual(t.dom.nodes["detail-panel"].hidden, false, "창이 안 열렸다");
    assert.strictEqual(msg(t), "",
      "투자사 명단에만 뜻이 있는 안내(카톡방 이름)가 스타트업 화면에 떴다");

    // 성함만 채우고 저장 — **막혀야 한다.**
    put(t, "name", "김대표");
    save(t);
    assert.deepStrictEqual(t.sent, [],
      "기업명 없이 저장했는데 요청이 나갔다 — 반쪽짜리 줄이 생긴다");
    assert.strictEqual(msg(t), "기업명을 입력하세요",
      "막았는데 무엇을 채우라는 건지 안 적혔다");

    // 기업명을 채우면 들어간다 — 그리고 **지금 보던 탭**을 싣는다.
    put(t, "firm", "새로넣은기업");
    save(t);
    assert.strictEqual(t.sent.length, 1, "기업명을 채웠는데도 안 나갔다");
    assert.strictEqual(t.sent[0].url, "/api/contacts");
    assert.strictEqual(t.sent[0].opts.method, "POST");
    const b = body(t.sent[0]);
    assert.strictEqual(b.firm, "새로넣은기업");
    assert.strictEqual(b.sheet, STARTUP.sheet,
      "지금 보던 명단을 안 실었다 — 그 줄은 어느 탭에도 안 뜬다");
    await flush();
    assert.strictEqual(t.win.reloaded, true, "넣고 나서 화면을 안 다시 받았다");
  }

  // ── 2. 투자사 관리 현황 — 지금까지 그대로 ────────────────────────────────
  {
    const t = run(VC);
    add(t);
    assert.strictEqual(t.dom.nodes["detail-title"].textContent, "담당자 추가");
    assert.strictEqual(msg(t), VC.hint, "투자사 화면의 안내가 사라졌다");

    put(t, "firm", "가나벤처스");
    save(t);
    assert.deepStrictEqual(t.sent, [], "이름 없이 저장했는데 요청이 나갔다");
    assert.strictEqual(msg(t), "담당자명을 입력하세요");

    put(t, "name", "박심사");
    save(t);
    assert.strictEqual(t.sent.length, 1);
    const b = body(t.sent[0]);
    assert.strictEqual(b.name, "박심사");
    assert.ok(!("sheet" in b),
      "명단을 안 고른 자리인데 빈 명단을 실어 보냈다 — `직접 추가` 로 가야 한다");
  }

  // ── 3. 설정이 없는 화면도 죽지 않는다 ────────────────────────────────────
  //
  // 넣을 수 없는 명단에서는 단추가 아예 안 서고, 그때 `window.DEALFLOW_ADD_ROW`
  // 는 `null` 이다. 그 값을 그대로 읽다가 터지면 **그 아래가 통째로 안 걸린다**
  // — 필터도 검색도 안 붙는데 표는 멀쩡히 그려져서 무엇이 고장인지 알 수 없다
  // (이 파일 머리의 `on()` 주석이 말하는 그 사고다).
  for (const none of [null, undefined]) {
    const t = run(none);
    add(t);   // 단추가 없는 화면이라 실제로는 안 눌리지만, 눌러도 안 죽어야 한다
    put(t, "name", "박심사");
    save(t);
    assert.strictEqual(t.sent.length, 1,
      "설정이 없는 화면에서 저장이 통째로 막혔다");
    assert.ok(!("sheet" in body(t.sent[0])));
  }

  // ── 4. **고칠 때는 안 막는다** ───────────────────────────────────────────
  //
  // 표에서 칸 하나만 눌러 고치는 일이 잦다(메모·카톡방 이름). 거기서 필수 칸을
  // 물으면 메모 한 줄 고치는 데 이름이 필요해진다.
  {
    // 줄을 눌러 연다 — 여는 길 자체는 `contacts_open_test.js` 가 잰다.
    const t2 = run(STARTUP);
    t2.dom.nodes["contacts-table"].fire("click", {
      target: {
        tagName: "TD", classList: { contains() { return false; } },
        closest(sel) {
          if (sel !== "tr.data-row") return null;
          const tr = makeEl("tr");
          tr.setAttribute("data-id", "7");
          tr.querySelector = function () { return makeEl("rowno"); };
          return tr;
        }
      }
    });
    await flush();
    assert.strictEqual(t2.sent.length, 1, "줄을 눌렀는데 안 불러왔다");

    // 필수 칸을 비워도 **고치기는 나간다.**
    put(t2, "firm", "");
    put(t2, "name", "");
    save(t2);
    assert.strictEqual(t2.sent.length, 2,
      "칸 하나 고치는데 필수 칸을 물어 막았다 — 표에서 눌러 고치는 길이 죽는다");
    assert.strictEqual(t2.sent[1].url, "/api/contacts/7");
    assert.strictEqual(t2.sent[1].opts.method, "PATCH");
    assert.ok(!("sheet" in body(t2.sent[1])),
      "고칠 때 명단을 실어 보냈다 — 명단을 옮기는 길은 [이관] 하나뿐이다");
  }

  console.log("startup_add_row_test: 통과");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
