// 칸을 감싼 **td 의 빈 자리**를 눌러도 그 칸이 열리는가. (node tests/js/inline_edit_td_click_test.js)
//
// #97 — 딜 소싱 › M&A 찾는 투자사 탭에서 `선호 투자분야` · `메모` 가 안 적혔다.
// 그 두 칸은 td 안쪽 div 가 칸이다(`<td><div class="cell clamp2" data-field="memo">`).
// div 는 글자 한 줄 높이인데 줄은 이름 칸(삭제 · 딜 받음 · 투자사 관리 현황 연결
// 표시 · 연결 풀기) 때문에 몇 배 높아서, td 의 대부분을 눌러도 아무 일이 없었다.
// 빈 칸은 그 한 줄도 안 보인다. td 자체가 칸인 칸(휴대폰 · 직함 · 담당자)은
// 그대로 적혔다 — 그래서 '두 칸만 안 된다' 로 보였다.
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

// 딜 소싱 표 한 줄(`sourcing.html`) — 이름 칸에 단추, 메모는 td 안쪽 div.
function build() {
  const name = D.el("b", { class: "cell", "data-field": "name" });
  name.textContent = "홍길동";
  const del = D.el("button", { class: "linkbtn danger js-sourcing-del" });
  const nameTd = D.el("td", {}, [name, D.el("div", { class: "cell-sub row-actions" }, [del])]);
  const memo = D.el("div", { class: "cell clamp2", "data-field": "memo", "data-type": "long" });
  const memoTd = D.el("td", {}, [memo]);
  const rowNo = D.el("td", { class: "rowno muted" });
  const tr = D.el("tr", { "data-id": "159" }, [rowNo, nameTd, memoTd]);
  const table = D.el("table", { id: "sourcing-table", "data-inline-url": "/api/sourcing" },
    [D.el("tbody", {}, [tr])]);
  return { root: D.el("div", {}, [table]), memo: memo, memoTd: memoTd,
           del: del, rowNo: rowNo };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1400, innerHeight: 900,
    addEventListener: function () {}, removeEventListener: function () {}
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function (m) { throw new Error("alert: " + m); },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse((opts && opts.body) || "{}") });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "inline_edit.js" });
  return {
    sent: sent,
    pop: function () { return dom.root.querySelector(".cell-pop"); },
    press: function (node) { node.fire("pointerdown"); node.fire("click"); }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 메모 td 의 빈 자리를 누르면 메모 창이 열리고, 적은 것이 저장된다 ──
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.memoTd);
    assert.ok(t.pop(), "메모 칸의 빈 자리를 눌렀는데 편집창이 안 떴다 ★ #97");
    t.pop().querySelector(".cell-pop-input").value = "M&A 관심 메모";
    dom.rowNo.fire("pointerdown");            // 바깥을 눌러 닫는다
    await flush();
    assert.deepStrictEqual(t.sent, [{ url: "/api/sourcing/159", body: { memo: "M&A 관심 메모" } }]);
  }

  // ── 2. td 안의 단추는 제 일만 — 이름 칸 [삭제] 를 눌러도 이름 창은 안 뜬다 ──
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.del);
    assert.strictEqual(t.pop(), null, "[삭제] 를 눌렀는데 칸 편집이 열렸다");
  }

  // ── 3. 고칠 칸이 없는 td(번호)는 아무 일도 없다 ──────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rowNo);
    assert.strictEqual(t.pop(), null, "고칠 칸이 없는 td 를 눌렀는데 무언가 열렸다");
    assert.deepStrictEqual(t.sent, []);
  }

  console.log("inline_edit_td_click_test: 통과");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
