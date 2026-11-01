// 투자컨설턴트 `기업명` 칸 · [기업 추가] 칸 — 두 글자부터 IR 기업 후보가 뜨고, 고르면 저장되는가.
// (node tests/js/consulting_company_hint_test.js)
//
// consulting.js 와 ir_company_hint.js 를 **같은 판에** 그대로 돌린다(화면과 같은 차례).
//   1. 한 글자로는 안 뜨고, 두 글자부터 이름 **가운데 글자로도** 뜬다.
//   2. 목록이 떠 있을 때 Esc 는 목록만 닫는다(편집은 그대로) — 다음 Esc 가 취소다.
//   3. ↓ + Enter 로 고르면 그 이름 그대로 PATCH 가 **한 번** 나간다.
//   4. 서버가 이어서 채운 칸(`linked.fields`)을 그 자리에서 적고, 연결 표시도 고친다.
//   5. [기업 추가] — 처음 누르면 칸이 열리고, 후보를 고르면 그 이름으로 POST 가 나간다.
//
// 기업 이름은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const HINT = fs.readFileSync(path.join(SRC, "ir_company_hint.js"), "utf8");
const TABLE = fs.readFileSync(path.join(SRC, "consulting.js"), "utf8");
const NAMES = ["비에샘플랩", "비이샘플", "비티샘플바이오", "가나샘플"];

function td(field, value) {
  const cell = D.el("td", { class: "cell", "data-field": field });
  cell.textContent = value;
  return cell;
}

function build() {
  const main = D.el("div", { class: "cell-main" });
  main.textContent = "비";
  const sub = D.el("div", { class: "ir-link-sub muted" });
  sub.textContent = "IR 기업: 연결 안 됨";
  const name = D.el("td", { class: "cell strong", "data-field": "company_name" }, [main, sub]);
  const ceo = td("ceo_name", "");
  const phone = td("phone", "010-0000-2222");
  const region = td("region", "");
  const tr = D.el("tr", {
    "data-id": "7", "data-search": "", "data-f-mgmt": "", "data-f-region": "",
    "data-contacted": "0", "data-contacted-folded": "0", "data-contacted-prev": "0"
  }, [name, ceo, phone, region]);
  const addName = D.el("input", { id: "cs-add-name", type: "text" });
  addName.hidden = true;
  const toolbar = D.el("div", { class: "toolbar-right" }, [
    D.el("input", { id: "cs-search" }), addName,
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" })
  ]);
  const root = D.el("div", {}, [
    D.el("div", { id: "opts-ir-company", hidden: "", "data-names": JSON.stringify(NAMES) }),
    toolbar,
    D.el("table", { id: "cs-table", "data-contract-sheet": "0" }, [D.el("tbody", {}, [tr])]),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]);
  return { root, tr, name, main, sub, ceo, phone, region, addName, toolbar };
}

function run(dom, reply) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const el = made.call(document, tag);
    el.focus = function () {};
    el.setSelectionRange = function () {};
    return el;
  };
  dom.addName.focus = function () {};
  const calls = [];
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    window: { location: { reload: function () { calls.push({ reload: true }); } } },
    alert: function () {}, confirm: function () { return true; },
    fetch: function (url, opt) {
      calls.push({ url: url, method: opt.method, body: JSON.parse(opt.body || "{}") });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve(reply); } });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(HINT, sandbox, { filename: "ir_company_hint.js" });
  vm.runInContext(TABLE, sandbox, { filename: "consulting.js" });
  return calls;
}

function type(input, value) {
  input.value = value;
  input.selectionStart = value.length;
  input.fire("input");
}

// 판(`_dom.js`)은 이벤트를 새 객체로 합쳐 넘긴다 — `this` 에 적어 뒤 손이 보게 하고, 여기서는 따로 센다.
function key(input, name) {
  const out = { defaultPrevented: false };
  input.fire("keydown", { key: name, preventDefault: function () {
    this.defaultPrevented = true; out.defaultPrevented = true; } });
  return out;
}

function items(host) {
  const box = host.querySelector(".name-hint");
  return box && !box.hidden
    ? box.querySelectorAll(".name-hint-item").map(function (n) { return n.textContent; }) : [];
}

const tick = function () { return new Promise(function (r) { setTimeout(r, 0); }); };

async function main() {
  // ── 1~4. `기업명` 칸 ────────────────────────────────────────────────────
  {
    const dom = build();
    const reply = { id: 7, stamps: {}, linked: {
      ir_name: "비에샘플랩",
      fields: { ceo_name: "김샘플", phone: "010-0000-2222", region: "서울" } } };
    const calls = run(dom, reply);
    dom.name.fire("click", { target: dom.name });
    const input = dom.main.children.find(function (c) { return c.classList.contains("cell-input"); });
    assert.ok(input, "기업명 칸을 눌렀는데 입력칸이 안 생겼다");

    type(input, "비");
    assert.deepStrictEqual(items(dom.main), [], "한 글자에 후보가 떴다 ★ 두 글자부터다");
    type(input, "비에");
    assert.deepStrictEqual(items(dom.main), ["비에샘플랩"]);
    type(input, "샘플");
    assert.deepStrictEqual(items(dom.main), NAMES, "이름 가운데 글자로 못 찾는다");

    // 2. 떠 있을 때 Esc 는 목록만 닫는다.
    key(input, "Escape");
    assert.deepStrictEqual(items(dom.main), []);
    assert.strictEqual(calls.length, 0, "목록을 닫는 Esc 가 편집을 끝냈다");
    assert.strictEqual(input.value, "샘플", "목록을 닫는 Esc 가 친 글자를 되돌렸다");

    // 3. ↓ + Enter 로 고른다 → 그 이름 그대로 한 번 저장.
    type(input, "비에");
    key(input, "ArrowDown");
    const enter = key(input, "Enter");
    assert.ok(enter.defaultPrevented, "고르는 Enter 를 후보 목록이 안 가져갔다");
    assert.strictEqual(calls.length, 1, "고른 Enter 가 저장을 두 번 했다");
    assert.deepStrictEqual(calls[0], { url: "/api/consulting/7", method: "PATCH",
                                       body: { company_name: "비에샘플랩" } });
    await tick();
    // 4. 이어서 채운 칸을 그 자리에서 — 화면을 다시 받지 않는다.
    assert.strictEqual(dom.ceo.textContent, "김샘플");
    assert.strictEqual(dom.region.textContent, "서울");
    assert.strictEqual(dom.phone.textContent, "010-0000-2222");
    assert.strictEqual(dom.sub.textContent, "IR 기업: 비에샘플랩 (자동 연결)");
    assert.ok(dom.tr.getAttribute("data-search").indexOf("김샘플") >= 0, "검색 값이 안 따라왔다");
    assert.strictEqual(dom.tr.getAttribute("data-f-region"), "서울");
    assert.ok(!calls.some(function (c) { return c.reload; }), "칸을 고치고 화면을 다시 받았다");
  }

  // ── 2'. 목록이 닫힌 뒤의 Esc 는 예전처럼 취소다 ─────────────────────────
  {
    const dom = build();
    const calls = run(dom, { id: 7, stamps: {} });
    dom.name.fire("click", { target: dom.name });
    const input = dom.main.children.find(function (c) { return c.classList.contains("cell-input"); });
    type(input, "가나");
    key(input, "Escape");
    key(input, "Escape");
    assert.strictEqual(calls.length, 0, "취소했는데 저장이 나갔다");
    assert.strictEqual(dom.main.textContent, "비", "취소했는데 값이 안 돌아왔다");
  }

  // ── 5. [기업 추가] 칸 ───────────────────────────────────────────────────
  {
    const dom = build();
    const calls = run(dom, { id: 9 });
    const add = dom.root.querySelector("#cs-add");
    add.fire("click", { target: add });
    assert.strictEqual(dom.addName.hidden, false, "[기업 추가] 를 눌러도 칸이 안 열렸다");
    assert.strictEqual(calls.length, 0, "빈 칸으로 추가가 나갔다");
    type(dom.addName, "비이");
    assert.deepStrictEqual(items(dom.toolbar), ["비이샘플"]);
    const item = dom.toolbar.querySelector(".name-hint-item");
    item.fire("mousedown", { preventDefault: function () {} });
    assert.deepStrictEqual(calls[0], { url: "/api/consulting", method: "POST",
                                       body: { company_name: "비이샘플", sheet: "스타트업" } });
    // 고르지 않고 적은 새 기업도 Enter 로 그대로 들어간다.
    type(dom.addName, "새샘플기업");
    key(dom.addName, "Enter");
    assert.deepStrictEqual(calls[1].body, { company_name: "새샘플기업", sheet: "스타트업" });
  }
  console.log("consulting_company_hint_test OK");
}

main().catch(function (err) { console.error(err); process.exit(1); });
