// 계약 탭 `계약여부` 칸 — 보기를 골라 넣고, 보기 밖 옛 값은 **지우지 않고 표시**하는가.
// (node tests/js/consulting_contract_pick_test.js)
//
// consulting.js 를 그대로 돌린다(consulting_contract_received_test.js 와 같은 방식).
//   1. 보기 둘 + `비움` 이 선다.
//   2. 보기 밖 옛 값은 `옛 값:` 단추로 맨 앞에 켜져 서고, 누르면 아무것도 안 나간다.
//   3. 보기를 고르면 `management` 로 나간다.
//   4. 서버가 막으면(400) 그 까닭을 띄우고 칸을 옛 값으로 되돌린다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");
const CHOICES = "무료,유료";

function row(id, value) {
  const cell = D.el("td", {
    class: "cell", "data-field": "management", "data-filter-key": "mgmt",
    "data-choices": CHOICES
  });
  cell.textContent = value;
  return D.el("tr", {
    "data-id": String(id), "data-search": "", "data-f-mgmt": value,
    "data-contacted": "0", "data-contacted-folded": "0", "data-contacted-prev": "0"
  }, [cell]);
}

const rows = [row(1, ""), row(2, "유료 90만")];
const root = D.el("div", {}, [
  D.el("span", { class: "kpi-value", "data-kpi": "total" }),
  D.el("button", { "data-cs-filter": "" }),
  D.el("table", { id: "cs-table", "data-contract-sheet": "1" }, [D.el("tbody", {}, rows)]),
  D.el("input", { id: "cs-search" }),
  D.el("p", { id: "cs-note" }),
  D.el("button", { id: "cs-add", "data-sheet": "월간 계약 업무현황표" }),
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

// 이 작은 DOM 은 `textContent = ""` 이 자식을 안 지운다 — 늘 마지막 것을 꺼낸다.
function open(tr) {
  const cell = tr.querySelector('[data-field="management"]');
  cell.fire("click", { target: cell });
  const boxes = cell.children.filter(function (c) {
    return c.classList.contains("cell-pop-choices");
  });
  return { cell: cell, chips: boxes[boxes.length - 1].children };
}
function labels(chips) { return chips.map(function (c) { return c.textContent; }); }
function settle() { return new Promise(function (r) { setTimeout(r, 0); }); }
async function choose(tr, label) {
  const ui = open(tr);
  const chip = ui.chips.filter(function (c) { return c.textContent === label; })[0];
  assert.ok(chip, "`" + label + "` 단추가 없습니다 — " + labels(ui.chips).join(", "));
  chip.fire("mousedown", { target: chip });
  await settle();
  await settle();
  return ui;
}

(async function () {
  // 1. 보기 둘 + 비움
  assert.deepStrictEqual(labels(open(rows[0]).chips), ["무료", "유료", "비움"]);

  // 2. 옛 값은 맨 앞에 켜져 선다 — 보기 중 어느 것도 켜지지 않는다.
  const old = open(rows[1]).chips;
  assert.deepStrictEqual(labels(old), ["옛 값: 유료 90만", "무료", "유료", "비움"]);
  assert.deepStrictEqual(labels(old.filter(function (c) { return c.classList.contains("on"); })),
    ["옛 값: 유료 90만"], "옛 값에 표시가 없습니다");
  sent.length = 0;
  const kept = await choose(rows[1], "옛 값: 유료 90만");
  assert.deepStrictEqual(sent, [], "옛 값을 눌렀는데 저장이 나갔습니다");
  assert.strictEqual(kept.cell.textContent, "유료 90만", "옛 값이 칸에서 사라졌습니다");

  // 3. 보기를 고르면 `management` 로 나간다.
  sent.length = 0;
  await choose(rows[0], "유료");
  assert.deepStrictEqual(sent, [{
    url: "/api/consulting/1", method: "PATCH", body: { management: "유료" }
  }]);
  assert.strictEqual(rows[0].getAttribute("data-f-mgmt"), "유료");

  // 4. 서버가 막으면 까닭을 띄우고 옛 값으로 되돌린다.
  reply = { ok: false, body: { detail: "계약여부는 무료 · 유료 중에서 고르거나 비워 두세요" } };
  const ui = open(rows[1]);
  const inputs = ui.cell.children.filter(function (c) { return c.tag === "input"; });
  const input = inputs[inputs.length - 1];
  input.value = "무료 (구두)";
  input.fire("blur", { target: input });
  await settle();
  await settle();
  assert.deepStrictEqual(alerts, [reply.body.detail], "서버가 막은 까닭이 안 보입니다");
  assert.strictEqual(ui.cell.textContent, "유료 90만", "막혔는데 칸이 옛 값으로 안 돌아왔습니다");

  console.log("consulting_contract_pick_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
