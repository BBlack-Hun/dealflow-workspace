// 선호 투자분야를 **분야 기준 목록에서 여러 개 고른다**(#2).
// (node tests/js/sector_picker_test.js)
//
// ── 여기서 잠그는 것 ────────────────────────────────────────────────────────
//
// · 표 칸(`data-type="sectors"`)을 누르면 떠 있는 창에 목록이 선다.
// · 체크하면 고른 차례대로 `, ` 로 이어지고, 바깥을 누르면 그 값이 저장된다.
// · **목록 밖의 옛 값은 지우지 않는다** — 체크된 채 `목록 밖 값` 으로 서고,
//   사람이 끄면 그때 빠진다. 창을 여는 것만으로 옛 글이 사라지면 안 된다.
// · 철자만 다른 말(`ai saas`)은 목록의 철자(`AI SaaS`)로 돌린다.
// · Esc 는 되돌린다(저장이 안 나간다).
//
// 목록 이름은 사용자가 정한 표의 일부다. 사람 · 회사 이름은 없다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const PICKER = fs.readFileSync(path.join(SRC, "sector_picker.js"), "utf8");
const INLINE = fs.readFileSync(path.join(SRC, "inline_edit.js"), "utf8");

const TREE = [
  { name: "AI·SaaS·데이터", minors: ["AI SaaS", "생성형AI"] },
  { name: "딥테크·제조", minors: ["로봇", "반도체"] }
];

function build(before) {
  const carrier = D.el("div", { id: "sector-taxonomy", hidden: "",
                                "data-tree": JSON.stringify(TREE) });
  const cell = D.el("div", { class: "cell clamp2", "data-field": "sectors",
                             "data-type": "sectors", "data-filter-key": "sector",
                             "data-filter-sep": "," });
  cell.textContent = before;
  const plain = D.el("td", { class: "who" });
  const tr = D.el("tr", { "data-id": "7", "data-f-sector": "" },
                  [D.el("td", {}, [cell]), plain]);
  const table = D.el("table", { id: "contacts-table", "data-inline-url": "/api/contacts" },
                     [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [carrier, table]);
  return { root, table, cell, plain, tr };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = { innerWidth: 1400, innerHeight: 900,
                addEventListener() {}, removeEventListener() {} };
  const sandbox = {
    document, console, setTimeout, alert() {},
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch(url, opts) {
      sent.push({ url, body: JSON.parse((opts && opts.body) || "{}") });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  // 화면이 싣는 차례 그대로 — 고르기 부품이 먼저다.
  vm.runInContext(PICKER, sandbox, { filename: "sector_picker.js" });
  // 부품은 `window` 에 선다 — 표 편집기가 `global.DealflowSectorPicker` 로 찾는다.
  sandbox.DealflowSectorPicker = win.DealflowSectorPicker;
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  return {
    sent,
    press(node) { node.fire("pointerdown"); node.fire("click"); },
    pop() { return dom.root.querySelector(".cell-pop"); },
    boxes() {
      const pop = dom.root.querySelector(".cell-pop");
      return pop ? pop.querySelectorAll(".sector-pick-item input") : [];
    },
    box(value) {
      return this.boxes().filter((b) => b.value === value)[0];
    },
    toggle(value) {
      const b = this.box(value);
      assert.ok(b, `고를 칸이 없다: ${value}`);
      b.checked = !b.checked;
      b.fire("change");
    }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 누르면 목록이 서고, 고른 차례대로 저장된다 ────────────────────────
  {
    const dom = build("");
    const t = run(dom);
    t.press(dom.cell);
    assert.ok(t.pop(), "칸을 눌렀는데 고르는 창이 안 떴다");
    const values = t.boxes().map((b) => b.value);
    assert.deepStrictEqual(values,
      ["AI·SaaS·데이터", "AI SaaS", "생성형AI", "딥테크·제조", "로봇", "반도체"],
      "목록이 대분류 → 소분류 차례로 안 선다");

    t.toggle("로봇");
    t.toggle("AI·SaaS·데이터");
    assert.deepStrictEqual(t.sent, [], "고르기만 했는데 저장이 나갔다");
    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent.length, 1, "바깥을 눌렀는데 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].body.sectors, "로봇, AI·SaaS·데이터",
      "고른 차례가 아니거나 구분자가 다르다");
    assert.strictEqual(dom.tr.getAttribute("data-f-sector"), "로봇|AI·SaaS·데이터",
      "필터 값이 태그 단위로 안 나뉘었다");
  }

  // ── 2. 목록 밖 옛 값은 지우지 않는다 ─────────────────────────────────────
  {
    const dom = build("6/17 반도체 위주, ai saas");
    const t = run(dom);
    t.press(dom.cell);
    const old = t.box("6/17 반도체 위주");
    assert.ok(old, "목록 밖 옛 값이 창에 안 보인다 ★ 열기만 해도 사라진다");
    assert.strictEqual(old.checked, true, "옛 값이 꺼진 채로 섰다");
    assert.strictEqual(t.box("AI SaaS").checked, true,
      "철자만 다른 `ai saas` 를 목록의 `AI SaaS` 로 못 알아봤다");

    t.toggle("반도체");
    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent[0].body.sectors, "6/17 반도체 위주, AI SaaS, 반도체",
      "옛 값이 빠졌거나 철자가 목록대로 안 돌아왔다");
  }

  // ── 3. 옛 값을 끄면 빠진다 ──────────────────────────────────────────────
  {
    const dom = build("방 나가셨음, 로봇");
    const t = run(dom);
    t.press(dom.cell);
    t.toggle("방 나가셨음");
    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent[0].body.sectors, "로봇");
  }

  // ── 4. Esc 는 되돌린다 ──────────────────────────────────────────────────
  {
    const dom = build("로봇");
    const t = run(dom);
    t.press(dom.cell);
    t.toggle("반도체");
    const pop = t.pop();
    pop.fire("keydown", { key: "Escape" });
    await flush();
    assert.deepStrictEqual(t.sent, [], "Esc 를 눌렀는데 저장이 나갔다");
    assert.strictEqual(dom.cell.textContent, "로봇", "Esc 뒤 칸이 원래 값으로 안 돌아왔다");
  }

  console.log("sector_picker_test: ok");
}

main().catch((err) => { console.error(err); process.exit(1); });
