// IR 기업 현황에서 가져오는 칸(`td.ir-ro`)을 누르면 **왜 못 고치는지** 뜬다.
// (node tests/js/consulting_ir_readonly_test.js)
//
// 11/12 신고 — IR 기업과 아직 안 이은 새 줄에서 `기업 한줄 소개`·`대분류` 같은 IR 칸을
// 눌러도 아무 일이 없어 "기업 줄에 내용을 써 넣을 수 없다" 로 읽혔다. 줄이 읽기
// 전용일 때(`consulting_readonly_test.js`)와 같은 말풍선을 띄우고, 글자는 서버가 표에
// 실어 준 것(`data-ir-why`)을 그대로 옮긴다. 편집은 안 열리고 저장도 안 나간다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");
const WHY = "IR 기업 현황에서 가져오는 칸이라 여기서는 고칠 수 없습니다 — 샘플 안내.";

function build() {
  const name = D.el("td", { class: "cell", "data-field": "company_name" });
  name.textContent = "샘플기업";
  const inner = D.el("div", { class: "ellipsis" });
  const ir = D.el("td", { class: "ir-ro", "data-ir": "business_desc", title: "" }, [inner]);
  const tr = D.el("tr", {
    "data-id": "1", "data-search": "", "data-f-mgmt": "",
    "data-contacted": "0", "data-contacted-folded": "0", "data-contacted-prev": "0"
  }, [name, ir]);
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0", "data-ir-why": WHY },
                     [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]);
  return { root: root, name: name, ir: ir, inner: inner };
}

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
  const ctx = vm.createContext({
    document: document,
    window: { location: { reload: function () {} }, DealflowFilters: undefined },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    fetch: function (url) {
      sent.push(url);
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  });
  vm.runInContext(src, ctx, { filename: "consulting.js" });
  return sent;
}

(async function () {
  const dom = build();
  const sent = run(dom);

  // 칸 안의 글자 상자를 눌러도(실제 클릭은 대개 그 자리다) IR 칸으로 읽는다.
  dom.ir.fire("click", { target: dom.inner });
  const pop = dom.root.querySelector(".readonly-pop");
  assert.ok(pop, "IR 칸을 눌렀는데 아무 말이 없습니다 — 고장으로 읽힙니다");
  assert.strictEqual(pop.hidden, false, "말풍선을 만들고 감춰 두었습니다");
  assert.strictEqual(pop.textContent, WHY, "서버가 실어 준 이유가 아닌 말이 떴습니다: " + pop.textContent);
  assert.strictEqual(dom.ir.querySelector(".cell-input"), null, "IR 칸에 입력칸이 열렸습니다");
  await new Promise(function (r) { setTimeout(r, 0); });
  assert.strictEqual(sent.length, 0, "IR 칸을 눌렀는데 저장 요청이 나갔습니다");

  // 고칠 수 있는 칸을 누르면 말풍선은 걷히고 편집이 열린다.
  dom.name.fire("click", { target: dom.name });
  assert.ok(dom.name.querySelector(".cell-input"), "IR 칸을 누른 뒤로 내 칸 편집이 안 열립니다");
  assert.strictEqual(pop.hidden, true, "편집을 여는데 IR 칸 말풍선이 그대로 떠 있습니다");

  console.log("consulting_ir_readonly_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
