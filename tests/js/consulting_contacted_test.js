// 접어 둔 달의 기록이 칸을 고치는 순간 사라지는가. (node tests/js/consulting_contacted_test.js)
//
// `연락 기록 없음` 칩은 줄의 `data-contacted` 를 본다. 서버는 **모든 달**을 보고
// 그 값을 적는데, 칸을 고치면 consulting.js 가 그 값을 **다시** 적는다 — 그때
// JS 가 볼 수 있는 것은 화면에 서 있는 칸뿐이다. 최근 석 달만 펴 두는 표라,
// 접힌 달에만 기록이 있는 줄은 고치는 순간 `기록 없음` 으로 뒤집혔다
// (실데이터 34줄 중 12줄이 그 상태였다). 화면에는 그 기록이 안 보이니 고친
// 사람은 이유를 알 수가 없다.
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 실제로
// 돌린다** — 작은 DOM 을 세우고 칸을 눌러 고치는 데까지 흉내 낸다
// (contacts_open_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 표 한 줄. 펴 둔 달의 칸은 비어 있고, 기록은 접힌 달에 있다 -------------
function build(folded) {
  const cells = [
    D.el("td", { class: "cell", "data-field": "region" }),
    D.el("td", { class: "cell", "data-field": "management" }),
    // 펴 둔 달의 칸 — **비어 있다.** 접힌 달의 칸은 화면에 아예 없다.
    D.el("td", { class: "cell multi", "data-note": "11" })
  ];
  const tr = D.el("tr", {
    "data-id": "7", "data-search": "", "data-managed": "0", "data-dropped": "0",
    "data-contacted": folded ? "1" : "0",
    "data-contacted-folded": folded ? "1" : "0",
    "data-f-region": "", "data-f-mgmt": ""
  }, cells);

  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0" }, [
    D.el("tbody", {}, [tr])
  ]);
  const chip = D.el("button", { "data-cs-filter": "nocontact" });
  chip.classList.add("chip");

  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" }),
    chip
  ]);
  return { root: root, tr: tr, cell: cells[0], chip: chip };
}

// --- consulting.js 를 그대로 돌린다 -----------------------------------------
function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const made = document.createElement;
  // 실제 입력칸에만 있는 것들. 없으면 startEdit 이 그 줄에서 죽는다.
  document.createElement = function (tag) {
    const el = made.call(document, tag);
    el.focus = function () {};
    el.setSelectionRange = function () {};
    return el;
  };

  const calls = [];
  const sandbox = {
    document: document,
    window: { location: { reload: function () {} } },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    prompt: function () { return null; },
    fetch: function (url, opt) {
      calls.push({ url: url, opt: opt });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window.DealflowFilters = undefined;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "consulting.js" });
  return calls;
}

// --- 칸을 하나 고친다 (누르기 → 값 넣기 → 칸 밖으로) ------------------------
function edit(dom, value) {
  dom.cell.fire("click", { target: dom.cell });
  const input = dom.cell.children[0];
  assert.ok(input, "칸을 눌렀는데 입력칸이 안 생겼습니다");
  input.value = value;
  input.fire("blur", { target: input });
  // 저장은 fetch 뒤에 이어진다 — 마이크로태스크가 다 돌 때까지 기다린다.
  return new Promise(function (r) { setTimeout(r, 0); });
}

(async function () {
  // 1) 접힌 달에 기록이 있는 줄 — 고쳐도 `연락 기록 있음` 그대로여야 한다.
  {
    const dom = build(true);
    const calls = run(dom);
    await edit(dom, "서울");
    assert.strictEqual(calls.length, 1, "저장 요청이 안 나갔습니다");
    assert.strictEqual(
      dom.tr.getAttribute("data-contacted"), "1",
      "접힌 달의 기록이 칸을 고치는 순간 사라졌습니다 — " +
      "그 줄이 `연락 기록 없음` 목록에 잘못 뜹니다");
  }

  // 2) 어디에도 기록이 없는 줄 — 고쳐도 `기록 없음` 그대로여야 한다.
  //    (1번을 통과시키려고 무조건 1 로 적어 두는 것을 막는다)
  {
    const dom = build(false);
    run(dom);
    await edit(dom, "부산");
    assert.strictEqual(
      dom.tr.getAttribute("data-contacted"), "0",
      "기록이 없는 줄까지 `연락 기록 있음` 으로 적혔습니다");
  }

  // 3) 펴 둔 달에 적어 넣으면 그때는 `기록 있음` 이 된다.
  {
    const dom = build(false);
    run(dom);
    const note = dom.tr.querySelector("[data-note]");
    note.fire("click", { target: note });
    const input = note.children[0];
    input.value = "8월 통화 완료";
    input.fire("blur", { target: input });
    await new Promise(function (r) { setTimeout(r, 0); });
    assert.strictEqual(dom.tr.getAttribute("data-contacted"), "1");
  }

  console.log("consulting_contacted_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
