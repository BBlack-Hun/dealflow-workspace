// IR 기업 현황 — **날짜·숫자 머리글을 눌러 세운다.** (node tests/js/company_sort_test.js)
//
// 사용자 요청: 「수정한 날짜 기준 정렬」. 범위는 **날짜·숫자 칸 전부**로 정해져,
// 이 탭에서는 셋이 선다 — `수정한 날짜`·`소개 횟수`·`미팅제공일자`.
//
// 세우는 일 자체는 주간 업무·투자사 명단이 쓰던 부품 그대로다(`table_sort.js`).
// 그래서 여기서 다시 보는 것은 **그 부품이 이 표에 제대로 물렸는가**와, 이 표에만
// 있는 판단들이다.
//
//   · `소개 횟수` 는 화면에 `6회 · 180명` 으로 뜬다. 글자로 세우면 `10회` 가
//     `2회` 보다 앞에 서고, 한 번도 안 나간 `–` 가 빈 값으로 읽혀 끝으로 밀린다.
//   · `미팅제공일자` 는 손으로 적는 칸이라 `9월 중`·`미정` 이 섞여 있다. 날짜가
//     아닌 글자는 빈 값으로 실려 **방향과 상관없이 늘 끝**에 서야 한다.
//   · `NO` 는 보이는 것 기준 1,2,3… 이라 **차례가 곧 번호**다. 세우고 안 다시
//     매기면 번호가 옛 자리에 남아 목록을 셀 수가 없다.
//   · 검색·필터와 **싸우면 안 된다.** 감춰 둔 줄이 세우는 순간 되살아나면
//     걸어 둔 조건이 풀린다.
//   · 한 줄을 고치면 `수정한 날짜` 가 오른다 — 그 새 값으로 **다시 서야** 한다.
//
// 규칙을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모르므로 **파일 넷을 그대로
// 돌린다**(filters.js · table_sort.js · panel_modal.js · companies.js).
//
// 기업명은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(SRC, name), "utf8");

// **서버가 그려 주는 차례 그대로** 넣는다(이 탭은 이름순 — `sort_for_tab`).
// 정렬을 끄면 이 차례로 돌아와야 하고, 같은 값끼리도 이 차례가 남아야 한다.
//
//   id 1 가온샘플  09-16 19:44:43   2회   2026-09-15
//   id 2 나루샘플  09-01 08:00:00  10회   (빈 칸)        ← 두 자리 수 · 빈 날짜
//   id 3 다온샘플  09-16 19:48:16   0회   9월 중         ← 한 번도 안 나감 · 날짜 아닌 글자
//   id 4 라온샘플  08-02 03:04:05   2회   2026-10-01     ← `2` 가 둘(동률)
//   id 5 마루샘플  09-20 00:00:00   3회   2026-09-15     ← 같은 날짜가 둘(동률)
const ROWS = [
  { id: "1", name: "가온샘플", updated: "2026-09-16 19:44:43", sent: 2,
    meetingText: "2026-09-15", meetingSort: "2026-09-15", assignee: "담당가" },
  { id: "2", name: "나루샘플", updated: "2026-09-01 08:00:00", sent: 10,
    meetingText: "", meetingSort: "", assignee: "담당나" },
  { id: "3", name: "다온샘플", updated: "2026-09-16 19:48:16", sent: 0,
    meetingText: "9월 중", meetingSort: "", assignee: "담당가" },
  { id: "4", name: "라온샘플", updated: "2026-08-02 03:04:05", sent: 2,
    meetingText: "2026-10-01", meetingSort: "2026-10-01", assignee: "담당나" },
  { id: "5", name: "마루샘플", updated: "2026-09-20 00:00:00", sent: 3,
    meetingText: "2026-09-15", meetingSort: "2026-09-15", assignee: "담당가" }
];

function th(attrs, label) {
  const cell = D.el("th", attrs || {});
  cell.textContent = label;
  return cell;
}

// 화면(`app/templates/companies.html`)이 그리는 만큼만 세운다.
function build() {
  const head = D.el("thead", {}, [D.el("tr", {}, [
    th({ class: "num stick stick-a" }, "NO"),
    // 글자 칸이다 — **정렬을 일부러 안 붙인다**(가나다순은 쓸모가 적고,
    // 가로로 고정된 칸이다). 아래 ⑨ 가 그것을 못 박는다.
    th({ class: "stick stick-b" }, "기업명"),
    th({ "data-sort": "updated" }, "수정한 날짜"),
    // 같은 표에 필터도 붙어 있다 — 정렬이 그것을 풀지 않는지 봐야 한다.
    th({ "data-filters": "assignee:담당자" }, "담당자"),
    th({ class: "num", "data-sort": "sent" }, "소개 횟수"),
    th({ "data-sort": "meeting" }, "미팅제공일자")
  ])]);

  const body = D.el("tbody", {}, ROWS.map(function (r) {
    const updated = D.el("td", { class: "updated-at" });
    updated.textContent = r.updated;
    const name = D.el("td", { class: "co-name stick stick-b" });
    name.textContent = r.name;
    const assignee = D.el("td", { class: "cell", "data-field": "assignee_name",
                                  "data-filter-key": "assignee" });
    assignee.textContent = r.assignee;
    // 화면에는 `2회 · 12건` 같은 **글자**가 뜬다. 세울 값은 그것이 아니다.
    const sent = D.el("td", { class: "num sent-count" });
    sent.textContent = r.sent ? r.sent + "회 · " + (r.sent * 6) + "건" : "–";
    const meeting = D.el("td", { class: "cell", "data-field": "meeting_offered_at" });
    meeting.textContent = r.meetingText;

    return D.el("tr", {
      "data-id": r.id,
      "data-search": (r.name + " " + r.assignee).toLowerCase(),
      "data-f-assignee": r.assignee,
      "data-s-updated": r.updated,
      "data-s-sent": String(r.sent),
      "data-s-meeting": r.meetingSort
    }, [D.el("td", { class: "rowno" }), name, updated, assignee, sent, meeting]);
  }));

  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
                     [head, body]);
  const search = D.el("input", { id: "co-search" });
  const root = D.el("div", {}, [
    table, search,
    D.el("p", { id: "co-note" }),
    D.el("p", { id: "co-status" }),
    D.el("p", { id: "co-updated" }),
    D.el("aside", { id: "co-panel" }),
    D.el("div", { id: "co-backdrop" }),
    D.el("button", { id: "co-add" }),
    D.el("button", { id: "co-close" }),
    D.el("button", { id: "co-cancel" }),
    D.el("button", { id: "co-save" })
  ]);
  return { root: root, table: table, body: body, search: search,
           heads: D.queryAll(table, "th") };
}

// --- 화면 파일들을 그대로 돌린다 ---------------------------------------------
function run(dom, search) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const urls = [];
  const win = {
    location: { pathname: "/companies", search: search || "", reload: function () {} },
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
    MutationObserver: function () { this.observe = function () {}; },
    alert: function () {}, confirm: function () { return false; },
    setTimeout: setTimeout,
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function () {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  // 화면이 부르는 차례 그대로다(companies.html) — 정렬기가 뒤에 오면
  // companies.js 가 `window.DealflowSort` 를 못 본다.
  ["filters.js", "panel_modal.js", "table_sort.js", "companies.js"].forEach(function (name) {
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

// 머리글 단추. `heads` 차례는 build() 의 그것이다.
const AT = { updated: 2, sent: 4, meeting: 5 };
function button(dom, key) { return dom.heads[AT[key]].querySelector("button"); }

// --- ① 수정한 날짜 — 요청의 핵심 ---------------------------------------------
{
  const dom = build();
  run(dom);
  assert.strictEqual(ids(dom), "1,2,3,4,5",
    "처음 차례가 서버가 그려 준 그대로가 아니다");

  const btn = button(dom, "updated");
  assert.ok(btn && btn.tag === "button",
    "`수정한 날짜` 머리글이 단추가 아니면 키보드(Tab·Enter)로 정렬할 수 없다");
  assert.strictEqual(btn.getAttribute("data-mark"), "↕",
    "눌러야 세워지는 칸임이 안 보이면, 칸 열여섯 개짜리 표에서 아무 머리글이나 눌러 보게 된다");

  btn.fire("click");
  assert.strictEqual(ids(dom), "4,2,1,3,5",
    "오래된 것부터가 아니다 — 같은 날 19:44:43 과 19:48:16 도 **초까지** 갈라야 한다");
  assert.strictEqual(dom.heads[AT.updated].getAttribute("aria-sort"), "ascending");

  btn.fire("click");
  assert.strictEqual(ids(dom), "5,3,1,2,4", "최근 것부터가 아니다");
  assert.strictEqual(dom.heads[AT.updated].getAttribute("aria-sort"), "descending");

  btn.fire("click");
  assert.strictEqual(ids(dom), "1,2,3,4,5",
    "정렬을 끄면 서버가 그려 준 차례(이름순)로 돌아와야 한다");
  assert.strictEqual(dom.heads[AT.updated].getAttribute("aria-sort"), "none");
}

// --- ② 소개 횟수 — **수로 센다.** 그리고 `–` 는 빈 값이 아니라 0 이다 --------
//
// 화면 글자(`10회 · 60건`)로 세우면 `10회` 가 `2회` 보다 앞에 선다. 그리고 한
// 번도 안 나간 기업을 빈 값으로 실으면 방향과 상관없이 늘 끝으로 밀려, 오름차순
// 맨 위에서 "아직 한 번도 안 나간 곳" 을 찾을 수가 없다.
{
  const dom = build();
  run(dom);
  const btn = button(dom, "sent");

  btn.fire("click");
  assert.strictEqual(ids(dom), "3,1,4,5,2",
    "0 → 2 → 2 → 3 → 10 이 아니다 — 글자로 세우면 `10` 이 `2` 앞에 선다");
  assert.strictEqual(ids(dom).split(",")[0], "3",
    "한 번도 안 나간 줄(`–`)이 오름차순 맨 위가 아니다 — 그것은 빈 값이 아니라 0 이다");

  btn.fire("click");
  assert.strictEqual(ids(dom), "2,5,1,4,3", "많이 나간 것부터가 아니다");
  assert.strictEqual(ids(dom).split(",").pop(), "3",
    "내림차순에서 0 회가 끝이 아니다 — 0 을 빈 값으로 실으면 여기서 맨 위로 온다");
}

// --- ③ 소개 횟수 — 같은 회차끼리는 **처음 차례를 지킨다** --------------------
{
  const dom = build();
  run(dom);
  button(dom, "sent").fire("click");
  const at = ids(dom).split(",");
  assert.ok(at.indexOf("1") + 1 === at.indexOf("4"),
    "같은 2회인 두 줄이 붙어 서지 않았다 — 회차로 세우지 않은 것이다");
  assert.ok(at.indexOf("1") < at.indexOf("4"),
    "같은 회차끼리 처음 차례(이름순 1 → 4)가 무너졌다");
}

// --- ④ 미팅제공일자 — 날짜가 아닌 글자는 **방향과 상관없이 늘 끝** ----------
//
// 손으로 적는 칸이라 `9월 중`·`미정` 이 섞여 들어온다(달력 고르개를 일부러 안
// 붙였다). 그 글자를 그대로 세우면 내림차순에서 `미정` 이 맨 위로 올라와, 가장
// 나중 날짜를 보려고 세웠는데 날짜 없는 줄부터 읽게 된다.
{
  const dom = build();
  run(dom);
  const btn = button(dom, "meeting");

  btn.fire("click");
  assert.strictEqual(ids(dom), "1,5,4,2,3",
    "빠른 날짜부터가 아니다 — 날짜 없는 둘(빈 칸 2 · `9월 중` 3)은 끝이어야 한다");

  btn.fire("click");
  assert.strictEqual(ids(dom), "4,1,5,2,3",
    "늦은 날짜부터가 아니다 — 날짜 없는 둘이 방향을 따라 맨 위로 올라왔다");
  assert.strictEqual(ids(dom).split(",").slice(-2).join(","), "2,3",
    "날짜 없는 줄끼리도 처음 차례(이름순)가 남아야 한다");
}

// --- ⑤ 세우면 **NO 를 다시 매긴다** -----------------------------------------
{
  const dom = build();
  run(dom);
  assert.strictEqual(numbers(dom), "1,2,3,4,5");
  button(dom, "updated").fire("click");
  assert.strictEqual(ids(dom), "4,2,1,3,5");
  assert.strictEqual(numbers(dom), "1,2,3,4,5",
    "세우고 나서 NO 를 다시 안 매겼다 — 번호가 `4,2,1,3,5` 로 옛 자리에 남았다");
}

// --- ⑥ 검색·필터와 **싸우지 않는다** ----------------------------------------
{
  const dom = build();
  run(dom);
  dom.search.value = "담당가";
  dom.search.fire("input");
  assert.strictEqual(shown(dom), "1,3,5", "검색이 안 걸렸다");

  button(dom, "updated").fire("click");
  assert.strictEqual(shown(dom), "1,3,5",
    "걸러낸 줄만 세워야 한다 — 오래된 것부터면 1 → 3 → 5 다");
  assert.strictEqual(dom.body.children.filter(function (tr) { return !tr.hidden; }).length, 3,
    "세우는 순간 감춰 둔 줄이 되살아났다 — 걸어 둔 조건이 풀린 것이다");

  button(dom, "updated").fire("click");
  assert.strictEqual(shown(dom), "5,3,1", "내림차순에서도 걸러낸 줄만 서야 한다");
  // 번호는 **보이는 것** 기준이다 — 감춘 줄은 빈칸으로 남는다.
  assert.strictEqual(
    dom.body.children.filter(function (tr) { return !tr.hidden; })
      .map(function (tr) { return tr.querySelector(".rowno").textContent; }).join(","),
    "1,2,3", "걸러낸 뒤의 NO 가 1 부터가 아니다");
}

// --- ⑦ 주소에 남는다 · 남의 쿼리는 그대로 -----------------------------------
//
// **이 화면은 저장하면 페이지를 통째로 다시 불러온다**(`companies.js` 의
// `location.reload`). 정렬이 주소에 안 남으면 한 줄 고칠 때마다 차례가 풀린다.
{
  const dom = build();
  const out = run(dom, "?q=%EA%B0%80%EC%98%A8");
  button(dom, "sent").fire("click");
  const last = out.urls[out.urls.length - 1];
  assert.ok(last.indexOf("q=") >= 0,
    "정렬이 검색어를 주소에서 날렸다: " + last);
  assert.ok(last.indexOf("sort=sent") >= 0,
    "정렬이 주소에 안 남으면 저장 뒤 다시 불러올 때 풀린다: " + last);
}

// --- ⑧ 주소에 적힌 정렬로 열린다 --------------------------------------------
{
  const dom = build();
  run(dom, "?sort=-updated");
  assert.strictEqual(ids(dom), "5,3,1,2,4", "주소에 적힌 정렬대로 안 열렸다");
  assert.strictEqual(numbers(dom), "1,2,3,4,5", "그때도 NO 는 위에서부터다");
}

// --- ⑨ 글자 칸에는 **안 붙는다** --------------------------------------------
//
// 이 표의 머리글 폭은 전부 "필터를 건 뒤의 머리글" 에 맞춘 최소값이라, 정렬
// 꼬리표까지 더하면 두 줄로 접힌다. 그리고 `NO` 는 보이는 것 기준 번호라
// 그것으로 세울 것이 없다.
{
  const dom = build();
  run(dom);
  assert.strictEqual(dom.heads[0].querySelector("button"), null,
    "`NO` 에 정렬 단추가 섰다 — 차례가 곧 번호라 세울 것이 없는 칸이다");
  assert.strictEqual(dom.heads[1].querySelector("button"), null,
    "`기업명` 에 정렬 단추가 섰다 — 글자 칸은 이번 범위가 아니다");
  assert.ok(dom.heads[3].querySelector(".filter-btn"),
    "`담당자` 의 필터 단추가 없어졌다");
  assert.strictEqual(dom.heads[3].querySelector("button.sort-btn"), null,
    "필터가 선 머리글에 정렬 단추까지 섰다 — 한 머리글에 단추가 둘이면 접힌다");
}

// --- ⑩ 한 줄을 고치면 **그 새 시각으로 다시 선다** --------------------------
//
// 값은 처음 한 번만 읽는다(`table_sort.js`). 고친 뒤 다시 안 읽으면 칸에는 방금
// 시각이 떠 있는데 줄은 **옛 시각 자리**에 그대로 앉아 있다. 이 화면은 값이
// 두 손을 거친다 — 응답이 칸과 `data-s-updated` 를 고쳐 적고, 그다음 정렬기가
// 다시 읽는다. 차례가 뒤집히면 방금 고친 줄만 옛 자리에 남는다.
{
  const dom = build();
  run(dom);
  const btn = button(dom, "updated");
  btn.fire("click");
  btn.fire("click");                                   // 최근 것부터
  assert.strictEqual(ids(dom), "5,3,1,2,4");

  // 가장 오래된 줄(4)을 고쳤다 — 맨 위로 와야 한다.
  const row = D.queryAll(dom.table, 'tr[data-id="4"]')[0];
  const NEW = "2026-09-21 11:22:33";
  dom.table.fire("inline-saved", {
    detail: { row: row, cell: row.querySelector('[data-field="assignee_name"]'),
              value: "담당가", data: { updated_at: NEW, meeting_sort: "2026-10-01" } }
  });

  assert.strictEqual(row.querySelector("td.updated-at").textContent, NEW,
    "`수정한 날짜` 칸이 응답 값으로 안 바뀌었다");
  assert.strictEqual(row.getAttribute("data-s-updated"), NEW,
    "세울 값(`data-s-updated`)이 안 따라 바뀌었다 — 줄은 옛 시각 자리에 남는다");

  setTimeout(function () {
    assert.strictEqual(ids(dom), "4,5,3,1,2",
      "고친 줄이 새 시각 자리로 안 갔다 — 세울 값을 다시 안 읽은 것이다");
    assert.strictEqual(numbers(dom), "1,2,3,4,5", "다시 선 뒤 NO 가 옛 자리에 남았다");
    done();
  }, 0);
}

// --- ⑪ 미팅제공일자를 고치면 **추려 낸 날짜**가 따라온다 --------------------
//
// 세울 값은 화면 글자가 아니라 거기서 날짜만 추려 낸 것이라(`meeting_sort_key`),
// 브라우저가 제 손으로 만들 수 없다 — 응답이 실어 준다.
function step11() {
  const dom = build();
  run(dom);
  const btn = button(dom, "meeting");
  btn.fire("click");
  assert.strictEqual(ids(dom), "1,5,4,2,3");

  // `9월 중` 이던 줄(3)에 날짜를 적었다 — 맨 앞으로 와야 한다.
  const row = D.queryAll(dom.table, 'tr[data-id="3"]')[0];
  dom.table.fire("inline-saved", {
    detail: { row: row, cell: row.querySelector('[data-field="meeting_offered_at"]'),
              value: "2026-08-20",
              data: { updated_at: "2026-09-22 09:00:00", meeting_sort: "2026-08-20" } }
  });
  assert.strictEqual(row.getAttribute("data-s-meeting"), "2026-08-20",
    "세울 값이 응답(`meeting_sort`)으로 안 바뀌었다");

  setTimeout(function () {
    assert.strictEqual(ids(dom), "3,1,5,4,2",
      "날짜를 적은 줄이 여전히 '날짜 없음' 자리(끝)에 남아 있다");
    console.log("company_sort_test: 통과");
  }, 0);
}

function done() { step11(); }
