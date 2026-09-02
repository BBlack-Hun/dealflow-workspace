// 남의 담당 줄은 **눌러도 편집이 안 시작된다.** (node tests/js/consulting_readonly_test.js)
//
// 이 화면은 컨설턴트 한 사람의 개인 표이면서, 그 표들을 모아 팀이 보는 자리다.
// 팀원은 전체를 보되 자기 줄만 고친다 — 그래서 화면에 **고칠 수 없는 줄**이 섞인다.
//
// 서버는 이미 404 로 막는다(`routers/consulting.py` 의 `owned`). 그런데 브라우저가
// 안 막으면 칸이 입력칸으로 바뀌고 글자까지 쳐진 뒤에 **저장만 실패한다** — 쓴 것이
// 그대로 사라지고, 왜 안 되는지는 알림창 한 줄뿐이다.
//
// 어느 줄이 그런지는 서버가 `data-readonly` 로 실어 준다. 판정을 브라우저가 다시
// 하면(역할을 보고 정하는 식) 규칙이 두 벌이 되어 한쪽이 낡는다.
//
// 규칙을 옮겨 적으면 두 벌이 되므로 **파일을 실제로 돌린다**
// (consulting_chips_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

// 서버가 그리는 것과 같은 모양의 줄. `readonly` 면 `data-readonly` 가 붙는다.
function row(id, opts) {
  const mgmt = D.el("td", {
    class: "cell multi", "data-field": "management", "data-filter-key": "mgmt"
  });
  mgmt.textContent = opts.management || "";
  const note = D.el("td", { class: "cell multi", "data-note": "1" });
  note.textContent = "";

  const attrs = {
    "data-id": String(id),
    "data-search": "",
    "data-f-region": "",
    "data-f-mgmt": opts.tags || "",
    "data-contacted": "0",
    "data-contacted-folded": "0",
    "data-contacted-prev": "0"
  };
  if (opts.readonly) attrs["data-readonly"] = "1";
  return D.el("tr", attrs, [mgmt, note]);
}

function build() {
  const rows = [
    row(1, { management: "관리 중", tags: "관리 중" }),                  // 내 줄
    row(2, { management: "관리 중", tags: "관리 중", readonly: true })   // 남의 줄
  ];
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0" }, [
    D.el("tbody", {}, rows)
  ]);
  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]);
  return { root: root, rows: rows };
}

// consulting.js 를 그대로 돌린다. 저장이 나갔는지 보려고 fetch 를 세어 둔다.
function run(dom) {
  D.resetHandlers();
  const sent = [];
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
    window: { location: { reload: function () {} }, DealflowFilters: undefined },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    prompt: function () { return null; },
    fetch: function (url, opts) {
      sent.push({ url: url, body: opts && opts.body });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "consulting.js" });
  return sent;
}

// 칸을 눌러 본다. 편집이 시작됐으면 입력칸이 생긴다.
function click(tr) {
  const cell = tr.querySelector('[data-field="management"]');
  const before = cell.children.length;
  cell.fire("click", { target: cell });
  return { cell: cell, opened: cell.children.length > before };
}

(async function () {
  const dom = build();
  const sent = run(dom);

  // --- 내 줄은 지금까지 그대로 -------------------------------------------
  const mine = click(dom.rows[0]);
  assert.ok(mine.opened,
    "내 줄인데 칸을 눌러도 편집이 안 시작됩니다 — 막는 김에 자기 것까지 막았습니다");
  const input = mine.cell.children[mine.cell.children.length - 1];
  input.value = "관리 중 · 재통화";
  input.fire("blur", { target: input });
  await new Promise(function (r) { setTimeout(r, 0); });
  assert.strictEqual(sent.length, 1, "내 줄을 고쳤는데 저장이 안 나갔습니다");
  assert.ok(sent[0].url.indexOf("/api/consulting/1") === 0, sent[0].url);

  // --- 남의 줄은 눌러도 아무 일이 없다 -------------------------------------
  const theirs = click(dom.rows[1]);
  assert.ok(!theirs.opened,
    "남의 담당 줄인데 편집창이 열립니다 — 글자를 친 뒤에야 저장이 안 되는 것을 " +
    "알게 되고, 쓴 것은 그대로 사라집니다");
  // 칸의 글자도 그대로여야 한다. 편집이 시작되면 `textContent` 가 먼저 비워진다.
  assert.strictEqual(theirs.cell.textContent, "관리 중",
    "편집이 안 시작됐는데 칸의 글자가 지워졌습니다");
  await new Promise(function (r) { setTimeout(r, 0); });
  assert.strictEqual(sent.length, 1, "남의 줄에서 저장 요청이 나갔습니다");

  console.log("consulting_readonly_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
