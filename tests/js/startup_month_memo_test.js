// 스타트업 표의 **월별 칸은 여러 줄 메모**다. (node tests/js/startup_month_memo_test.js)
//
// 사용자가 정한 것: "o,x 가 아니라 메모처럼 2-3줄의 메모를 남길 수 있게."
// 파이썬 쪽(`tests/test_startup_month_memo.py`)은 화면에 `data-type="long"` 이
// 실리는지까지 본다. **칸을 눌렀을 때 실제로 여러 줄을 칠 수 있는지**는
// `inline_edit.js` 를 돌려야 보인다.
//
// ── 여기서 잠그는 것 ────────────────────────────────────────────────────
//
// 1. 칸을 누르면 **한 줄짜리 입력이 아니라 `<textarea>`** 가 뜬다. 한 줄 입력이
//    뜨면 줄바꿈을 칠 수가 없어 "2-3줄" 이 애초에 불가능하다.
// 2. **고를 거리가 안 뜬다.** 줄마다 다른 글이라 고를 것이 아니다 — 칩이 뜨면
//    옛 `O`/`발송 완료` 가 목록으로 서서 다시 한 낱말짜리 칸이 된다.
// 3. **줄바꿈이 그대로 저장된다.** 어딘가에서 공백으로 펴지면 세 줄로 적은
//    메모가 한 줄로 뭉개진다.
// 4. 값은 **`notes` 묶음으로** 나간다(`data-note`) — 월별 칸은 그 명단에만
//    있는 칸이라 담당자 모델의 칸이 아니다. 묶음이 빠지면 서버가 200 을
//    주면서 아무것도 안 넣는다.
// 5. **이미 들어 있는 옛 값이 그대로 열린다.** `O` 도 `7/24 o` 도 메모 칸에서는
//    그냥 적힌 글이라, 열었을 때 사라지거나 비어 있으면 안 된다.
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

// 운영에 실제로 들어 있던 값들(`O` 71칸 · `7/24 o` 13칸 · `o` 1칸 — 2026-09-21
// 개발 DB 실측). 고르는 칸이던 시절의 값이고, 메모 칸에서는 그냥 글자다.
const OLD = "7/24 o";
// 사람이 새로 적는 메모. **세 줄**이다.
const MEMO = "9/2 문자 발송\n9/5 부재중 — 다시 걸기로\n9/8 통화 완료, 자료 보내기로";

// 월별 칸. 열쇠는 열 id 라 `c` 로 시작한다(`contact_columns.note_key`).
function monthCell(key, text) {
  const div = D.el("div", {
    class: "cell clamp2", "data-field": key, "data-note": "",
    "data-type": "long"
  });
  div.textContent = text || "";
  return div;
}

function build() {
  const send1 = monthCell("c12", "");
  const call1 = monthCell("c13", OLD);
  const plain = D.el("td", { class: "who" });        // 바깥
  const rows = [
    D.el("tr", { "data-id": "11" }, [
      D.el("td", {}, [send1]), D.el("td", {}, [call1]), plain
    ])
  ];
  const table = D.el("table",
    { id: "contacts-table", "data-inline-url": "/api/contacts" },
    [D.el("tbody", {}, rows)]);
  return { root: D.el("div", {}, [table]),
           send1: send1, call1: call1, plain: plain };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1600, innerHeight: 900,
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
  return {
    sent: sent,
    pop: function () { return dom.root.querySelector(".cell-pop"); },
    input: function () {
      return dom.root.querySelector(".cell-pop .cell-pop-input");
    },
    chips: function () {
      const pop = dom.root.querySelector(".cell-pop");
      return pop ? Array.prototype.map.call(
        pop.querySelectorAll(".cell-pop-choice"),
        function (b) { return b.textContent; }) : [];
    },
    press: function (node) { node.fire("pointerdown"); node.fire("click"); }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 여러 줄을 칠 수 있는 칸이 뜬다 ─────────────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.send1);
    assert.ok(t.pop(), "칸을 눌렀는데 편집창이 안 떴다");
    assert.strictEqual(t.input().tag, "textarea",
      "여러 줄 칸이 아니라 한 줄 입력이 떴다 ★ 줄바꿈을 칠 수가 없다");
    // 한 줄짜리 입력에 붙는 표시가 없어야 한다 — 붙으면 CSS 가 높이를 한 줄로
    // 눌러 세 줄을 적어도 한 줄만 보인다.
    assert.ok(!t.input().classList.contains("one-line"),
      "여러 줄 칸에 한 줄 표시(`one-line`)가 붙었다");
  }

  // ── 2. 고를 거리가 안 뜬다 ────────────────────────────────────────────
  //
  // 줄마다 다른 글이라 고를 것이 아니다. 칩이 서면 옛 `O` 가 목록이 되어
  // 다시 한 낱말짜리 칸으로 돌아간다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.send1);
    assert.deepStrictEqual(t.chips(), [],
      "메모 칸에 고를 거리가 떴다 ★ 다시 한 낱말짜리 칸이 된다\n" +
      "  뜬 것 " + JSON.stringify(t.chips()));
  }

  // ── 3. 이미 들어 있는 옛 값이 그대로 열린다 ───────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.call1);
    assert.strictEqual(t.input().value, OLD,
      "옛 값이 편집창에 안 실렸다 ★ 사람은 지워진 줄 알고 다시 적는다");
  }

  // ── 4·5. 줄바꿈이 그대로, `notes` 묶음으로 나간다 ─────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.send1);
    t.input().value = MEMO;
    dom.plain.fire("pointerdown");          // 칸 밖을 누르면 저장이다
    await flush();
    assert.strictEqual(t.sent.length, 1, "적은 메모가 저장되지 않았다");
    assert.strictEqual(t.sent[0].url, "/api/contacts/11");
    assert.deepStrictEqual(t.sent[0].body, { notes: { c12: MEMO } },
      "줄바꿈이 사라졌거나 `notes` 묶음으로 안 나갔다 ★ 세 줄이 한 줄로 뭉개진다");
    assert.strictEqual(dom.send1.textContent, MEMO,
      "적은 메모가 칸에 안 그려졌다");
    // 잘린 글은 마우스를 올려 읽는다 — 표에서는 두 줄까지만 보인다(`.clamp2`).
    assert.strictEqual(dom.send1.title, MEMO,
      "잘린 글을 읽을 길(`title`)이 안 붙었다");
  }

  console.log("startup_month_memo_test: 통과");
}

main().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
