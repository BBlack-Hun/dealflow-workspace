// 엔터로는 추가되지 않는가. (node tests/js/weekly_enter_submit_test.js)
//
// 사용자가 말한 것: "엔터로는 추가가 안되게 해주고, 추가버튼을 눌러야 추가가
// 되게". 세부업무가 여러 줄 칸이 되면서 **그 칸의** 엔터는 줄바꿈이 됐지만,
// 같은 폼의 한 줄 칸(항목)에서 친 엔터는 여전히 폼을 보냈다.
//
// 막는 김에 **막으면 안 되는 것**이 있다 — 여러 줄 칸의 줄바꿈과, 키보드로
// 누르는 [추가] 단추다. 그 둘이 이 검사의 절반이다.
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 파일을 그대로
// 돌린다(weekly_status_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "weekly_tasks.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 반복 업무 등록 폼 한 벌 -------------------------------------------------
function build(guard) {
  const attrs = { method: "post", action: "/todo/routines", class: "rule-form" };
  if (guard) attrs["data-no-enter-submit"] = "";

  const parts = {
    category: D.el("input", { type: "text", name: "category" }),
    title: D.el("textarea", { name: "title", rows: "2" }),
    weekday: D.el("input", { type: "checkbox", name: "weekdays", value: "0" }),
    when: D.el("select", { name: "time_of_day" }),
    add: D.el("button", { type: "submit", class: "secondary-btn" })
  };
  const form = D.el("form", attrs, [
    parts.category, parts.title, parts.weekday, parts.when, parts.add
  ]);
  parts.form = form;
  parts.root = D.el("div", {}, [form]);
  return parts;
}

function run(dom) {
  D.resetHandlers();
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: { location: { reload: function () {} } },
    setTimeout: setTimeout,
    alert: function () {},
    fetch: function () { return Promise.resolve({ ok: true }); }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "weekly_tasks.js" });
}

// 그 키를 쳤을 때 브라우저의 기본 동작(= 폼 보내기)이 막혔는가.
function press(el, key, extra) {
  let stopped = false;
  el.fire("keydown", Object.assign(
    { key: key, preventDefault: function () { stopped = true; } }, extra || {}));
  return stopped;
}

// 1) 한 줄 칸(항목)의 엔터는 막힌다 — 여기서 폼이 나가던 자리다.
{
  const dom = build(true);
  run(dom);
  assert.ok(press(dom.category, "Enter"),
    "항목 칸에서 친 엔터가 그대로 폼을 보냅니다 — 적다 만 규칙이 들어갑니다");
}

// 2) 여러 줄 칸의 엔터는 **막으면 안 된다.** 막으면 줄바꿈을 못 넣는다 —
//    이 고침이 하려던 바로 그것이 없어진다.
{
  const dom = build(true);
  run(dom);
  assert.ok(!press(dom.title, "Enter"),
    "세부업무 칸의 엔터까지 막으면 줄바꿈을 넣을 수가 없습니다");
}

// 3) [추가] 단추 위의 엔터는 **막으면 안 된다.** 키보드만 쓰는 사람은 단추에
//    닿아서 엔터·스페이스로 누른다 — 막으면 그 사람에게는 추가할 길이 없다.
{
  const dom = build(true);
  run(dom);
  assert.ok(!press(dom.add, "Enter"),
    "[추가] 단추의 엔터를 막으면 키보드로는 추가할 수가 없습니다");
  assert.ok(!press(dom.add, " "),
    "단추의 스페이스를 막으면 키보드로는 추가할 수가 없습니다");
}

// 4) 요일 체크상자 — **켜고 끄는 키(스페이스)는 그대로 둔다.** 거기서의
//    엔터는 토글이 아니라 폼 보내기라 막는다: 고르는 조작은 하나도 안 준다.
{
  const dom = build(true);
  run(dom);
  assert.ok(!press(dom.weekday, " "),
    "체크상자의 스페이스를 막으면 키보드로는 요일을 고를 수가 없습니다");
  assert.ok(press(dom.weekday, "Enter"),
    "체크상자 위의 엔터가 폼을 보냅니다 — 요일만 고르고 만 규칙이 들어갑니다");
}

// 5) **한글을 조합하는 중의 엔터는 비켜선다.** 그 엔터는 만들던 글자를 굳히는
//    것이라 입력기가 먹는다. 여기서 가로채면 조합이 깨진다 — 적는 말이 죄다
//    한글이라 그 자리가 곧 일상이다.
{
  const dom = build(true);
  run(dom);
  assert.ok(!press(dom.category, "Enter", { isComposing: true }),
    "조합 중의 엔터까지 가로채면 만들던 글자가 깨집니다");
  assert.ok(!press(dom.category, "Enter", { keyCode: 229 }),
    "옛 브라우저의 조합 중 엔터(keyCode 229)도 같은 자리입니다");
}

// 6) 표시를 안 단 폼은 건드리지 않는다 — 이 화면의 다른 폼(가져오기·삭제)은
//    단추 하나짜리라 엔터로 보내도 될 일이고, 여기서 다 막으면 그것까지 죽는다.
{
  const dom = build(false);
  run(dom);
  assert.ok(!press(dom.category, "Enter"),
    "표시를 안 단 폼까지 막았습니다 — 막을 곳은 폼이 고른다");
}

console.log("weekly_enter_submit_test OK");
