// [수정] 창의 `소개 이력` — 줄이 제대로 서는가 · 다시 열 때 앞 기업 것이 남는가.
// (node tests/js/company_history_test.js)
//
// 파이썬으로는 잴 수 없는 자리가 넷이다.
//
//   1. **다시 그릴 때 비운다.** 창 하나를 344개 기업이 돌려 쓴다. 안 비우면
//      두 번째로 연 기업의 표에 앞 기업의 회차가 그대로 남아, **다른 회사에
//      보낸 것**을 이 회사 것으로 읽는다.
//   2. **`[113, 1, 1]` 이 그대로 읽힌다.** 한 명에게만 나간 날이 단체 발송과
//      같은 줄로 뭉치면 이 표를 펼친 뜻이 없다.
//   3. **요약과 표가 같은 것을 말한다.** 합계를 따로 세면 둘이 갈린다.
//   4. **읽기 전용이다.** 이력이 저장 요청에 실리면, 창은 모든 칸을 한 번에
//      보내므로 열어 본 것만으로 엉뚱한 값이 서버로 간다.
//
// 규칙을 옮겨 적지 않고 companies.js 를 그대로 돌린다
// (company_desc_backup_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const src = fs.readFileSync(path.join(SRC, "companies.js"), "utf8");
const MODAL = fs.readFileSync(path.join(SRC, "panel_modal.js"), "utf8");

// 서버가 실제로 주는 모양 그대로(`routers/companies.py` 의 `history_rows`).
// **투자사 이름은 없다** — 수만 온다.
const 가나 = {
  id: 1, name: "샘플가나헬스", one_liner: "소개", introducible: true,
  sent_investors: 118,
  history: [
    { day: "2026-08-19", weekday: "수", investors: 113, batch_title: "",
      source: "sheet", source_label: "시트",
      senders: [{ label: "(담당) 강민준", count: 113, guessed: true }] },
    { day: "2026-08-13", weekday: "목", investors: 1, batch_title: "",
      source: "sheet", source_label: "시트",
      senders: [{ label: "(담당) 강민준", count: 1, guessed: true }] },
    { day: "2026-08-04", weekday: "화", investors: 1, batch_title: "8월 1주차",
      source: "app", source_label: "앱 발송",
      senders: [{ label: "윤서아", count: 1, guessed: false }] }
  ]
};
const 나다 = {
  id: 2, name: "샘플나다물류", one_liner: "소개", introducible: false,
  blocked_reason: "IR 자료 없음", sent_investors: 0, history: []
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

  const nameInput = D.el("input", { id: "f-name" });
  nameInput.focus = function () {};

  const tbody = D.el("tbody", {});
  const hist = D.el("table", { id: "co-history", class: "grid-table compact" },
                    [tbody]);
  const sum = D.el("p", { id: "co-history-sum", class: "hint" });
  const empty = D.el("p", { id: "co-history-empty", class: "hint" });
  empty.hidden = true;

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
    D.el("div", { id: "f-desc_backup" }),
    D.el("div", { id: "f-desc_backup-box" }),
    sum, hist, empty
  ]);
  return { root: root, rows: rows, body: tbody, sum: sum, empty: empty };
}

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
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(src, sandbox, { filename: "companies.js" });
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });
const cells = (tr) => tr.children.map(function (td) { return td.textContent; });

async function main() {
  const byId = { 1: 가나, 2: 나다 };

  // ── 1. 날짜마다 한 줄 · 그날 몇 명에게 갔는지가 그대로 ──────────────────
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();

    assert.strictEqual(dom.body.children.length, 3, "회차 줄이 안 섰습니다");
    assert.deepStrictEqual(
      dom.body.children.map(function (tr) { return tr.children[2].textContent; }),
      ["113", "1", "1"],
      "한 명에게만 간 날이 단체 발송과 뭉쳤습니다 ★ 펼친 뜻이 없습니다");
    assert.deepStrictEqual(cells(dom.body.children[0]),
      ["2026-08-19", "수", "113", "(담당) 강민준 113", "", "시트"]);
    assert.deepStrictEqual(cells(dom.body.children[2]),
      ["2026-08-04", "화", "1", "윤서아", "8월 1주차", "앱 발송"]);
  }

  // ── 2. 요약 한 줄은 **표에서 그대로 더한 값**이다 ──────────────────────
  //
  // 따로 세면 요약과 표가 갈린다. `보낸 날` 과 `발송` 이 나란히 있어야
  // 180건짜리와 103건짜리가 구별된다.
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();

    assert.strictEqual(
      dom.sum.textContent,
      "보낸 날 3회 · 투자사 118명 · 발송 115건 · 마지막 2026-08-19");
    assert.strictEqual(dom.empty.hidden, true);
  }

  // ── 3. 추정으로 적은 이름은 그렇게 보인다 ──────────────────────────────
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();

    const 추정 = dom.body.children[0].children[3];
    const 실제 = dom.body.children[2].children[3];
    assert.ok(추정.classList.contains("guessed"),
      "추정인데 단언처럼 보입니다 ★ 담당이 바뀌면 과거 발송이 통째로 옮겨 붙습니다");
    assert.ok(!실제.classList.contains("guessed"),
      "실제로 보낸 사람이 남는 줄인데 추정으로 표시됐습니다");
  }

  // ── 4. 다시 열면 앞 기업의 회차가 남아 있으면 안 된다 ──────────────────
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();
    dom.rows[1].querySelector("button.js-co-edit").fire("click");
    await flush();

    assert.strictEqual(dom.body.children.length, 0,
      "앞서 연 기업의 회차가 남아 있습니다 ★ 다른 회사에 보낸 것입니다");
    assert.strictEqual(dom.empty.hidden, false,
      "이력이 없는 기업인데 빈 표만 떠 있습니다 — 안 보냈다는 것인지 이름이 " +
      "안 맞았다는 것인지 화면이 말하지 못합니다");
    assert.strictEqual(dom.sum.hidden, true);
  }

  // ── 5. [기업 추가] 에서도 앞 기업의 회차가 안 남는다 ───────────────────
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();
    dom.root.querySelector("#co-add").fire("click");

    assert.strictEqual(dom.body.children.length, 0);
    assert.strictEqual(dom.empty.hidden, false);
  }

  // ── 6. 저장 요청에 이력이 안 실린다 (읽기 전용) ────────────────────────
  {
    const dom = build();
    run(dom, byId);
    dom.rows[0].querySelector("button.js-co-edit").fire("click");
    await flush();
    dom.root.querySelector("#f-name").value = "샘플가나헬스";
    dom.root.querySelector("#co-save").fire("click");
    await flush();

    assert.ok(sent, "저장 요청이 안 나갔습니다");
    assert.ok(!("history" in sent), "이력이 저장 요청에 실렸습니다 ★");
    assert.ok(!("sent_investors" in sent));
  }

  console.log("company_history_test OK");
}

main().catch(function (e) { console.error(e); process.exit(1); });
