// IR 기업 현황 메뉴의 `Series A 이상 딜 소싱` 탭 — 브라우저 쪽.
// (node tests/js/series_a_test.js)
//
// 규칙을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모르므로 **파일 셋을 그대로
// 돌린다**(filters.js · table_sort.js · series_a.js — 화면이 부르는 차례 그대로).
//
//   ① 처음 열면 줄 번호가 보이는 것 기준 1,2,3… 이다.
//   ② 검색 · 머리글 필터가 AND 로 걸리고, 번호를 다시 매긴다.
//   ③ `수신 일자` 머리글을 눌러 세우고, 세운 뒤에도 번호를 다시 매긴다.
//   ④ 저장 뒤 **서버만 아는 값**(투자라운드의 짧은 꼴 · IR 딱지)을 응답에서 받아 적는다.
//   ⑤ [삭제] 는 이름을 대고 묻고, 아니라면 아무것도 안 보낸다.
//   ⑥ 기업명을 넣어 IR 기업에 이어지면 채워진 칸 · `IR 기업:` 표시가 새로고침 없이 선다.
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

// 서버가 그려 주는 차례 그대로(수신 일자 최신순 — `routers/series_a.sort_rows`).
const ROWS = [
  { id: "1", name: "가온샘플", day: "2026-08-25", type: "딜 소싱 네트워크",
    series: "Series B", short: "Series B", ir: "" },
  { id: "2", name: "샘플메디", day: "2026-07-01", type: "후속 투자 연계",
    series: "Series A (누적투자금 10억이상)", short: "Series A", ir: "" },
  { id: "3", name: "나루샘플", day: "", type: "딜 소싱 네트워크",
    series: "", short: "", ir: "" }
];

function th(attrs, label) {
  const cell = D.el("th", attrs || {});
  cell.textContent = label;
  return cell;
}

// 화면(`app/templates/companies_series_a.html`)이 그리는 만큼만 세운다.
function build() {
  const head = D.el("thead", {}, [D.el("tr", {}, [
    th({ class: "num stick stick-a" }, "NO"),
    th({ class: "stick stick-b" }, "기업명"),
    th({ "data-sort": "received_at", "data-sort-default": "desc" }, "수신 일자"),
    th({ "data-filters": "type:Type" }, "Type"),
    th({ "data-filters": "series:투자라운드" }, "투자라운드"),
    th({}, "")
  ])]);
  const body = D.el("tbody", {}, ROWS.map(function (r) {
    const name = D.el("b", { class: "cell", "data-field": "name" });
    name.textContent = r.name;
    const link = D.el("a", { class: "room-badge ok ir-link",
                             href: "/companies?q=" + encodeURIComponent(r.ir) });
    link.hidden = !r.ir;
    const day = D.el("td", { class: "cell", "data-field": "received_at", "data-type": "date" });
    day.textContent = r.day;
    const type = D.el("td", { class: "cell", "data-field": "deal_type", "data-type": "pick",
                              "data-filter-key": "type" });
    type.textContent = r.type;
    const series = D.el("div", { class: "cell clamp2", "data-field": "series",
                                 "data-type": "pick", "data-filter-key": "series",
                                 "data-value": r.series });
    series.textContent = r.short;
    const del = D.el("button", { class: "linkbtn js-sa-delete" });
    return D.el("tr", {
      "data-id": r.id,
      "data-search": (r.name + " " + r.type).toLowerCase(),
      "data-f-type": r.type,
      "data-f-series": r.short,
      "data-s-received_at": r.day
    }, [D.el("td", { class: "rowno muted stick stick-a" }),
        D.el("td", { class: "co-name stick stick-b" }, [name, link]),
        day, type, D.el("td", { title: r.series }, [series]), D.el("td", {}, [del])]);
  }));
  const table = D.el("table", { id: "sa-table", "data-inline-url": "/api/series-a-companies" },
                     [head, body]);
  const search = D.el("input", { id: "sa-search" });
  const root = D.el("div", {}, [
    search, D.el("button", { id: "sa-add" }),
    D.el("div", { class: "chip-row", "data-filter-chips": "" }),
    D.el("p", { id: "sa-note" }), table
  ]);
  return { root: root, table: table, body: body, search: search,
           heads: D.queryAll(table, "th") };
}

function run(dom, search, answer) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const calls = [];
  const asked = [];
  const win = {
    location: { pathname: "/companies", search: search || "", reload: function () {} },
    history: {
      replaceState: function (a, b, url) {
        const at = String(url).indexOf("?");
        win.location.search = at < 0 ? "" : String(url).slice(at);
      }
    }
  };
  const sandbox = {
    document: document, console: console,
    alert: function () {},
    confirm: function (text) { asked.push(text); return !!answer; },
    prompt: function () { return ""; },
    setTimeout: setTimeout,
    encodeURIComponent: encodeURIComponent,
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, init) {
      calls.push({ url: url, method: init && init.method });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  ["filters.js", "table_sort.js", "series_a.js"].forEach(function (name) {
    vm.runInContext(read(name), sandbox, { filename: name });
  });
  return { calls: calls, asked: asked, win: win };
}

const ids = (dom) => dom.body.children.map((tr) => tr.getAttribute("data-id")).join(",");
const shown = (dom) => dom.body.children.filter((tr) => !tr.hidden)
  .map((tr) => tr.getAttribute("data-id")).join(",");
const numbers = (dom) => dom.body.children
  .map((tr) => tr.querySelector(".rowno").textContent).join(",");
const note = (dom) => dom.root.querySelector("#sa-note");

// --- ① 처음 ---------------------------------------------------------------
{
  const dom = build();
  run(dom);
  assert.strictEqual(ids(dom), "1,2,3", "서버가 그려 준 차례(최신순)가 아니다");
  assert.strictEqual(numbers(dom), "1,2,3", "줄 번호가 안 매겨졌다");
  assert.strictEqual(note(dom).hidden, true, "다 보이는데 `n / m 건` 이 떠 있다");
}

// --- ② 검색 · 필터 ----------------------------------------------------------
{
  const dom = build();
  run(dom);
  dom.search.value = "샘플메디";
  dom.search.fire("input");
  assert.strictEqual(shown(dom), "2", "검색이 안 걸렸다");
  assert.strictEqual(numbers(dom), ",1,", "보이는 줄만 번호가 매겨져야 한다");
  assert.strictEqual(note(dom).textContent, "1 / 3건 표시 중");
}
{
  // 주소에 걸어 둔 필터(`?type=…`)로 열면 그 조건으로 선다 — 옆 탭과 같은 계약.
  const dom = build();
  run(dom, "?type=" + encodeURIComponent("딜 소싱 네트워크"));
  assert.strictEqual(shown(dom), "1,3", "머리글 필터가 안 걸렸다");
  assert.strictEqual(numbers(dom), "1,,2");
  // 필터 위에 검색을 얹으면 AND 다.
  dom.search.value = "나루";
  dom.search.fire("input");
  assert.strictEqual(shown(dom), "3", "검색과 필터가 서로를 지웠다");
}

// --- ③ 수신 일자로 세우기 ----------------------------------------------------
{
  const dom = build();
  run(dom);
  const btn = dom.heads[2].querySelector("button");
  assert.ok(btn, "`수신 일자` 머리글이 단추로 서지 않았다");
  // 처음부터 이 칸 최신순이다(서버가 그렇게 그려 준다) — 머리글도 **그렇다고**
  // 말해야 한다. `↕`(안 세움)로 두면 첫 클릭이 오래된 순이 되는 것이 뜻밖이다.
  assert.strictEqual(dom.heads[2].getAttribute("aria-sort"), "descending",
    "처음 차례가 수신 일자 최신순인데 머리글이 안 세운 칸으로 보인다");
  assert.strictEqual(btn.getAttribute("data-mark"), "▼");
  btn.fire("click");
  // 오름차순 — 날짜 없는 줄은 방향과 상관없이 끝.
  assert.strictEqual(ids(dom), "2,1,3", "오래된 것부터가 아니다(빈 날짜는 끝)");
  assert.strictEqual(numbers(dom), "1,2,3", "세운 뒤 번호를 다시 매기지 않았다");
  assert.strictEqual(dom.heads[2].getAttribute("aria-sort"), "ascending");
  btn.fire("click");
  // 다시 누르면 처음 차례(최신순)로 — 같은 최신순을 두 번 거치지 않는다.
  assert.strictEqual(ids(dom), "1,2,3", "내림차순에서 빈 날짜가 끝이 아니다");
  assert.strictEqual(dom.heads[2].getAttribute("aria-sort"), "descending");
  btn.fire("click");
  assert.strictEqual(ids(dom), "2,1,3", "세 번째 클릭이 다시 오래된 순이 아니다");
}
{
  // 다른 칸으로 세웠다가 이 칸을 누르면 **처음 차례(최신순)** 로 돌아온다.
  const dom = build();
  const got = run(dom, "?sort=received_at");
  assert.strictEqual(ids(dom), "2,1,3", "주소에 남긴 오름차순으로 안 섰다");
  dom.heads[2].querySelector("button").fire("click");
  assert.strictEqual(ids(dom), "1,2,3");
  assert.strictEqual(got.win.location.search, "", "처음 차례인데 주소에 정렬이 남았다");
}

// --- ④ 저장 뒤처리 -----------------------------------------------------------
{
  const dom = build();
  run(dom);
  const row = dom.body.children[0];
  const cell = row.querySelector('[data-field="series"]');
  // inline_edit.js 는 고른 글자(전체)를 칸에 적어 둔 채 알린다.
  cell.textContent = "Series C (누적투자금 50억 이상)";
  dom.table.dispatchEvent(new (function (type, init) {
    this.type = type; this.detail = init.detail;
  })("inline-saved", { detail: { row: row, cell: cell, value: cell.textContent, data: {
    id: 1, name: "가온샘플", received_at: "2026-08-25", received_sort: "2026-08-25",
    series: "Series C (누적투자금 50억 이상)", series_short: "Series C", ir_name: ""
  } } }));
  assert.strictEqual(cell.textContent, "Series C", "칸이 짧은 꼴로 돌아오지 않았다");
  assert.strictEqual(cell.getAttribute("data-value"), "Series C (누적투자금 50억 이상)");
  assert.strictEqual(row.getAttribute("data-f-series"), "Series C",
    "필터 값이 짧은 꼴이 아니면 옆 줄의 `Series C` 와 두 벌로 갈린다");

  // 이름을 고쳐 IR 기업 현황의 기업과 맞으면 딱지가 선다.
  const name = row.querySelector('[data-field="name"]');
  dom.table.dispatchEvent(new (function (type, init) {
    this.type = type; this.detail = init.detail;
  })("inline-saved", { detail: { row: row, cell: name, value: "샘플애그", data: {
    id: 1, name: "샘플애그", received_at: "2026-08-25", received_sort: "2026-08-25",
    series: "", series_short: "", ir_name: "샘플애그"
  } } }));
  const link = row.querySelector(".ir-link");
  assert.strictEqual(link.hidden, false, "IR 기업 현황에도 있는 기업인데 딱지가 안 섰다");
  assert.strictEqual(link.getAttribute("href"), "/companies?q=" + encodeURIComponent("샘플애그"));
}

// --- ④-2 칸은 **서버가 저장한 값**으로 다시 그린다 ---------------------------
//
// 기업명을 비우고 저장하면 서버는 비우지 않고 옛 이름을 돌려준다
// (`routers/series_a._assign`). inline_edit.js 는 적힌 그대로(빈 칸)를 칸에 둔 채
// 알리므로, 응답으로 다시 그리지 않으면 **화면만 빈 이름**으로 남는다.
function saved(dom, row, cell, value, data) {
  dom.table.dispatchEvent(new (function (type, init) {
    this.type = type; this.detail = init.detail;
  })("inline-saved", { detail: { row: row, cell: cell, value: value, data: data } }));
}
{
  const dom = build();
  run(dom);
  const row = dom.body.children[0];
  const name = row.querySelector('[data-field="name"]');
  name.textContent = "";                         // inline_edit.js 가 적어 둔 빈 이름
  saved(dom, row, name, "", {
    id: 1, name: "가온샘플", received_at: "2026-08-25", received_sort: "2026-08-25",
    series: "Series B", series_short: "Series B", ir_name: "",
    search: "가온샘플 2026-08-25 딜 소싱 네트워크 series b"
  });
  assert.strictEqual(name.textContent, "가온샘플",
    "서버가 빈 이름을 받지 않았는데 화면에는 빈 칸이 남았다");

  // 다른 글자 칸도 서버가 다듬은 값으로 선다(앞뒤 공백 등).
  const type = row.querySelector('[data-field="deal_type"]');
  type.textContent = "  후속 투자 연계 ";
  saved(dom, row, type, "  후속 투자 연계 ", {
    id: 1, name: "가온샘플", deal_type: "후속 투자 연계", received_at: "2026-08-25",
    received_sort: "2026-08-25", series: "Series B", series_short: "Series B",
    ir_name: "", search: "가온샘플 2026-08-25 후속 투자 연계 series b"
  });
  assert.strictEqual(type.textContent, "후속 투자 연계");
  assert.strictEqual(row.getAttribute("data-f-type"), "후속 투자 연계",
    "필터 값이 서버가 저장한 값과 다르다");
}

// --- ④-3 고친 값이 **새로고침 없이** 검색에 걸린다 ----------------------------
{
  const dom = build();
  run(dom);
  const row = dom.body.children[1];
  const name = row.querySelector('[data-field="name"]');
  name.textContent = "샘플바이오";
  saved(dom, row, name, "샘플바이오", {
    id: 2, name: "샘플바이오", received_at: "2026-07-01", received_sort: "2026-07-01",
    series: "Series A (누적투자금 10억이상)", series_short: "Series A", ir_name: "",
    search: "샘플바이오 2026-07-01 후속 투자 연계 series a (누적투자금 10억이상)"
  });
  dom.search.value = "샘플바이오";
  dom.search.fire("input");
  assert.strictEqual(shown(dom), "2", "고친 이름이 검색에 안 걸린다(새로고침 전)");
  dom.search.value = "샘플메디";
  dom.search.fire("input");
  assert.strictEqual(shown(dom), "", "옛 이름이 아직 검색에 걸린다");
}

// --- ⑥ 기업명을 넣으면 IR 기업에 이어지고 빈칸이 채워진다(기업 동기화 3단계) ------
//
// 서버는 저장할 때 이름이 정확히 하나 맞는 IR 기업에 잇고 대표자 · 매출 · 금액 빈칸을
// 채운다(`services/company_sync.py`). 고친 칸만 다시 그리면 채워진 칸은 새로고침 전까지
// 비어 보인다 — 줄의 칸 전부와 `IR 기업:` 표시를 응답으로 다시 그린다.
{
  const dom = build();
  const row = dom.body.children[0];
  const ceo = D.el("td", { class: "cell", "data-field": "ceo_name" });
  const rev = D.el("td", { class: "cell num", "data-field": "revenue_2026" });
  row.appendChild(ceo);
  row.appendChild(rev);
  const box = D.el("div", { class: "ir-link-sub muted sa-ir-link",
                            "data-ir-link": JSON.stringify({ linked: false, candidates: 0 }) });
  row.querySelector(".co-name").appendChild(box);
  run(dom);
  assert.strictEqual(box.hidden, true, "안 이었고 이름이 같은 IR 기업도 없는데 표시가 섰다");

  const name = row.querySelector('[data-field="name"]');
  name.textContent = "샘플가람";
  saved(dom, row, name, "샘플가람", {
    id: 1, name: "샘플가람", received_at: "2026-08-25", received_sort: "2026-08-25",
    series: "Series B", series_short: "Series B", ir_name: "샘플가람",
    ceo_name: "김샘플", revenue_2026: "12",
    ir_link: { linked: true, auto: true, name: "샘플가람", company_id: 7,
               company_href: "/companies?q=" + encodeURIComponent("샘플가람"),
               link_href: "/ir-link?tab=series-a&row=1", candidates: 0 }
  });
  assert.strictEqual(ceo.textContent, "김샘플", "IR 에서 채운 대표자명이 새로고침 전에 안 보인다");
  assert.strictEqual(rev.textContent, "12", "IR 에서 채운 매출이 새로고침 전에 안 보인다");
  assert.strictEqual(box.hidden, false, "이어졌는데 `IR 기업:` 표시가 안 섰다");
  // 이 DOM 은 글자를 칸마다 따로 담는다(`_dom.js`) — 자식 글자를 이어 읽는다.
  const said = box.children.map((kid) => kid.textContent).join("");
  assert.strictEqual(said, "IR 기업: 샘플가람 (자동 연결 · 연결 풀기)", said);
  const links = box.querySelectorAll("a");
  assert.strictEqual(links[links.length - 1].textContent, "연결 풀기");
  assert.strictEqual(links[links.length - 1].getAttribute("href"), "/ir-link?tab=series-a&row=1");
  // 투자라운드는 짧은 꼴 그대로(전체 글로 덮지 않는다).
  assert.strictEqual(row.querySelector('[data-field="series"]').textContent, "Series B");
}

// --- ⑦ 계약여부 · 계약서 수신 여부(0125) — 칸 · 필터는 **말**, 저장은 열쇠 ------------
//
// 응답의 `contract_status` 는 열쇠(`paid`)다. 그대로 적으면 칸에 `paid` 가 보이고 필터가
// `유료계약완료` 와 두 벌로 갈린다 — `contract_label` 로 그린다(IR 표와 같다). 기업명을
// 넣어 IR 에서 채워진 계약 칸도 새로고침 없이 말로 서고, 거르는 값도 따라간다.
{
  const dom = build();
  const row = dom.body.children[0];
  const contract = D.el("td", { class: "cell", "data-field": "contract_status",
                                "data-type": "pick", "data-filter-key": "contract" });
  const received = D.el("td", { class: "cell", "data-field": "contract_received",
                                "data-type": "pick", "data-filter-key": "received" });
  contract.textContent = "미계약";
  row.setAttribute("data-f-contract", "미계약");
  row.setAttribute("data-f-received", "");
  row.appendChild(contract);
  row.appendChild(received);
  run(dom);

  contract.textContent = "유료계약완료";
  saved(dom, row, contract, "유료계약완료", {
    id: 1, name: "가온샘플", received_sort: "2026-08-25", series: "Series B",
    series_short: "Series B", ir_name: "",
    contract_status: "paid", contract_label: "유료계약완료", contract_received: ""
  });
  assert.strictEqual(contract.textContent, "유료계약완료", "칸에 열쇠가 보인다");
  assert.strictEqual(row.getAttribute("data-f-contract"), "유료계약완료");

  const name = row.querySelector('[data-field="name"]');
  saved(dom, row, name, "샘플가람", {
    id: 1, name: "샘플가람", received_sort: "2026-08-25", series: "Series B",
    series_short: "Series B", ir_name: "샘플가람",
    contract_status: "free", contract_label: "무료계약완료", contract_received: "O"
  });
  assert.strictEqual(contract.textContent, "무료계약완료", "IR 에서 채운 계약여부가 말로 안 섰다");
  assert.strictEqual(received.textContent, "O");
  assert.strictEqual(row.getAttribute("data-f-contract"), "무료계약완료",
    "다시 그린 칸의 필터 값이 옛 값에 남았다");
  assert.strictEqual(row.getAttribute("data-f-received"), "O");
}

// --- ⑤ 삭제 --------------------------------------------------------------
{
  const dom = build();
  const got = run(dom, "", false);
  dom.body.children[1].querySelector(".js-sa-delete").fire("click");
  assert.ok(/샘플메디/.test(got.asked[0] || ""), "무엇을 지우는지 이름으로 묻지 않는다");
  assert.strictEqual(got.calls.length, 0, "아니라고 했는데 지우는 요청이 나갔다");
}
{
  const dom = build();
  const got = run(dom, "", true);
  dom.body.children[1].querySelector(".js-sa-delete").fire("click");
  assert.deepStrictEqual(got.calls[0], { url: "/api/series-a-companies/2", method: "DELETE" });
}

console.log("series_a_test: 모두 통과");
