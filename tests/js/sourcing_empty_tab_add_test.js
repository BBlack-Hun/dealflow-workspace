// 딜 소싱 [+ 탭 추가]로 막 만든 **빈 탭**에서 [○○에 추가] 단추가 사는가.
// (node tests/js/sourcing_empty_tab_add_test.js)
//
// 사용자: "아직도 딜 소싱에서 탭을 추가 했을때 탭 추가가 안됨"
//
// 만든 탭은 사람이 없어 표(`#sourcing-table`)가 안 선다 — 빈 탭 안내가 "위 [○○에
// 추가]로 넣으세요" 라고 한다. 그런데 화면 스크립트가 표가 없으면 **단추를 잇기 전에**
// 돌아가서, 단추를 눌러도 아무 일도 없었다(탭은 섰는데 사람을 넣을 길이 없다).
//
// 화면 스크립트는 `sourcing.html` 안에 있다 — 그 글을 그대로 읽어 돌린다(Jinja
// 꺾쇠만 걷는다). 이름은 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const el = dom_.el;

const HTML = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "templates", "sourcing.html"), "utf8");
const blocks = HTML.split("{% block scripts %}")[1];
const inline = /<script>([\s\S]*?)<\/script>/.exec(blocks)[1]
  .replace(/\{%[\s\S]*?%\}/g, "").replace(/\{\{[\s\S]*?\}\}/g, "0");

const TAB = "바이오 딜 찾는 투자사";

dom_.resetHandlers();
const root = dom_.makeEl("html");
// 서버가 그린 빈 탭 — 표는 없고 [○○에 추가] 단추와 빈 탭 안내만 있다.
const addBtn = el("button", { type: "button", id: "sourcing-add", "data-bucket": TAB });
root.appendChild(addBtn);
root.appendChild(el("p", { "data-testid": "sourcing-empty-tab" }));

const answers = ["박도윤", ""];          // 이름 · 휴대폰(비움)
const sent = [];
let reloaded = 0;
const win = { location: { reload: function () { reloaded += 1; } } };
const ctx = {
  document: dom_.makeDocument(root), window: win, console: console,
  setTimeout: function () { return 0; }, location: win.location,
  alert: function () {}, confirm: function () { return true; },
  prompt: function () { return answers.shift(); },
  fetch: function (url, opts) {
    sent.push({ url: url, opts: opts });
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 1 }); } });
  }
};
vm.runInNewContext(inline, ctx, { filename: "sourcing.html<script>" });

addBtn.fire("click");
assert.strictEqual(sent.length, 1, "빈 탭에서 [추가]를 눌러도 아무것도 안 보낸다");
assert.strictEqual(sent[0].url, "/api/sourcing?bucket=" + encodeURIComponent(TAB));
assert.strictEqual(sent[0].opts.method, "POST");
assert.deepStrictEqual(JSON.parse(sent[0].opts.body), { name: "박도윤" });

setImmediate(function () {
  assert.strictEqual(reloaded, 1, "넣은 뒤 다시 그려야 표가 선다");
  console.log("sourcing_empty_tab_add_test: ok");
});
