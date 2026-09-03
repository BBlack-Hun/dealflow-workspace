"use strict";
/* [전체 자동조합] 패널 — 파이썬으로는 잴 수 없는 자리만 여기서 잰다.
 *
 *   · 전체 선택이 목록 전체를 집는가 · 고른 수가 맞는가
 *   · 적용 뒤 **표의 그 칸**이 그 자리에서 되칠해지는가 (title 까지)
 *   · 되돌린 뒤 표가 원래 글자로 돌아오는가
 *   · 다시 그릴 때 줄이 **쌓이지 않는가**
 *   · 서버에 보내는 것이 **고른 id 뿐**인가
 *
 * 규칙을 다시 구현하지 않는다 — 진짜 `one_liner_bulk.js` 를 vm 으로 돌린다.
 * 기업명은 전부 지어낸 것이다(공개 저장소).
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const src = fs.readFileSync(path.join(SRC, "one_liner_bulk.js"), "utf8");

const STATE = {
  rows: [
    { id: 11, name: "가나테크", current: "사람이 다듬어 쓴 소개",
      suggestion: "산업용 센서 제조 | 매출 8.9억", filled: true },
    { id: 12, name: "나다물류", current: "", filled: false,
      suggestion: "물류 최적화 | 매출 23년 2억, 24년 4억" }
  ],
  counts: { changes: 2, filled: 1, empty: 1, unchanged: 1, no_source: 1, total: 4 },
  undo: { batch: null, count: 0, at: "" }
};

function build() {
  // 화면의 뼈대 — companies.html 의 `#ol-bulk` 와 표의 한 줄.
  const cell = D.el("div", { class: "cell", "data-field": "one_liner" });
  cell.textContent = "사람이 다듬어 쓴 소개";
  const td = D.el("td", { title: "사람이 다듬어 쓴 소개" }, [cell]);
  const tr = D.el("tr", { "data-id": "11" }, [td]);

  const root = D.el("div", {}, [
    D.el("button", { id: "ol-bulk-btn" }),
    D.el("section", { id: "ol-bulk" }, [
      D.el("button", { id: "ol-bulk-close" }),
      D.el("p", { id: "ol-summary" }),
      D.el("input", { id: "ol-pick-all", type: "checkbox" }),
      D.el("span", { id: "ol-count" }),
      D.el("button", { id: "ol-apply" }),
      D.el("button", { id: "ol-undo" }),
      D.el("span", { id: "ol-undo-note" }),
      D.el("div", { id: "ol-list" })
    ]),
    D.el("table", {}, [tr])
  ]);
  root.querySelector("#ol-bulk").hidden = true;
  root.querySelector("#ol-undo").hidden = true;
  return { root, cell, td };
}

function run(replies) {
  D.resetHandlers();
  const dom = build();
  const calls = [];
  let alerted = [];
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: {},
    alert(m) { alerted.push(String(m)); },
    confirm() { return true; },
    Number: Number, Array: Array, String: String, JSON: JSON,
    fetch(url, opts) {
      const body = opts && opts.body ? JSON.parse(opts.body) : null;
      calls.push({ url: url, method: (opts && opts.method) || "GET", body: body });
      const next = replies.shift();
      return Promise.resolve({
        ok: next.ok !== false,
        json() { return Promise.resolve(next.d); }
      });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "one_liner_bulk.js" });
  return { dom, calls, alerted: () => alerted, doc: sandbox.document };
}

const tick = () => new Promise((r) => setImmediate(r));

(async function () {
  // --- 열면 불러오고 목록을 그린다 ------------------------------------------
  {
    const t = run([{ d: STATE }]);
    t.dom.root.querySelector("#ol-bulk-btn").fire("click");
    await tick();

    assert.strictEqual(t.calls[0].url, "/api/one-liner/bulk");
    const boxes = t.dom.root.querySelectorAll(".ol-cb");
    assert.strictEqual(boxes.length, 2, "바뀔 곳 2줄이 그려져야 한다");

    const summary = t.dom.root.querySelector("#ol-summary").textContent;
    assert.ok(summary.indexOf("4곳 중 바뀔 곳 2곳") >= 0,
      "왜 4곳인데 2줄뿐인지 적어야 한다: " + summary);
    assert.ok(summary.indexOf("재료가 없어 만들 수 없는 곳 1") >= 0, summary);

    // 빈 칸은 빈 칸이라고 보여야 한다 — 아무것도 없으면 안 바뀌는 줄로 읽힌다.
    const nows = t.dom.root.querySelectorAll(".ol-now");
    assert.strictEqual(nows[1].textContent, "(비어 있음)");

    // 아직 아무것도 안 골랐으면 [적용] 은 못 누른다.
    assert.strictEqual(t.dom.root.querySelector("#ol-apply").disabled, true);
    assert.strictEqual(t.dom.root.querySelector("#ol-count").textContent, "0곳 선택");
    console.log("  · 목록 · 요약 · 빈 칸 표시 OK");
  }

  // --- 전체 선택 -------------------------------------------------------------
  {
    const t = run([{ d: STATE }]);
    t.dom.root.querySelector("#ol-bulk-btn").fire("click");
    await tick();

    const all = t.dom.root.querySelector("#ol-pick-all");
    all.checked = true;
    all.fire("change");
    assert.strictEqual(t.dom.root.querySelector("#ol-count").textContent, "2곳 선택");
    assert.strictEqual(t.dom.root.querySelector("#ol-apply").disabled, false);

    all.checked = false;
    all.fire("change");
    assert.strictEqual(t.dom.root.querySelector("#ol-count").textContent, "0곳 선택");
    assert.strictEqual(t.dom.root.querySelector("#ol-apply").disabled, true,
      "하나도 안 고른 채로 누를 수 있으면 안 된다");
    console.log("  · 전체 선택/해제 OK");
  }

  // --- 고른 것만 보낸다 + 표를 되칠한다 --------------------------------------
  {
    const applied = JSON.parse(JSON.stringify(STATE));
    applied.rows = [];
    applied.counts = { changes: 0, filled: 0, empty: 0, unchanged: 3, no_source: 1, total: 4 };
    applied.undo = { batch: 1, count: 1, at: "2026-09-03T09:00:00+09:00" };

    const t = run([{ d: STATE }, { d: Object.assign({ applied: 1, skipped: 0 }, applied) }]);
    t.dom.root.querySelector("#ol-bulk-btn").fire("click");
    await tick();

    // 첫 줄만 고른다.
    const boxes = t.dom.root.querySelectorAll(".ol-cb");
    boxes[0].checked = true;
    boxes[0].fire("change");
    assert.strictEqual(t.dom.root.querySelector("#ol-count").textContent, "1곳 선택");

    t.dom.root.querySelector("#ol-apply").fire("click");
    await tick(); await tick();

    const post = t.calls[1];
    assert.strictEqual(post.method, "POST");
    assert.deepStrictEqual(post.body, { company_ids: [11] },
      "고르지 않은 줄까지 보내면 안 된다");

    // 표의 칸이 그 자리에서 바뀐다 — 새로고침 없이.
    assert.strictEqual(t.dom.cell.textContent, "산업용 센서 제조 | 매출 8.9억");
    assert.strictEqual(t.dom.td.getAttribute("title"), "산업용 센서 제조 | 매출 8.9억",
      "잘려 보이는 칸이라 title 도 같이 안 고치면 옛 문장이 뜬다");

    // 다시 그린 목록에 줄이 쌓이지 않는다.
    assert.strictEqual(t.dom.root.querySelectorAll(".ol-cb").length, 0);
    // 이제 되돌릴 것이 있다.
    assert.strictEqual(t.dom.root.querySelector("#ol-undo").hidden, false);
    assert.ok(t.dom.root.querySelector("#ol-undo-note").textContent.indexOf("1곳") >= 0);
    console.log("  · 고른 것만 전송 · 표 되칠 · 되돌리기 단추 등장 OK");
  }

  // --- 되돌리면 표가 원래 글자로 돌아온다 ------------------------------------
  {
    const applied = Object.assign({}, STATE, {
      rows: [], counts: { changes: 0, filled: 0, empty: 0, unchanged: 3, no_source: 1, total: 4 },
      undo: { batch: 1, count: 1, at: "" }, applied: 1, skipped: 0
    });
    const undone = Object.assign({}, STATE, {
      restored: 1, kept: 1,
      restored_rows: [{ id: 11, one_liner: "사람이 다듬어 쓴 소개" }]
    });

    const t = run([{ d: STATE }, { d: applied }, { d: undone }]);
    t.dom.root.querySelector("#ol-bulk-btn").fire("click");
    await tick();
    const boxes = t.dom.root.querySelectorAll(".ol-cb");
    boxes[0].checked = true; boxes[0].fire("change");
    t.dom.root.querySelector("#ol-apply").fire("click");
    await tick(); await tick();
    assert.strictEqual(t.dom.cell.textContent, "산업용 센서 제조 | 매출 8.9억");

    t.dom.root.querySelector("#ol-undo").fire("click");
    await tick(); await tick();

    assert.strictEqual(t.calls[2].url, "/api/one-liner/bulk/undo");
    assert.strictEqual(t.dom.cell.textContent, "사람이 다듬어 쓴 소개",
      "되돌렸는데 표는 바뀐 채로 남아 있다");
    assert.strictEqual(t.dom.td.getAttribute("title"), "사람이 다듬어 쓴 소개");

    // 되돌리지 **않은** 줄이 있으면 반드시 말한다.
    const said = t.alerted().join("\n");
    assert.ok(said.indexOf("1곳을 되돌렸습니다") >= 0, said);
    assert.ok(said.indexOf("1곳은 그 뒤에 손으로 고쳐서 그대로 두었습니다") >= 0,
      "조용히 넘어가면 '되돌렸다' 는 말과 화면이 어긋난다: " + said);
    console.log("  · 되돌리기 · 표 복구 · 안 되돌린 줄 알림 OK");
  }

  // --- 서버가 거절하면 알리고 다시 누를 수 있어야 한다 -----------------------
  {
    const t = run([{ d: STATE }, { ok: false, d: { detail: "그 사이 값이 바뀌었습니다" } }]);
    t.dom.root.querySelector("#ol-bulk-btn").fire("click");
    await tick();
    const boxes = t.dom.root.querySelectorAll(".ol-cb");
    boxes[0].checked = true; boxes[0].fire("change");
    t.dom.root.querySelector("#ol-apply").fire("click");
    await tick(); await tick();

    assert.ok(t.alerted().join("").indexOf("그 사이 값이 바뀌었습니다") >= 0,
      "서버가 왜 거절했는지 그대로 보여야 한다");
    assert.strictEqual(t.dom.root.querySelector("#ol-apply").disabled, false,
      "실패한 뒤 단추가 잠긴 채면 다시 시도할 길이 없다");
    assert.strictEqual(t.dom.cell.textContent, "사람이 다듬어 쓴 소개",
      "거절당했는데 표를 미리 칠하면 안 된다");
    console.log("  · 거절 처리 OK");
  }

  console.log("one_liner_bulk 통과");
})().catch(function (e) { console.error(e); process.exit(1); });
