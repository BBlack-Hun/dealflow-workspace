// 줄이 제 저장 주소(`data-inline-url`)를 들고 있으면 그쪽으로 저장하는가(#147).
// (node tests/js/inline_edit_row_url_test.js)
//
// 업무 보고의 `소개한 기업` 표는 IR 줄과 Series A 줄이 한 표에 섞인다. 계약여부를
// 골라 고치면 **값을 읽어 온 그 줄**에 저장해야 한다 — IR 줄은 `/api/companies`,
// Series A 줄은 `/api/series-a-companies`.
//
//   ① 줄에 주소가 있으면 그 주소 + 줄 번호로 간다.
//   ② 줄에 주소가 없으면 예전처럼 표의 주소로 간다(다른 화면은 그대로).
//   ③ 번호가 없는 줄(이름으로 짝을 못 찾은 기업)은 칸이 아니라 아무 데도 안 간다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "inline_edit.js"), "utf8");

const CHOICES = ["미계약", "무료계약완료", "유료계약완료", "계약검토중"];
const flush = () => new Promise((r) => setTimeout(r, 0));

function pick(text) {
  const td = D.el("td", { class: "cell", "data-field": "contract_status",
                          "data-type": "pick", "data-choices": CHOICES.join(", ") });
  td.textContent = text;
  return td;
}

function build() {
  const sa = pick("무료계약완료");
  const ir = pick("미계약");
  const plain = D.el("td", {});
  plain.textContent = "";
  const rows = [
    D.el("tr", { "data-id": "5", "data-inline-url": "/api/series-a-companies" },
         [D.el("td", {}), sa]),
    D.el("tr", { "data-id": "7" }, [D.el("td", {}), ir]),
    D.el("tr", {}, [D.el("td", {}), plain])
  ];
  const table = D.el("table", { "data-inline-url": "/api/companies" },
                     [D.el("tbody", {}, rows)]);
  return { root: D.el("div", {}, [table]), sa: sa, ir: ir, plain: plain };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = { innerWidth: 1400, innerHeight: 900,
                addEventListener: function () {}, removeEventListener: function () {} };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {},
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, method: opts.method, body: JSON.parse(opts.body || "{}") });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "inline_edit.js" });
  return sent;
}

function choose(dom, cell, value) {
  cell.fire("pointerdown");
  cell.fire("click");
  const pop = dom.root.querySelector(".cell-pop");
  assert.ok(pop, "계약여부 칸을 눌렀는데 고르기 창이 안 떴다");
  const chip = Array.prototype.find.call(pop.querySelectorAll(".cell-pop-choice"),
    function (b) { return b.textContent === value; });
  assert.ok(chip, "보기에 " + value + " 가 없다");
  chip.fire("mousedown");
}

async function main() {
  const dom = build();
  const sent = run(dom);

  // ① 줄의 주소
  choose(dom, dom.sa, "유료계약완료");
  await flush();
  assert.deepStrictEqual(sent[0], {
    url: "/api/series-a-companies/5", method: "PATCH",
    body: { contract_status: "유료계약완료" }
  }, "Series A 줄이 줄의 주소로 안 갔다: " + JSON.stringify(sent[0]));
  assert.strictEqual(dom.sa.textContent, "유료계약완료");

  // ② 주소 없는 줄은 표의 주소 그대로
  choose(dom, dom.ir, "계약검토중");
  await flush();
  assert.deepStrictEqual(sent[1], {
    url: "/api/companies/7", method: "PATCH",
    body: { contract_status: "계약검토중" }
  }, "줄 주소가 없는 줄이 표의 주소로 안 갔다: " + JSON.stringify(sent[1]));

  // ③ 번호 없는 줄은 고칠 칸이 아니다
  dom.plain.fire("pointerdown");
  dom.plain.fire("click");
  await flush();
  assert.strictEqual(dom.root.querySelector(".cell-pop"), null, "글자 칸에 고르기 창이 떴다");
  assert.strictEqual(sent.length, 2, "짝 없는 줄에서 저장이 나갔다");

  console.log("ok — inline_edit_row_url");
}

main().catch(function (err) { console.error(err); process.exit(1); });
