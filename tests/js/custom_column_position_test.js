// 관리자가 자리를 고른 **추가 칸**이 그 기존 칸 뒤로 옮겨 서는가(0110).
// (node tests/js/custom_column_position_test.js)
//
//   ① 앵커(머리글 이름) 뒤로 머리글과 줄마다의 칸이 같이 옮겨 간다.
//   ② 같은 앵커 뒤에 여럿이면 서버가 그린 차례(`position`) 그대로다.
//   ③ 앵커가 없는 칸 · 앵커가 없는 표(탭)에서는 맨 끝 그대로다.
//   ④ 옮긴 칸에서 필터 · 정렬 · 칸 고치기가 **그 칸**을 가리킨다 — 화면처럼
//      `custom_cols.js` 를 먼저, 그다음 `inline_edit.js` · `filters.js` ·
//      `table_sort.js` 를 그대로 돌린다(`base.html` · `companies.html` 차례).
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(JS, name), "utf8");

const flush = () => new Promise((r) => setTimeout(r, 0));

// 머리글 이름은 **글자 노드**다 — filters.js 가 그 노드를 지우고 단추를 세운다.
function text(s) {
  const node = D.makeEl("#text");
  node.nodeType = 3;
  node.textContent = s;
  return node;
}

function th(k, label, attrs, kids) {
  // `textContent` 는 안 채운다 — 이 DOM 에서는 자식과 따로 노는 칸이라, 채우면
  // 글자 노드를 지운 뒤에도 이름이 남아 브라우저와 다른 것을 보증한다.
  return D.el("th", Object.assign({ "data-k": k }, attrs || {}),
              [text(label)].concat(kids || []));
}

// 화면(`companies.html` + `_custom_cols.html`)이 그리는 꼴. 추가 칸 넷은 서버가
// `position` 차례로 오른쪽 끝([수정] 앞)에 그린 그대로다:
//   A(5, O/X) 기업명 뒤 · B(6) 없는 칸 뒤 · C(7) 대분류 뒤 · D(8) 기업명 뒤
const ROWS = [
  { id: "1", name: "가샘플", sector: "AI", ox: "O" },
  { id: "2", name: "나샘플", sector: "바이오", ox: "X" },
  { id: "3", name: "다샘플", sector: "AI", ox: "O" }
];

function build() {
  const head = D.el("tr", {}, [
    th("no", "NO", { class: "num stick stick-a" }),
    th("name", "기업명", { class: "stick stick-b", "data-sort": "name" }),
    th("sector", "대분류", { "data-filters": "sector:대분류" },
       [D.el("div", { class: "th-filters" })]),
    th("ir", "IR 자료"),
    th("A", "시험OX", { class: "custom-col", "data-after": "기업명",
                       "data-filters": "cc5:시험OX" }, [D.el("div", { class: "th-filters" })]),
    th("B", "시험메모", { class: "custom-col", "data-after": "없는 칸" }),
    th("C", "시험둘", { class: "custom-col", "data-after": "  대분류 " }),
    th("D", "시험셋", { class: "custom-col", "data-after": "기업명" }),
    th("edit", "")
  ]);
  const rows = ROWS.map(function (r) {
    function td(k, kids, attrs) {
      return D.el("td", Object.assign({ "data-k": k, "data-row": r.id }, attrs || {}), kids || []);
    }
    const name = D.el("b", { class: "cell", "data-field": "name" });
    name.textContent = r.name;
    const ox = D.el("div", { class: "cell", "data-field": "cc5", "data-custom": "5",
                             "data-custom-rows": "ir_companies" });
    ox.textContent = r.ox;
    return D.el("tr", { "data-id": r.id, "data-s-name": r.name, "data-f-sector": r.sector,
                        "data-f-cc5": r.ox },
      [td("no"), td("name", [name]), td("sector"), td("ir"), td("A", [ox]),
       td("B"), td("C"), td("D"), td("edit")]);
  });
  // 줄이 없을 때 서는 안내 줄 — 칸 수가 머리글과 달라 건드리면 안 된다.
  const note = D.el("tr", {}, [D.el("td", { colspan: "9", "data-k": "note" })]);
  const table = D.el("table", { id: "t", "data-inline-url": "/api/companies" },
    [D.el("thead", {}, [head]), D.el("tbody", {}, rows.concat([note]))]);

  // 옆 탭 — `기업명` 이 없는 표. 같은 칸(A)이 여기서는 맨 끝 그대로여야 한다.
  const otherHead = D.el("tr", {}, [
    th("no", "NO"), th("type", "Type"),
    th("A", "시험OX", { class: "custom-col", "data-after": "기업명" }), th("edit", "")
  ]);
  const otherRow = D.el("tr", { "data-id": "9" },
    ["no", "type", "A", "edit"].map(function (k) { return D.el("td", { "data-k": k }); }));
  const other = D.el("table", { id: "other" },
    [D.el("thead", {}, [otherHead]), D.el("tbody", {}, [otherRow])]);

  return { root: D.el("div", {}, [table, other]), table: table, head: head, rows: rows,
           note: note, otherHead: otherHead, otherRow: otherRow };
}

const keys = (tr) => tr.children.map((c) => c.getAttribute("data-k")).join(",");

(async function main() {
  const dom = build();
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const sent = [];
  const win = {
    innerWidth: 1400, innerHeight: 900,
    addEventListener: function () {}, removeEventListener: function () {},
    location: { pathname: "/companies", search: "?cc5=O&sort=-name" },
    history: { replaceState: function () {} }
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {}, confirm: function () { return true; },
    prompt: function () { return null; },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, method: opts.method, body: JSON.parse(opts.body || "{}") });
      return Promise.resolve({ ok: true, json: function () {
        return Promise.resolve({ value: "O", updated_at: "2026-10-18 10:00" });
      } });
    }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  // 화면의 차례 그대로 — `base.html` 의 custom_cols.js 가 페이지 스크립트보다 먼저다.
  ["custom_cols.js", "inline_edit.js", "filters.js", "table_sort.js"].forEach(function (name) {
    vm.runInContext(read(name), sandbox, { filename: name });
  });

  // ① · ② · ③ 자리
  const want = "no,name,A,D,sector,C,ir,B,edit";
  assert.strictEqual(keys(dom.head), want, "머리글이 고른 자리에 안 섰다: " + keys(dom.head));
  dom.rows.forEach(function (tr) {
    assert.strictEqual(keys(tr), want, "줄의 칸이 머리글과 다른 차례다: " + keys(tr));
  });
  assert.strictEqual(keys(dom.note), "note", "안내 줄(colspan)을 건드렸다");
  assert.strictEqual(keys(dom.otherHead), "no,type,A,edit", "앵커가 없는 탭에서 칸이 움직였다");
  assert.strictEqual(keys(dom.otherRow), "no,type,A,edit", "앵커가 없는 탭에서 줄의 칸이 움직였다");

  // ④-1 필터 — 옮긴 머리글에 단추가 서고, 그 칸 값으로 거른다.
  sandbox.window.DealflowFilters.init({ table: "#t" });
  const moved = dom.head.children[2];
  assert.strictEqual(moved.getAttribute("data-k"), "A");
  assert.ok(moved.querySelector(".th-filters button"), "옮긴 O/X 칸에 필터 단추가 없다");
  assert.strictEqual(dom.head.children[4].getAttribute("data-k"), "sector");
  assert.ok(dom.head.children[4].querySelector(".th-filters button"), "대분류 필터 단추가 없다");
  const shown = dom.rows.filter((tr) => !tr.hidden).map((tr) => tr.getAttribute("data-id"));
  assert.deepStrictEqual(shown.sort(), ["1", "3"], "O/X 필터가 그 칸 값으로 안 걸렀다");

  // ④-2 정렬 — 줄째 옮겨지므로 칸은 제 줄과 함께 다닌다.
  sandbox.window.DealflowSort.init({ table: "#t" });
  const body = dom.table.querySelector("tbody");
  const order = body.children.filter((tr) => tr.getAttribute("data-id"))
    .map((tr) => tr.getAttribute("data-id"));
  assert.deepStrictEqual(order, ["3", "2", "1"], "이름 내림차순으로 안 섰다: " + order);
  body.children.filter((tr) => tr.getAttribute("data-id")).forEach(function (tr) {
    assert.strictEqual(keys(tr), want, "정렬 뒤에 칸 차례가 흐트러졌다");
    assert.ok(tr.children.every((c) => c.getAttribute("data-row") === tr.getAttribute("data-id")),
      "정렬 뒤에 다른 줄의 칸이 섞였다");
  });

  // ④-3 칸 고치기 — 옮긴 자리(셋째 칸)를 누르면 그 추가 칸(5번)으로 간다.
  const row = dom.rows[0];
  const cell = row.children[2].querySelector(".cell");
  cell.fire("click");
  const input = cell.querySelector(".cell-input");
  assert.ok(input, "옮긴 칸을 눌렀는데 입력칸이 안 열렸다");
  input.value = "o";
  input.blur();
  await flush();
  await flush();
  assert.deepStrictEqual(sent[0], {
    url: "/api/custom-values/ir_companies/1", method: "PUT",
    body: { column_id: 5, value: "o" }
  }, "옮긴 칸이 다른 칸으로 저장됐다: " + JSON.stringify(sent[0]));
  assert.strictEqual(cell.textContent, "O");
  assert.strictEqual(row.getAttribute("data-f-cc5"), "O", "필터 값이 저장값과 다르다");

  console.log("custom_column_position_test: ok");
})().catch(function (err) { console.error(err); process.exit(1); });
