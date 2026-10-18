// 관리자가 붙인 **추가 칸**(`data-custom`)을 눌러 적으면 칸 값 길로 가는가.
// (node tests/js/custom_column_save_test.js)
//
// 두 편집기가 같은 약속을 지킨다 — `inline_edit.js`(IR 기업 현황 · 딜 소싱 ·
// 스타트업 · 매출예상리스트)와 `consulting.js`(투자컨설턴트 표만 따로).
//
//   ① 추가 칸 → `PUT /api/custom-values/{표}/{줄}` 에 `{column_id, value}`.
//   ② 같은 표의 **다른 칸은 그대로** 줄의 PATCH 로 간다.
//   ③ 서버가 맞춘 값(`o` → `O`)으로 칸과 필터 값(`data-f-cc*`)을 다시 적는다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const INLINE = fs.readFileSync(path.join(JS, "inline_edit.js"), "utf8");
const CONSULTING = fs.readFileSync(path.join(JS, "consulting.js"), "utf8");

const flush = () => new Promise((r) => setTimeout(r, 0));

function sandboxFor(document, sent, reply) {
  return {
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {}, confirm: function () { return true; },
    prompt: function () { return null; },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, method: opts.method, body: JSON.parse(opts.body || "{}") });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve(reply); } });
    }
  };
}

// ── inline_edit.js ──────────────────────────────────────────────────────────
async function inlineEdit() {
  const memo = D.el("div", { class: "cell", "data-field": "cc5", "data-custom": "5",
                             "data-custom-rows": "ir_companies" });
  memo.textContent = "";
  const plain = D.el("td", { class: "cell", "data-field": "founded_year" });
  plain.textContent = "2020";
  const tr = D.el("tr", { "data-id": "7", "data-f-cc5": "" }, [D.el("td", {}, [memo]), plain]);
  const table = D.el("table", { id: "t", "data-inline-url": "/api/companies" },
    [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [table]);

  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(root);
  const sandbox = sandboxFor(document, sent, { value: "O", updated_at: "2026-10-18 10:00" });
  const win = { innerWidth: 1400, innerHeight: 900,
                addEventListener: function () {}, removeEventListener: function () {} };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });

  // ① 추가 칸
  memo.fire("click");
  let input = memo.querySelector(".cell-input");
  assert.ok(input, "추가 칸을 눌렀는데 입력칸이 안 열렸다");
  input.value = "o";
  input.blur();
  await flush();
  await flush();
  assert.deepStrictEqual(sent[0], {
    url: "/api/custom-values/ir_companies/7", method: "PUT",
    body: { column_id: 5, value: "o" }
  }, "추가 칸이 칸 값 길로 안 갔다: " + JSON.stringify(sent[0]));
  // ③ 서버가 맞춘 값으로 다시 적는다
  assert.strictEqual(memo.textContent, "O", "서버가 맞춘 값으로 칸을 다시 적지 않았다");
  assert.strictEqual(tr.getAttribute("data-f-cc5"), "O", "필터 값이 저장값과 다르다");

  // ② 다른 칸은 그대로
  plain.fire("click");
  input = plain.querySelector(".cell-input");
  input.value = "2021";
  input.blur();
  await flush();
  assert.deepStrictEqual(sent[1], {
    url: "/api/companies/7", method: "PATCH", body: { founded_year: "2021" }
  }, "보통 칸의 저장 길이 바뀌었다: " + JSON.stringify(sent[1]));
}

// ── consulting.js ───────────────────────────────────────────────────────────
async function consulting() {
  const custom = D.el("td", { class: "cell", "data-field": "cc9", "data-custom": "9",
                              "data-custom-rows": "consulting_companies",
                              "data-choices": "O,X" });
  custom.textContent = "";
  const region = D.el("td", { class: "cell", "data-field": "region" });
  region.textContent = "서울";
  const tr = D.el("tr", {
    "data-id": "3", "data-search": "", "data-f-region": "서울", "data-f-cc9": "",
    "data-contacted": "0", "data-contacted-folded": "0", "data-contacted-prev": "0"
  }, [custom, region]);
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0" },
    [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [
    D.el("span", { class: "kpi-value", "data-kpi": "total" }),
    D.el("button", { "data-cs-filter": "" }),
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]);

  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const el = made.call(document, tag);
    el.focus = function () {};
    el.setSelectionRange = function () {};
    el.blur = function () { el.fire("blur", { target: el }); };
    return el;
  };
  const sandbox = sandboxFor(document, sent, { value: "X" });
  sandbox.window = { location: { reload: function () {} } };
  sandbox.window.DealflowFilters = undefined;
  vm.createContext(sandbox);
  vm.runInContext(CONSULTING, sandbox, { filename: "consulting.js" });

  // ① 추가 칸 — O/X 단추로 고른다
  custom.fire("click", { target: custom });
  const box = custom.children.filter((c) => c.classList.contains("cell-pop-choices"))[0];
  assert.ok(box, "추가 O/X 칸에 고르는 단추가 없다");
  const chip = box.children.filter((c) => c.textContent === "X")[0];
  chip.fire("mousedown", { target: chip });
  await flush();
  await flush();
  assert.deepStrictEqual(sent[0], {
    url: "/api/custom-values/consulting_companies/3", method: "PUT",
    body: { column_id: 9, value: "X" }
  }, "투자컨설턴트 표의 추가 칸이 칸 값 길로 안 갔다: " + JSON.stringify(sent[0]));
  assert.strictEqual(tr.getAttribute("data-f-cc9"), "X", "필터 값이 안 따라왔다");

  // ② 다른 칸은 그대로
  region.fire("click", { target: region });
  const input = region.children.filter((c) => c.tag === "input")[0];
  input.value = "부산";
  input.blur();
  await flush();
  assert.deepStrictEqual(sent[1], {
    url: "/api/consulting/3", method: "PATCH", body: { region: "부산" }
  }, "보통 칸의 저장 길이 바뀌었다: " + JSON.stringify(sent[1]));
}

(async function main() {
  await inlineEdit();
  await consulting();
  console.log("ok — 추가 칸은 칸 값 길로, 다른 칸은 그대로");
})().catch(function (err) {
  console.error(err && err.stack || err);
  process.exit(1);
});
