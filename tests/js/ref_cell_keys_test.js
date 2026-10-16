// 참고 표 **칸 편집기의 키**. (node tests/js/ref_cell_keys_test.js)
//
// 딜소개 스크립트처럼 문단을 넣는 칸이다. 예전에는 한 줄 높이로 열리고 엔터가
// 곧 저장이라, 줄을 나누려고 엔터를 치는 순간 칸이 닫히며 저장됐다 — "스크롤이
// 안 내려가고 내용 기입이 안 된다" 는 말이 그것이다(#11 · #13).
//
// 키는 이 앱의 다른 여러 줄 칸과 같아야 한다(투자컨설턴트 현황의 `multi` 칸 ·
// 공통 편집기의 긴 글 칸): Enter 줄바꿈 · Ctrl/Cmd+Enter 저장 · Esc 취소.
// 머리글은 한 줄 이름이라 Enter 가 곧 저장이다.
//
// 규칙을 옮겨 적지 않고 `ref_edit.js` 를 **그대로 돌린다**
// (ref_head_edit_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "ref_edit.js");
const src = fs.readFileSync(SRC, "utf8");

function build() {
  const head = D.el("th", { class: "ref-cell ref-head", "data-col": "0" });
  head.textContent = "스크립트";
  const cell = D.el("td", { class: "ref-cell", "data-row": "0", "data-col": "0" });
  cell.textContent = "첫 줄";
  const table = D.el("table", { id: "ref-table", "data-ref-id": "7" }, [
    D.el("thead", {}, [D.el("tr", {}, [head])]),
    D.el("tbody", {}, [D.el("tr", {}, [cell])])
  ]);
  return { root: D.el("div", {}, [table]), table: table, head: head, cell: cell };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: {},
    alert: function () {},
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse(opts.body) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "ref_edit.js" });
  return sent;
}

function open(dom, cell) {
  dom.table.fire("click", { target: cell });
  const input = cell.querySelector(".cell-input");
  assert.ok(input, "눌렀는데 고칠 칸이 안 떴다");
  return input;
}

// 키를 누른다. 막았는지(preventDefault)도 같이 돌려준다.
function press(input, key, mods) {
  let prevented = false;
  input.fire("keydown", Object.assign({
    key: key, preventDefault() { prevented = true; }
  }, mods || {}));
  return prevented;
}

// 칸이 아직 열려 있는가 — 열려 있으면 다시 눌러도 새 입력칸이 안 생긴다.
// 칸이 닫혔는지는 저장이 나갔는지와 `textContent` 로 본다.
const tick = () => new Promise((r) => setTimeout(r, 0));

(async function () {
  // 1) 칸에서 Enter 는 **줄바꿈**이다 — 닫히지도 저장되지도 않는다.
  {
    const dom = build();
    const sent = run(dom);
    const input = open(dom, dom.cell);
    input.value = "첫 줄\n둘째 줄";
    const prevented = press(input, "Enter");
    await tick();
    assert.strictEqual(prevented, false,
      "칸에서 Enter 를 막았다 — 줄을 나눌 수가 없다");
    assert.strictEqual(sent.length, 0, "칸에서 Enter 를 쳤더니 저장이 나갔다");
    assert.strictEqual(dom.cell.querySelector(".cell-input"), input,
      "칸에서 Enter 를 쳤더니 입력칸이 닫혔다");
  }

  // 2) Ctrl+Enter 는 저장이다 — 나눈 줄이 **그대로** 간다.
  {
    const dom = build();
    const sent = run(dom);
    const input = open(dom, dom.cell);
    input.value = "안녕하세요\n딜 소개 드립니다\n\n감사합니다";
    const prevented = press(input, "Enter", { ctrlKey: true });
    await tick();
    assert.ok(prevented, "Ctrl+Enter 가 줄바꿈까지 넣었다");
    assert.strictEqual(sent.length, 1, "Ctrl+Enter 로 저장이 안 나갔다");
    assert.strictEqual(sent[0].url, "/api/ref-sheets/7/cell");
    assert.deepStrictEqual(sent[0].body,
      { row: 0, col: 0, value: "안녕하세요\n딜 소개 드립니다\n\n감사합니다" });
    assert.strictEqual(dom.cell.textContent, "안녕하세요\n딜 소개 드립니다\n\n감사합니다");
  }

  // 3) 맥의 Cmd+Enter 도 같다.
  {
    const dom = build();
    const sent = run(dom);
    const input = open(dom, dom.cell);
    input.value = "고친 글";
    press(input, "Enter", { metaKey: true });
    await tick();
    assert.strictEqual(sent.length, 1, "Cmd+Enter 로 저장이 안 나갔다");
  }

  // 4) Esc 는 **취소**다 — 친 것을 버리고 아무것도 안 보낸다.
  {
    const dom = build();
    const sent = run(dom);
    const input = open(dom, dom.cell);
    input.value = "지울 글\n여러 줄";
    press(input, "Escape");
    await tick();
    assert.strictEqual(sent.length, 0, "Esc 를 눌렀는데 저장이 나갔다");
    assert.strictEqual(dom.cell.textContent, "첫 줄", "Esc 뒤에 원래 글자로 안 돌아왔다");
  }

  // 5) 한글을 **조합하는 중**의 Enter 는 건드리지 않는다 — Ctrl 이 같이 눌려도.
  //    입력기가 글자를 굳히려는 키를 가로채면 만들던 글자째 칸이 닫힌다.
  {
    const dom = build();
    const sent = run(dom);
    const input = open(dom, dom.cell);
    input.value = "안녕";
    press(input, "Enter", { ctrlKey: true, isComposing: true });
    press(input, "Enter", { metaKey: true, keyCode: 229 });
    await tick();
    assert.strictEqual(sent.length, 0, "글자를 조합하는 중의 Enter 로 저장이 나갔다");
  }

  // 6) 머리글은 **한 줄 이름**이라 Enter 가 곧 저장이다.
  {
    const dom = build();
    const sent = run(dom);
    const input = open(dom, dom.head);
    input.value = "딜소개 스크립트";
    const prevented = press(input, "Enter");
    await tick();
    assert.ok(prevented, "머리글에서 Enter 가 줄바꿈으로 들어갔다");
    assert.strictEqual(sent.length, 1, "머리글에서 Enter 로 저장이 안 나갔다");
    assert.strictEqual(sent[0].url, "/api/ref-sheets/7/column");
    assert.deepStrictEqual(sent[0].body, { col: 0, value: "딜소개 스크립트" });
  }

  // 7) 무엇을 누르면 저장되는지 **칸 밑에 적는다** — 엔터가 줄바꿈이 된 것을
  //    모르면 저장하려고 엔터를 치다 줄만 는다. 칸과 머리글의 말이 다르다.
  {
    const dom = build();
    run(dom);
    open(dom, dom.cell);
    const hint = dom.cell.querySelector(".cell-pop-hint");
    assert.ok(hint, "칸 밑에 키 안내가 없다");
    assert.ok(/Enter 줄바꿈/.test(hint.textContent) && /Ctrl\+Enter 저장/.test(hint.textContent)
              && /Esc 취소/.test(hint.textContent), hint.textContent);

    const dom2 = build();
    run(dom2);
    open(dom2, dom2.head);
    const headHint = dom2.head.querySelector(".cell-pop-hint");
    assert.ok(headHint && /^Enter 저장/.test(headHint.textContent),
      "머리글 안내가 Enter 저장이 아니다: " + (headHint && headHint.textContent));
  }

  // 8) **쓰는 만큼 자란다** — 한 줄 높이에 묶이지 않는다. 처음부터 세 줄로
  //    열리고, 글이 늘면 그 키(`scrollHeight`)만큼 커진다.
  {
    const dom = build();
    run(dom);
    const input = open(dom, dom.cell);
    assert.ok(input.rows >= 3, "칸이 한 줄 높이로 열린다: rows=" + input.rows);
    input.scrollHeight = 950;          // 쉰 줄 스크립트를 붙여 넣은 키
    input.fire("input");
    assert.strictEqual(input.style.height, "952px",
      "글이 늘었는데 입력칸이 안 자란다: " + input.style.height);

    // 그림이 없는 자리(키를 모를 때)는 높이를 건드리지 않는다 — `NaNpx` 금지.
    const dom2 = build();
    run(dom2);
    const input2 = open(dom2, dom2.cell);
    assert.ok(!/NaN/.test(String(input2.style.height)), "높이에 NaN 을 적었다");
  }

  console.log("ref_cell_keys_test: 통과");
})().catch(function (e) { console.error(e); process.exit(1); });
