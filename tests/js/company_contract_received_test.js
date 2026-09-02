// `계약서 수신됨` 칸이 저장 뒤에 **맞춘 값**으로 되그려지는가.
// (node tests/js/company_contract_received_test.js)
//
// 이 칸은 `O`/`X` 라 화면 글자가 곧 저장되는 값이다 — 옆 칸(`계약여부`)이
// 겪은 사고(표는 `딜소개 불가` 를 보내는데 저장은 `blocked` 여야 했던 것)가
// 여기서는 날 자리가 없다. 그래도 되그려야 하는 이유가 둘 있다.
//
//   1. 소문자 `o` 를 쳐 넣으면 서버가 `O` 로 맞춘다. 누른 글자를 그대로 두면
//      칸에는 `o`, DB 에는 `O` 가 남아 필터 목록이 두 벌로 갈린다 —
//      한쪽을 골랐을 때 방금 고친 그 기업만 사라진다.
//   2. 비우면 `(비어 있음)` 쪽으로 옮겨 가야 한다(= 아직 안 정함).
//
// 그리고 **응답 하나가 두 칸을 건드릴 수 있다.** 기업 PATCH 응답에는 늘
// `contract_label` 과 `contract_received` 가 함께 실린다(`_contract_result`).
// 두 되그리기가 서로 `data-field` 를 안 보면, 기업명 하나를 고쳤을 뿐인데
// 엉뚱한 칸 글자가 바뀐다. 규칙을 옮겨 적지 않고 **companies.js 를 그대로
// 돌려서** 본다(consulting_contacted_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const src = fs.readFileSync(path.join(SRC, "companies.js"), "utf8");
const F = require(path.join(SRC, "filters.js"));

// --- 표 한 줄 — 템플릿의 IR 기업 현황 탭과 같은 속성만 세운다 ---------------
function build() {
  const contract = D.el("td", {
    class: "cell", "data-field": "contract_status", "data-type": "pick",
    "data-filter-key": "contract"
  });
  contract.textContent = "유료계약완료";

  const received = D.el("td", {
    class: "cell", "data-field": "contract_received", "data-type": "pick",
    "data-filter-key": "received", "data-choices": "O,X"
  });

  const name = D.el("td", { class: "cell", "data-field": "name" });
  name.textContent = "샘플에이";

  const tr = D.el("tr", {
    "data-id": "7", "data-search": "",
    "data-f-contract": "유료계약완료", "data-f-received": ""
  }, [D.el("td", { class: "rowno muted" }), name, contract, received]);

  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" }, [
    D.el("tbody", {}, [tr])
  ]);

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
  return { root: root, table: table, tr: tr, received: received,
           contract: contract, name: name };
}

// --- companies.js 를 그대로 돌린다 ------------------------------------------
function run(dom) {
  D.resetHandlers();
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: { location: { reload: function () {} }, DealflowFilters: undefined },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    fetch: function () {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "companies.js" });
}

// inline_edit.js 가 저장 뒤에 쏘는 그 이벤트. 응답은 서버가 실제로 주는 모양
// 그대로 — 계약 두 칸이 **늘 함께** 실려 온다(`_contract_result`).
function saved(dom, cell, data) {
  dom.table.fire("inline-saved", { detail: { row: dom.tr, cell: cell, data: data } });
}

// ── 1. 소문자로 쳐 넣어도 화면은 맞춘 값으로 돌아온다 ───────────────────────
{
  const dom = build();
  run(dom);
  dom.received.textContent = "o";                 // 눌러 친 글자
  dom.tr.setAttribute("data-f-received", "o");    // inline_edit.js 가 적어 둔 것
  saved(dom, dom.received, { contract_label: "유료계약완료", blocked: false,
                             contract_received: "O" });

  assert.strictEqual(dom.received.textContent, "O",
    "칸에 친 글자가 그대로 남았습니다 — DB 에는 `O`, 화면에는 `o` 입니다");
  assert.strictEqual(dom.tr.getAttribute("data-f-received"), "O",
    "필터 목록이 `o` 와 `O` 두 벌로 갈립니다 — 한쪽을 고르면 이 기업만 사라집니다");
}

// ── 2. 비우면 `아직 안 정함` 으로 돌아간다 ──────────────────────────────────
{
  const dom = build();
  run(dom);
  dom.received.textContent = "O";
  dom.tr.setAttribute("data-f-received", "O");
  saved(dom, dom.received, { contract_label: "유료계약완료", blocked: false,
                             contract_received: "" });

  assert.strictEqual(dom.received.textContent, "",
    "지웠는데 칸에 글자가 남았습니다");
  assert.strictEqual(dom.tr.getAttribute("data-f-received"), "",
    "지운 줄이 필터에서 `(비어 있음)` 쪽으로 안 옮겨 갑니다");
  // 빈 값은 filters.js 가 `(비어 있음)` 한 덩어리로 모은다 — 그래서 `O`/`X`
  // 둘뿐인 칸에서도 **아직 안 정한 기업만** 골라낼 수 있다.
  assert.deepStrictEqual(F.splitValues(dom.tr.getAttribute("data-f-received")),
                         ["(비어 있음)"]);
}

// ── 3. 응답에 둘이 함께 와도 자기 칸만 고친다 ───────────────────────────────
//
// 기업명 하나만 고쳐도 응답에는 계약 두 값이 늘 실린다. 되그리기가 `data-field`
// 를 안 보면, 이름을 고쳤을 뿐인데 계약 칸 두 개가 덮인다.
{
  const dom = build();
  run(dom);
  dom.received.textContent = "X";
  saved(dom, dom.name, { contract_label: "미계약", blocked: false,
                         contract_received: "O" });

  assert.strictEqual(dom.received.textContent, "X",
    "이름을 고쳤는데 계약서 수신됨 칸이 덮였습니다");
  assert.strictEqual(dom.contract.textContent, "유료계약완료",
    "이름을 고쳤는데 계약여부 칸이 덮였습니다");
  assert.strictEqual(dom.name.textContent, "샘플에이");
}

// ── 4. 옆 칸을 고쳐도 이 칸은 그대로다 (반대 방향) ──────────────────────────
{
  const dom = build();
  run(dom);
  dom.received.textContent = "X";
  saved(dom, dom.contract, { contract_label: "딜소개 불가", blocked: true,
                             contract_received: "O" });

  assert.strictEqual(dom.contract.textContent, "딜소개 불가",
    "계약여부 되그리기가 안 걸렸습니다");
  assert.strictEqual(dom.received.textContent, "X",
    "계약여부를 고쳤는데 계약서 수신됨 칸까지 덮였습니다");
}

console.log("company_contract_received_test OK");
