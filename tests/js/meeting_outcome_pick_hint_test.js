// 고르개 안내 글 — `data-choices-only` 칸만 `새로 적어도 됩니다` 를 안 세운다.
// (node tests/js/meeting_outcome_pick_hint_test.js)
//
// 딜 진행 관리 › 미팅 후기 `결과` 칸(#176)은 보기 셋 밖의 말을 서버가 400 으로 거절한다.
// 안내가 `새로 적어도 됩니다` 라면 적었다가 저장이 막힌다. 그 칸에만 붙는 표시
// (`data-choices-only`)가 있으면 `N가지 중에서 고릅니다` 로 서고, 다른 콤보 칸
// (`data-fixed-choices` 만 있는 칸 · 그냥 pick 칸)의 안내는 그대로다.
//
// 값은 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "inline_edit.js"), "utf8");

function hintFor(attrs) {
  D.resetHandlers();
  const cell = D.el("div", Object.assign({ class: "cell", "data-field": "outcome",
                                           "data-type": "pick",
                                           "data-choices": "가 결과,나 결과,다 결과" }, attrs));
  cell.textContent = "나 결과";
  const tr = D.el("tr", { "data-id": "7" }, [D.el("td", {}, [cell])]);
  const table = D.el("table", { id: "review-table", "data-inline-url": "/api/meetings" },
    [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [D.el("div", { class: "table-wrap" }, [table])]);
  const document = D.makeDocument(root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const node = made(tag);
    node.select = function () {};
    return node;
  };
  const win = { innerWidth: 1400, innerHeight: 900,
                addEventListener: function () {}, removeEventListener: function () {} };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout, alert: function () {},
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function () {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "inline_edit.js" });
  cell.fire("keydown", { key: "Enter", preventDefault: function () {} });
  const pop = root.querySelector(".cell-pop");
  assert.ok(pop, "Enter 로 창이 안 열렸다");
  return pop.querySelectorAll(".cell-pop-hint").map((h) => h.textContent).join(" | ");
}

// 1) 미팅 결과 칸 — 보기 밖은 안 받는다
const only = hintFor({ "data-fixed-choices": "", "data-choices-only": "" });
assert.ok(!/새로 적어도/.test(only), "보기 밖을 안 받는 칸에 `새로 적어도` 안내: " + only);
assert.ok(/3가지 중에서 고릅니다/.test(only), only);
assert.ok(/Enter 저장 · Esc 취소/.test(only), only);

// 2) 다른 콤보 칸 안내는 그대로
for (const attrs of [{ "data-fixed-choices": "" }, {}]) {
  const hint = hintFor(attrs);
  assert.ok(/고릅니다\(새로 적어도 됩니다\)/.test(hint),
    "다른 콤보 칸 안내가 바뀌었다(" + JSON.stringify(attrs) + "): " + hint);
}

console.log("meeting_outcome_pick_hint_test: ok");
