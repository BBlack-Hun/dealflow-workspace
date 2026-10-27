// 표에서 **정해 둔 말을 체크해 여럿 고르는 칸**(`data-type="checks"`).
// (node tests/js/inline_edit_checks_test.js)
//
// 투자사 관리 현황 `펀드 종류` — 보기는 칸의 `data-choices`(서버 `investor_firms.FUND_TYPES`).
// `딜 소싱`(`branches`)과 같은 체크 창을 쓰되, 저장한 값을 **칸 글자로** 다시 적는다
// (딱지를 그리는 `branches` 와 다른 점).
//
//   1. 창을 열면 보기마다 체크 상자가 서고, 지금 값은 체크된 채다.
//   2. 체크를 더하고 Enter — 고른 것이 `, ` 로 이어져 저장되고 칸 글자도 그 값이다.
//   3. 안내 글에 딜 소싱 말이 섞이지 않는다.
//
// 값은 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "inline_edit.js"), "utf8");

const CHOICES = "모태 창업초기·청년,지역 펀드,PEF";

function run() {
  D.resetHandlers();
  const cell = D.el("div", { class: "cell", "data-field": "fund_types", "data-type": "checks",
                             "data-choices": CHOICES });
  cell.textContent = "PEF";
  const tr = D.el("tr", { "data-id": "11" }, [D.el("td", {}, [cell])]);
  const table = D.el("table", { id: "contacts-table", "data-inline-url": "/api/contacts" },
    [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [D.el("div", { class: "table-wrap wide" }, [table])]);
  const document = D.makeDocument(root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const node = made(tag);
    node.select = function () {};
    return node;
  };
  const sent = [];
  const win = { innerWidth: 1400, innerHeight: 900,
                addEventListener: function () {}, removeEventListener: function () {} };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout, alert: function () {},
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse((opts && opts.body) || "{}") });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "inline_edit.js" });
  return { root: root, cell: cell, sent: sent };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  const t = run();
  t.cell.fire("keydown", { key: "Enter", preventDefault: function () {} });
  const pop = t.root.querySelector(".cell-pop");
  assert.ok(pop, "Enter 로 창이 안 열렸다");

  // --- 1) 보기마다 체크 상자 · 지금 값은 체크된 채 -------------------------
  const boxes = pop.querySelectorAll(".branch-pick input");
  assert.deepStrictEqual(boxes.map((b) => b.value), ["모태 창업초기·청년", "지역 펀드", "PEF"]);
  assert.deepStrictEqual(boxes.map((b) => b.checked), [false, false, true]);

  // --- 3) 안내 글은 딜 소싱 말이 아니다 -------------------------------------
  const hints = pop.querySelectorAll(".cell-pop-hint").map((h) => h.textContent);
  assert.strictEqual(hints.length, 1, "안내 글이 없다");
  assert.ok(/여러 개 고를 수 있습니다/.test(hints[0]), hints[0]);
  assert.ok(!/딜 소싱/.test(hints[0]), "펀드 종류 칸에 딜 소싱 안내가 붙었다: " + hints[0]);

  // --- 2) 더 체크하고 Enter — 이어진 값이 저장되고 칸 글자도 그 값 ------------
  boxes[0].checked = true;
  boxes[0].fire("change");
  t.root.querySelector(".cell-pop .cell-pop-input").fire("keydown",
    { key: "Enter", preventDefault: function () {} });
  await flush();
  assert.strictEqual(t.root.querySelector(".cell-pop"), null, "Enter 로 창이 안 닫혔다");
  assert.strictEqual(t.sent.length, 1, "저장 요청이 안 나갔다");
  assert.strictEqual(t.sent[0].url, "/api/contacts/11");
  assert.deepStrictEqual(t.sent[0].body, { fund_types: "모태 창업초기·청년, PEF" });
  assert.strictEqual(t.cell.textContent, "모태 창업초기·청년, PEF",
    "칸 글자가 고른 값으로 안 바뀌었다 ★ branches 처럼 딱지 칸으로 다뤘다");

  console.log("inline_edit_checks_test: ok");
}

main().catch((err) => { console.error(err); process.exit(1); });
