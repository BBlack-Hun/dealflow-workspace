// 참고 표의 **머리글**을 눌러 고치는 길. (node tests/js/ref_head_edit_test.js)
//
// 표를 화면에서 세울 수 있게 되면서 머리글이 `칸 1 · 칸 2 …` 로 선다. 표는
// 세울 수 있는데 그 칸을 뭐라 부르는지 정할 길이 없으면 이름 없는 표가 그대로
// 굳는다.
//
// 여기서 지키는 것은 **칸과 같은 길인가**다. 한 표 안에서 머리글과 칸을 고치는
// 법이 다르면 쓰는 사람이 헷갈리고, 나중에 한쪽만 고쳐진다 — 그래서 규칙을
// 옮겨 적지 않고 `ref_edit.js` 를 **그대로 돌린다**(weekly_status_test.js 와
// 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "ref_edit.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 참고 표 하나 (머리글 2칸 · 줄 1개) --------------------------------------
function build() {
  const heads = [0, 1].map(function (i) {
    const th = D.el("th", { class: "ref-cell ref-head", "data-col": String(i) });
    th.textContent = "칸 " + (i + 1);
    return th;
  });
  const cell = D.el("td", { class: "ref-cell", "data-row": "0", "data-col": "0" });
  cell.textContent = "적어 둔 것";

  const table = D.el("table", { id: "ref-table", "data-ref-id": "3" }, [
    D.el("thead", {}, [D.el("tr", {}, heads)]),
    D.el("tbody", {}, [D.el("tr", {}, [cell])])
  ]);
  return { root: D.el("div", {}, [table]), table: table,
           heads: heads, cell: cell };
}

// --- ref_edit.js 를 그대로 돌린다 ---------------------------------------------
function run(dom, reply) {
  D.resetHandlers();
  const sent = [];
  const alerts = [];
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: {},
    alert: function (m) { alerts.push(m); },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse(opts.body), method: opts.method });
      return Promise.resolve(reply || { ok: true, json: () => Promise.resolve({ ok: true }) });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "ref_edit.js" });
  return { sent: sent, alerts: alerts };
}

// 눌러서 고치고 빠져나온다 — 화면에서 하는 그대로다.
function edit(dom, cell, typed) {
  dom.table.fire("click", { target: cell });
  const input = cell.querySelector(".cell-input");
  assert.ok(input, "눌렀는데 고칠 칸이 안 떴다");
  input.value = typed;
  input.fire("blur");
  return new Promise(function (r) { setTimeout(r, 0); });
}

(async function () {
  // 1) 머리글을 눌러 고치면 머리글 자리로 저장한다.
  {
    const dom = build();
    const out = run(dom);
    await edit(dom, dom.heads[1], "투자대상");

    assert.strictEqual(out.sent.length, 1, "머리글을 눌렀는데 아무 데도 안 보냈다");
    assert.strictEqual(out.sent[0].url, "/api/ref-sheets/3/column");
    assert.strictEqual(out.sent[0].method, "PATCH");
    assert.deepStrictEqual(out.sent[0].body, { col: 1, value: "투자대상" });
    // 머리글에는 줄이 없다 — 줄 번호를 실어 보내면 칸을 가리키게 된다.
    assert.ok(!("row" in out.sent[0].body), "머리글에 줄 번호가 실렸다");
    assert.strictEqual(dom.heads[1].textContent, "투자대상");
  }

  // 2) 칸은 **하나도 안 달라졌다** — 같은 손잡이를 지난다.
  {
    const dom = build();
    const out = run(dom);
    await edit(dom, dom.cell, "고쳐 적음");

    assert.strictEqual(out.sent[0].url, "/api/ref-sheets/3/cell");
    assert.deepStrictEqual(out.sent[0].body, { row: 0, col: 0, value: "고쳐 적음" });
  }

  // 3) 안 바꾸고 빠져나오면 아무것도 안 보낸다(칸과 같다).
  {
    const dom = build();
    const out = run(dom);
    await edit(dom, dom.heads[0], "칸 1");
    assert.strictEqual(out.sent.length, 0, "고치지도 않았는데 저장을 불렀다");
  }

  // 4) 저장이 **조용히 삼켜지지 않는다** — 되돌리고, 왜 안 됐는지 말한다.
  //    빈 머리글을 물리는 것이 이 길로 온다(서버의 400 + 이유).
  {
    const dom = build();
    const out = run(dom, {
      ok: false,
      json: () => Promise.resolve({ detail: "머리글 이름을 적어 주세요" })
    });
    await edit(dom, dom.heads[0], "");

    assert.strictEqual(dom.heads[0].textContent, "칸 1",
                       "저장에 실패했는데 화면에는 고친 것으로 남았다");
    assert.strictEqual(out.alerts.length, 1, "실패를 알려 주지 않았다");
    assert.ok(out.alerts[0].indexOf("머리글 이름을 적어 주세요") >= 0,
              "왜 안 됐는지 안 말한다: " + out.alerts[0]);
  }

  // 5) 연결이 끊겨 대답조차 없을 때도 되돌리고 알린다.
  {
    const dom = build();
    D.resetHandlers();
    const alerts = [];
    const sandbox = {
      document: D.makeDocument(dom.root),
      window: {},
      alert: function (m) { alerts.push(m); },
      fetch: function () { return Promise.reject(new Error("끊김")); }
    };
    vm.createContext(sandbox);
    vm.runInContext(src, sandbox, { filename: "ref_edit.js" });

    await edit(dom, dom.heads[0], "새 이름");
    assert.strictEqual(dom.heads[0].textContent, "칸 1", "끊겼는데 고친 것으로 남았다");
    assert.strictEqual(alerts.length, 1, "끊긴 것을 안 알려 준다");
  }

  // 6) 머리글과 칸이 **한 손잡이**를 지나는가 — 파일 자체를 본다.
  //    둘로 갈라 두면 한쪽만 고쳐지는 날 화면에서만 어긋난다.
  {
    assert.strictEqual((src.match(/addEventListener\("click"/g) || []).length, 1,
                       "머리글과 칸이 서로 다른 손잡이를 쓴다");
    assert.ok(/closest\("\.ref-cell"\)/.test(src),
              "머리글이 칸과 같은 선택자로 안 잡힌다");
    assert.ok(/classList\.contains\("ref-head"\)/.test(src),
              "어디에 저장할지 가리는 표시가 없다");
  }

  console.log("ref_head_edit_test: 통과");
})();
