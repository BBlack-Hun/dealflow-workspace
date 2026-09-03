// [수정] 창의 `합치기 전 값` — 읽기 전용인가 · 다시 열어도 줄이 쌓이지 않는가.
// (node tests/js/company_desc_backup_test.js)
//
// `사업분야`(스타트업DB)와 `기업 한줄 소개`(IR 기업 현황)를 한 칸으로 합치면서,
// 합치기 전 두 값을 백업해 두었다(0051). 그 값을 보여 주는 자리가 이 상자다.
//
// 파이썬으로는 잴 수 없는 자리가 셋이다.
//
//   1. **저장 요청에 안 실린다.** 백업 글자가 `collect()` 에 섞이면, 되살리려고
//      열어 본 것만으로 저장 때 덮어쓴다 — 되살릴 것을 지우는 화면이 된다.
//   2. **다시 그릴 때 비운다.** 패널 하나를 321개 기업이 돌려 쓴다. 안 비우면
//      두 번째로 연 기업의 상자에 앞 기업의 줄이 그대로 남아, **다른 회사의
//      옛 설명**을 이 회사 것으로 읽게 된다.
//   3. **없으면 통째로 숨는다.** 빈 상자가 늘 떠 있으면 무슨 뜻인지 매번
//      다시 읽어야 한다.
//
// 규칙을 옮겨 적지 않고 companies.js 를 그대로 돌린다
// (company_contract_received_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const src = fs.readFileSync(path.join(SRC, "companies.js"), "utf8");

// 서버가 실제로 주는 모양 그대로(`routers/companies.py` 의 `desc_backup_lines`).
const 가나 = {
  id: 1, name: "샘플가나헬스", one_liner: "사람이 다듬어 쓴 소개",
  introducible: true,
  desc_backup: [
    { label: "사업분야 (스타트업DB)", value: "시트에 적혀 있던 사업 설명" },
    { label: "기업 한줄 소개 (IR 기업 현황)", value: "사람이 다듬어 쓴 소개" }
  ]
};
const 나다 = {
  id: 2, name: "샘플나다물류", one_liner: "소개만 있는 기업",
  introducible: false, blocked_reason: "IR 자료 없음",
  desc_backup: []                       // 합치기 전에도 두 칸이 다 비어 있었다
};

// --- 템플릿의 [수정] 패널과 같은 뼈대만 세운다 -------------------------------
function build() {
  function editBtn(id) {
    const b = D.el("button", { class: "linkbtn js-co-edit" });
    return D.el("tr", { "data-id": String(id), "data-search": "" },
                [D.el("td", { class: "rowno muted" }), D.el("td", {}, [b])]);
  }
  const rows = [editBtn(1), editBtn(2)];
  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
                     [D.el("tbody", {}, rows)]);

  // [기업 추가] 는 이 칸에 커서를 놓는다. 이 DOM 에는 초점이라는 것이 없고,
  // 있는 척해도 볼 것이 없다 — 이 검사에서만 조용히 받아 준다.
  const nameInput = D.el("input", { id: "f-name" });
  nameInput.focus = function () {};

  const box = D.el("div", { id: "f-desc_backup", class: "backup-box" });
  const wrap = D.el("div", { id: "f-desc_backup-box", class: "field wide" }, [box]);
  wrap.hidden = true;

  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "co-search" }),
    D.el("p", { id: "co-note" }),
    D.el("p", { id: "co-status" }),
    D.el("aside", { id: "co-panel" }),
    D.el("div", { id: "co-backdrop" }),
    D.el("h2", { id: "co-title" }),
    D.el("button", { id: "co-add" }),
    D.el("button", { id: "co-close" }),
    D.el("button", { id: "co-cancel" }),
    D.el("button", { id: "co-save" }),
    nameInput,
    D.el("textarea", { id: "f-one_liner" }),
    D.el("input", { id: "f-is_top_deal" }),
    wrap, box
  ]);
  return { root: root, table: table, rows: rows, box: box, wrap: wrap };
}

// --- companies.js 를 그대로 돌린다 -------------------------------------------
let sent = null;

function run(dom, byId) {
  D.resetHandlers();
  sent = null;
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: { location: { reload: function () {} }, DealflowFilters: undefined },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    fetch: function (url, opts) {
      if (opts && opts.body) sent = JSON.parse(opts.body);
      const m = /\/api\/companies\/(\d+)$/.exec(url);
      const body = m && !opts ? byId[m[1]] : {};
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve(body); } });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "companies.js" });
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });
const lines = (box) => box.children.map(function (line) {
  return line.children.map(function (span) { return span.textContent; });
});

async function main() {
  const byId = { 1: 가나, 2: 나다 };

  // ── 1. 백업이 있으면 두 줄이 이름과 함께 보인다 ────────────────────────
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();

    assert.strictEqual(dom.wrap.hidden, false, "백업이 있는데 상자가 숨어 있습니다");
    assert.deepStrictEqual(lines(dom.box), [
      ["사업분야 (스타트업DB)", "시트에 적혀 있던 사업 설명"],
      ["기업 한줄 소개 (IR 기업 현황)", "사람이 다듬어 쓴 소개"]
    ], "어느 칸에서 온 값인지 알아볼 수 없습니다");
  }

  // ── 2. 다시 열면 앞 기업의 줄이 남아 있으면 안 된다 ────────────────────
  //
  // 남으면 **다른 회사의 옛 설명**을 이 회사 것으로 읽는다. 되살리려고 보는
  // 값이라, 틀린 회사 것을 그대로 복사해 붙이게 된다.
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();

    assert.strictEqual(dom.box.children.length, 2,
      "다시 열었더니 줄이 쌓였습니다 — 앞서 본 기업의 값이 그대로 남습니다");
  }

  // ── 3. 백업이 없는 기업에서는 통째로 숨고, 앞 기업의 줄도 안 남는다 ────
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();
    dom.rows[1].querySelector("button.js-co-edit").fire("click");
    await flush();

    assert.strictEqual(dom.wrap.hidden, true,
      "백업이 없는 기업인데 빈 상자가 떠 있습니다");
    assert.strictEqual(dom.box.children.length, 0,
      "앞서 연 기업의 합치기 전 값이 남아 있습니다 ★ 다른 회사 설명입니다");
  }

  // ── 4. [기업 추가] 에서도 상자는 안 뜬다 ──────────────────────────────
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();
    dom.root.querySelector("#co-add").fire("click");

    assert.strictEqual(dom.wrap.hidden, true, "새 기업에는 합치기 전 값이 없습니다");
    assert.strictEqual(dom.box.children.length, 0);
  }

  // ── 5. 저장 요청에 백업이 안 실린다 (읽기 전용) ───────────────────────
  //
  // 실리면 되살리려고 **열어 본 것만으로** 저장 때 덮어쓴다.
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();
    dom.root.querySelector("#f-name").value = "샘플가나헬스";
    dom.root.querySelector("#co-save").fire("click");
    await flush();

    assert.ok(sent, "저장 요청이 안 나갔습니다");
    assert.ok(!("desc_backup" in sent),
      "합치기 전 값이 저장 요청에 실렸습니다 ★ 열어 본 것만으로 백업이 덮입니다");
    assert.strictEqual(sent.one_liner, "사람이 다듬어 쓴 소개",
      "정작 고쳐야 할 한줄 소개가 안 실렸습니다");
  }

  console.log("company_desc_backup_test OK");
}

main().catch(function (e) { console.error(e); process.exit(1); });
