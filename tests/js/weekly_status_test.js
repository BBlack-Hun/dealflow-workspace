// 상태를 못 저장했을 때 칸이 되돌아오는가. (node tests/js/weekly_status_test.js)
//
// 주간 업무의 상태 칸은 고르는 순간 저장한다. 저장이 실패하면 알림만 뜨고
// 칸은 고른 그대로 서 있었다 — 화면에는 `완료`, 서버에는 `예정`. 새로고침
// 전까지는 다 한 줄로 보이고, 알림을 놓친 사람은 그대로 넘어간다.
// 칸 수정(inline_edit.js)은 실패하면 이미 원래 값으로 되돌린다.
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 그대로
// 돌린다** (consulting_contacted_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "weekly_tasks.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 주간 업무 표 한 줄 ------------------------------------------------------
function build() {
  const select = D.el("select", {
    class: "task-status", "data-id": "7", "data-prev": "todo"
  });
  select.value = "todo";

  const tr = D.el("tr", { "data-id": "7" }, [
    D.el("td", { class: "cell", "data-field": "title" }),
    D.el("td", {}, [select])
  ]);
  const table = D.el("table", {
    id: "task-table", "data-inline-url": "/api/todo/tasks"
  }, [D.el("tbody", {}, [tr])]);

  return { root: D.el("div", {}, [table]), table: table, tr: tr, select: select };
}

// --- weekly_tasks.js 를 그대로 돌린다 ----------------------------------------
function run(dom, ok) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const alerts = [];
  const sandbox = {
    document: document,
    window: { location: { reload: function () {} } },
    setTimeout: setTimeout,
    alert: function (m) { alerts.push(m); },
    fetch: function () {
      return ok ? Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
                : Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "weekly_tasks.js" });
  return alerts;
}

function pick(dom, value) {
  dom.select.value = value;
  dom.table.fire("change", { target: dom.select });
  return new Promise(function (r) { setTimeout(r, 0); });
}

(async function () {
  // 1) 저장에 실패하면 고른 값이 되돌아와야 한다.
  {
    const dom = build();
    const alerts = run(dom, false);
    await pick(dom, "done");
    assert.strictEqual(alerts.length, 1, "실패를 알려 주지 않았습니다");
    assert.strictEqual(
      dom.select.value, "todo",
      "저장에 실패했는데 칸은 `완료` 그대로입니다 — 서버에는 `예정` 이 남아 있습니다");
    assert.ok(!dom.tr.classList.contains("task-done"),
      "저장에 실패했는데 줄이 다 한 것처럼 그려졌습니다");
  }

  // 2) 저장되면 그대로 두고, 다음 실패는 그 값으로 되돌아간다.
  {
    const dom = build();
    run(dom, true);
    await pick(dom, "doing");
    assert.strictEqual(dom.select.value, "doing");
    assert.strictEqual(dom.select.getAttribute("data-prev"), "doing",
      "저장된 값을 기억하지 않으면 다음 실패 때 엉뚱한 값으로 되돌아갑니다");
  }

  console.log("weekly_status_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
