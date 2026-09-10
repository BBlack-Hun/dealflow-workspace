// IR 요청 투자사에서 이름을 쳐서 줄이 걸러지는가. (node tests/js/closed_search_test.js)
//
// 검색 규칙을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **실제로
// 나가는 코드 두 개를 그대로 돌린다** —
//
//   app/static/js/filters.js                          공용 필터 모듈
//   app/templates/_closed_followups.html 안의 <script>  이 화면이 그것을 거는 자리
//
// 화면 쪽 스크립트를 파일에서 뽑아 오므로, 나중에 그 자리를 고치면 여기가 같이
// 움직인다(따로 베껴 두면 화면만 죽어 있는 상태가 된다).
//
// 특히 보는 것:
//  · **`placeholder` 에 적은 것으로 정말 찾아지는가.** 적어 놓고 안 찾아지면
//    거짓말이고, 안 적힌 것으로 걸리면 "왜 이게 걸렸지" 가 된다.
//  · 검색과 다른 조건이 서로 `tr.hidden` 을 덮어쓰지 않는가(이 저장소가 겪었다).
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
  path.join(ROOT, "app", "templates", "_closed_followups.html"), "utf8");

// 화면이 필터를 거는 자리 — `src` 없는 `<script>` 가 그것이다.
const inline = PANEL.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(inline, "IR 요청 투자사 화면에서 필터를 거는 <script> 를 못 찾았다");
const HOOK = inline[1];
assert.ok(/closed-search/.test(HOOK) && /DealflowFilters/.test(HOOK),
  "그 <script> 가 검색칸을 공용 필터에 걸고 있지 않다");

// ── `placeholder` 와 줄이 싣는 것이 같은가 ─────────────────────────────────
//
// 화면에 적힌 다섯(`이름 · 투자사 · 단계 · 상태 · 사유`)이 곧 `data-search` 에
// 실리는 다섯(`name` · `firm` · `stage_label` · `status_label` · `reason`)이다.
// 한쪽만 늘리면 곧바로 거짓말이 되므로 파일에서 둘 다 읽어 견준다.
{
  const ph = PANEL.match(/placeholder="([^"]*)"/);
  assert.ok(ph, "검색칸에 placeholder 가 없다 — 무엇으로 찾는지 알 길이 없다");
  const words = ph[1].split("·").map(function (s) { return s.trim(); });
  assert.deepStrictEqual(words, ["이름", "투자사", "단계", "상태", "사유"],
    "placeholder 에 적힌 것이 바뀌었다 — data-search 도 같이 바뀌었는지 보라");

  const ds = PANEL.match(/data-search="\{\{([^"]*)\}\}"/);
  assert.ok(ds, "줄이 data-search 를 안 싣는다");
  const carried = ds[1];
  ["r.name", "r.firm", "r.stage_label", "r.status_label", "r.reason"]
    .forEach(function (f) {
      assert.ok(carried.indexOf(f) >= 0,
        "`" + f + "` 이 data-search 에 안 실렸다 — placeholder 가 거짓말이 된다");
    });
  assert.ok(/\|lower/.test(carried),
    "data-search 를 소문자로 안 내린다 — 대문자로 치면 안 걸린다");
}

// 가상의 담당자다 — 저장소가 공개라 실제 이름·회사를 두지 않는다.
// 단계·상태 글자는 **실제로 쓰는 것**을 그대로 둔다(`cadence.STAGE_LABELS` ·
// `STATUS_LABELS`) — 여기만 지어낸 말을 쓰면 검사는 통과하는데 화면에서는
// 안 걸리는 일이 생긴다.
const ROWS = [
  { name: "가담당", firm: "가나벤처스", stage: "리마인드",
    status: "답 옴", reason: "IR 자료를 요청했습니다" },
  { name: "나담당", firm: "DaRa Invest", stage: "미팅 요청",
    status: "중단", reason: "사람이 중단" },
  { name: "다담당", firm: "가나벤처스", stage: "미팅 요청",
    status: "완료", reason: "미팅이 잡혔습니다" }
];

function buildDom() {
  dom_.resetHandlers();
  const root = makeEl("html");

  const trs = ROWS.map(function (r) {
    return el("tr", {
      class: "data-row",
      // 화면(`_closed_followups.html`)이 싣는 것과 같은 다섯 — 소문자로 내려서.
      "data-search": [r.name, r.firm, r.stage, r.status, r.reason]
        .join(" ").toLowerCase()
    });
  });
  const table = el("table", { id: "closed-table", class: "grid-table compact" },
    [el("thead", {}, []), el("tbody", {}, trs)]);

  root.appendChild(table);
  root.appendChild(el("input", { id: "closed-search", type: "search" }));
  root.appendChild(el("span", { id: "closed-count", class: "hint" }));
  const empty = el("p", { id: "closed-empty", class: "muted" });
  empty.hidden = true;
  root.appendChild(empty);

  return { root: root, document: dom_.makeDocument(root), trs: trs };
}

function run() {
  const dom = buildDom();
  const win = { location: { search: "", pathname: "/ir", hash: "#remind" },
                history: {} };
  const ctx = { document: dom.document, console: console,
                setTimeout: function (fn) { return fn && fn(); } };
  ctx.window = win;
  win.document = dom.document;
  vm.runInNewContext(FILTERS, ctx, { filename: "filters.js" });
  assert.ok(ctx.window.DealflowFilters, "공용 필터 모듈이 안 실렸다");
  vm.runInNewContext(HOOK, ctx, { filename: "_closed_followups.html <script>" });
  return dom;
}

function shown(dom) {
  return dom.trs.filter(function (tr) { return !tr.hidden; })
    .map(function (tr) { return tr.getAttribute("data-search").split(" ")[0]; });
}
function type(dom, text) {
  const box = dom.document.getElementById("closed-search");
  box.value = text;
  box.fire("input");
}

// ── 아무 것도 안 쳤으면 전부 보인다 ─────────────────────────────────────────
{
  const dom = run();
  assert.deepStrictEqual(shown(dom), ["가담당", "나담당", "다담당"]);
  assert.strictEqual(dom.document.getElementById("closed-count").textContent,
    "3 / 3건", "몇 건이 남았는지 안 적혀 있다");
}

// ── 이름으로 걸러진다 ───────────────────────────────────────────────────────
{
  const dom = run();
  type(dom, "나담당");
  assert.deepStrictEqual(shown(dom), ["나담당"], "이름을 쳤는데 안 걸러진다");
  assert.strictEqual(dom.document.getElementById("closed-empty").hidden, true);
  assert.strictEqual(dom.document.getElementById("closed-count").textContent,
    "1 / 3건");
}

// ── 투자사로도 걸러진다 ─────────────────────────────────────────────────────
// 사람 이름이 잘 안 떠오를 때 "그 가나벤처스 분" 으로 찾는다.
// 사용자가 원한 것이 바로 이것이다 — 투자사 이름으로 찾기.
{
  const dom = run();
  type(dom, "가나벤처스");
  assert.deepStrictEqual(shown(dom), ["가담당", "다담당"]);
}

// ── 영문 투자사는 대소문자를 안 가린다 ──────────────────────────────────────
// 줄은 소문자로 실려 있고(`|lower`) 친 글자도 소문자로 내려 견준다.
// 한쪽만 내리면 `DaRa` 로 쳤을 때 안 걸린다.
{
  for (const q of ["DaRa Invest", "dara invest", "DARA", "Invest"]) {
    const dom = run();
    type(dom, q);
    assert.deepStrictEqual(shown(dom), ["나담당"],
      "`" + q + "` 로 쳤는데 안 걸린다 — 대소문자를 가리고 있다");
  }
}

// ── 앞뒤 공백은 무시한다 ────────────────────────────────────────────────────
// 다른 화면에서 이름을 복사해 붙이면 공백이 딸려 온다.
{
  const dom = run();
  type(dom, "  가나벤처스  ");
  assert.deepStrictEqual(shown(dom), ["가담당", "다담당"]);
}

// ── 마지막 단계·상태·사유로도 걸러진다 ─────────────────────────────────────
// `placeholder` 에 적어 두었으므로 셋 다 실제로 걸려야 한다.
{
  const dom = run();
  type(dom, "미팅 요청");
  assert.deepStrictEqual(shown(dom), ["나담당", "다담당"], "마지막 단계로 안 걸린다");
}
{
  const dom = run();
  type(dom, "중단");
  assert.deepStrictEqual(shown(dom), ["나담당"], "상태로 안 걸린다");
}
{
  // 이 표를 여는 까닭 그 자체 — 자료를 요청한 투자사만 추린다.
  const dom = run();
  type(dom, "ir 자료를 요청");
  assert.deepStrictEqual(shown(dom), ["가담당"], "사유로 안 걸린다");
}

// ── 아무 것도 안 걸리면 그렇다고 말한다 ─────────────────────────────────────
// 빈 표만 남으면 그 투자사가 딜 진행 관리에 아예 없는 줄 안다 —
// 실제로는 옆 묶음(오늘 보낼 리마인드 · 예약된 리마인드)에 있을 수 있다.
{
  const dom = run();
  type(dom, "없는이름");
  assert.deepStrictEqual(shown(dom), []);
  assert.strictEqual(dom.document.getElementById("closed-empty").hidden, false,
    "다 걸러졌는데 안내가 안 뜬다 — 투자사가 사라진 줄 안다");
  assert.strictEqual(dom.document.getElementById("closed-count").textContent,
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
  assert.strictEqual(dom.document.getElementById("closed-empty").hidden, true);
}

console.log("closed_search_test: 통과");
