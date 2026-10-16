// 기업 표 — **기본은 수신일 최신순, 이름순은 골라서.** (node tests/js/company_received_order_test.js)
//
// 두 탭(IR 기업 현황 · 스타트업DB)의 기본 차례는 서버가 정한다 — 수신일 최신순,
// 날짜 없는 곳은 맨 아래(`routers/companies.py` 의 `sort_by_received`, 규칙 하나).
// 여기서 보는 것은 **거기서 벗어나는 길**이다.
//
//   · `?sort=name` 으로 열면 이름순으로 선다(서버는 그 값을 모른다 — 세우는
//     것은 `table_sort.js` 다).
//   · `기업명` 머리글을 누르면 오름 → 내림 → 끔. **끄면 수신일 최신순**으로
//     돌아온다 — 서버가 그려 준 차례가 곧 기본 차례이기 때문이다.
//   · 두 탭 모두 같다. 스타트업DB 는 주소에 `?tab=db` 가 붙어 있어서, 정렬이
//     그것을 지우면 머리글 한 번에 옆 탭으로 튄다.
//   · 옆 탭에만 있는 정렬 키(`updated`)가 주소에 남아 있어도 깨지지 않는다.
//
// 규칙을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모르므로 **화면 파일 넷을 그대로
// 돌린다**(filters.js · panel_modal.js · table_sort.js · companies.js) —
// `company_sort_test.js` 와 같은 틀이다.
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

// **서버가 그려 주는 차례 그대로** 넣는다 — 수신일 최신순, 같은 날은 이름순,
// 날짜 없는 둘(빈 칸 · `날짜 미정`)은 맨 아래에서 이름순. 이름순과는 **일부러
// 다르게** 골랐다 — 같으면 `?sort=name` 이 아무 일도 안 해도 통과한다.
//
//   id 1 마루샘플  2026-09-20
//   id 2 가온샘플  2026-09-11
//   id 3 다온샘플  2026-09-11     ← 같은 날 — 이름순(가온 → 다온)
//   id 4 나루샘플  2026-08-01
//   id 5 라온샘플  (빈 칸)        ← 날짜 없음
//   id 6 바다샘플  날짜 미정      ← 날짜 없음
//
// 이름순이면 가온(2) 나루(4) 다온(3) 라온(5) 마루(1) 바다(6).
const ROWS = [
  { id: "1", name: "마루샘플", received: "2026-09-20", updated: "2026-09-01 10:00" },
  { id: "2", name: "가온샘플", received: "2026-09-11", updated: "2026-09-03 10:00" },
  { id: "3", name: "다온샘플", received: "2026-09-11", updated: "2026-09-02 10:00" },
  { id: "4", name: "나루샘플", received: "2026-08-01", updated: "2026-09-05 10:00" },
  { id: "5", name: "라온샘플", received: "", updated: "2026-09-04 10:00" },
  { id: "6", name: "바다샘플", received: "날짜 미정", updated: "2026-09-06 10:00" }
];
const SERVER = "1,2,3,4,5,6";
const BY_NAME = "2,4,3,5,1,6";
const BY_NAME_DESC = "6,1,5,3,4,2";

function th(attrs, label) {
  const cell = D.el("th", attrs || {});
  cell.textContent = label;
  return cell;
}

function td(attrs, text) {
  const cell = D.el("td", attrs || {});
  cell.textContent = text || "";
  return cell;
}

// 화면(`app/templates/companies.html`)이 그리는 만큼만 세운다. 두 탭이 같은
// id(`co-table`)를 쓰고 같은 companies.js 가 붙는다 — 다른 것은 칸들이다.
//
//   IR 기업 현황: NO · 기업명(정렬) · 수신일 · 수정한 날짜(정렬) · 담당자(필터)
//   스타트업DB  : NO · 수신일 · 기업명(정렬) · IR 자료(필터)
function build(tab) {
  const status = tab !== "db";
  const heads = status ? [
    th({ class: "num stick stick-a" }, "NO"),
    th({ class: "stick stick-b", "data-sort": "name" }, "기업명"),
    th({}, "수신일"),
    th({ "data-sort": "updated" }, "수정한 날짜"),
    th({ "data-filters": "assignee:담당자" }, "담당자")
  ] : [
    th({ class: "num" }, "NO"),
    th({}, "수신일"),
    th({ "data-sort": "name" }, "기업명"),
    th({ "data-filters": "ir:IR 자료" }, "IR 자료")
  ];
  const head = D.el("thead", {}, [D.el("tr", {}, heads)]);

  const body = D.el("tbody", {}, ROWS.map(function (r) {
    const name = td({ class: "co-name" });
    name.appendChild(D.el("b", { class: "cell", "data-field": "name" }));
    name.querySelector("b").textContent = r.name;
    const received = td({ class: "cell", "data-field": "received_at", "data-type": "date" },
                        r.received);
    const attrs = { "data-id": r.id, "data-search": r.name.toLowerCase(),
                    "data-s-name": r.name };
    let cells;
    if (status) {
      attrs["data-f-assignee"] = "담당가";
      attrs["data-s-updated"] = r.updated;
      cells = [td({ class: "rowno" }), name, received,
               td({ class: "updated-at" }, r.updated),
               td({ class: "cell", "data-field": "assignee_name",
                    "data-filter-key": "assignee" }, "담당가")];
    } else {
      attrs["data-f-ir"] = "● 있음";
      cells = [td({ class: "rowno" }), received, name, td({}, "📎 있음")];
    }
    return D.el("tr", attrs, cells);
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
  const nameAt = status ? 1 : 2;
  return { root: root, table: table, body: body, search: search,
           nameHead: D.queryAll(table, "th")[nameAt] };
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
        // 브라우저처럼 `location.search` 도 따라 바꾼다 — 안 따라가면 두 부품
        // (필터·정렬)이 서로의 쿼리를 못 보고 지우는 사고를 검사가 못 본다.
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
  // 화면이 부르는 차례 그대로다(companies.html).
  ["filters.js", "panel_modal.js", "table_sort.js", "companies.js"].forEach(function (name) {
    vm.runInContext(read(name), sandbox, { filename: name });
  });
  return { urls: urls, win: win };
}

function ids(dom) {
  return dom.body.children.map(function (tr) { return tr.getAttribute("data-id"); }).join(",");
}

function numbers(dom) {
  return dom.body.children.map(function (tr) {
    return tr.querySelector(".rowno").textContent;
  }).join(",");
}

function nameButton(dom) { return dom.nameHead.querySelector("button"); }

["status", "db"].forEach(function (tab) {
  const base = tab === "db" ? "?tab=db" : "";
  const label = tab === "db" ? "스타트업DB" : "IR 기업 현황";

  // --- ① 주소에 아무것도 없으면 **서버가 그린 차례**(수신일 최신순) 그대로 ---
  {
    const dom = build(tab);
    run(dom, base);
    assert.strictEqual(ids(dom), SERVER,
      label + ": 처음 차례가 서버가 그려 준 수신일 최신순이 아니다");
    const btn = nameButton(dom);
    assert.ok(btn && btn.tag === "button",
      label + ": `기업명` 머리글이 단추가 아니다 — 이름순으로 바꿀 길이 없다");
    assert.strictEqual(btn.getAttribute("data-mark"), "↕",
      label + ": 아무것도 안 골랐는데 `기업명` 이 세워진 것처럼 보인다");
    assert.strictEqual(dom.nameHead.getAttribute("aria-sort"), "none");
  }

  // --- ② `?sort=name` 으로 열면 **이름순** ------------------------------------
  {
    const dom = build(tab);
    run(dom, base ? base + "&sort=name" : "?sort=name");
    assert.strictEqual(ids(dom), BY_NAME,
      label + ": `?sort=name` 으로 열었는데 이름순이 아니다");
    assert.strictEqual(numbers(dom), "1,2,3,4,5,6",
      label + ": 이름순으로 선 뒤 NO 를 다시 안 매겼다");
    assert.strictEqual(dom.nameHead.getAttribute("aria-sort"), "ascending");
    assert.strictEqual(nameButton(dom).getAttribute("data-mark"), "▲",
      label + ": 지금 이름순이라는 표시(▲)가 머리글에 없다");
  }

  // --- ③ 눌러서: 오름 → 내림 → 끔(= 수신일 최신순) ---------------------------
  {
    const dom = build(tab);
    const out = run(dom, base);
    const btn = nameButton(dom);

    btn.fire("click");
    assert.strictEqual(ids(dom), BY_NAME, label + ": 한 번 누르면 이름 오름차순이어야 한다");
    let last = out.urls[out.urls.length - 1];
    assert.ok(last.indexOf("sort=name") >= 0,
      label + ": 이름순이 주소에 안 남았다 — 새로고침하면 풀린다: " + last);
    if (base) {
      assert.ok(last.indexOf("tab=db") >= 0,
        label + ": 정렬이 `tab=db` 를 지웠다 — 새로고침하면 옆 탭으로 튄다: " + last);
    }

    btn.fire("click");
    assert.strictEqual(ids(dom), BY_NAME_DESC, label + ": 두 번 누르면 이름 내림차순이어야 한다");

    btn.fire("click");
    assert.strictEqual(ids(dom), SERVER,
      label + ": 세 번째(끔)에 **수신일 최신순**으로 돌아오지 않았다");
    assert.strictEqual(numbers(dom), "1,2,3,4,5,6");
    last = out.urls[out.urls.length - 1];
    assert.ok(last.indexOf("sort=") < 0,
      label + ": 끈 뒤에도 주소에 정렬이 남았다: " + last);
    if (base) {
      assert.ok(last.indexOf("tab=db") >= 0, label + ": 끄면서 `tab=db` 를 지웠다: " + last);
    }
  }

  // --- ④ 검색과 함께 — 걸러 낸 줄만 이름순으로 선다 --------------------------
  {
    const dom = build(tab);
    run(dom, base ? base + "&sort=name" : "?sort=name");
    dom.search.value = "루";                  // 마루(1)·나루(4) — 서버 차례로는 1 → 4
    dom.search.fire("input");
    const visible = dom.body.children.filter(function (tr) { return !tr.hidden; })
      .map(function (tr) { return tr.getAttribute("data-id"); }).join(",");
    assert.strictEqual(visible, "4,1",
      label + ": 이름순으로 선 표에서 검색이 걸러 낸 줄의 차례가 이름순이 아니다");
  }
});

// --- ⑤ 옆 탭에만 있는 정렬 키가 주소에 남아 있어도 **기본 차례로** 선다 -------
//
// IR 기업 현황에서 `수정한 날짜` 로 세워 둔 주소(`?sort=-updated`)에 `tab=db` 를
// 붙여 열 수 있다. 스타트업DB 에는 그 칸이 없으므로 모르는 키다 — 무시하고
// 수신일 최신순으로 서야 한다(`table_sort.js` 의 '모르는 칸이면 무시').
{
  const dom = build("db");
  run(dom, "?tab=db&sort=-updated");
  assert.strictEqual(ids(dom), SERVER,
    "스타트업DB: 모르는 정렬 키에 차례가 흔들렸다 — 기본 차례(수신일 최신순)여야 한다");
}

console.log("company_received_order_test: 통과");
