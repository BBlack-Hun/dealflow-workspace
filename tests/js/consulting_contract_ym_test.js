// 메타 탭 `계약년월`(#154) — 서버가 맞춘 값으로 칸을 다시 적는가.
// (node tests/js/consulting_contract_ym_test.js)
//
// consulting.js 를 그대로 돌린다(consulting_contract_pick_test.js 와 같은 방식).
//   1. `2026.3` 을 치면 `contract_ym` 으로 나가고, 응답의 `values`(`2026-03`)로 칸을 다시 적는다.
//   2. 응답에 `values` 가 없으면(옛 서버 · 깨진 본문) 친 글자 그대로 둔다.
//   3. 서버가 막으면(400) 까닭을 띄우고 칸을 옛 값으로 되돌린다.
//   4. 응답 `values` 에 **따라 바뀐 옆 칸**이 실려 오면 그 칸도 적는다 — 계약 완료로 고치면
//      비어 있던 `견적서 첨부 여부` 가 `O` 로 채워져 온다(i255).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

function row(id, value) {
  const cell = D.el("td", { class: "cell", "data-field": "contract_ym" });
  cell.textContent = value;
  return D.el("tr", {
    "data-id": String(id), "data-search": "", "data-f-mgmt": "",
    "data-contacted": "0", "data-contacted-folded": "0", "data-contacted-prev": "0"
  }, [cell]);
}

const rows = [row(1, ""), row(2, "2026-01"), row(3, "2026-05"), row(4, "")];
// 4번 줄에는 `견적서 첨부 여부` 칸도 선다(관리 스타트업 탭).
const quote = D.el("td", { class: "cell", "data-field": "contract_management" });
rows[3].appendChild(quote);
const root = D.el("div", {}, [
  D.el("span", { class: "kpi-value", "data-kpi": "total" }),
  D.el("button", { "data-cs-filter": "" }),
  D.el("table", { id: "cs-table", "data-contract-sheet": "0" }, [D.el("tbody", {}, rows)]),
  D.el("input", { id: "cs-search" }),
  D.el("p", { id: "cs-note" }),
  D.el("button", { id: "cs-add", "data-sheet": "메타" }),
  D.el("button", { id: "cs-import-btn" }),
  D.el("section", { id: "cs-import" }),
  D.el("button", { id: "cs-import-close" })
]);

const sent = [];
const alerts = [];
let reply = { ok: true, body: {} };

D.resetHandlers();
const document = D.makeDocument(root);
const made = document.createElement;
document.createElement = function (tag) {
  const el = made.call(document, tag);
  el.focus = function () {};
  el.setSelectionRange = function () {};
  el.blur = function () { el.fire("blur", { target: el }); };
  return el;
};
const sandbox = {
  document: document,
  window: { location: { reload: function () {} } },
  setTimeout: setTimeout,
  alert: function (m) { alerts.push(m); },
  confirm: function () { return true; },
  prompt: function () { return null; },
  fetch: function (url, opts) {
    sent.push({ url: url, method: opts.method, body: JSON.parse(opts.body) });
    const r = reply;
    return Promise.resolve({ ok: r.ok, json: function () { return Promise.resolve(r.body); } });
  }
};
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: "consulting.js" });

function settle() { return new Promise(function (r) { setTimeout(r, 0); }); }
// 칸을 열고 글자를 쳐서 칸 밖을 누른다 — 이 작은 DOM 은 늘 마지막 입력칸을 꺼낸다.
async function type(tr, text) {
  const cell = tr.querySelector('[data-field="contract_ym"]');
  cell.fire("click", { target: cell });
  const inputs = cell.children.filter(function (c) { return c.tag === "input"; });
  const input = inputs[inputs.length - 1];
  input.value = text;
  input.fire("blur", { target: input });
  await settle();
  await settle();
  return cell;
}

(async function () {
  // 1. 서버가 맞춘 값으로 다시 적는다.
  reply = { ok: true, body: { id: 1, stamps: {}, values: { contract_ym: "2026-03" } } };
  let cell = await type(rows[0], "2026.3");
  assert.deepStrictEqual(sent, [{
    url: "/api/consulting/1", method: "PATCH", body: { contract_ym: "2026.3" }
  }]);
  assert.strictEqual(cell.textContent, "2026-03", "서버가 맞춘 값으로 안 바뀌었습니다");

  // 2. `values` 가 없으면 친 글자 그대로.
  sent.length = 0;
  reply = { ok: true, body: {} };
  cell = await type(rows[1], "2026-02");
  assert.strictEqual(sent.length, 1);
  assert.strictEqual(cell.textContent, "2026-02");

  // 3. 막히면 까닭을 띄우고 옛 값으로.
  reply = { ok: false, body: { detail: "계약년월은 YYYY-MM 으로 적으세요 — 예: 2026-11" } };
  cell = await type(rows[2], "다음 달");
  assert.deepStrictEqual(alerts, [reply.body.detail], "서버가 막은 까닭이 안 보입니다");
  assert.strictEqual(cell.textContent, "2026-05", "막혔는데 칸이 옛 값으로 안 돌아왔습니다");

  // 4. 따라 바뀐 옆 칸도 응답 값으로 적는다.
  alerts.length = 0;
  reply = { ok: true, body: { id: 4, stamps: {},
                              values: { contract_ym: "2026-11", contract_management: "O" } } };
  cell = await type(rows[3], "2026-11");
  assert.strictEqual(cell.textContent, "2026-11");
  assert.strictEqual(quote.textContent, "O", "채워진 견적서 첨부 여부가 새로고침 전까지 안 보입니다");
  assert.deepStrictEqual(alerts, []);

  console.log("consulting_contract_ym_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
