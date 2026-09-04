// 예약된 리마인드에서 이름을 쳐서 줄이 걸러지는가. (node tests/js/upcoming_search_test.js)
//
// 검색 규칙을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **실제로
// 나가는 코드 두 개를 그대로 돌린다** —
//
//   app/static/js/filters.js                     공용 필터 모듈
//   app/templates/_upcoming_followups.html 안의 <script>   이 화면이 그것을 거는 자리
//
// 화면 쪽 스크립트를 파일에서 뽑아 오므로, 나중에 그 자리를 고치면 여기가 같이
// 움직인다(따로 베껴 두면 화면만 죽어 있는 상태가 된다).
//
// 특히 보는 것: **검색과 다른 조건이 서로를 지우지 않는가.** 이 저장소는
// 검색과 필터가 번갈아 `tr.hidden` 을 덮어써 서로를 지운 적이 있다.
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
const PANEL = fs.readFileSync(
  path.join(ROOT, "app", "templates", "_upcoming_followups.html"), "utf8");

// 화면이 필터를 거는 자리 — `src` 없는 `<script>` 가 그것이다.
const inline = PANEL.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(inline, "예약된 리마인드 화면에서 필터를 거는 <script> 를 못 찾았다");
const HOOK = inline[1];
assert.ok(/upcoming-search/.test(HOOK) && /DealflowFilters/.test(HOOK),
  "그 <script> 가 검색칸을 공용 필터에 걸고 있지 않다");

// 가상의 담당자다 — 저장소가 공개라 실제 이름·회사를 두지 않는다.
const ROWS = [
  { name: "가담당", firm: "가나벤처스", next: "리마인드" },
  { name: "나담당", firm: "다라인베스트", next: "미팅 요청" },
  { name: "다담당", firm: "가나벤처스", next: "미팅 요청" }
];

function buildDom() {
  dom_.resetHandlers();
  const root = makeEl("html");

  const trs = ROWS.map(function (r) {
    return el("tr", {
      class: "data-row",
      "data-search": (r.name + " " + r.firm + " " + r.next).toLowerCase()
    });
  });
  const table = el("table", { id: "upcoming-table", class: "grid-table compact" },
    [el("thead", {}, []), el("tbody", {}, trs)]);

  root.appendChild(table);
  root.appendChild(el("input", { id: "upcoming-search", type: "search" }));
  root.appendChild(el("span", { id: "upcoming-count", class: "hint" }));
  const empty = el("p", { id: "upcoming-empty", class: "muted" });
  empty.hidden = true;
  root.appendChild(empty);

  return { root: root, document: dom_.makeDocument(root), trs: trs };
}

function run() {
  const dom = buildDom();
  const win = { location: { search: "", pathname: "/ir" }, history: {} };
  const ctx = { document: dom.document, console: console,
                setTimeout: function (fn) { return fn && fn(); } };
  ctx.window = win;
  win.document = dom.document;
  vm.runInNewContext(FILTERS, ctx, { filename: "filters.js" });
  assert.ok(ctx.window.DealflowFilters, "공용 필터 모듈이 안 실렸다");
  vm.runInNewContext(HOOK, ctx, { filename: "_upcoming_followups.html <script>" });
  return dom;
}

function shown(dom) {
  return dom.trs.filter(function (tr) { return !tr.hidden; })
    .map(function (tr) { return tr.getAttribute("data-search").split(" ")[0]; });
}
function type(dom, text) {
  const box = dom.document.getElementById("upcoming-search");
  box.value = text;
  box.fire("input");
}

// ── 아무 것도 안 쳤으면 전부 보인다 ─────────────────────────────────────────
{
  const dom = run();
  assert.deepStrictEqual(shown(dom), ["가담당", "나담당", "다담당"]);
  assert.strictEqual(dom.document.getElementById("upcoming-count").textContent,
    "3 / 3건", "몇 건이 남았는지 안 적혀 있다");
}

// ── 이름으로 걸러진다 ───────────────────────────────────────────────────────
{
  const dom = run();
  type(dom, "나담당");
  assert.deepStrictEqual(shown(dom), ["나담당"], "이름을 쳤는데 안 걸러진다");
  assert.strictEqual(dom.document.getElementById("upcoming-empty").hidden, true);
}

// ── 회사로도 걸러진다 ───────────────────────────────────────────────────────
// 사람 이름이 잘 안 떠오를 때 "그 가나벤처스 분" 으로 찾는다.
{
  const dom = run();
  type(dom, "가나벤처스");
  assert.deepStrictEqual(shown(dom), ["가담당", "다담당"]);
}

// ── 다음 단계로도 걸러진다 ──────────────────────────────────────────────────
{
  const dom = run();
  type(dom, "미팅 요청");
  assert.deepStrictEqual(shown(dom), ["나담당", "다담당"]);
}

// ── 아무 것도 안 걸리면 그렇다고 말한다 ─────────────────────────────────────
// 빈 표만 남으면 리마인드가 없어진 줄 안다.
{
  const dom = run();
  type(dom, "없는이름");
  assert.deepStrictEqual(shown(dom), []);
  assert.strictEqual(dom.document.getElementById("upcoming-empty").hidden, false,
    "다 걸러졌는데 안내가 안 뜬다 — 리마인드가 사라진 줄 안다");
  assert.strictEqual(dom.document.getElementById("upcoming-count").textContent,
    "0 / 3건");
}

// ── 지웠다 다시 치면 돌아온다 ───────────────────────────────────────────────
// 검색이 `tr.hidden` 을 자기 마음대로 만지면, 한 번 감춘 줄이 안 돌아온다.
{
  const dom = run();
  type(dom, "나담당");
  type(dom, "");
  assert.deepStrictEqual(shown(dom), ["가담당", "나담당", "다담당"],
    "검색어를 지웠는데 줄이 안 돌아온다");
}

console.log("upcoming_search_test: 통과");
