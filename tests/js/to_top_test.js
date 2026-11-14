// '맨 위로' 단추가 **두 스크롤을 다 보는가.** (node tests/js/to_top_test.js)
//
// 창만 보는 단추는 넓은 표 상자(`.table-wrap.wide`) 안에서 수백 줄을 내려가도
// 안 뜨고, 눌러도 표는 아래에 그대로 있다. 그리고 올리면서 **가로까지 0 으로
// 돌리면** 1,900px 넘게 밀어 둔 표에서 보던 칸을 잃는다. 아래가 그 셋을 본다.
// 실제 파일(`static/js/to_top.js`)을 `vm` 으로 그대로 돌린다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { el, makeDocument, resetHandlers } = require("./_dom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "to_top.js"), "utf8");

// 화면 하나: 단추 · 넓은 표 상자(둘일 수 있다 — IR 발송) · 따로 구르는 다른 상자.
function run(opts) {
  opts = opts || {};
  resetHandlers();
  const btn = el("button", { id: "to-top", type: "button" });
  btn.hidden = true;
  const wraps = [];
  for (let i = 0; i < (opts.wraps === undefined ? 1 : opts.wraps); i += 1) {
    const w = el("div", { class: "table-wrap wide" });
    w.scrollTop = 0; w.scrollLeft = 0;
    wraps.push(w);
  }
  // 넓지 않은 상자 — 수정창 안쪽처럼 따로 구르는 자리. 단추와 상관없다.
  const other = el("div", { class: "detail-panel" });
  other.scrollTop = 0;
  const root = el("body", {}, (opts.noButton ? [] : [btn]).concat(wraps, [other]));
  const doc = makeDocument(root);

  // 문서에 거는 손이 **잡는 단계**인지 적어 둔다 — `scroll` 은 버블링하지 않아서
  // 그렇지 않으면 브라우저에서는 표 상자 안의 스크롤이 문서에 안 닿는다.
  // (이 DOM 은 편의상 위로 올려 주므로, 그 차이를 여기서 따로 본다.)
  const listened = [];
  const add = doc.addEventListener;
  doc.addEventListener = function (type, fn, capture) {
    listened.push([type, capture]);
    add(type, fn);
  };

  const scrolls = [];
  const win = {
    pageXOffset: opts.x || 0, pageYOffset: opts.y || 0,
    document: doc,
    addEventListener() {},
    scrollTo(x, y) { scrolls.push([x, y]); this.pageXOffset = x; this.pageYOffset = y; },
    requestAnimationFrame(fn) { fn(); },
  };
  const ctx = { window: win, module: { exports: {} }, setTimeout: setTimeout };
  vm.runInNewContext(SRC, ctx, { filename: "to_top.js" });

  return {
    btn, wraps, other, win, scrolls, listened,
    SHOW_AT: ctx.module.exports.SHOW_AT,
    // 창이 구르면 브라우저는 문서에 `scroll` 을 쏜다.
    scrollWindow(y) { win.pageYOffset = y; root.fire("scroll", { target: doc }); },
    scrollBox(box, y) { box.scrollTop = y; box.fire("scroll"); },
  };
}

// ── 1. 문서에서 잡는 단계로 듣는다 ──────────────────────────────────────────
{
  const t = run();
  assert.deepStrictEqual(t.listened, [["scroll", true]],
    "scroll 을 문서의 잡는 단계(capture)로 안 듣는다 — 표 상자 안의 스크롤을 못 듣는다");
  assert.strictEqual(t.btn.hidden, true, "맨 위에서 단추가 떠 있다");
}

// ── 2. 창을 내리면 뜨고, 올리면 숨는다 ─────────────────────────────────────
{
  const t = run();
  t.scrollWindow(t.SHOW_AT);
  assert.strictEqual(t.btn.hidden, true, `${t.SHOW_AT}px 에서 벌써 떴다`);
  t.scrollWindow(t.SHOW_AT + 1);
  assert.strictEqual(t.btn.hidden, false, "창을 내렸는데 단추가 안 떴다");
  t.scrollWindow(0);
  assert.strictEqual(t.btn.hidden, true, "맨 위로 돌아왔는데 단추가 남아 있다");
}

// ── 3. 표 상자 안에서 내려도 뜬다 — 창은 맨 위 그대로 ────────────────────────
{
  const t = run();
  t.scrollBox(t.wraps[0], 800);
  assert.strictEqual(t.win.pageYOffset, 0);
  assert.strictEqual(t.btn.hidden, false, "표 상자 안에서 내려갔는데 단추가 안 떴다");
  t.scrollBox(t.wraps[0], 0);
  assert.strictEqual(t.btn.hidden, true, "표 상자를 올렸는데 단추가 남아 있다");
}

// ── 4. 넓은 표가 아닌 상자는 상관없다 ───────────────────────────────────────
{
  const t = run();
  t.scrollBox(t.other, 900);
  assert.strictEqual(t.btn.hidden, true, "수정창 같은 다른 상자가 굴렀는데 단추가 떴다");
}

// ── 5. 누르면 창과 표 상자가 **세로만** 맨 위로 간다 ─────────────────────────
{
  const t = run({ x: 40 });
  t.wraps[0].scrollLeft = 1500;
  t.scrollBox(t.wraps[0], 800);
  t.scrollWindow(1200);
  t.other.scrollTop = 500;
  assert.strictEqual(t.btn.hidden, false);

  t.btn.fire("click");
  assert.strictEqual(t.wraps[0].scrollTop, 0, "표 상자가 안 올라갔다");
  assert.strictEqual(t.wraps[0].scrollLeft, 1500, "표 상자의 가로 자리가 돌아갔다 — 보던 칸을 잃는다");
  assert.deepStrictEqual(t.scrolls, [[40, 0]], "창을 올리면서 가로 자리를 바꿨다");
  assert.strictEqual(t.win.pageXOffset, 40);
  assert.strictEqual(t.win.pageYOffset, 0, "창이 안 올라갔다");
  assert.strictEqual(t.other.scrollTop, 500, "넓은 표가 아닌 상자까지 올렸다");
  assert.strictEqual(t.btn.hidden, true, "맨 위로 갔는데 단추가 남아 있다");
}

// ── 6. 표 상자가 여럿이면(IR 발송) 어느 것이 내려가도 뜨고, 다 올린다 ─────────
{
  const t = run({ wraps: 2 });
  t.scrollBox(t.wraps[1], 600);
  assert.strictEqual(t.btn.hidden, false, "두 번째 표 상자가 내려갔는데 안 떴다");
  t.wraps[0].scrollTop = 400;
  t.btn.fire("click");
  assert.deepStrictEqual(t.wraps.map((w) => w.scrollTop), [0, 0], "표 상자 하나가 아래에 남았다");
}

// ── 7. 굴리기만 해서는 자리를 **안 쓴다** ───────────────────────────────────
// 다시 그린 뒤 `contacts.js`(restoreScroll) 가 표의 가로·세로 자리와 창 자리를
// 되살린다. 그 직후 오는 `scroll` 에서 단추가 자리를 건드리면 되살린 것이 망가진다.
{
  const t = run();
  const wrap = t.wraps[0];
  wrap.scrollLeft = 1320; wrap.scrollTop = 2400;   // 되살린 자리
  t.win.scrollTo(0, 150);
  t.scrolls.length = 0;
  t.scrollBox(wrap, 2400);
  t.scrollWindow(150);
  assert.deepStrictEqual([wrap.scrollLeft, wrap.scrollTop], [1320, 2400],
    "굴리는 동안 단추가 표 자리를 바꿨다");
  assert.deepStrictEqual(t.scrolls, [], "굴리는 동안 단추가 창을 움직였다");
  assert.strictEqual(t.btn.hidden, false, "되살린 자리가 아래인데 단추가 안 떴다");
}

// ── 8. 자리를 되살린 채 열린 화면은 처음부터 단추가 서 있다 ──────────────────
{
  const t = run({ y: 900 });
  assert.strictEqual(t.btn.hidden, false, "내려간 채 열린 화면에서 단추가 숨어 있다");
}

// ── 9. 단추가 없는 화면에서도 죽지 않는다 ──────────────────────────────────
{
  const t = run({ noButton: true });
  assert.deepStrictEqual(t.listened, [], "단추가 없는데 스크롤을 듣는다");
}

console.log("to_top_test 통과");
