// 투자사 관리 현황 — `Series A 딜 소싱` 칸은 **서버가 읽은 값**으로 다시 그린다.
// (node tests/js/contacts_sourcing_join_test.js)
//
// 이 칸은 줄에 저장된 글자가 아니라 딜 소싱의 이어진 줄에서 읽은 값이다
// (`services/sourcing_sync.py`). 그래서 사람이 `o` 를 적어도 서버는 `O` 를
// 돌려주는데, 화면이 적힌 글자를 그대로 두면 칸과 필터가 서버와 다른 말을 한다.
// 다른 칸을 고친 응답에도 이 값이 실려 오면 그대로 맞춘다.
//
// 바로 옆 `참여 요청일`(읽기만 — #28)도 같은 응답(`sourcing_requested_at`)으로
// 다시 그린다. O 로 새 줄이 생기거나 이어지면 그 줄의 날짜가 선다.
//
// 이름은 지어낸 값이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(JS, name), "utf8");

// 화면(`app/templates/contacts.html`)이 그리는 만큼만 세운다.
function build() {
  const sourcing = D.el("td", { class: "cell", "data-field": "sourcing_join",
                                "data-type": "pick", "data-choices": "O,X",
                                "data-filter-key": "sourcing" });
  const requested = D.el("td", { class: "sourcing-requested", title: "" });
  const memo = D.el("div", { class: "cell clamp2", "data-field": "memo" });
  const row = D.el("tr", {
    class: "data-row", "data-id": "7", "data-name": "홍길동", "data-f-sourcing": "",
    "data-f-sourcing_date": ""
  }, [D.el("td", { class: "rowno" }), sourcing, requested, D.el("td", {}, [memo])]);
  const table = D.el("table", { id: "contacts-table" },
                     [D.el("thead"), D.el("tbody", {}, [row])]);
  const root = D.el("div", {}, [D.el("div", {}, [table])]);
  return { root: root, table: table, row: row, sourcing: sourcing, memo: memo,
           requested: requested };
}

function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const seenByFilter = [];
  const win = { location: { pathname: "/contacts", search: "" },
                history: { replaceState: function () {} } };
  const sandbox = {
    document: document, console: console,
    MutationObserver: function () { this.observe = function () {}; },
    alert: function () {}, confirm: function () { return false; },
    setTimeout: setTimeout,
    fetch: function () { return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } }); }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  win.DealflowFilters = {
    init: function () {
      return {
        apply: function () {},
        refresh: function () { seenByFilter.push(dom.row.getAttribute("data-f-sourcing")); }
      };
    }
  };
  vm.createContext(sandbox);
  ["panel_modal.js", "contacts.js"].forEach(function (name) {
    vm.runInContext(read(name), sandbox, { filename: name });
  });
  return { seenByFilter: seenByFilter };
}

function saved(dom, cell, value, data) {
  dom.table.dispatchEvent({ type: "inline-saved",
    detail: { row: dom.row, cell: cell, value: value, data: data } });
}

// --- 1) `o` 를 적었다 → 칸 · 필터 값은 서버가 읽은 `O` -----------------------
{
  const dom = build();
  const at = run(dom);
  dom.sourcing.textContent = "o";                // inline_edit.js 가 적은 그대로
  dom.row.setAttribute("data-f-sourcing", "o");
  saved(dom, dom.sourcing, "o", {
    ok: true, sourcing_join: "O",
    sourcing_msg: "딜 소싱 › 시리즈 A 이상 딜 소싱 참여 심사역 에 새로 넣었습니다."
  });
  assert.strictEqual(dom.sourcing.textContent, "O", "칸에 적힌 글자가 서버 값과 다르다");
  assert.strictEqual(dom.row.getAttribute("data-f-sourcing"), "O",
    "칸은 O 인데 필터는 o 로 거른다");
  assert.ok(/새로 넣었습니다/.test(dom.sourcing.getAttribute("title") || ""),
    "딜 소싱에서 일어난 일이 칸 어디에도 안 남는다");
  assert.deepStrictEqual(at.seenByFilter, ["O"],
    "필터가 옛 값으로 목록을 만든 뒤에 행 값이 바뀌었다 — 손을 거는 차례가 거꾸로다");
}

// --- 2) 다른 칸을 고친 응답에 실려 온 값도 맞춘다 -------------------------------
{
  const dom = build();
  run(dom);
  dom.sourcing.textContent = "O";
  saved(dom, dom.memo, "통화함", { ok: true, sourcing_join: "X" });
  assert.strictEqual(dom.sourcing.textContent, "X");
  assert.strictEqual(dom.row.getAttribute("data-f-sourcing"), "X");
}

// --- 3) 그 값이 없는 응답은 아무것도 안 건드린다 --------------------------------
{
  const dom = build();
  run(dom);
  dom.sourcing.textContent = "O";
  dom.row.setAttribute("data-f-sourcing", "O");
  saved(dom, dom.memo, "x", { ok: true });
  assert.strictEqual(dom.sourcing.textContent, "O");
  assert.strictEqual(dom.row.getAttribute("data-f-sourcing"), "O");
}

// --- 4) `참여 요청일` — 응답의 값으로 칸 · 풍선말 · 거를 값 ----------------
{
  const dom = build();
  run(dom);
  saved(dom, dom.sourcing, "O", { ok: true, sourcing_join: "O",
                                  sourcing_requested_at: "2026-10-16" });
  assert.strictEqual(dom.requested.textContent, "2026-10-16");
  assert.strictEqual(dom.requested.getAttribute("title"), "2026-10-16");
  assert.strictEqual(dom.row.getAttribute("data-f-sourcing_date"), "2026-10-16");

  // 그 값이 없는 응답은 날짜를 안 건드린다
  saved(dom, dom.memo, "x", { ok: true });
  assert.strictEqual(dom.requested.textContent, "2026-10-16");
}

console.log("contacts_sourcing_join_test: ok");
