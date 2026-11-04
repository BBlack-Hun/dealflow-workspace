// IR 기업 현황 `IR 자료` 칸을 **표에서 바로** 고치는가(#151).
// (node tests/js/company_ir_file_inline_test.js)
//
// 팀원 요청: "IR 없음 → 있음으로 [수정] 으로 안 가고 바로 수정할 수 있게".
// 칸은 배지(`📎 있음`/`⚠ 없음`) 밑에 파일 이름 한 줄이고, 배지는 칸 **밖** 형제다
// (companies.html — 칸 안에 두면 배지 글자가 파일 이름으로 저장된다).
//
//   ① 배지를 누르면 파일 이름 칸이 열린다(`cell-hint`) — 빈 칸은 누를 자리가 배지뿐이다.
//   ② 적고 나가면 `ir_file_name` 하나만 PATCH 로 가고, 응답(`has_ir`)으로 배지 ·
//      줄의 `data-f-ir`(필터 값)가 `● 있음` 으로 바뀐다. 칸 글자는 서버가 다듬은 값이다.
//   ③ 비우면 `⚠ 없음` 으로 돌아간다.
//   ④ 서버가 거절하면(파일 이름이 아님 · 400) 칸 글자도 배지도 그대로다.
//   ⑤ 다른 칸을 고쳐도 응답에 `has_ir` 가 실려 오지만 배지는 안 건드린다.
//
// inline_edit.js 와 companies.js 를 **그대로 함께** 돌린다 — 규칙을 옮겨 적으면 둘이
// 갈려도 여기서는 안 보인다. 값은 전부 지어낸 것이다 — 저장소가 공개다.
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

// --- 표 한 줄 — 템플릿의 그 칸과 같은 모양 ---------------------------------
function build(fileName) {
  const has = !!fileName;
  const badge = D.el("span", { class: "room-badge cell-hint ir-badge " + (has ? "ok" : "warn") });
  badge.textContent = has ? "📎 있음" : "⚠ 없음";
  const cell = D.el("div", { class: "cell ellipsis ir-file-name", "data-field": "ir_file_name",
                             "data-filter-key": "ir", "data-filter-derived": "" });
  cell.textContent = fileName;
  const irTd = D.el("td", { class: "ir-file" }, [badge, cell]);

  const name = D.el("td", { class: "cell", "data-field": "name" });
  name.textContent = "샘플애그";

  const tr = D.el("tr", { "data-id": "7", "data-search": "",
                          "data-f-ir": has ? "● 있음" : "⚠ 없음" },
    [D.el("td", { class: "rowno muted" }), name, irTd]);
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
  return { root: root, table: table, tr: tr, badge: badge, cell: cell, name: name };
}

// `reply(body)` → 서버 응답 `{ status, data }`.
function run(dom, reply) {
  D.resetHandlers();
  const sent = [];
  const alerts = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1400, innerHeight: 900,
    location: { reload: function () {} }, DealflowFilters: undefined,
    addEventListener: function () {}, removeEventListener: function () {}
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function (m) { alerts.push(m); },
    confirm: function () { return true; },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      const body = JSON.parse((opts && opts.body) || "{}");
      sent.push({ url: url, method: opts && opts.method, body: body });
      const out = reply(body);
      return Promise.resolve({ ok: out.status < 400, status: out.status,
                               json: function () { return Promise.resolve(out.data); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(COMPANIES, sandbox, { filename: "companies.js" });
  return { sent: sent, alerts: alerts };
}

// 서버가 실제로 주는 모양 — 다듬은 파일 이름과 `has_ir`(routers/companies.update_company).
function okReply(body) {
  const text = (body.ir_file_name || "").trim();
  return { status: 200, data: { id: 7, ir_file_name: text, has_ir: !!text,
                                contract_label: "미계약", contract_status: "none" } };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

function openFromBadge(dom) {
  dom.badge.fire("pointerdown");
  dom.badge.fire("click");
  const input = dom.cell.querySelector(".cell-input");
  assert.ok(input, "`⚠ 없음` 배지를 눌렀는데 파일 이름 칸이 안 열렸다 ★ #151");
  return input;
}

async function main() {
  // ── ① · ② 배지를 눌러 적으면 `있음` 이 되고 필터 값도 따라온다 ──────────
  {
    const dom = build("");
    const t = run(dom, okReply);
    const input = openFromBadge(dom);
    input.value = "  샘플애그_IR_2026.pdf ";
    input.blur();
    await flush(); await flush();

    assert.deepStrictEqual(t.sent.map((s) => [s.method, s.url, s.body]),
      [["PATCH", "/api/companies/7", { ir_file_name: "샘플애그_IR_2026.pdf" }]],
      "한 칸만 PATCH 로 가야 한다: " + JSON.stringify(t.sent));
    assert.strictEqual(dom.badge.textContent, "📎 있음", "저장했는데 배지가 그대로 `없음` 이다");
    assert.ok(dom.badge.classList.contains("ok") && !dom.badge.classList.contains("warn"));
    assert.ok(dom.badge.classList.contains("cell-hint"), "다시 그린 배지를 눌러도 칸이 열려야 한다");
    assert.strictEqual(dom.tr.getAttribute("data-f-ir"), "● 있음",
      "`⚠ 없음` 으로 걸러 둔 표에 방금 채운 기업이 그대로 남는다 — 필터 수가 어긋난다");
    assert.strictEqual(dom.cell.textContent, "샘플애그_IR_2026.pdf");
    assert.deepStrictEqual(t.alerts, []);
  }

  // ── ③ 비우면 `없음` 으로 돌아간다 ─────────────────────────────────────────
  {
    const dom = build("샘플애그_IR_2026.pdf");
    const t = run(dom, okReply);
    dom.cell.fire("click");
    const input = dom.cell.querySelector(".cell-input");
    assert.strictEqual(input.value, "샘플애그_IR_2026.pdf", "열린 칸에 지금 파일 이름이 있어야 한다");
    input.value = "";
    input.blur();
    await flush(); await flush();

    assert.deepStrictEqual(t.sent.map((s) => s.body), [{ ir_file_name: "" }]);
    assert.strictEqual(dom.badge.textContent, "⚠ 없음");
    assert.ok(dom.badge.classList.contains("warn") && !dom.badge.classList.contains("ok"));
    assert.strictEqual(dom.tr.getAttribute("data-f-ir"), "⚠ 없음");
    assert.strictEqual(dom.cell.textContent, "");
  }

  // ── ④ 서버가 거절하면 칸도 배지도 그대로 ────────────────────────────────
  {
    const dom = build("");
    const t = run(dom, function () {
      return { status: 400, data: { detail: "자료 폴더 안의 파일 이름만 적습니다" } };
    });
    const input = openFromBadge(dom);
    input.value = "https://example.invalid/ir.pdf";
    input.blur();
    await flush(); await flush();

    assert.strictEqual(t.alerts.length, 1, "거절됐는데 아무 말이 없다");
    assert.ok(/파일 이름만/.test(t.alerts[0]), t.alerts[0]);
    assert.strictEqual(dom.cell.textContent, "", "저장 못 한 값이 칸에 남았다");
    assert.strictEqual(dom.badge.textContent, "⚠ 없음");
    assert.strictEqual(dom.tr.getAttribute("data-f-ir"), "⚠ 없음");
  }

  // ── ⑤ 다른 칸을 고친 응답은 배지를 안 건드린다 ───────────────────────────
  {
    const dom = build("");
    run(dom, okReply);
    dom.table.fire("inline-saved", { detail: { row: dom.tr, cell: dom.name,
      data: { ir_file_name: "엉뚱.pdf", has_ir: true } } });
    assert.strictEqual(dom.badge.textContent, "⚠ 없음", "기업명을 고쳤는데 IR 배지가 바뀌었다");
    assert.strictEqual(dom.tr.getAttribute("data-f-ir"), "⚠ 없음");
  }

  console.log("company_ir_file_inline_test OK");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
