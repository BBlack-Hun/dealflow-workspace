// 칩 넷이 각각 어느 줄을 잡는가. (node tests/js/consulting_chips_test.js)
//
// `연락 기록 없음` 이 **월별 리마인드 칸만** 보고 있었다. 그래서 `기업 관리` 에
// `관리 중 : 미팅 완. -> 견적서 보내기 완료.` 라고 적어 둔 줄이, 리마인드가
// 비었다는 이유로 `관리 중` 과 `연락 기록 없음` 에 **동시에** 떴다. 화면에서는
// 칩이 나란히 붙어 한 갈래로 읽히는데 실제로는 두 갈래를 섞어 놓은 것이라,
// 관리 중인 기업이 "연락 기록 없음" 에 뜨는 것이 틀려 보인다.
//
// 이제 `연락 기록 없음` 은 **아무것도 안 적힌 줄**이다 — 두 칸을 같이 본다.
// 그리고 두 마디에 안 걸리는 나머지는 `그 외` 가 받는다(자유 서술이라 값의
// 종류가 무한하므로 값마다 칩을 세울 수는 없다. 값별로 고르는 일은 머리글
// `기업 관리 ▾` 가 이미 한다).
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 실제로
// 돌린다** — 작은 DOM 을 세우고 칩을 눌러 남는 줄을 센다
// (consulting_kpi_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 서버가 그리는 것과 같은 모양의 줄 ---------------------------------------
//
// 갈래 표시는 `data-f-mgmt` 하나다. 칩도 KPI 도 머리글 필터도 그것을 나눠 본다.
function row(id, opts) {
  const mgmtCell = D.el("td", {
    class: "cell multi", "data-field": "management", "data-filter-key": "mgmt"
  });
  mgmtCell.textContent = opts.management;
  const noteCell = D.el("td", { class: "cell multi", "data-note": "1" });
  noteCell.textContent = opts.note || "";

  return D.el("tr", {
    "data-id": String(id),
    "data-search": "",
    "data-f-region": "",
    "data-f-mgmt": opts.tags,
    "data-contacted": opts.note ? "1" : "0",
    "data-contacted-folded": "0",
    "data-contacted-prev": "0"
  }, [mgmtCell, noteCell]);
}

function chip(value, label) {
  const btn = D.el("button", { "data-cs-filter": value });
  btn.classList.add("chip");
  if (value === "") btn.classList.add("active");
  btn.textContent = label;
  return btn;
}

function kpi(key, value) {
  const span = D.el("span", { class: "kpi-value", "data-kpi": key });
  span.textContent = String(value);
  return span;
}

// 실제 시트에 있는 모양을 그대로 본뜬다(값은 가상).
const SHAPES = [
  // 1) 관리 중 · 리마인드 **전부 빔** — 예전에 `연락 기록 없음` 에도 떴던 줄.
  { management: "관리 중 : 미팅 완. -> 견적서 보내기 완료.", tags: "관리 중" },
  // 2) 관리 중 · 리마인드 있음
  { management: "관리 중", tags: "관리 중", note: "8월 통화" },
  // 3) 드랍 · 리마인드 전부 빔
  { management: "드랍 : 연락 두절", tags: "드랍" },
  // 4) 한 줄에 두 마디 — 적힌 그대로 드랍이다.
  { management: "백업팀으로 전환 · 논의 중임. 드랍", tags: "드랍|백업팀 전환" },
  // 5) 자유 서술 — 시트가 정한 어느 마디도 아니다. `그 외` 가 받는다.
  { management: "제안서 검토 후 진행 안 하기로 함", tags: "기타 메모" },
  // 6) 마디는 맞지만 칩이 따로 없는 값 — 이것도 `그 외` 다.
  { management: "백업팀으로 전환", tags: "백업팀 전환" },
  // 7) 둘 다 빔 — 이 줄만 `연락 기록 없음` 이다.
  { management: "", tags: "" },
  // 8) 기업 관리는 비었는데 리마인드는 있음 — 어느 칩도 아니다.
  //    (머리글 `기업 관리 ▾ → (비어 있음)` 이 받는다)
  { management: "", tags: "", note: "7월 통화" }
];

function build() {
  const rows = SHAPES.map(function (s, i) { return row(i + 1, s); });
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0" }, [
    D.el("tbody", {}, rows)
  ]);
  const chips = [chip("", "전체"), chip("managed", "관리 중"),
                 chip("dropped", "드랍"), chip("other", "그 외"),
                 chip("nocontact", "연락 기록 없음")];
  const kpis = [kpi("total", 0), kpi("managed", 0), kpi("dropped", 0)];

  const root = D.el("div", {}, kpis.concat(chips, [
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]));
  return { root: root, rows: rows, chips: chips, root_: root };
}

// --- consulting.js 를 그대로 돌린다 -----------------------------------------
function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const el = made.call(document, tag);
    el.focus = function () {};
    el.setSelectionRange = function () {};
    return el;
  };
  const sandbox = {
    document: document,
    window: { location: { reload: function () {} } },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    prompt: function () { return null; },
    fetch: function () {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  // 공통 컬럼 필터는 안 싣는다 — 칩만 떼어 본다.
  sandbox.window.DealflowFilters = undefined;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "consulting.js" });
}

// 칩을 누르고 남은 줄의 번호(1부터)를 센다.
function pick(dom, index) {
  const btn = dom.chips[index];
  btn.fire("click", { target: btn });
  return dom.rows
    .map(function (tr, i) { return tr.hidden ? null : i + 1; })
    .filter(function (v) { return v !== null; });
}

// 칸을 고친다 (누르기 → 값 넣기 → 칸 밖으로). 저장은 fetch 뒤에 이어지므로
// 마이크로태스크가 다 돌 때까지 기다린다 — consulting_contacted_test.js 와 같다.
//
// 입력칸은 **마지막** 자식에서 꺼낸다. 이 검사용 DOM 은 `textContent = ""` 이
// 자식을 지우지 않아서(글자를 한 칸에 담는 아주 작은 DOM 이다), 같은 칸을 두 번
// 고치면 첫 번째 입력칸이 그대로 남아 `children[0]` 이 **옛 것**을 준다.
// 그 옛 입력칸에 값을 넣으면 저장이 아예 안 나가 검사가 조용히 통과한다.
function edit(tr, value) {
  const cell = tr.querySelector('[data-field="management"]');
  cell.fire("click", { target: cell });
  const input = cell.children[cell.children.length - 1];
  assert.ok(input, "칸을 눌렀는데 입력칸이 안 생겼습니다");
  input.value = value;
  input.fire("blur", { target: input });
  return new Promise(function (r) { setTimeout(r, 0); });
}

(async function () {
  const dom = build();
  run(dom);

  assert.deepStrictEqual(pick(dom, 0), [1, 2, 3, 4, 5, 6, 7, 8], "전체");
  assert.deepStrictEqual(pick(dom, 1), [1, 2], "관리 중");
  assert.deepStrictEqual(pick(dom, 2), [3, 4], "드랍");

  // 자유 서술과 `백업팀 전환` 은 `그 외` 가 받는다. 관리 중·드랍과 겹치면
  // 같은 줄이 두 칩에 떠서 어느 갈래인지 알 수 없다.
  assert.deepStrictEqual(pick(dom, 3), [5, 6], "그 외");

  // **여기가 이 검사의 핵심이다.** 1번(관리 중인데 리마인드가 빈 줄)은
  // `연락 기록 없음` 에 뜨면 안 된다. 7번(둘 다 빈 줄)만 뜬다.
  assert.deepStrictEqual(
    pick(dom, 4), [7],
    "`기업 관리` 에 값이 있는 줄이 `연락 기록 없음` 에 떴습니다 — " +
    "그 칩은 아무것도 안 적힌 줄만 받아야 합니다");

  // --- 칸을 고치면 그 자리에서 따라오는가 -----------------------------------
  //
  // 7번 줄(둘 다 빔)의 `기업 관리` 에 값을 적으면 `연락 기록 없음` 에서 빠지고
  // `그 외` 로 넘어가야 한다. 서버가 다시 그려 주기 전에 브라우저가 하는 일이다.
  await edit(dom.rows[6], "확인 중 — 다음 주에 다시 연락");
  assert.deepStrictEqual(
    pick(dom, 4), [],
    "값을 적었는데도 `연락 기록 없음` 에 그대로 남아 있습니다");
  assert.deepStrictEqual(
    pick(dom, 3), [5, 6, 7],
    "값을 적었는데 `그 외` 로 안 넘어왔습니다");

  // 지웠으면 되돌아와야 한다 — 한쪽으로만 흐르면 고쳐 놓고 되돌릴 수가 없다.
  await edit(dom.rows[6], "");
  assert.deepStrictEqual(pick(dom, 4), [7], "지웠는데 `연락 기록 없음` 으로 안 돌아왔습니다");

  console.log("consulting_chips_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
