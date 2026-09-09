// 투자사 관리 현황 — **이름 머리글을 눌러 정렬**한다. (node tests/js/contacts_sort_test.js)
//
// 사용자 원문: "투자사 관리현황의 딜 소개 탭의 이름 기준으로 정렬이 필요함."
//
// 세우는 일은 주간 업무가 쓰던 부품이 그대로 한다(`table_sort.js`). 그래서 여기서
// 다시 보는 것은 **그 부품이 이 표에 제대로 물렸는가**와, 이 화면에만 있는 두
// 가지다:
//
//   · `NO` 는 보이는 것 기준 1,2,3… 이라 **차례가 곧 번호**다. 줄을 세우고 번호를
//     안 다시 매기면, 정렬한 표의 번호가 `3,5,1,4,2` 로 남아 목록을 셀 수가 없다.
//   · 거르는 일(`filters.js`)과 **싸우면 안 된다.** 검색·필터를 걸어 둔 채로
//     머리글을 눌렀을 때 감춰 둔 줄이 되살아나면, 세우는 순간 조건이 풀린다.
//
// 규칙을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모르므로 **파일 셋을 그대로
// 돌린다**(table_sort.js · filters.js · contacts.js). `table_sort_test.js` 와
// 같은 방식이다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(JS, name), "utf8");

// 가상의 담당자다 — 저장소가 공개라 실제 이름·회사를 두지 않는다.
//
// **서버가 그려 주는 차례 그대로** 넣는다(정렬을 끄면 이 차례로 돌아와야 한다).
// 일부러 섞어 둔다 — 이미 이름순으로 넣으면 정렬이 아무 일도 안 해도 통과한다.
//
//   id 1  이서준 · 가나벤처스
//   id 2  (이름 없음) · 다라캐피탈     ← 빈 이름
//   id 3  김하늘 · 가나벤처스
//   id 4  이서준 · 마바인베스트        ← 같은 이름이 둘
//   id 5  박지우 · 다라캐피탈
const ROWS = [
  { id: "1", name: "이서준", firm: "가나벤처스" },
  { id: "2", name: "", firm: "다라캐피탈" },
  { id: "3", name: "김하늘", firm: "가나벤처스" },
  { id: "4", name: "이서준", firm: "마바인베스트" },
  { id: "5", name: "박지우", firm: "다라캐피탈" }
];

function th(attrs, label) {
  const cell = D.el("th", attrs || {});
  cell.textContent = label;
  return cell;
}

// 화면(`app/templates/contacts.html`)이 그리는 만큼만 세운다.
function build() {
  const head = D.el("thead", {}, [D.el("tr", {}, [
    th({ class: "num" }, "NO"),
    th({ "data-sort": "name" }, "이름"),
    // 같은 표에 필터도 붙어 있다 — 정렬이 그것을 풀지 않는지 봐야 한다.
    th({ "data-filters": "firm:회사" }, "회사")
  ])]);
  const body = D.el("tbody", {}, ROWS.map(function (r) {
    return D.el("tr", {
      class: "data-row",
      "data-id": r.id,
      "data-s-name": r.name,
      "data-f-firm": r.firm,
      "data-search": (r.name + " " + r.firm).toLowerCase()
    }, [
      D.el("td", { class: "rowno" }),
      D.el("td", {}, [D.el("b", { class: "cell", "data-field": "name" })]),
      D.el("td", { class: "cell", "data-field": "firm" })
    ]);
  }));
  const table = D.el("table", { id: "contacts-table" }, [head, body]);
  const search = D.el("input", { id: "vc-search" });
  const count = D.el("b", { "data-filter-count": "" });
  const root = D.el("div", {}, [count, search, D.el("div", {}, [table])]);
  return { root: root, table: table, body: body, search: search, count: count,
           heads: D.queryAll(table, "th") };
}

// --- 화면 파일들을 그대로 돌린다 ---------------------------------------------
function run(dom, search) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const urls = [];
  const win = {
    location: { pathname: "/contacts", search: search || "" },
    history: {
      replaceState: function (a, b, url) {
        urls.push(url);
        // 브라우저는 주소를 바꾸면 `location.search` 도 따라 바뀐다. 안 따라가면
        // 두 부품(필터·정렬)이 서로의 쿼리를 못 보고 지워 버리는 사고를
        // 검사가 못 본다.
        const at = String(url).indexOf("?");
        win.location.search = at < 0 ? "" : String(url).slice(at);
      }
    }
  };
  const sandbox = {
    document: document, console: console,
    // 줄을 감추는 일은 이 검사가 직접 시킨다(검색칸·정렬 단추). 브라우저의
    // 관찰자까지 흉내 내면 무엇이 번호를 다시 매겼는지가 흐려진다.
    MutationObserver: function () { this.observe = function () {}; },
    alert: function () {}, confirm: function () { return false; },
    setTimeout: setTimeout,
    fetch: function () { return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } }); }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  // 화면이 부르는 차례 그대로다(contacts.html) — 정렬기가 뒤에 오면
  // contacts.js 가 `window.DealflowSort` 를 못 본다.
  ["filters.js", "table_sort.js", "contacts.js"].forEach(function (name) {
    vm.runInContext(read(name), sandbox, { filename: name });
  });
  return { urls: urls, win: win };
}

// 지금 서 있는 차례(감춘 줄까지 전부)
function ids(dom) {
  return dom.body.children.map(function (tr) { return tr.getAttribute("data-id"); }).join(",");
}

// 보이는 줄만
function shown(dom) {
  return dom.body.children.filter(function (tr) { return !tr.hidden; })
    .map(function (tr) { return tr.getAttribute("data-id"); }).join(",");
}

// 화면에 찍힌 NO
function numbers(dom) {
  return dom.body.children.map(function (tr) {
    return tr.querySelector(".rowno").textContent;
  }).join(",");
}

function nameButton(dom) {
  return dom.heads[1].querySelector("button");
}

// --- 1) 머리글을 누르면 이름순, 세 번 누르면 원래대로 -------------------------
{
  const dom = build();
  run(dom);
  assert.strictEqual(ids(dom), "1,2,3,4,5",
    "처음 차례가 서버가 그려 준 그대로가 아니다");
  assert.strictEqual(numbers(dom), "1,2,3,4,5");

  const btn = nameButton(dom);
  assert.ok(btn && btn.tag === "button",
    "이름 머리글이 단추가 아니면 키보드(Tab·Enter)로 정렬할 수 없다");
  assert.strictEqual(btn.getAttribute("data-mark"), "↕",
    "눌러야 세워지는 칸임이 안 보이면, 칸 스무 개짜리 표에서 아무 머리글이나 눌러 보게 된다");

  btn.fire("click");
  assert.strictEqual(ids(dom), "3,5,1,4,2",
    "이름 오름차순(가나다)이 아니다 — 김하늘 → 박지우 → 이서준 → (빈 이름)");
  assert.strictEqual(dom.heads[1].getAttribute("aria-sort"), "ascending");

  btn.fire("click");
  assert.strictEqual(ids(dom), "1,4,5,3,2",
    "이름 내림차순이 아니다 — 빈 이름은 방향을 따라가면 안 된다");
  assert.strictEqual(dom.heads[1].getAttribute("aria-sort"), "descending");

  btn.fire("click");
  assert.strictEqual(ids(dom), "1,2,3,4,5",
    "정렬을 끄면 서버가 그려 준 차례로 돌아와야 한다");
  assert.strictEqual(dom.heads[1].getAttribute("aria-sort"), "none");
}

// --- 2) 빈 이름은 **방향과 상관없이 늘 끝** ----------------------------------
//
// 방향을 따르게 두면 내림차순에서 이름 없는 줄이 맨 위로 올라와, 목록의 머리가
// 빈칸이 된다 — 무엇을 보는 표인지 첫 줄이 말해 주지 못한다.
// (필터도 `(비어 있음)` 을 늘 끝에 둔다 — `filters.js`.)
{
  const dom = build();
  run(dom);
  const btn = nameButton(dom);
  btn.fire("click");
  assert.strictEqual(ids(dom).split(",").pop(), "2", "오름차순에서 빈 이름이 끝이 아니다");
  btn.fire("click");
  assert.strictEqual(ids(dom).split(",").pop(), "2", "내림차순에서 빈 이름이 끝이 아니다");
}

// --- 3) 같은 이름끼리는 **처음 차례를 지킨다** -------------------------------
//
// 동명이인이 실제로 있다(회사가 다르다). 누를 때마다 자기들끼리 뒤섞이면
// 어제 본 자리에서 그 사람을 못 찾는다.
{
  const dom = build();
  run(dom);
  nameButton(dom).fire("click");
  const at = ids(dom).split(",");
  assert.ok(at.indexOf("1") + 1 === at.indexOf("4"),
    "같은 이름인 두 줄이 붙어 서지 않았다 — 이름으로 세우지 않은 것이다");
  assert.ok(at.indexOf("1") < at.indexOf("4"),
    "같은 이름끼리 처음 차례(1 → 4)가 무너졌다");
}

// --- 4) 세우면 **NO 를 다시 매긴다** -----------------------------------------
//
// `NO` 는 보이는 것 기준 1,2,3… 이라 차례가 곧 번호다. 안 매기면 정렬한 표의
// 번호가 `3,5,1,4,2` 로 남아 목록을 셀 수가 없다.
{
  const dom = build();
  run(dom);
  nameButton(dom).fire("click");
  assert.strictEqual(ids(dom), "3,5,1,4,2");
  assert.strictEqual(numbers(dom), "1,2,3,4,5",
    "세우고 나서 NO 를 다시 안 매겼다 — 번호가 `3,5,1,4,2` 로 옛 자리에 남았다");
}

// --- 5) 걸어 둔 조건과 **싸우지 않는다** -------------------------------------
//
// 검색·필터를 걸어 둔 채로 머리글을 눌렀을 때 감춰 둔 줄이 되살아나면, 세우는
// 순간 조건이 풀린다. 거르는 쪽은 줄을 `hidden` 으로 감출 뿐 차례를 안 보고,
// 세우는 쪽은 감춘 줄까지 함께 옮긴다 — 그래서 둘이 겹쳐도 남는다.
{
  const dom = build();
  run(dom);
  dom.search.value = "가나벤처스";
  dom.search.fire("input");
  assert.strictEqual(shown(dom), "1,3", "검색이 안 걸렸다");

  nameButton(dom).fire("click");
  assert.strictEqual(shown(dom), "3,1", "세우고 나니 검색 결과의 차례가 안 바뀌었다");
  assert.strictEqual(dom.body.children.filter(function (tr) { return !tr.hidden; }).length, 2,
    "세우는 순간 감춰 둔 줄이 되살아났다 — 걸어 둔 조건이 풀린 것이다");
  // 번호는 **보이는 것** 기준이다 — 감춘 줄은 빈칸으로 남는다.
  assert.strictEqual(
    dom.body.children.filter(function (tr) { return !tr.hidden; })
      .map(function (tr) { return tr.querySelector(".rowno").textContent; }).join(","),
    "1,2", "걸러낸 뒤의 NO 가 1 부터가 아니다");
}

// --- 6) 주소에 남는다 · 남의 쿼리는 그대로 -----------------------------------
//
// 명단 탭은 `?sheet=` 로 정해진다. 정렬이 그것을 지우면 머리글 한 번 누르는 것이
// 다른 명단으로 튀는 일이 된다.
{
  const dom = build();
  const out = run(dom, "?sheet=%EA%B0%80%EB%82%98");
  nameButton(dom).fire("click");
  const last = out.urls[out.urls.length - 1];
  assert.ok(last.indexOf("sheet=") >= 0,
    "정렬이 보고 있던 명단을 주소에서 날렸다: " + last);
  assert.ok(last.indexOf("sort=name") >= 0,
    "정렬이 주소에 안 남으면 새로고침에 풀린다: " + last);
}

// --- 7) 주소에 적힌 정렬로 열린다 --------------------------------------------
{
  const dom = build();
  run(dom, "?sort=-name");
  assert.strictEqual(ids(dom), "1,4,5,3,2", "주소에 적힌 정렬대로 안 열렸다");
  assert.strictEqual(numbers(dom), "1,2,3,4,5", "그때도 NO 는 위에서부터다");
}

// --- 8) 이름을 고치면 **세울 값도 따라 고쳐진다** ----------------------------
//
// 값은 처음 한 번만 읽는다(`table_sort.js`). 고친 뒤 다시 안 읽으면 화면에는 새
// 이름이 떠 있는데 머리글을 누르면 **옛 이름 자리**에 선다 — 필터가 같은 이유로
// 이미 `refresh` 를 갖고 있다.
{
  const dom = build();
  run(dom);
  // `inline_edit.js` 가 저장 뒤에 하는 일: 줄에 적힌 값을 고치고 알린다.
  const row = D.queryAll(dom.table, 'tr[data-id="1"]')[0];
  row.setAttribute("data-s-name", "가온");        // 이서준 → 가온(맨 앞으로 가야 한다)
  dom.table.fire("inline-saved");

  nameButton(dom).fire("click");
  assert.strictEqual(ids(dom).split(",")[0], "1",
    "고친 이름이 정렬에 안 반영됐다 — 옛 이름 자리에 섰다");
}

console.log("contacts_sort_test: 통과");
