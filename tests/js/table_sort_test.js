// 머리글을 눌러 표를 세우는가. (node tests/js/table_sort_test.js)
//
// 사용자 원문: "주간 업무 정렬이 추가되어야함 기준은 항목, 일시, 상태를 기준으로
// 오름 및 내림차순" · "정렬은 머리글을 눌러서 정렬되게 해줘".
//
// 세우는 일은 브라우저가 한다(한 주가 60줄 안팎이라 왕복할 이유가 없다). 규칙을
// 여기 옮겨 적으면 두 벌이 되어 어긋나도 모르므로 **파일을 그대로 돌린다**
// (weekly_status_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "table_sort.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 주간 업무 표를 세운다 ---------------------------------------------------
//
// 서버가 그려 주는 차례 그대로 넣는다 — `상태 → 일시 → position → id`
// (`app/services/weekly.py`). 정렬을 끄면 이 차례로 돌아와야 한다.
//   id 1  IR   · 8/07 · 진행중(0)
//   id 2  메일 · 8/21 · 진행중(0)
//   id 3  딜   ·  없음 · 예정(1)
//   id 4  메일 · 8/14 · 완료(2)
const ROWS = [
  { id: "1", category: "IR", due: "2026-08-07", status: "0" },
  { id: "2", category: "메일", due: "2026-08-21", status: "0" },
  { id: "3", category: "딜", due: "", status: "1" },
  { id: "4", category: "메일", due: "2026-08-14", status: "2" }
];

function th(key, label) {
  const cell = D.el("th", key ? { "data-sort": key } : {});
  cell.textContent = label;
  return cell;
}

function build() {
  const head = D.el("thead", {}, [D.el("tr", {}, [
    th("category", "항목"), th(null, "세부업무"), th("due", "일시"), th("status", "상태")
  ])]);
  const body = D.el("tbody", {}, ROWS.map(function (r) {
    return D.el("tr", {
      "data-id": r.id, "data-s-category": r.category,
      "data-s-due": r.due, "data-s-status": r.status
    });
  }));
  // 안내 줄(`이번 주 업무가 없습니다`)은 `data-s-*` 가 없다 — 세우는 대상이
  // 아니어야 하고, 자리도 안 바뀌어야 한다.
  body.appendChild(D.el("tr", { id: "empty-note" }));
  const table = D.el("table", { id: "task-table" }, [head, body]);

  const links = [
    D.el("a", { href: "/todo?week=2026-08-17", "data-sort-keep": "" }),
    D.el("a", { href: "/todo", "data-sort-keep": "" })
  ];
  const root = D.el("div", {}, [D.el("div", {}, links), table]);
  return { root: root, table: table, body: body, links: links,
           heads: D.queryAll(table, "th[data-sort]") };
}

// --- table_sort.js 를 그대로 돌린다 -----------------------------------------
function run(dom, search) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const urls = [];
  const win = {
    location: { pathname: "/todo", search: search || "" },
    history: { replaceState: function (a, b, url) { urls.push(url); } }
  };
  const sandbox = { document: document, window: win };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "table_sort.js" });
  const api = win.DealflowSort;
  api.init({ table: "#task-table" });
  return { urls: urls, sort: api };
}

function ids(dom) {
  return dom.body.children.map(function (tr) {
    return tr.getAttribute("data-id");
  }).filter(function (v) { return v !== null; }).join(",");
}

function button(dom, at) {
  return dom.heads[at].querySelector("button");
}

const CATEGORY = 0, DUE = 1, STATUS = 2;   // th[data-sort] 순서

// --- 1) 머리글을 누르면 세워지고, 세 번 누르면 원래대로 ----------------------
{
  const dom = build();
  run(dom);
  assert.strictEqual(ids(dom), "1,2,3,4", "처음 차례가 서버가 그려 준 그대로가 아니다");

  const btn = button(dom, DUE);
  assert.strictEqual(btn.tag, "button",
    "머리글이 단추가 아니면 키보드(Tab·Enter)로 정렬할 수 없다");
  // 세워져 있지 않아도 **눌러야 세워지는 칸**임이 보여야 한다. 세 칸만 정렬되는
  // 표에서 표시가 없으면 사람이 아무 머리글이나 눌러 보게 된다.
  assert.strictEqual(btn.getAttribute("data-mark"), "↕");
  assert.strictEqual(
    D.queryAll(dom.table, "th").filter(function (t) {
      return !t.getAttribute("data-sort") && t.querySelector("button");
    }).length, 0, "정렬 대상이 아닌 머리글에도 단추가 붙었다");

  btn.fire("click");
  assert.strictEqual(ids(dom), "1,4,2,3",
    "일시 오름차순이 아니다 — 빈 일시는 늘 끝이어야 한다");
  assert.strictEqual(dom.heads[DUE].getAttribute("aria-sort"), "ascending");
  assert.strictEqual(btn.getAttribute("data-mark"), "▲");

  btn.fire("click");
  assert.strictEqual(ids(dom), "2,4,1,3",
    "일시 내림차순이 아니다 — 빈 일시가 방향을 따라 맨 위로 올라왔다면, " +
    "날짜를 안 정한 일이 제일 급한 일처럼 보인다");
  assert.strictEqual(dom.heads[DUE].getAttribute("aria-sort"), "descending");

  btn.fire("click");
  assert.strictEqual(ids(dom), "1,2,3,4",
    "정렬을 끄면 서버가 그려 준 차례(상태 → 일시 → position → id)로 돌아와야 한다");
  assert.strictEqual(dom.heads[DUE].getAttribute("aria-sort"), "none");
}

// --- 2) 상태는 **글자순이 아니다** ------------------------------------------
//
// `진행중 → 예정 → 완료` 라는 일하는 차례가 따로 있다(`STATUS_ORDER`). 가나다로
// 세우면 `예정 → 완료 → 진행중` 이 되어 **다 한 일이 진행 중인 일보다 위**에 온다.
{
  const dom = build();
  run(dom);
  button(dom, STATUS).fire("click");
  assert.strictEqual(ids(dom), "1,2,3,4",
    "상태 오름차순은 진행중 → 예정 → 완료 여야 한다");
  button(dom, STATUS).fire("click");
  assert.strictEqual(ids(dom), "4,3,1,2",
    "상태 내림차순은 그 차례를 뒤집은 것이어야 한다");
}

// --- 3) 같은 값끼리는 처음 차례를 지킨다 -------------------------------------
//
// 항목으로 세워도 `메일` 두 줄 안에서는 서버가 매긴 차례(2 → 4)가 남아야 한다.
// 안 그러면 머리글을 누를 때마다 같은 값 줄이 자기들끼리 뒤섞인다.
//
// **전체 차례를 못 박지 않는다.** 항목에는 `IR` 처럼 한글이 아닌 값이 섞여 있고,
// 한글과 라틴 글자 사이의 차례는 `localeCompare` 를 돌리는 엔진의 사전이 정한다
// (node 와 브라우저가 다를 수 있다). 여기서 지킬 것은 **같은 값끼리의 차례**다.
{
  const dom = build();
  run(dom);
  button(dom, CATEGORY).fire("click");
  const at = ids(dom).split(",");
  assert.ok(at.indexOf("2") < at.indexOf("4"), "같은 항목끼리 처음 차례가 무너졌다");
  assert.ok(at.indexOf("2") + 1 === at.indexOf("4"),
    "같은 항목(`메일`)인 두 줄이 붙어 서지 않았다 — 값으로 세우지 않은 것이다");
}

// --- 4) 다른 머리글을 누르면 그 칸의 오름차순부터 ----------------------------
{
  const dom = build();
  run(dom);
  button(dom, DUE).fire("click");
  button(dom, DUE).fire("click");            // 일시 내림차순
  button(dom, STATUS).fire("click");
  assert.strictEqual(ids(dom), "1,2,3,4");
  assert.strictEqual(dom.heads[DUE].getAttribute("aria-sort"), "none",
    "앞서 세운 칸의 표시가 남아 있으면 무엇으로 세워졌는지 두 칸이 서로 다르게 말한다");
  assert.strictEqual(dom.heads[STATUS].getAttribute("aria-sort"), "ascending");
}

// --- 5) 주소에 남는다 · 남의 쿼리는 그대로 ----------------------------------
{
  const dom = build();
  const out = run(dom, "?week=2026-08-17");
  button(dom, DUE).fire("click");
  const last = out.urls[out.urls.length - 1];
  assert.strictEqual(last, "/todo?week=2026-08-17&sort=due",
    "정렬이 주소에 안 남거나, 보고 있는 주가 주소에서 날아갔다");

  button(dom, DUE).fire("click");
  assert.strictEqual(out.urls[out.urls.length - 1], "/todo?week=2026-08-17&sort=-due");

  button(dom, DUE).fire("click");
  assert.strictEqual(out.urls[out.urls.length - 1], "/todo?week=2026-08-17",
    "정렬을 껐는데 주소에 남아 있으면 새로고침에 되살아난다");
}

// --- 6) 주소에 적힌 정렬로 열린다(새로고침해도 남는다) -----------------------
{
  const dom = build();
  run(dom, "?week=2026-08-17&sort=-due");
  assert.strictEqual(ids(dom), "2,4,1,3", "주소에 적힌 정렬대로 안 열렸다");
  assert.strictEqual(dom.heads[DUE].getAttribute("aria-sort"), "descending");
}

// --- 7) 모르는 칸이 적혀 있으면 무시한다 ------------------------------------
//
// 주소는 사람이 고쳐 쓸 수 있는 자리다. 모르는 값에 화면이 멎으면 안 된다.
{
  const dom = build();
  run(dom, "?sort=%EC%97%86%EB%8A%94%EC%B9%B8");
  assert.strictEqual(ids(dom), "1,2,3,4");
}

// --- 8) 주를 옮기는 링크가 정렬을 실어 간다 ---------------------------------
//
// [← 지난 주] 는 링크라 화면이 한 번 새로 그려진다. 안 실어 주면 세워 둔 차례가
// 그 한 번에 풀린다.
{
  const dom = build();
  run(dom, "?week=2026-08-17");
  button(dom, STATUS).fire("click");
  assert.strictEqual(dom.links[0].getAttribute("href"),
    "/todo?week=2026-08-17&sort=status");
  assert.strictEqual(dom.links[1].getAttribute("href"), "/todo?sort=status",
    "쿼리가 없던 링크에는 `?` 로 붙어야 한다");

  button(dom, STATUS).fire("click");         // 내림
  button(dom, STATUS).fire("click");         // 끔
  assert.strictEqual(dom.links[0].getAttribute("href"), "/todo?week=2026-08-17",
    "정렬을 껐는데 링크에 남아 있으면 주를 옮기는 순간 되살아난다");
}

// --- 9) 값이 없는 줄은 세우지 않는다 -----------------------------------------
{
  const dom = build();
  run(dom);
  button(dom, DUE).fire("click");
  const note = dom.body.children[dom.body.children.length - 1];
  assert.strictEqual(note.getAttribute("id"), "empty-note",
    "`data-s-*` 가 없는 안내 줄이 정렬에 끌려 들어갔다");
}

console.log("table_sort_test: 통과");
