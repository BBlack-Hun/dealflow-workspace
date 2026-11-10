// IR 기업 현황 금액 칸에 숫자만 적으면 **저장된 값(`30억`)으로** 칸이 다시 그려지는가(#217).
// (node tests/js/company_amount_unit_test.js)
//
// 서버가 맨숫자에 `억` 을 붙여 저장한다(`amount.with_unit`). 칸이 친 글자(`30`)로 남으면
// 새로고침 전까지 화면과 저장값이 다르다 — 응답의 `amounts` 로 그 칸을 다시 그린다.
//
//   ① `투자유치희망금액`(`amount_cell` 의 span) · 연도 매출(td 자체가 칸) 둘 다 되그린다.
//   ② 응답에 그 칸 값이 없으면(다른 칸을 고쳤다) 금액 칸은 안 건드린다.
//
// inline_edit.js 와 companies.js 를 **그대로 함께** 돌린다. 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const INLINE = fs.readFileSync(path.join(SRC, "inline_edit.js"), "utf8");
const MODAL = fs.readFileSync(path.join(SRC, "panel_modal.js"), "utf8");
const COMPANIES = fs.readFileSync(path.join(SRC, "companies.js"), "utf8");

// 표 한 줄 — 템플릿(companies.html)의 그 칸들과 같은 모양.
function build() {
  const raise = D.el("span", { class: "cell", "data-field": "raise_target", "data-filter-derived": "" });
  raise.textContent = "";
  const year = D.el("td", { class: "cell num", "data-field": "revenue_2025", "data-filter-derived": "" });
  year.textContent = "";
  const name = D.el("td", { class: "cell", "data-field": "name" });
  name.textContent = "샘플금액";
  const tr = D.el("tr", { "data-id": "7", "data-search": "", "data-f-raise_target": "" },
    [D.el("td", { class: "rowno muted" }), name, year, D.el("td", { class: "num" }, [raise])]);
  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
    [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "co-search" }),
    D.el("p", { id: "co-note" }),
    D.el("p", { id: "co-status" }),
    D.el("aside", { id: "co-panel" }),
    D.el("div", { id: "co-backdrop" }),
    D.el("button", { id: "co-add" }),
    D.el("button", { id: "co-close" }),
    D.el("button", { id: "co-cancel" }),
    D.el("button", { id: "co-save" })
  ]);
  return { root: root, table: table, tr: tr, raise: raise, year: year, name: name };
}

function run(dom, reply) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1400, innerHeight: 900,
    location: { reload: function () {} }, DealflowFilters: undefined,
    addEventListener: function () {}, removeEventListener: function () {}
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function (m) { throw new Error("alert: " + m); },
    confirm: function () { return true; },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      const body = JSON.parse((opts && opts.body) || "{}");
      sent.push(body);
      const out = reply(body);
      return Promise.resolve({ ok: true, status: 200,
                               json: function () { return Promise.resolve(out); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(COMPANIES, sandbox, { filename: "companies.js" });
  return sent;
}

// 서버가 실제로 주는 모양 — 보낸 금액 칸만 `amounts` 에 저장값으로(routers/companies.update_company).
function reply(body) {
  const amounts = {};
  Object.keys(body).forEach(function (k) {
    if (k !== "name") amounts[k] = /^\d+(\.\d+)?$/.test(body[k]) ? body[k] + "억" : body[k];
  });
  return { id: 7, amounts: amounts, bands: {} };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function type(cell, text) {
  cell.fire("pointerdown");
  cell.fire("click");
  const input = cell.querySelector(".cell-input");
  assert.ok(input, "금액 칸이 안 열렸다");
  input.value = text;
  input.blur();
  await flush(); await flush();
}

async function main() {
  // ── ① 숫자만 적으면 칸이 `30억` 으로 다시 그려진다 ──────────────────────
  {
    const dom = build();
    const sent = run(dom, reply);
    await type(dom.raise, "30");
    await type(dom.year, "12.5");
    assert.deepStrictEqual(sent, [{ raise_target: "30" }, { revenue_2025: "12.5" }]);
    assert.strictEqual(dom.raise.textContent, "30억", "저장값은 `30억` 인데 칸은 친 글자 그대로다 ★ #217");
    assert.strictEqual(dom.year.textContent, "12.5억", "연도 매출 칸도 저장값으로 그려야 한다");
  }

  // ── ② 다른 칸을 고친 응답은 금액 칸을 안 건드린다 ───────────────────────
  {
    const dom = build();
    dom.raise.textContent = "20";
    run(dom, reply);
    dom.table.fire("inline-saved", { detail: { row: dom.tr, cell: dom.name,
      data: { id: 7, amounts: {} } } });
    assert.strictEqual(dom.raise.textContent, "20");
  }

  console.log("company_amount_unit_test OK");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
