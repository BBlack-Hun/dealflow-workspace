// 투자컨설턴트의 IR 칸(`td.ir-ro`) — 이은 줄은 **눌러 고쳐 IR 기업 현황에 저장**하고,
// 안 여는 칸은 **왜 못 고치는지** 띄운다. (node tests/js/consulting_ir_readonly_test.js)
//
// 11/12 신고 — IR 기업과 아직 안 이은 새 줄에서 `기업 한줄 소개`·`대분류` 같은 IR 칸을
// 눌러도 아무 일이 없어 "기업 줄에 내용을 써 넣을 수 없다" 로 읽혔다. 같은 날 사용자:
// 이은 줄에서는 여기서 고쳐도 IR 기업 현황까지 바뀌어야 한다(`routers/consulting.update_ir`).
//
//   이은 · 고칠 수 있는 줄   `td.ir-ro.cell` — 열리고, 저장은 `/api/consulting/{id}/ir`
//   안 이은 줄              표의 `data-ir-why`
//   이은 줄의 안 여는 칸     그 칸의 `data-why`(IR 자료)
//   남의 줄                 그 줄의 `data-readonly-why`
//
// 글자는 전부 서버가 실어 준 것이다 — 여기서는 어느 것을 띄우는지만 본다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");
const WHY = "IR 기업과 이어지지 않은 줄이라 이 칸은 비어 있고 고칠 수 없습니다 — 샘플 안내.";
const FIXED = "IR 자료(파일 이름)는 여기서 고치지 않습니다 — 샘플 안내.";
const ROW_WHY = "다른사람 담당 줄은 볼 수만 있습니다 — 샘플 안내.";

function irCell(key, value, opts) {
  opts = opts || {};
  const attrs = { class: "ir-ro" + (opts.edit ? " cell" + (opts.multi ? " multi" : "") : ""),
                  "data-ir": key, title: value };
  if (opts.why) attrs["data-why"] = opts.why;
  const inner = D.el("div", { class: opts.edit ? "cell-main" : "ellipsis" });
  inner.textContent = value;
  return D.el("td", attrs, [inner]);
}

function row(id, cells, extra) {
  const name = D.el("td", { class: "cell", "data-field": "company_name" });
  name.textContent = "샘플기업" + id;
  return D.el("tr", Object.assign({
    "data-id": String(id), "data-search": "샘플기업" + id, "data-f-mgmt": "",
    "data-contacted": "0", "data-contacted-folded": "0", "data-contacted-prev": "0"
  }, extra || {}), [name].concat(cells));
}

function build() {
  const linked = {
    desc: irCell("business_desc", "스마트팜 설비", { edit: true, multi: true }),
    pitch: irCell("one_liner", "옛 소개 문구", { edit: true, multi: true }),
    file: irCell("ir_file_name", "있음", { why: FIXED })
  };
  const loose = { desc: irCell("business_desc", "") };
  const theirs = { desc: irCell("business_desc", "남의 소개") };
  const rows = [
    row(1, [linked.desc, linked.pitch, linked.file]),
    row(2, [loose.desc]),
    row(3, [theirs.desc], { "data-readonly": "1", "data-readonly-why": ROW_WHY })
  ];
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0", "data-ir-why": WHY },
                     [D.el("tbody", {}, rows)]);
  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]);
  return { root: root, rows: rows, linked: linked, loose: loose, theirs: theirs };
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
    fetch: function (url, opts) {
      sent.push({ url: url, method: opts && opts.method, body: opts && JSON.parse(opts.body) });
      // 서버는 그 IR 기업의 화면 글자 전부를 돌려준다 — `딜 소개 문구` 가 따라 바뀐 것까지.
      const data = { id: 1, ir: { business_desc: "수직 농장 설비", one_liner: "새 소개 문구",
                                  ir_file_name: "있음" } };
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve(data); } });
    }
  });
  vm.runInContext(src, ctx, { filename: "consulting.js" });
  return sent;
}

function pop(dom) { return dom.root.querySelector(".readonly-pop"); }

(async function () {
  const dom = build();
  const sent = run(dom);

  // --- 이은 줄 — 열리고, IR 길로 저장되고, 그 줄의 IR 칸이 서버 글자로 다시 적힌다 ----
  const desc = dom.linked.desc;
  desc.fire("click", { target: desc.querySelector(".cell-main") });
  const area = desc.querySelector(".cell-input");
  assert.ok(area, "이은 줄의 IR 칸이 안 열립니다 — 여기서 고쳐야 IR 기업 현황까지 바뀝니다");
  assert.strictEqual(pop(dom), null, "열리는 칸인데 못 고친다는 말풍선이 떴습니다");
  area.value = "수직 농장 설비";
  area.fire("blur", { target: area });
  await new Promise(function (r) { setTimeout(r, 0); });
  assert.strictEqual(sent.length, 1, "IR 칸을 고쳤는데 저장이 안 나갔습니다");
  assert.strictEqual(sent[0].url, "/api/consulting/1/ir", "IR 칸이 이 표의 칸 길로 갔습니다: " + sent[0].url);
  assert.strictEqual(sent[0].method, "PATCH");
  assert.deepStrictEqual(sent[0].body, { business_desc: "수직 농장 설비" });
  await new Promise(function (r) { setTimeout(r, 0); });
  const pitch = dom.linked.pitch;
  assert.strictEqual(pitch.querySelector("div").textContent, "새 소개 문구",
    "따라 바뀐 `딜 소개 문구` 가 새로고침 전까지 옛 글자로 남습니다");
  assert.strictEqual(pitch.getAttribute("title"), "새 소개 문구");
  // IR 글자는 이 표의 검색 재료가 아니다(서버도 안 넣는다) — 고친 뒤에도 그대로다.
  assert.strictEqual(dom.rows[0].getAttribute("data-search").indexOf("수직"), -1,
    "IR 칸을 고쳤더니 검색 글자에 IR 값이 섞였습니다");

  // --- 이은 줄의 안 여는 칸(IR 자료) — 그 칸의 까닭 ---------------------------
  dom.linked.file.fire("click", { target: dom.linked.file.querySelector("div") });
  assert.ok(pop(dom) && pop(dom).hidden === false, "IR 자료 칸을 눌렀는데 아무 말이 없습니다");
  assert.strictEqual(pop(dom).textContent, FIXED);
  assert.strictEqual(dom.linked.file.querySelector(".cell-input"), null);

  // --- 안 이은 줄 — 표의 안내 --------------------------------------------
  dom.loose.desc.fire("click", { target: dom.loose.desc.querySelector("div") });
  assert.strictEqual(pop(dom).textContent, WHY, "안 이은 줄인데 다른 말이 떴습니다: " + pop(dom).textContent);
  assert.strictEqual(dom.loose.desc.querySelector(".cell-input"), null, "안 이은 줄의 IR 칸이 열렸습니다");

  // --- 남의 줄 — 그 줄의 까닭(IR 안내가 아니다) -----------------------------
  dom.theirs.desc.fire("click", { target: dom.theirs.desc.querySelector("div") });
  assert.strictEqual(pop(dom).textContent, ROW_WHY, "남의 줄인데 IR 안내가 떴습니다");

  await new Promise(function (r) { setTimeout(r, 0); });
  assert.strictEqual(sent.length, 1, "안 여는 칸을 눌렀는데 저장 요청이 나갔습니다");
  console.log("consulting_ir_readonly_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
