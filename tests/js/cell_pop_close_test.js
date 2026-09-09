// 칸 위에 뜨는 편집창은 **바깥을 눌렀을 때만** 닫힌다.
// (node tests/js/cell_pop_close_test.js)
//
// ── 무엇이 고장이었나 ────────────────────────────────────────────────────
//
// 닫는 자리가 입력칸의 `blur` **하나**였다. 그래서 창 안을 눌러도 focus 가
// 입력칸에서 빠지기만 하면 창이 **저장되며 닫혔다**:
//
//   · 창의 여백(`.cell-pop` 은 6px 패딩이다)
//   · 보기 목록의 스크롤바 — `.cell-pop-choices` 는 132px 에서 넘치면 스크롤된다.
//     고를 것을 보려고 목록을 내리다 창이 사라진다.
//
// 이제는 `pointerdown` 을 문서에서 듣고 `pop.contains()` 로 안팎을 가른다.
//
// ── 여기서 **정하고 잠그는** 것 ──────────────────────────────────────────
//
// 칸 옆의 안내 딱지(`.cell-hint`, 빈 사업분야의 `추천 3`)는 **바깥**이다.
// 그것은 창의 일부가 아니라 **다른 칸의 손잡이**라서, 누르면 지금 창이 끝나고
// 그 칸이 열려야 한다. 안쪽으로 치면 딱지를 눌러도 아무 일이 안 일어나
// 고장으로 읽힌다(빈 칸은 글자가 없어 누를 자리가 그 딱지뿐이다).
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

// 표 한 줄. 고칠 칸 둘 — 하나는 그냥 칸, 하나는 옆에 안내 딱지가 붙은 칸이다.
function build() {
  const sector = D.el("div", {
    class: "cell", "data-field": "sector_major", "data-type": "pick",
    "data-choices": "AI·SaaS, 헬스케어·바이오, 딥테크·제조"
  });
  sector.textContent = "AI·SaaS";

  const hinted = D.el("div", {
    class: "cell", "data-field": "series", "data-type": "pick",
    "data-choices": "시드, 프리A, 시리즈A"
  });
  const hint = D.el("button", { class: "cell-hint" });

  const plain = D.el("td", { class: "who" });     // 아무것도 아닌 자리(= 바깥)

  const tr = D.el("tr", { "data-id": "7" }, [
    D.el("td", {}, [sector]),
    D.el("td", {}, [hinted, hint]),
    plain
  ]);
  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
    [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [table]);
  return { root: root, table: table, sector: sector, hinted: hinted,
           hint: hint, plain: plain };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const alerts = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1400, innerHeight: 900,
    addEventListener: function () {}, removeEventListener: function () {}
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function (m) { alerts.push(String(m)); },
    // 저장 뒤에 표에 알리는 자리가 쓴다. 없으면 그 줄에서 예외가 나고, 그것을
    // 감싼 `catch` 가 멀쩡한 저장을 실패로 되돌린다.
    CustomEvent: function (type, init) {
      this.type = type;
      this.detail = init && init.detail;
    },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse((opts && opts.body) || "{}") });
      return Promise.resolve({
        ok: true, json: function () { return Promise.resolve({}); }
      });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "inline_edit.js" });
  return {
    sent: sent, alerts: alerts,
    pop: function () { return dom.root.querySelector(".cell-pop"); },
    // 브라우저의 차례 그대로 — pointerdown 이 먼저, click 이 나중이다.
    press: function (node) { node.fire("pointerdown"); node.fire("click"); },
    escape: function () { dom.root.fire("keydown", { key: "Escape" }); }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 창의 **여백**을 눌러도 안 닫힌다 ────────────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.sector);
    const pop = t.pop();
    assert.ok(pop, "칸을 눌렀는데 편집창이 안 떴다");

    pop.fire("pointerdown");                 // 창 자체(= 여백)를 눌렀다
    assert.strictEqual(t.pop(), pop,
      "창의 여백을 눌렀는데 창이 닫혔다 ★ 고치던 중에 창이 사라진다");
    assert.deepStrictEqual(t.sent, [], "여백을 눌렀는데 저장까지 나갔다");
  }

  // ── 2. **보기 목록**(스크롤바)을 눌러도 안 닫힌다 ──────────────────────
  //
  // `.cell-pop-choices` 는 132px 에서 넘치면 스크롤된다. 스크롤바를 잡는 것도
  // 여기서는 그 상자를 누르는 일이다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.sector);
    const pop = t.pop();
    const choices = pop.querySelector(".cell-pop-choices");
    assert.ok(choices, "고를 보기 목록이 안 그려졌다");

    choices.fire("pointerdown");
    assert.strictEqual(t.pop(), pop,
      "보기 목록을 눌렀는데 창이 닫혔다 ★ 목록을 내리다 창이 사라진다");
    assert.deepStrictEqual(t.sent, [], "목록을 눌렀는데 저장까지 나갔다");

    // 보기를 실제로 고르는 길은 그대로 산다.
    choices.querySelectorAll(".cell-pop-choice")[1].fire("mousedown");
    await flush();
    assert.strictEqual(t.pop(), null, "보기를 골랐는데 창이 안 닫혔다");
    assert.strictEqual(t.sent.length, 1, "보기를 골랐는데 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].body.sector_major, "헬스케어·바이오",
      "고른 값이 아닌 것이 저장됐다");
  }

  // ── 3. **바깥**을 누르면 닫히고 저장된다 ───────────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.sector);
    t.pop().querySelector(".cell-pop-input").value = "딥테크·제조";

    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.pop(), null, "바깥을 눌렀는데 창이 안 닫혔다");
    assert.deepStrictEqual(t.sent.map((s) => s.url), ["/api/companies/7"]);
    assert.strictEqual(t.sent[0].body.sector_major, "딥테크·제조",
      "바깥을 눌러 닫을 때 적어 둔 값이 안 저장됐다");
    assert.strictEqual(dom.sector.textContent, "딥테크·제조", "칸에 새 값이 안 그려졌다");
  }

  // ── 4. **Escape 는 버리고 닫는다** — 여백을 눌러 초점이 빠진 뒤에도 ────
  //
  // 예전에는 입력칸에만 걸려 있어서, 여백을 한 번 누르고 나면 Escape 가 안
  // 먹었다. 이제 문서에서 듣는다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.sector);
    const pop = t.pop();
    pop.querySelector(".cell-pop-input").value = "딥테크·제조";
    pop.fire("pointerdown");                 // 여백을 눌러 초점을 뺀다
    t.escape();
    await flush();
    assert.strictEqual(t.pop(), null, "Escape 를 눌렀는데 창이 안 닫혔다");
    assert.deepStrictEqual(t.sent, [], "Escape 로 취소했는데 저장이 나갔다");
    assert.strictEqual(dom.sector.textContent, "AI·SaaS", "취소했는데 칸이 바뀌었다");
  }

  // ── 5. 안내 딱지(`.cell-hint`)는 **바깥**이다 ──────────────────────────
  //
  // 정해 두고 잠근다: 딱지는 다른 칸의 손잡이라, 누르면 지금 창이 끝나고
  // 그 칸이 열린다. 안쪽으로 쳤다면 딱지를 눌러도 아무 일이 안 일어난다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.sector);
    const first = t.pop();
    first.querySelector(".cell-pop-input").value = "딥테크·제조";

    t.press(dom.hint);
    await flush();

    assert.notStrictEqual(t.pop(), first,
      "딱지를 눌렀는데 앞 창이 그대로다 ★ 딱지를 창 안쪽으로 쳤다");
    assert.ok(t.pop(), "딱지를 눌렀는데 그 칸의 창이 안 열렸다 — 빈 칸은 딱지가 유일한 손잡이다");
    assert.strictEqual(t.sent.length, 1, "앞 창에 적어 둔 값이 저장되지 않았다");
    assert.strictEqual(t.sent[0].body.sector_major, "딥테크·제조");
  }

  // ── 6. 닫힌 창은 **두 번 저장하지 않는다** ─────────────────────────────
  //
  // 문서에 건 손을 안 떼면, 창이 사라진 뒤에도 바깥을 누를 때마다 그 자리가
  // 다시 돈다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.sector);
    t.pop().querySelector(".cell-pop-input").value = "딥테크·제조";
    dom.plain.fire("pointerdown");
    await flush();
    dom.plain.fire("pointerdown");
    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent.length, 1,
      "창이 닫힌 뒤에도 바깥 누름을 듣고 있다 — 저장이 여러 번 나간다");
  }

  console.log("cell_pop_close_test: 통과");
}

main().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
