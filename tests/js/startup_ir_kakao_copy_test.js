// IR 요청 투자사 **카톡 문구**를 복사할 수 있는가.
// (node tests/js/startup_ir_kakao_copy_test.js)
//
// 이 화면은 보내 주지 않는다 — 스타트업 카톡방이 아직 자료에 없어서, 사람이
// 문구를 집어 대표님 방에 손으로 붙인다. 그러니 **집어가는 것이 되는지**가
// 이 화면의 전부다.
//
// 지킬 것은 셋이다.
//
//  1. 담기는 것이 **글 전문 그대로**여야 한다. 옆의 안내("N통으로 나갑니다",
//     못 맞춘 건수)가 섞이면 그것까지 대표님 카톡방에 붙는다.
//  2. 눌렀다는 것이 **보여야** 한다. `navigator.clipboard` 는 https·localhost
//     가 아니면 아예 없어서, 아무 일도 안 나면 빈 것을 붙여 넣게 된다.
//  3. 복사를 **제 손으로 짜지 않는다** — 공용 한 벌(`ir_attach_list.js`)이
//     한다. 그래서 이 검사는 두 파일을 화면 차례대로 돌린다.
//
// 아이디가 실제로 그려진 화면과 같은지는 파이썬 쪽이 본다
// (`tests/test_startup_ir_kakao.py`).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

// 가상의 기업·투자사다. 투자사는 **이미 가려진 값**으로만 화면에 온다.
const TEXT = [
  "안녕하세요 대표님",
  "7월 말까지 샘플에이",
  "IR 자료 요청한투자사 리스트 입니다 미팅요청 투자사가 나오면 연락을 드릴예정 입니다.",
  "",
  "5/22 샘플에이 가***",
  "6/17 샘플에이 마***"
].join("\n");

function resolved(v) {
  return { then: function (ok) { if (ok) ok(v); return this; } };
}

function build(opts) {
  opts = opts || {};
  dom_.resetHandlers();
  const ta = el("textarea", { class: "bubble-edit", id: "ir-kakao-message" });
  ta.value = TEXT;
  const btn = el("button", { type: "button", class: "linkbtn", id: "ir-kakao-copy" });
  btn.textContent = "문구 복사";
  const root = el("div", { class: "layout" }, [
    // 옆에 선 안내들. **이것이 복사에 섞이면 안 된다.**
    el("p", { class: "split-notice" }),
    ta,
    el("div", { class: "charcount" }),
    btn,
    el("p", { class: "warn-box" })
  ]);
  root.querySelector(".split-notice").textContent = "2통으로 나눠 보내야 합니다";
  root.querySelector(".warn-box").textContent = "3건은 어느 기업 몫인지 몰라";

  const document = dom_.makeDocument(root);
  const win = { location: { search: "", href: "" } };
  const ctx = {
    document: document, console: console, window: win,
    // 기본은 **클립보드가 없는 쪽**이다 — 사내에서 http 로 여는 화면이 그렇다.
    navigator: opts.navigator || {},
    setTimeout: function () { return 0; },
    clearTimeout: function () {}
  };
  win.document = document;
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  // 화면과 **같은 차례**로 돌린다(공용 한 벌이 먼저).
  ["ir_attach_list.js", "startup_ir_kakao.js"].forEach(function (name) {
    vm.runInNewContext(fs.readFileSync(path.join(JS, name), "utf8"), ctx,
                       { filename: name });
  });
  return { document: document, ta: ta, btn: btn, window: win };
}

// ── 1. 담기는 것이 글 전문 그대로다 ─────────────────────────────────────────
(function () {
  const box = [];
  const dom = build({
    navigator: { clipboard: { writeText: function (t) { box.push(t); return resolved(); } } }
  });
  dom.btn.fire("click");
  assert.deepStrictEqual(box, [TEXT],
    "복사된 것이 글 전문이 아니다");
  assert.ok(box[0].indexOf("통으로 나눠") < 0, "옆의 안내가 같이 복사됐다");
  assert.ok(box[0].indexOf("어느 기업 몫인지") < 0, "옆의 안내가 같이 복사됐다");
  assert.ok(/복사했/.test(dom.btn.textContent),
    "눌렀는데 아무 말이 없다: " + dom.btn.textContent);
}());

// ── 2. 클립보드가 없는 브라우저(http)에서도 길을 알려 준다 ──────────────────
(function () {
  const dom = build();   // navigator.clipboard 없음
  dom.btn.fire("click");
  assert.ok(/Ctrl/.test(dom.btn.textContent),
    "클립보드가 없는데 아무 말이 없다: " + dom.btn.textContent);
}());

// ── 3. 문구가 없는 달에는 조용히 만다 ───────────────────────────────────────
(function () {
  dom_.resetHandlers();
  const root = el("div", { class: "layout" });
  const ctx = {
    document: dom_.makeDocument(root), console: console,
    window: { location: { search: "", href: "" } },
    navigator: {}, setTimeout: function () { return 0; }, clearTimeout: function () {}
  };
  ctx.window.document = ctx.document;
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  ["ir_attach_list.js", "startup_ir_kakao.js"].forEach(function (name) {
    vm.runInNewContext(fs.readFileSync(path.join(JS, name), "utf8"), ctx,
                       { filename: name });
  });   // 터지지 않으면 통과다
}());

console.log("ok — 카톡 문구를 글 전문 그대로 집어갈 수 있다");
