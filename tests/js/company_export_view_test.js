// IR 기업 현황 [지금 화면 내려받기] — 누르는 순간 **지금 조건**을 주소에 싣는다.
// (node tests/js/company_export_view_test.js · 10/17 회의 #43)
//
// 서버가 같은 조건으로 다시 뽑는다(`services/company_view.py`). 화면이 할 일은
// 조건을 빠짐없이 넘기는 것 하나다.
//
//   · 머리글 필터 · 정렬 — 이미 주소에 있다(`filters.js` · `table_sort.js`). 그대로.
//   · 검색창 글자 — 주소에 안 남는다. 누를 때 `q=` 로 붙인다.
//   · 주소에 남아 있던 옛 `q=`(발송 화면에서 넘어온 값)는 버린다 — 지금 검색창이
//     화면을 거르는 값이다.
//
// `companies.js` 를 그대로 돌린다. 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const COMPANIES = fs.readFileSync(path.join(SRC, "companies.js"), "utf8");
const MODAL = fs.readFileSync(path.join(SRC, "panel_modal.js"), "utf8");

function build() {
  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" }, [
    D.el("tbody", {}, [D.el("tr", { "data-id": "1", "data-search": "샘플가나" })])
  ]);
  const link = D.el("a", { id: "co-export-view", href: "/api/export/companies-view.xlsx" });
  const search = D.el("input", { id: "co-search" });
  const root = D.el("div", {}, [
    table, link, search,
    D.el("p", { id: "co-note" }), D.el("p", { id: "co-status" }),
    D.el("p", { id: "co-updated" }), D.el("aside", { id: "co-panel" }),
    D.el("div", { id: "co-backdrop" }), D.el("button", { id: "co-add" }),
    D.el("button", { id: "co-close" }), D.el("button", { id: "co-cancel" }),
    D.el("button", { id: "co-save" })
  ]);
  return { root: root, link: link, search: search };
}

function run(dom, query) {
  D.resetHandlers();
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: { location: { search: query, reload: function () {} },
              DealflowFilters: undefined },
    setTimeout: setTimeout, alert: function () {}, confirm: function () { return true; },
    fetch: function () {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(COMPANIES, sandbox, { filename: "companies.js" });
}

// 1) 필터 · 정렬은 주소 그대로 넘어간다.
{
  const dom = build();
  run(dom, "?sector=%ED%97%AC%EC%8A%A4%EC%BC%80%EC%96%B4&sort=-updated");
  dom.link.fire("click");
  assert.strictEqual(dom.link.href,
    "/api/export/companies-view.xlsx?sector=%ED%97%AC%EC%8A%A4%EC%BC%80%EC%96%B4&sort=-updated",
    "걸어 둔 필터·정렬이 내려받기 주소에 안 실렸다");
}

// 2) 검색창 글자는 `q=` 로 붙고, 주소의 옛 `q=` 는 버린다.
{
  const dom = build();
  run(dom, "?q=%EC%98%9B%EA%B8%80&ir=%E2%97%8F%20%EC%9E%88%EC%9D%8C");
  dom.search.value = " 샘플 가나 ";
  dom.link.fire("click");
  assert.strictEqual(dom.link.href,
    "/api/export/companies-view.xlsx?ir=%E2%97%8F%20%EC%9E%88%EC%9D%8C&q=" +
      encodeURIComponent("샘플 가나"),
    "검색창 글자가 안 실렸거나 옛 q= 가 남았다");
}

// 3) 아무 조건도 없으면 맨 주소 — 서버가 표 차례 그대로 전부 준다.
{
  const dom = build();
  run(dom, "");
  dom.link.fire("click");
  assert.strictEqual(dom.link.href, "/api/export/companies-view.xlsx");
}

// 4) 누를 때마다 다시 짓는다 — 눌러 놓고 검색을 바꿔도 다음 누름이 따라온다.
{
  const dom = build();
  run(dom, "");
  dom.search.value = "가";
  dom.link.fire("click");
  dom.search.value = "";
  dom.link.fire("click");
  assert.strictEqual(dom.link.href, "/api/export/companies-view.xlsx",
    "검색을 지웠는데 옛 검색어가 주소에 남았다");
}

console.log("company_export_view: 모두 통과");
