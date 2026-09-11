// 스타트업 명단의 머리글 필터가 **실제로 줄을 거르는가.**
// (node tests/js/startup_filters_test.js)
//
// 여태 이 자리는 검사가 없었다. `tests/js/filters_test.js` 는 순수 함수
// (`matchRow`·`facets`)만 보고, DOM 연결부(`init`)는 "브라우저에서 확인한다" 고
// 적어 둔 채였다 — 그래서 **단추를 눌러 값을 고르는 한 바퀴**는 아무도 안 봤다.
// 여기서는 실제로 나가는 `app/static/js/filters.js` 를 그대로 돌리고, 스타트업
// 표와 같은 모양의 DOM 위에서 눌러 본다.
//
// 보는 것:
//   1. 거르면 **맞는 줄만** 남는다 (그리고 남은 수가 화면에 적힌다)
//   2. 필터 둘을 같이 걸면 **둘 다 맞는 줄만** 남는다 (컬럼 간 AND)
//   3. 한 칸에서 둘을 고르면 둘 중 하나만 맞아도 남는다 (컬럼 안 OR)
//   4. 풀면 **전부 돌아온다**
//   5. 값이 빈 줄은 `(비어 있음)` 으로 고를 수 있다 — 안 적은 줄을 찾는 일이
//      이 명단에서는 잦다(그 달에 아직 아무것도 안 한 기업)
//   6. 주소에 실린 조건도 그대로 걸리고, 아무 줄도 안 남으면 그렇게 적는다
//
// 이름·기업명은 전부 지어낸 값이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const { makeEl, el } = dom_;

const ROOT = path.join(__dirname, "..", "..");
const FILTERS = fs.readFileSync(
  path.join(ROOT, "app", "static", "js", "filters.js"), "utf8");

// 스타트업 표의 모양 그대로: 고를 수 있는 칸에만 필터가 서고, 자유롭게 적는
// 칸(기업명·메모)에는 안 선다. 월별 칸은 `O`/`X` 라 잘 듣는다.
const ROWS = [
  { firm: "샘플기업1", contract: "미계약", month: "O" },
  { firm: "샘플기업2", contract: "유료계약완료", month: "X" },
  { firm: "샘플기업3", contract: "미계약", month: "X" },
  { firm: "샘플기업4", contract: "", month: "O" }
];

function buildDom() {
  dom_.resetHandlers();
  const root = makeEl("html");

  function th(label, filters) {
    const cell = el("th", filters ? { "data-filters": filters } : {});
    cell.textContent = label;
    if (filters) cell.appendChild(el("div", { class: "th-filters" }));
    return cell;
  }

  const head = el("tr", {}, [
    th("NO", null),
    th("기업명", null),
    th("계약여부", "contract:계약여부"),
    th("9월 리마인드 문자", "c1:9월 리마인드 문자"),
    th("메모", null)
  ]);

  const trs = ROWS.map(function (r) {
    return el("tr", {
      class: "data-row",
      "data-f-contract": r.contract,
      "data-f-c1": r.month,
      "data-firm": r.firm
    });
  });

  const table = el("table", { id: "contacts-table", class: "grid-table" },
    [el("thead", {}, [head]), el("tbody", {}, trs)]);

  root.appendChild(table);
  root.appendChild(el("div", { class: "chip-row", "data-filter-chips": "" }));
  const count = el("b", { "data-filter-count": "" });
  root.appendChild(count);
  const empty = el("div", { class: "placeholder-card", "data-filter-empty": "" });
  empty.hidden = true;
  root.appendChild(empty);

  const document_ = dom_.makeDocument(root);
  // `clampIntoView` 가 화면 너비를 묻는다. 그림이 없는 DOM 이라 넉넉히 준다 —
  // 여기서 볼 것은 창의 좌표가 아니라 **무엇이 걸러지는가**다.
  document_.documentElement = { clientWidth: 1200 };
  return { root: root, document: document_, trs: trs, head: head,
           count: count, empty: empty };
}

function run(search) {
  const dom = buildDom();
  const win = { location: { search: search || "", pathname: "/startup", hash: "" },
                history: { replaceState: function () {} } };
  const ctx = {
    document: dom.document,
    console: console,
    setTimeout: function (fn) { return fn && fn(); },
    // `clampIntoView` 가 부모의 `overflow-x` 와 창의 `left` 를 읽는다.
    getComputedStyle: function () { return { overflowX: "visible", left: "0px" }; }
  };
  ctx.window = win;
  win.document = dom.document;
  vm.runInNewContext(FILTERS, ctx, { filename: "filters.js" });
  assert.ok(ctx.window.DealflowFilters, "공용 필터 모듈이 안 실렸다");
  // 화면(`contacts.js`)이 거는 것과 같은 한 줄.
  dom.api = ctx.window.DealflowFilters.init({ table: "#contacts-table" });
  assert.ok(dom.api, "필터가 안 걸렸다");
  return dom;
}

// ── 눌러 보는 손 ───────────────────────────────────────────────────────────

function thFor(dom, key) {
  return dom.head.children.filter(function (cell) {
    const spec = cell.getAttribute("data-filters") || "";
    return spec.split("|").some(function (p) { return p.split(":")[0] === key; });
  })[0];
}

/** 그 칸의 필터 단추를 눌러 창을 연다. */
function open(dom, key) {
  const cell = thFor(dom, key);
  assert.ok(cell, "`" + key + "` 필터를 세운 머리글이 없다");
  const buttons = cell.querySelectorAll(".filter-btn");
  assert.ok(buttons.length, "머리글에 필터 단추가 안 섰다");
  buttons[0].fire("click");
  const panel = cell.querySelectorAll(".filter-panel")[0];
  assert.ok(panel, "필터 창이 안 열렸다");
  return panel;
}

/** 이 DOM 에서 값 글자는 글자 노드에 담긴다(`createTextNode`). */
function optionText(label) {
  return label.children
    .filter(function (n) { return n.nodeType === 3; })
    .map(function (n) { return n.textContent; })
    .join("")
    .trim();
}

/** 창에서 그 값을 켜거나 끈다. */
function pick(panel, value, on) {
  const hit = panel.querySelectorAll("label.filter-option").filter(function (lb) {
    return optionText(lb).indexOf(value) === 0;
  })[0];
  assert.ok(hit, "`" + value + "` 을 고를 수가 없다 — 목록에 없다");
  const box = hit.querySelectorAll("input")[0];
  box.checked = on === undefined ? true : on;
  box.fire("change");
}

function shown(dom) {
  return dom.trs.filter(function (tr) { return !tr.hidden; })
    .map(function (tr) { return tr.getAttribute("data-firm"); });
}

// ── 1. 아무것도 안 골랐으면 전부 보인다 ─────────────────────────────────────
{
  const dom = run();
  assert.deepStrictEqual(shown(dom),
    ["샘플기업1", "샘플기업2", "샘플기업3", "샘플기업4"]);
  assert.strictEqual(dom.count.textContent, "4 / 4명",
    "거른 뒤 몇 줄 남았는지가 화면에 안 적혀 있다");
  assert.strictEqual(dom.empty.hidden, true);
}

// ── 2. 거르면 맞는 줄만 남는다 ──────────────────────────────────────────────
{
  const dom = run();
  pick(open(dom, "contract"), "미계약");
  assert.deepStrictEqual(shown(dom), ["샘플기업1", "샘플기업3"],
    "계약여부로 걸렀는데 맞지 않는 줄이 남아 있다");
  assert.strictEqual(dom.count.textContent, "2 / 4명");
}

// ── 3. 필터 둘을 같이 걸면 둘 다 맞는 줄만 ─────────────────────────────────
// 컬럼 간 AND. 하나만 맞는 줄이 남으면 "미계약이면서 O" 를 물었는데 답이
// "미계약이거나 O" 가 된다.
{
  const dom = run();
  pick(open(dom, "contract"), "미계약");
  pick(open(dom, "c1"), "O");
  assert.deepStrictEqual(shown(dom), ["샘플기업1"],
    "두 필터를 걸었는데 한쪽만 맞는 줄이 남았다");
  assert.strictEqual(dom.count.textContent, "1 / 4명");
}

// ── 4. 풀면 전부 돌아온다 ───────────────────────────────────────────────────
// 칩의 [필터 초기화] 가 그 자리다 — 창을 다시 열어 하나씩 끄지 않아도 되게.
{
  const dom = run();
  pick(open(dom, "contract"), "미계약");
  pick(open(dom, "c1"), "O");

  const chips = dom.document.querySelector("[data-filter-chips]");
  const reset = chips.querySelectorAll(".reset")[0];
  assert.ok(reset, "고른 것을 한 번에 푸는 자리가 없다");
  reset.fire("click");

  assert.deepStrictEqual(shown(dom),
    ["샘플기업1", "샘플기업2", "샘플기업3", "샘플기업4"],
    "필터를 풀었는데 줄이 다 안 돌아왔다");
  assert.strictEqual(dom.count.textContent, "4 / 4명");
}

// ── 5. 한 칸에서 둘을 고르면 OR ─────────────────────────────────────────────
{
  // 창은 값을 고른 뒤에도 열려 있다 — 둘째 값은 같은 창에서 고른다.
  const dom = run();
  const panel = open(dom, "contract");
  pick(panel, "미계약");
  pick(panel, "유료계약완료");
  assert.deepStrictEqual(shown(dom), ["샘플기업1", "샘플기업2", "샘플기업3"]);
}

// ── 6. 안 적은 줄도 고를 수 있다 ────────────────────────────────────────────
// 그 달에 아직 아무것도 안 한 기업을 찾는 일이 이 명단에서는 잦다.
{
  const dom = run();
  pick(open(dom, "contract"), "(비어 있음)");
  assert.deepStrictEqual(shown(dom), ["샘플기업4"]);
  assert.strictEqual(dom.empty.hidden, true);
}

// ── 7. 주소에 실린 조건도 그대로 걸린다 ────────────────────────────────────
// 고른 것은 주소에 남아 새로고침·공유해도 유지된다. **아무 줄도 안 남는 조합**
// 이 여기로 들어올 수 있다 — 창에서 고를 때는 남는 값만 목록에 서지만
// (`facets`), 주소로 들어오는 값은 그 걸름을 안 지난다. 그때 빈 표만 남으면
// "고장인가" 가 되므로, 조건에 맞는 줄이 없다고 적어야 한다.
{
  const dom = run("?contract=%EC%9C%A0%EB%A3%8C%EA%B3%84%EC%95%BD%EC%99%84%EB%A3%8C&c1=O");
  assert.deepStrictEqual(shown(dom), []);
  assert.strictEqual(dom.empty.hidden, false,
    "조건에 맞는 줄이 없다는 말이 안 뜬다");
  assert.strictEqual(dom.count.textContent, "0 / 4명");
}

// ── 8. 창에 서는 값은 **고르면 남는 값**뿐이다 ─────────────────────────────
// 다른 필터를 이미 건 상태에서, 골라 봐야 0줄이 되는 값이 목록에 서면
// 누르고 나서야 헛걸음인 줄 안다.
{
  const dom = run();
  pick(open(dom, "contract"), "유료계약완료");     // 샘플기업2 만 남는다(월별 X)
  const panel = open(dom, "c1");
  const values = panel.querySelectorAll("label.filter-option")
    .map(optionText).map(function (t) { return t.split(" (")[0]; });
  assert.deepStrictEqual(values, ["X"],
    "고르면 0줄이 되는 값이 목록에 서 있다");
}

console.log("startup_filters_test: 통과");
