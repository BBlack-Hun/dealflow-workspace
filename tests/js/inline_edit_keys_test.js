// 표에서 **키보드로 칸·줄 사이를 넘어간다.**
// (node tests/js/inline_edit_keys_test.js)
//
// ── 무엇이 고장이었나 ────────────────────────────────────────────────────
//
// 담당 줄이 여든인 사람이 같은 칸을 여든 번 고친다. 그런데 칸 하나를 끝내면
// 초점이 문서 맨 위(BODY)로 빠졌다 — 표 안에서 초점을 받는 것이 그 줄의
// [수정] 단추뿐이었기 때문이다. 그래서 **다음 칸을 마우스로 다시 조준**해야
// 했고, 여든 줄이면 백예순 번을 겨냥했다. 적는 일보다 겨냥하는 일이 많았다.
//
// ── 여기서 **정하고 잠그는** 것 ──────────────────────────────────────────
//
// · Tab 은 옆 칸으로 간다. **줄의 끝에서는 막지 않는다** — 그 자리를 가로채면
//   표 안에서 [수정] 단추에 닿을 길이 없어진다(브라우저의 차례에 맡긴다).
// · Enter 는 고치기 시작하고, 고치던 것은 저장하고 **아래 줄 같은 칸**으로.
// · 방향키는 고치지 않는 동안의 이동이다.
// · **거른 표에서는 보이는 줄만 지난다**(`tr.hidden`). 안 그러면 걸러 놓고
//   안 보이는 줄을 고치게 된다.
// · 고르는 칸(`pick`)은 ↑↓ 로 짚고 Enter 로 확정한다. 숫자키로도 고른다.
// · **고르는 칸을 열면 옛 값이 통째로 골라져 있다.** 커서를 끝에 두면 치는
//   글자가 옛 값 뒤에 이어 붙어, `미확인` 이 든 칸에 적으면
//   `미확인투자유치 진행 중` 이 저장된다(검토가 실측한 함정이다).
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

const CHOICES = "미발송,발송 예정,발송 완료";

// 세 줄짜리 표. 줄마다 글자 칸 둘 · 고르는 칸 하나 · [수정] 단추 하나.
function build() {
  const rows = [];
  ["가 기업", "나 기업", "다 기업"].forEach(function (name, i) {
    const firm = D.el("td", { class: "cell", "data-field": "firm" });
    firm.textContent = name;
    const memo = D.el("td", { class: "cell", "data-field": "memo" });
    const send = D.el("td", {
      class: "cell", "data-field": "send", "data-type": "pick",
      "data-choices": CHOICES
    });
    const edit = D.el("button", { class: "linkbtn" });
    edit.textContent = "수정";
    const tr = D.el("tr", { "data-id": String(11 + i) },
      [firm, memo, send, D.el("td", {}, [edit])]);
    rows.push({ tr: tr, firm: firm, memo: memo, send: send, edit: edit });
  });

  const table = D.el("table", { id: "list-table", "data-inline-url": "/api/contacts" },
    [D.el("tbody", {}, rows.map(function (r) { return r.tr; }))]);
  const wrap = D.el("div", { class: "table-wrap wide" }, [table]);
  const root = D.el("div", {}, [wrap]);
  return { root: root, table: table, rows: rows };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const selected = [];        // `select()` 가 불린 입력칸
  let focused = null;

  // 초점이 어디로 갔는지 본다 — 이 DOM 의 `focus()` 는 원래 아무 일도 안 한다.
  dom.root.querySelectorAll(".cell[data-field]").forEach(function (cell) {
    cell.focus = function () { focused = cell; };
  });

  const document = D.makeDocument(dom.root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const node = made(tag);
    node.select = function () { selected.push(node); };
    return node;
  };

  const win = {
    innerWidth: 1400, innerHeight: 900,
    addEventListener: function () {}, removeEventListener: function () {}
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {},
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

  // 키를 한 번 누른다. 돌려주는 것은 **화면 기본 동작을 막았는가** —
  // 줄의 끝에서 Tab 을 막지 않는 것이 [수정] 단추에 닿는 길이다.
  function press(node, key, more) {
    let blocked = false;
    const ev = Object.assign({ key: key, preventDefault: function () { blocked = true; } },
      more || {});
    node.fire("keydown", ev);
    return blocked;
  }

  return {
    sent: sent, selected: selected,
    // **초점이 어디 있는지를 읽을 수 있는 이름으로** 돌려준다.
    // 칸 그대로를 견주면, 어긋났을 때 node 가 가짜 DOM 을 통째로 펼쳐 보이려다
    // 메모리를 다 쓰고 죽는다(줄과 부모가 서로를 가리킨다) — 정작 무엇이
    // 어긋났는지는 한 줄도 안 남는다.
    where: function () {
      if (!focused) return "(초점 없음)";
      const tr = focused.closest("tr");
      return (tr ? tr.getAttribute("data-id") : "?") + "/"
        + focused.getAttribute("data-field");
    },
    press: press,
    pop: function () { return dom.root.querySelector(".cell-pop"); },
    popInput: function () { return dom.root.querySelector(".cell-pop .cell-pop-input"); },
    chips: function () {
      const pop = dom.root.querySelector(".cell-pop");
      return pop ? pop.querySelectorAll(".cell-pop-choice") : [];
    },
    cellInput: function (cell) { return cell.querySelector(".cell-input"); }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 칸이 **초점을 받을 수 있게** 되어 있다 ──────────────────────────
  //
  // 이것이 없으면 아래 전부가 뜻이 없다 — 키가 칸에 닿을 수가 없다.
  {
    const dom = build();
    run(dom);
    dom.rows.forEach(function (r) {
      ["firm", "memo", "send"].forEach(function (f) {
        assert.strictEqual(r[f].getAttribute("tabindex"), "0",
          "칸이 초점을 못 받는다 ★ 키보드가 표에 닿을 길이 없다: " + f);
      });
    });
  }

  // ── 2. Tab 은 옆 칸, 줄 끝에서는 **브라우저에 맡긴다** ────────────────
  {
    const dom = build();
    const t = run(dom);
    assert.ok(t.press(dom.rows[0].firm, "Tab"), "Tab 을 눌렀는데 아무 데도 안 갔다");
    assert.strictEqual(t.where(), "11/memo", "Tab 이 옆 칸으로 안 간다");

    assert.ok(t.press(dom.rows[0].memo, "Tab", { shiftKey: true }),
      "Shift+Tab 을 눌렀는데 아무 데도 안 갔다");
    assert.strictEqual(t.where(), "11/firm", "Shift+Tab 이 앞 칸으로 안 간다");

    // 줄의 **마지막 칸**에서는 막지 않는다 — 그다음이 [수정] 단추다.
    assert.strictEqual(t.press(dom.rows[0].send, "Tab"), false,
      "줄 끝에서 Tab 을 가로챘다 ★ 표 안에서 [수정] 단추에 닿을 길이 없어진다");
    // 줄의 **첫 칸**에서 Shift+Tab 도 같다(앞 줄의 단추로 간다).
    assert.strictEqual(t.press(dom.rows[1].firm, "Tab", { shiftKey: true }), false,
      "줄 첫 칸에서 Shift+Tab 을 가로챘다 ★ 앞 줄 [수정] 단추에 닿을 길이 없어진다");
  }

  // ── 3. 방향키 — 위·아래는 **같은 칸**, 좌·우는 옆 칸 ──────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rows[0].memo, "ArrowDown");
    assert.strictEqual(t.where(), "12/memo", "↓ 가 아래 줄 같은 칸으로 안 간다");
    t.press(dom.rows[1].memo, "ArrowUp");
    assert.strictEqual(t.where(), "11/memo", "↑ 가 윗 줄 같은 칸으로 안 간다");
    t.press(dom.rows[0].memo, "ArrowRight");
    assert.strictEqual(t.where(), "11/send", "→ 가 옆 칸으로 안 간다");
    t.press(dom.rows[0].send, "ArrowLeft");
    assert.strictEqual(t.where(), "11/memo", "← 가 앞 칸으로 안 간다");

    // 끝에서는 아무 데도 안 가고 **막지도 않는다**(표가 밀리게 둔다).
    assert.strictEqual(t.press(dom.rows[0].firm, "ArrowUp"), false,
      "첫 줄에서 ↑ 를 가로챘다");
    assert.strictEqual(t.press(dom.rows[2].firm, "ArrowDown"), false,
      "끝 줄에서 ↓ 를 가로챘다");
  }

  // ── 4. **거른 표에서는 보이는 줄만** 지난다 ────────────────────────────
  //
  // 안 그러면 걸러 놓고 안 보이는 줄을 고치게 된다 — 고친 사람은 무엇을
  // 고쳤는지 모른다.
  {
    const dom = build();
    const t = run(dom);
    dom.rows[1].tr.hidden = true;            // `filters.js` 가 이렇게 감춘다
    t.press(dom.rows[0].memo, "ArrowDown");
    assert.strictEqual(t.where(), "13/memo",
      "감춘 줄에 내려앉았다 ★ 안 보이는 줄을 고치게 된다");
    t.press(dom.rows[2].memo, "ArrowUp");
    assert.strictEqual(t.where(), "11/memo", "올라올 때도 감춘 줄을 지나야 한다");
  }

  // ── 5. Enter — 고치기 시작하고, **저장하고 아래 줄 같은 칸**으로 ───────
  {
    const dom = build();
    const t = run(dom);
    assert.ok(t.press(dom.rows[0].memo, "Enter"), "Enter 를 눌렀는데 안 막았다");
    const input = t.cellInput(dom.rows[0].memo);
    assert.ok(input, "Enter 를 눌렀는데 고칠 칸이 안 열렸다");

    input.value = "2분기 자료 받음";
    t.press(input, "Enter");
    await flush();
    assert.strictEqual(t.sent.length, 1, "Enter 로 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].url, "/api/contacts/11");
    assert.strictEqual(t.sent[0].body.memo, "2분기 자료 받음");
    assert.strictEqual(t.where(), "12/memo",
      "저장하고 아래 줄 같은 칸으로 안 갔다 ★ 여든 줄을 훑어 내려갈 수가 없다");
  }

  // ── 6. 고치던 중의 Tab 은 **저장하고 옆 칸**, Escape 는 버리고 제자리 ──
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rows[0].firm, "Enter");
    const input = t.cellInput(dom.rows[0].firm);
    input.value = "가 기업 (사명 변경)";
    t.press(input, "Tab");
    await flush();
    assert.strictEqual(t.sent.length, 1, "Tab 으로 넘어가면서 저장이 안 됐다");
    assert.strictEqual(t.sent[0].body.firm, "가 기업 (사명 변경)");
    assert.strictEqual(t.where(), "11/memo", "Tab 이 옆 칸으로 안 갔다");

    t.press(dom.rows[1].firm, "Enter");
    const two = t.cellInput(dom.rows[1].firm);
    two.value = "잘못 적었다";
    t.press(two, "Escape");
    await flush();
    assert.strictEqual(t.sent.length, 1, "Escape 로 버렸는데 저장이 나갔다");
    assert.strictEqual(t.where(), "12/firm",
      "Escape 뒤에 초점이 표를 떠났다 ★ 다음 칸을 다시 마우스로 찾게 된다");
  }

  // ── 7. 고르는 칸 — ↑↓ 로 짚고 Enter 로 확정 ───────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rows[0].send, "Enter");
    const pop = t.popInput();
    assert.ok(pop, "고르는 칸에서 Enter 를 눌렀는데 창이 안 떴다");
    assert.strictEqual(t.chips().length, 3, "보기가 다 안 떴다");

    // 아직 아무것도 안 짚었다 — 빈 칸이라 목록에 없는 값이다.
    assert.ok(!t.chips()[0].classList.contains("key-on"), "열자마자 무언가를 짚고 있다");
    t.press(pop, "ArrowDown");
    assert.ok(t.chips()[0].classList.contains("key-on"), "↓ 가 첫 보기를 안 짚는다");
    t.press(pop, "ArrowDown");
    t.press(pop, "ArrowDown");
    assert.ok(t.chips()[2].classList.contains("key-on"), "↓ 로 셋째 보기까지 못 간다");
    t.press(pop, "ArrowDown");
    assert.ok(t.chips()[2].classList.contains("key-on"), "목록 끝을 넘어갔다");

    t.press(pop, "Enter");
    await flush();
    assert.strictEqual(!!t.pop(), false, "Enter 로 확정했는데 창이 안 닫혔다");
    assert.strictEqual(t.sent.length, 1, "Enter 로 확정했는데 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].body.send, "발송 완료",
      "짚고 있던 보기가 아닌 것이 저장됐다");
    assert.strictEqual(t.where(), "12/send",
      "고르고 나서 아래 줄 같은 칸으로 안 갔다");
  }

  // ── 8. 숫자키 하나로 고른다 — 여든 줄에 같은 값을 적는 길 ─────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rows[0].send, "Enter");
    assert.strictEqual(t.chips()[2].getAttribute("data-key"), "3",
      "보기에 번호가 안 붙었다 ★ 숫자키를 쓸 수 있는지 화면에 안 보인다");
    t.press(t.popInput(), "3");
    await flush();
    assert.strictEqual(t.sent.length, 1, "숫자키로 골랐는데 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].body.send, "발송 완료", "숫자키가 엉뚱한 보기를 골랐다");
    assert.strictEqual(t.where(), "12/send", "숫자키로 고른 뒤 아래 줄로 안 갔다");
  }

  // ── 9. **타이핑하면 숫자는 다시 글자가 된다** ─────────────────────────
  //
  // 값에 숫자가 들어가는 칸이 있다(`2026-09`). 치는 숫자가 보기를 골라 버리면
  // 그런 값은 아예 적을 수가 없다. 번호 표시도 같이 지운다 — 안 되는 길이
  // 보이는 것이 더 나쁘다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rows[0].send, "Enter");
    const pop = t.popInput();
    pop.value = "9월 2";
    pop.fire("input", {});
    assert.strictEqual(t.chips()[2].getAttribute("data-key"), null,
      "직접 적기 시작했는데 보기에 번호가 그대로 붙어 있다");
    t.press(pop, "3");
    await flush();
    assert.strictEqual(t.sent.length, 0,
      "직접 적는 중에 숫자키가 보기를 골랐다 ★ 숫자가 든 값을 적을 수가 없다");

    pop.value = "9월 23일 발송";
    t.press(pop, "Enter");
    await flush();
    assert.strictEqual(t.sent.length, 1, "적은 그대로 저장이 안 됐다");
    assert.strictEqual(t.sent[0].body.send, "9월 23일 발송");
  }

  // ── 10. 고르는 칸을 열면 **옛 값이 통째로 골라져 있다** ───────────────
  //
  // 커서를 끝에 두면 치는 글자가 옛 값 뒤에 이어 붙는다 — `미확인` 이 든 칸에
  // 적으면 `미확인투자유치 진행 중` 이 저장됐다. 보기가 정해진 칸에 그런 값이
  // 하나 생기면 필터가 그 줄만 따로 센다.
  {
    const dom = build();
    const t = run(dom);
    dom.rows[0].send.textContent = "미발송";
    t.press(dom.rows[0].send, "Enter");
    const pop = t.popInput();
    assert.strictEqual(pop.value, "미발송", "옛 값이 창에 안 실렸다");
    assert.ok(t.selected.indexOf(pop) >= 0,
      "고르는 칸을 열었는데 글자가 안 골라져 있다 ★ 치는 글자가 옛 값 뒤에 붙는다");

    // 지금 값은 짚혀 있다 — 아무 키도 안 누르고 Enter 면 값이 그대로다.
    assert.ok(t.chips()[0].classList.contains("key-on"), "지금 값을 안 짚고 열렸다");
    t.press(pop, "Enter");
    await flush();
    assert.strictEqual(t.sent.length, 0, "안 고쳤는데 저장이 나갔다");
  }

  // ── 11. 글자 칸은 그대로 **끝에 커서**다 ──────────────────────────────
  //
  // 메모에 한 줄 덧붙이는 것이 하려던 일이라, 그쪽까지 통째로 골라 두면
  // 이어 적으려던 사람이 적어 둔 것을 날린다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rows[0].memo, "Enter");
    const input = t.cellInput(dom.rows[0].memo);
    assert.strictEqual(t.selected.indexOf(input) >= 0, false,
      "글자 칸까지 통째로 골라 뒀다 ★ 이어 적으려던 사람이 적어 둔 것을 날린다");
  }

  // ── 12. **한글을 조합하는 중에는 비켜선다** ──────────────────────────
  //
  // 한글 입력기는 글자를 만드는 동안 Enter·방향키를 제가 쓴다(조합을 굳히고,
  // 후보를 고른다). 여기서 가로채면 `ㄱㅏ` 를 굳히려고 친 Enter 가 **칸을
  // 저장하고 아래 줄로** 가 버려서, 만들던 글자가 통째로 사라진다 — 이 앱은
  // 적는 말이 죄다 한글이라 그 자리가 곧 일상이다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rows[0].memo, "Enter");
    const input = t.cellInput(dom.rows[0].memo);
    input.value = "통화함";
    t.press(input, "Enter", { isComposing: true });
    await flush();
    assert.strictEqual(t.sent.length, 0,
      "조합 중에 친 Enter 가 칸을 저장했다 ★ 만들던 글자가 사라진다");
    assert.strictEqual(t.where(), "(초점 없음)",
      "조합 중에 친 Enter 가 초점을 아래 줄로 옮겼다");

    // 굳힌 뒤의 Enter 는 예전처럼 저장하고 내려간다.
    t.press(input, "Enter");
    await flush();
    assert.strictEqual(t.sent.length, 1, "조합을 끝낸 뒤의 Enter 가 저장을 안 했다");
    assert.strictEqual(t.where(), "12/memo", "조합을 끝낸 뒤에 아래 줄로 안 갔다");
  }

  // 고르는 창도 같다 — 조합 중의 ↑↓ 는 입력기의 후보 고르기다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.rows[0].send, "Enter");
    const pop = t.popInput();
    t.press(pop, "ArrowDown", { isComposing: true });
    assert.ok(!t.chips()[0].classList.contains("key-on"),
      "조합 중에 친 ↓ 가 보기를 짚었다 ★ 입력기의 후보 고르기를 빼앗는다");
    t.press(pop, "Enter", { isComposing: true });
    await flush();
    assert.ok(t.pop(), "조합 중에 친 Enter 가 창을 닫았다 ★ 만들던 글자가 사라진다");
  }

  // ── 13. 떠서 고치는 창에서도 Tab 은 **저장하고 옆 칸** ───────────────
  //
  // 안 걸어 두면 Tab 이 초점만 빼 간다. 이 창은 바깥을 **눌렀을 때만** 닫히
  // 므로(#152) 초점이 빠져도 안 닫힌다 — 창은 떠 있는데 키는 딴 데서 먹는
  // 상태가 된다. 칸이 초점을 받게 된 뒤로는 그 자리가 늘 열려 있다.
  {
    const dom = build();
    const t = run(dom);
    // 줄의 **마지막 칸**이 고르는 칸이다 — 끝에서도 창이 닫히고 그 칸에 남는다.
    t.press(dom.rows[0].send, "Enter");
    assert.ok(t.pop(), "창이 안 떴다");
    t.pop().fire("keydown", { key: "Tab", preventDefault: function () {} });
    await flush();
    assert.strictEqual(!!t.pop(), false,
      "창에서 Tab 을 눌렀는데 창이 그대로다 ★ 초점만 빠져 키가 딴 데서 먹는다");
    assert.strictEqual(t.where(), "11/send", "줄 끝에서는 그 칸에 남아야 한다");

    // 가운데 칸이면 옆 칸으로, 적어 둔 값은 저장된다.
    t.press(dom.rows[1].memo, "Enter");
    const box = t.cellInput(dom.rows[1].memo);
    box.value = "카톡 확인";
    box.fire("keydown", { key: "Tab", preventDefault: function () {} });
    await flush();
    assert.strictEqual(t.sent.length, 1, "Tab 으로 나가면서 저장이 안 됐다");
    assert.strictEqual(t.sent[0].body.memo, "카톡 확인");
    assert.strictEqual(t.where(), "12/send", "Tab 이 옆 칸으로 안 갔다");
  }

  console.log("inline_edit_keys_test: 통과");
}

main().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
