// 투자사 관리 현황 — `소유 펀드` 필터. (node tests/js/contacts_fund_filter_test.js)
//
// 사용자 원문: "투자사 관리 현황에서 소유펀드 필터랑 카운트가 표시되었으면 좋겠어".
//
//   1. 펀드마다 줄 수가 뜨고, 펀드가 여럿인 줄은 그 펀드마다 센다.
//   2. 펀드 하나를 고르면 그 펀드를 가진 회사의 줄만 남는다.
//   3. 건수는 다른 필터를 따라간다(다른 머리글 필터와 같은 `facets`).
//   4. 한 줄에서 고치면 같은 회사의 다른 줄의 필터 값도 서버가 나눈 값으로 바뀐다.
//
// 펀드·회사·이름은 지어낸 값이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const F = require(path.join(JS, "filters.js"));

// 서버가 `data-f-fund` 로 싣는 꼴(`investor_firms.split_funds` 를 `|` 로 이은 것).
const rows = [
  { fund: F.splitValues("가상 1호|가상 2호"), group: ["1군"] },
  { fund: F.splitValues("가상 1호|가상 2호"), group: ["2군"] },
  { fund: F.splitValues("가상 2호"), group: ["1군"] },
  { fund: F.splitValues(""), group: ["1군"] },
];
const counts = (state) => Object.fromEntries(
  F.facets(rows, "fund", state).map((o) => [o.value, o.count]));

// --- 1) 펀드마다 줄 수 · 여러 펀드인 줄은 펀드마다 · 없는 줄은 (비어 있음) ---------
assert.deepStrictEqual(counts({}), { "가상 1호": 2, "가상 2호": 3, [F.EMPTY]: 1 });

// --- 2) 펀드를 고르면 그 펀드를 가진 줄만 ------------------------------------
assert.deepStrictEqual(
  rows.map((r, i) => F.matchRow(r, { fund: ["가상 1호"] }) ? i : -1).filter((i) => i >= 0),
  [0, 1]);
assert.deepStrictEqual(
  rows.map((r, i) => F.matchRow(r, { fund: [F.EMPTY] }) ? i : -1).filter((i) => i >= 0),
  [3], "`(비어 있음)` 은 소유 펀드가 없는 줄만");

// --- 3) 건수는 다른 필터를 따라간다(자기 칸 선택은 안 줄인다) -----------------
assert.deepStrictEqual(counts({ group: ["1군"] }), { "가상 1호": 1, "가상 2호": 2, [F.EMPTY]: 1 });
assert.deepStrictEqual(counts({ group: ["1군"], fund: ["가상 1호"] }),
  { "가상 1호": 1, "가상 2호": 2, [F.EMPTY]: 1 });

// --- 4) 한 줄에서 고치면 같은 회사 줄의 필터 값이 서버 값으로 ------------------
{
  const mk = (id, key, fund) => {
    const cell = D.el("div", { class: "cell clamp2", "data-field": "owned_funds",
                               "data-filter-key": "fund", "data-filter-sep": "," });
    const tr = D.el("tr", { class: "data-row", "data-id": id, "data-firm-key": key,
                            "data-f-fund": fund }, [D.el("td", {}, [cell])]);
    return { tr: tr, cell: cell };
  };
  const a = mk("1", "가상벤처스", "");
  const b = mk("2", "가상벤처스", "");
  const c = mk("3", "가상인베스트", "가상 9호");
  const table = D.el("table", { id: "contacts-table" },
                     [D.el("thead"), D.el("tbody", {}, [a.tr, b.tr, c.tr])]);
  D.resetHandlers();
  const seen = [];
  const sandbox = {
    document: D.makeDocument(D.el("div", {}, [table])), console: console,
    MutationObserver: function () { this.observe = function () {}; },
    alert: function () {}, confirm: function () { return false; }, setTimeout: setTimeout,
    fetch: function () { return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } }); }
  };
  sandbox.window = Object.assign({ location: { pathname: "/contacts", search: "" },
                                   history: { replaceState: function () {} } }, sandbox);
  sandbox.window.DealflowFilters = { init: function () {
    return { apply: function () {}, refresh: function () { seen.push(b.tr.getAttribute("data-f-fund")); } };
  } };
  vm.createContext(sandbox);
  ["panel_modal.js", "contacts.js"].forEach((name) =>
    vm.runInContext(fs.readFileSync(path.join(JS, name), "utf8"), sandbox, { filename: name }));

  table.dispatchEvent({ type: "inline-saved", detail: { row: a.tr, cell: a.cell,
    value: "가상 1호,  가상 2호",
    data: { ok: true, firm_key: "가상벤처스", owned_funds: "가상 1호,  가상 2호",
            owned_fund_list: ["가상 1호", "가상 2호"] } } });
  assert.strictEqual(a.tr.getAttribute("data-f-fund"), "가상 1호|가상 2호");
  assert.strictEqual(b.tr.getAttribute("data-f-fund"), "가상 1호|가상 2호",
    "같은 회사의 다른 줄은 칸만 바뀌고 필터에는 옛 값으로 남았다");
  assert.strictEqual(c.tr.getAttribute("data-f-fund"), "가상 9호", "다른 회사 줄을 건드렸다");
  assert.deepStrictEqual(seen, ["가상 1호|가상 2호"],
    "필터가 다시 읽은 뒤에 행 값이 바뀌었다 — 차례가 거꾸로다");
}

console.log("contacts_fund_filter_test: ok");
