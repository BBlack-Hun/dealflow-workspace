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
  if (opts.readonly) {
    attrs["data-readonly"] = "1";
    // 왜 안 열리는지 — 서버가 그 줄에 실어 준다(consulting.html).
    attrs["data-readonly-why"] = "다른사람 담당 줄은 볼 수만 있습니다 — 고칠 일이 있으면 담당자나 관리자에게 요청하세요.";
  }
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
  // 여러 줄 칸은 입력칸 밑에 안내 줄(`.cell-pop-hint`)이 선다 — 입력칸만 골라 꺼낸다.
  const input = mine.cell.children.filter(function (c) { return c.tag === "textarea"; })[0];
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

  // --- 그런데 **말없이** 막지는 않는다 -------------------------------------
  // 눌러도 아무 일이 없으면 고장으로 읽힌다(#13 — 월 칸을 새로 세운 뒤 남의
  // 줄을 눌러 본 사람이 "내용 기입이 안 된다" 고 했다). 누른 자리에 왜 안
  // 열리는지 뜬다. 글자는 서버가 줄에 실어 준 그대로다.
  const pop = dom.root.querySelector(".readonly-pop");
  assert.ok(pop, "남의 줄을 눌렀는데 왜 안 열리는지 아무 말이 없습니다");
  assert.strictEqual(pop.hidden, false, "말풍선을 만들고 감춰 두었습니다");
  assert.ok(pop.textContent.indexOf("다른사람 담당 줄은 볼 수만 있습니다") === 0,
    "서버가 실어 준 이유가 아닌 말이 떴습니다: " + pop.textContent);
  assert.ok(/px$/.test(pop.style.top) && !/NaN/.test(pop.style.left),
    "말풍선 자리를 못 잡았습니다: " + pop.style.top + " / " + pop.style.left);

  // 내 줄을 누르면 말풍선은 걷히고 편집이 열린다.
  const again = click(dom.rows[0]);
  assert.ok(again.opened, "말풍선이 뜬 뒤로 내 줄 편집이 안 열립니다");
  assert.strictEqual(pop.hidden, true, "내 줄을 고치는데 남의 줄 말풍선이 그대로 떠 있습니다");

  // 두 번 눌러도 말풍선은 **한 장**이다 — 누를 때마다 쌓이면 화면에 남는다.
  click(dom.rows[1]);
  click(dom.rows[1]);
  assert.strictEqual(dom.root.querySelectorAll(".readonly-pop").length, 1,
    "남의 줄을 누를 때마다 말풍선이 쌓입니다");

  // --- 여러 줄 칸은 쓰는 만큼 자란다 ----------------------------------------
  // 여섯 줄에 묶여 있으면 딜 소개문구 같은 문단이 칸 안에서만 굴러 어디를
  // 고치는지 안 보인다(참고 표 칸과 같은 처리).
  {
    const dom2 = build();
    run(dom2);
    const opened = click(dom2.rows[0]);
    const area = opened.cell.querySelector(".cell-input");
    assert.ok(area, "내 줄의 여러 줄 칸이 안 열립니다");
    area.scrollHeight = 600;
    area.fire("input");
    assert.strictEqual(area.style.height, "602px",
      "글이 늘었는데 입력칸이 안 자랍니다: " + area.style.height);
  }

  // --- 한글을 조합하는 중의 Enter 는 저장으로 읽지 않는다 ---------------------
  {
    const dom3 = build();
    const sent3 = run(dom3);
    const opened = click(dom3.rows[0]);
    const area = opened.cell.querySelector(".cell-input");
    area.value = "관리 중 · 통화";
    area.fire("keydown", { key: "Enter", ctrlKey: true, isComposing: true });
    await new Promise(function (r) { setTimeout(r, 0); });
    assert.strictEqual(sent3.length, 0, "조합 중인 Enter 로 저장이 나갔습니다");
  }

  console.log("consulting_readonly_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
