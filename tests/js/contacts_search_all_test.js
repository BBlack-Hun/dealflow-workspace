// 명단 탭에서 친 검색어를 들고 **`전체` 로 가는 링크**. (node tests/js/contacts_search_all_test.js)
//
// #22 "전체에서 기업 검색(지금은 탭별 검색만)". 검색은 그려진 줄만 거른다 —
// 명단 탭에서 치면 그 명단 안에서만 찾는다. 다른 명단의 기업은 `전체` 에서 찾아야
// 하는데, 그걸 모르면 "없는 기업" 으로 읽힌다. 그래서 무언가를 치는 동안
// [전체 명단에서 찾기] 가 서고, 그 주소에 검색어가 실린다(`?q=`).
//
// 그리고 `?q=` 로 들어온 화면은 **칸에 적힌 검색어로 이미 걸러져** 있어야 한다.
//
// 규칙을 옮겨 적지 않고 화면 파일을 그대로 돌린다(contacts_sort_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(JS, name), "utf8");

// 가상의 기업이다 — 저장소가 공개라 실제 이름을 두지 않는다.
const ROWS = [
  { id: "1", firm: "샘플가기업" },
  { id: "2", firm: "샘플나기업" },
  { id: "3", firm: "다른기업" }
];

function build(opts) {
  const body = D.el("tbody", {}, ROWS.map(function (r) {
    return D.el("tr", { class: "data-row", "data-id": r.id,
                        "data-search": r.firm.toLowerCase() },
                [D.el("td", { class: "rowno" }),
                 D.el("td", { class: "cell", "data-field": "firm" })]);
  }));
  const table = D.el("table", { id: "contacts-table" }, [
    D.el("thead", {}, [D.el("tr", {}, [D.el("th", {}), D.el("th", {})])]), body]);
  const search = D.el("input", { id: "vc-search" });
  search.value = (opts && opts.q) || "";
  const kids = [search, D.el("div", {}, [table])];
  let link = null;
  if (!opts || opts.link !== false) {
    link = D.el("a", { id: "search-all", href: "/startup?sheet=all",
                       "data-base": "/startup?sheet=all" });
    link.hidden = true;
    kids.push(link);
  }
  return { root: D.el("div", {}, kids), body: body, search: search, link: link };
}

function run(dom) {
  D.resetHandlers();
  const win = {
    location: { pathname: "/startup", search: "" },
    history: { replaceState: function () {} }
  };
  const sandbox = {
    document: D.makeDocument(dom.root), console: console,
    MutationObserver: function () { this.observe = function () {}; },
    alert: function () {}, confirm: function () { return false; },
    setTimeout: setTimeout,
    fetch: function () { return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } }); }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  ["filters.js", "table_sort.js", "panel_modal.js", "contacts.js"].forEach(function (name) {
    vm.runInContext(read(name), sandbox, { filename: name });
  });
}

const shown = (dom) => dom.body.children.filter((tr) => !tr.hidden).map((tr) => tr.getAttribute("data-id"));

// 1) 아무것도 안 쳤으면 링크는 숨어 있다.
{
  const dom = build();
  run(dom);
  assert.strictEqual(dom.link.hidden, true, "검색어가 없는데 [전체 명단에서 찾기] 가 떠 있다");
}

// 2) 치면 선다 — 그 검색어를 주소에 싣는다(한글은 인코딩).
{
  const dom = build();
  run(dom);
  dom.search.value = "샘플 나";
  dom.search.fire("input");
  assert.strictEqual(dom.link.hidden, false, "검색어를 쳤는데 링크가 안 선다");
  assert.strictEqual(dom.link.getAttribute("href"),
    "/startup?sheet=all&q=" + encodeURIComponent("샘플 나"));
  // 지우면 다시 숨고, 주소에서도 검색어가 빠진다.
  dom.search.value = "  ";
  dom.search.fire("input");
  assert.strictEqual(dom.link.hidden, true, "검색어를 지웠는데 링크가 그대로다");
  assert.strictEqual(dom.link.getAttribute("href"), "/startup?sheet=all");
}

// 3) `?q=` 로 들어온 화면은 칸에 적힌 검색어로 **이미 걸러져** 있다.
{
  const dom = build({ q: "샘플", link: false });
  run(dom);
  assert.deepStrictEqual(shown(dom), ["1", "2"],
    "검색어를 들고 왔는데 표가 안 걸러졌다: " + shown(dom));
}

// 4) 링크가 없는 화면(`전체` 를 보고 있다)에서도 검색은 그대로 돈다.
{
  const dom = build({ link: false });
  run(dom);
  dom.search.value = "다른";
  dom.search.fire("input");
  assert.deepStrictEqual(shown(dom), ["3"]);
}

console.log("contacts_search_all_test: 통과");
