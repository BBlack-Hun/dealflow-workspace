// IR 기업 연결 — 브라우저 쪽 둘.
// (node tests/js/ir_link_test.js)
//
// 지킬 것:
//  1. [연결 해제] 는 묻고, 아니라고 하면 폼을 안 보낸다.
//  2. 일괄 연결 확인 화면에서 체크를 풀면 **단추의 수**가 따라간다. 다 풀면
//     단추가 꺼지고 폼을 안 보낸다.
//  3. 수정창 표시는 서버가 준 값을 그대로 옮긴다 — 연결됨이면 기업 이름,
//     아니면 `연결 안 됨 → 연결하기`. 새 줄(값 없음)이면 숨는다.
//
// 아이디·클래스가 실제 화면과 같은지는 파이썬 쪽이 본다(`tests/test_ir_link.py`).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

const JS = path.join(__dirname, "..", "..", "app", "static", "js");

function run(file, root, answer) {
  dom_.resetHandlers();
  const document = dom_.makeDocument(root);
  const asked = [];
  const win = { confirm: function (t) { asked.push(t); return answer !== false; } };
  const ctx = { document: document, window: win, console: console, String: String };
  win.document = document;
  vm.runInNewContext(fs.readFileSync(path.join(JS, file), "utf8"), ctx, { filename: file });
  return { document: document, window: win, asked: asked };
}

function submit(form) {
  let prevented = false;
  form.fire("submit", { preventDefault: function () { prevented = true; } });
  return prevented;
}

// ── 1. [연결 해제] ─────────────────────────────────────────────────────────
(function () {
  function page(answer) {
    const btn = el("button", { class: "linkbtn ir-unlink-btn", "data-name": "가나다랩스",
                               "data-company": "(주)가나다랩스" });
    const form = el("form", { class: "inline-form ir-unlink-form" }, [btn]);
    const root = el("div", {}, [form]);
    return { env: run("ir_link.js", root, answer), form: form };
  }
  let p = page(false);
  assert.strictEqual(submit(p.form), true, "아니라고 했는데 풀었다");
  assert.ok(/가나다랩스/.test(p.env.asked[0]) && /\(주\)가나다랩스/.test(p.env.asked[0]),
            "무엇을 푸는지 묻지 않았다");
  p = page(true);
  assert.strictEqual(submit(p.form), false, "예라고 했는데 막았다");
})();

// ── 2. 일괄 연결 확인 화면 ─────────────────────────────────────────────────
(function () {
  const boxes = [1, 2, 3].map(function (i) {
    const b = el("input", { type: "checkbox", class: "ir-bulk-pick", name: "pair",
                            value: i + ":9" + i });
    b.checked = true;
    return b;
  });
  const label = el("span", { class: "ir-bulk-label" });
  const go = el("button", { id: "ir-link-bulk-go" }, [label]);
  const n = el("span", { id: "ir-link-bulk-n" });
  const form = el("form", { id: "ir-link-bulk-form" }, boxes.concat([n, go]));
  const root = el("div", {}, [form]);
  const env = run("ir_link.js", root);
  assert.strictEqual(n.textContent, "3");
  assert.strictEqual(label.textContent, "3줄 연결");

  boxes[0].checked = false;
  boxes[0].fire("change");
  assert.strictEqual(n.textContent, "2", "체크를 풀었는데 수가 그대로다");
  assert.strictEqual(label.textContent, "2줄 연결");
  assert.strictEqual(submit(form), false);
  assert.strictEqual(env.asked.length, 0, "확인 화면에서 한 번 더 묻지 않는다");

  boxes.forEach(function (b) { b.checked = false; b.fire("change"); });
  assert.strictEqual(go.disabled, true, "다 풀었는데 단추가 살아 있다");
  assert.strictEqual(submit(form), true, "고른 줄이 없는데 보냈다");
})();

// ── 3. 수정창 표시 ──────────────────────────────────────────────────────────
(function () {
  const box = el("p", { id: "ir-link-badge" });
  box.hidden = true;
  const root = el("div", {}, [box]);
  const env = run("ir_link_badge.js", root);
  const badge = env.window.IrLinkBadge;

  badge.show({ linked: true, name: "(주)가나다랩스", company_href: "/companies?q=x",
               link_href: "/ir-link?tab=startup&row=5" });
  assert.strictEqual(box.hidden, false);
  assert.ok(/\(주\)가나다랩스/.test(box.innerHTML) && /연결됨/.test(box.innerHTML));
  assert.ok(/\/ir-link\?tab=startup&amp;row=5/.test(box.innerHTML), "바꾸는 길이 없다");

  badge.show({ linked: false, candidates: 1, link_href: "/ir-link?tab=startup&row=6" });
  assert.ok(/연결 안 됨/.test(box.innerHTML) && /연결하기/.test(box.innerHTML));
  assert.ok(/1곳/.test(box.innerHTML), "후보 수를 안 적었다");

  // 이름에 든 꺾쇠는 글자로 남는다.
  badge.show({ linked: true, name: "<b>가짜</b>", company_href: "/c", link_href: "/l" });
  assert.ok(!/<b>가짜<\/b>/.test(box.innerHTML) && /&lt;b&gt;/.test(box.innerHTML));

  badge.show(null);
  assert.strictEqual(box.hidden, true, "새 줄에서 표시가 남았다");
})();

console.log("ir_link ok");
