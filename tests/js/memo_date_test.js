// 메모 칸에 새로 다는 줄 앞에 오늘 날짜가 붙는가(i139 · `memo_date.js`).
// (node tests/js/memo_date_test.js)
//
// ① 날짜는 서울 기준 `YYYY/MM/DD` 다(UTC 로 전날 밤 15시 = 서울 다음 날 0시).
// ② 열면 맨 끝 새 줄에 `날짜 + 빈칸` 이 서고, 아무것도 안 적고 닫으면 **옛 값 그대로**다
//    — 저장도 안 나간다. 빈 날짜 줄이 남지 않는다.
// ③ 적으면 `옛 메모\n날짜 적은 글` 로 저장된다. 옛 글은 한 글자도 안 바뀐다.
// ④ 날짜 뒤에 사람이 날짜를 또 적으면(`10/31 통화`) 붙인 날짜를 뗀다 — 둘이 서지 않는다.
// ⑤ 옛 글만 고치고 날짜 줄을 비워 두면 그 줄만 뗀다.
// ⑥ `data-memo-date` 가 없는 긴 글 칸(라운드 사이즈 등)에는 안 붙는다.
// ⑦ 투자컨설턴트 표(`consulting.js`)의 추가 메모 칸도 같다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const MEMO = fs.readFileSync(path.join(JS, "memo_date.js"), "utf8");
const INLINE = fs.readFileSync(path.join(JS, "inline_edit.js"), "utf8");
const CONSULTING = fs.readFileSync(path.join(JS, "consulting.js"), "utf8");

const flush = () => new Promise((r) => setTimeout(r, 0));

function helper() {
  const win = {};
  vm.runInNewContext(MEMO, { window: win });
  return win.DealflowMemoDate;
}

// ── 순수 함수 ───────────────────────────────────────────────────────────────
function pure() {
  const M = helper();
  const NOW = Date.UTC(2026, 10, 1, 15, 30);     // 서울 2026-11-02 00:30
  const S = "2026/11/02";
  // ①
  assert.strictEqual(M.today(NOW), S, "서울 날짜가 아니다");
  assert.strictEqual(M.today(Date.UTC(2026, 6, 25, 3)), "2026/07/25");

  // ②
  assert.strictEqual(M.open("", NOW), S + " ");
  assert.strictEqual(M.open("처음 메모", NOW), "처음 메모\n" + S + " ");
  for (const before of ["", "처음 메모", "첫 줄\n둘째 줄"]) {
    assert.strictEqual(M.close(M.open(before, NOW), before, NOW), before,
      "아무것도 안 적었는데 값이 바뀐다: " + JSON.stringify(before));
  }

  // ③
  assert.strictEqual(M.close("처음 메모\n" + S + " 다음 주 통화", "처음 메모", NOW),
    "처음 메모\n" + S + " 다음 주 통화");
  assert.strictEqual(M.close(S + " 자료 받음\n", "", NOW), S + " 자료 받음");
  // 옛 줄이 우연히 오늘 날짜 + 날짜로 시작해도 그 줄은 안 건드린다.
  const old = S + " 10/31 예전 기록";
  assert.strictEqual(M.close(old + "\n" + S + " 새 기록", old, NOW), old + "\n" + S + " 새 기록");
  assert.strictEqual(M.close(old + "\n" + S + " ", old, NOW), old);

  // ④
  assert.strictEqual(M.close("처음 메모\n" + S + " 10/31 통화함", "처음 메모", NOW),
    "처음 메모\n10/31 통화함", "사람이 적은 날짜 앞에 날짜가 겹쳤다");
  assert.strictEqual(M.close(S + " 2026.10.31: 미팅", "", NOW), "2026.10.31: 미팅");
  assert.strictEqual(M.close(S + " 2026-10-30 자료", "", NOW), "2026-10-30 자료");
  assert.strictEqual(M.close(S + " 3/4분기 매출 확인", "", NOW), S + " 3/4분기 매출 확인",
    "날짜가 아닌 글(3/4분기)을 날짜로 읽었다");

  // ⑤
  assert.strictEqual(M.close("처음 메모 고침\n" + S + " ", "처음 메모", NOW), "처음 메모 고침");
  // 옛 글이 원래 날짜만 있는 줄로 끝났으면 그건 옛 글이다 — 취소(Esc)가 그 값을 다시 넣는다.
  const bare = "기록\n" + S;
  assert.strictEqual(M.close(bare, bare, NOW), bare, "옛 글의 끝줄을 뗐다");
}

// ── inline_edit.js ─────────────────────────────────────────────────────────
function inlineHarness() {
  const memo = D.el("div", { class: "cell clamp2", "data-field": "memo",
                             "data-type": "long", "data-memo-date": "" });
  memo.textContent = "처음 메모";
  const round = D.el("div", { class: "cell clamp2", "data-field": "round_size",
                              "data-type": "long" });
  round.textContent = "시리즈 A";
  const outside = D.el("td", {});
  const tr = D.el("tr", { "data-id": "7" },
    [D.el("td", {}, [memo]), D.el("td", {}, [round]), outside]);
  const table = D.el("table", { id: "t", "data-inline-url": "/api/contacts" },
    [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [table]);

  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(root);
  const win = { innerWidth: 1400, innerHeight: 900,
                addEventListener: function () {}, removeEventListener: function () {} };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout, alert: function () {},
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse(opts.body || "{}") });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(MEMO, sandbox, { filename: "memo_date.js" });
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  return {
    memo: memo, round: round, sent: sent, S: win.DealflowMemoDate.today(),
    open: function (cell) {
      cell.fire("pointerdown");
      cell.fire("click");
      return root.querySelector(".cell-pop-input");
    },
    away: function () { outside.fire("pointerdown"); },
    escape: function () { root.fire("keydown", { key: "Escape" }); }
  };
}

async function inline() {
  const t = inlineHarness();
  // ② 열면 날짜가 서 있고, 그대로 닫으면 안 보낸다
  let area = t.open(t.memo);
  assert.strictEqual(area.value, "처음 메모\n" + t.S + " ", "열었는데 날짜 줄이 없다");
  t.away();
  await flush();
  assert.deepStrictEqual(t.sent, [], "아무것도 안 적었는데 저장이 나갔다");
  assert.strictEqual(t.memo.textContent, "처음 메모", "칸에 빈 날짜 줄이 남았다");

  // Esc 도 그대로
  area = t.open(t.memo);
  area.value += "적다가 취소";
  t.escape();
  await flush();
  assert.deepStrictEqual(t.sent, [], "취소했는데 저장이 나갔다");

  // ③ 적으면 날짜와 함께 저장
  area = t.open(t.memo);
  area.value += "다음 주 통화";
  t.away();
  await flush();
  await flush();
  assert.deepStrictEqual(t.sent[0], { url: "/api/contacts/7",
    body: { memo: "처음 메모\n" + t.S + " 다음 주 통화" } });
  assert.strictEqual(t.memo.textContent, "처음 메모\n" + t.S + " 다음 주 통화");

  // ⑥ 표시가 없는 긴 글 칸은 그대로
  area = t.open(t.round);
  assert.strictEqual(area.value, "시리즈 A", "메모가 아닌 칸에 날짜가 붙었다");
  t.away();
  await flush();
  assert.strictEqual(t.sent.length, 1, "안 고친 칸이 저장됐다");
}

// ── ⑦ consulting.js ────────────────────────────────────────────────────────
async function consulting() {
  const memo = D.el("td", { class: "cell multi", "data-field": "cc8", "data-custom": "8",
                            "data-custom-rows": "consulting_companies", "data-memo-date": "" });
  memo.textContent = "컨설팅 메모";
  const tr = D.el("tr", {
    "data-id": "3", "data-search": "",
    "data-contacted": "0", "data-contacted-folded": "0", "data-contacted-prev": "0"
  }, [memo]);
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0" },
    [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [
    D.el("span", { class: "kpi-value", "data-kpi": "total" }),
    D.el("button", { "data-cs-filter": "" }),
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]);

  D.resetHandlers();
  const sent = [];
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
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {}, confirm: function () { return true; },
    prompt: function () { return null; },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse(opts.body || "{}") });
      return Promise.resolve({ ok: true, json: function () {
        return Promise.resolve({ value: JSON.parse(opts.body).value });
      } });
    }
  };
  sandbox.window = { location: { reload: function () {} } };
  vm.createContext(sandbox);
  vm.runInContext(MEMO, sandbox, { filename: "memo_date.js" });
  vm.runInContext(CONSULTING, sandbox, { filename: "consulting.js" });
  const S = sandbox.window.DealflowMemoDate.today();
  const area = () => memo.children.filter((c) => c.tag === "textarea")[0];

  memo.fire("click", { target: memo });
  assert.strictEqual(area().value, "컨설팅 메모\n" + S + " ", "투자컨설턴트 메모 칸에 날짜 줄이 없다");
  area().blur();
  await flush();
  assert.deepStrictEqual(sent, [], "투자컨설턴트 메모 칸 — 안 적었는데 저장이 나갔다");

  memo.fire("click", { target: memo });
  area().value += "견적 회신 대기";
  area().blur();
  await flush();
  assert.deepStrictEqual(sent[0].body, { column_id: 8, value: "컨설팅 메모\n" + S + " 견적 회신 대기" });
}

(async function main() {
  pure();
  await inline();
  await consulting();
  console.log("ok — 메모 칸의 새 줄에만 오늘 날짜, 빈 날짜 줄은 안 남고 옛 글은 그대로");
})().catch(function (err) {
  console.error(err && err.stack || err);
  process.exit(1);
});
