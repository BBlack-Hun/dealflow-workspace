// `수정한 날짜` 칸 — **눌러도 아무 일이 없고, 옆 칸을 고치면 그 자리에서 바뀐다.**
// (node tests/js/company_updated_at_test.js)
//
// 이 칸은 앱이 적는 값이다. 그래서 화면 쪽에서 지켜야 하는 것이 정확히 둘이다.
//
//   1. **못 고친다.** `inline_edit.js` 는 `.cell[data-field]` 둘이 함께 있는
//      것만 연다. 표가 그 둘을 안 주므로 눌러도 편집창이 안 뜬다 — 그런데 그
//      약속은 마크업 한 줄에만 적혀 있어서, 다음 사람이 옆 칸을 흉내 내어
//      `class="cell"` 을 붙이는 순간 조용히 열린다. 규칙을 옮겨 적지 않고
//      **inline_edit.js 를 그대로 돌려서** 확인한다.
//
//   2. **고치면 바뀐다.** 옆 칸을 고쳐 저장하면 서버가 새 시각을 응답에 실어
//      준다(`updated_at`). 화면이 그것을 안 쓰면 칸에는 고치기 전 시각이 그대로
//      앉아 있고, 고친 사람 눈에는 저장이 안 된 것처럼 보인다 — 이 칸을 세운
//      이유가 통째로 무너진다. 이쪽도 `companies.js` 를 그대로 돌린다.
//
// **응답 하나가 여러 되그리기를 깨운다.** 기업 PATCH 응답에는 `contract_label`
// 과 `contract_received` 가 늘 함께 실린다(`_contract_result`). 되그리기들이
// 서로의 칸을 안 건드려야, 기업명 하나를 고쳤을 뿐인데 엉뚱한 칸이 바뀌지 않는다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const COMPANIES = fs.readFileSync(path.join(SRC, "companies.js"), "utf8");
const MODAL = fs.readFileSync(path.join(SRC, "panel_modal.js"), "utf8");
const INLINE = fs.readFileSync(path.join(SRC, "inline_edit.js"), "utf8");

const OLD = "2026-09-16 19:44:43";
const NEW = "2026-09-16 19:48:16";

// --- 표 한 줄 — 템플릿의 IR 기업 현황 탭과 **같은 속성만** 세운다 -----------
//
// `수정한 날짜` 칸에 `cell` 도 `data-field` 도 없는 것이 이 판의 핵심이다.
// 여기서 그 둘을 적어 넣으면 검사가 지키려는 것을 검사가 먼저 깬다.
function build() {
  const updated = D.el("td", {
    class: "updated-at muted",
    title: "만든 뒤로 아직 고친 적이 없습니다 — 만든 시각입니다"
  });
  updated.textContent = OLD;

  const meeting = D.el("td", { class: "cell", "data-field": "meeting_offered_at" });
  const name = D.el("td", { class: "cell", "data-field": "name" });
  name.textContent = "샘플가나헬스";

  const tr = D.el("tr", { "data-id": "7", "data-search": "" },
    [D.el("td", { class: "rowno muted" }), name, updated, meeting]);

  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" }, [
    D.el("tbody", {}, [tr])
  ]);

  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "co-search" }),
    D.el("p", { id: "co-note" }),
    D.el("p", { id: "co-status" }),
    D.el("p", { id: "co-updated" }),
    D.el("aside", { id: "co-panel" }),
    D.el("div", { id: "co-backdrop" }),
    D.el("button", { id: "co-add" }),
    D.el("button", { id: "co-close" }),
    D.el("button", { id: "co-cancel" }),
    D.el("button", { id: "co-save" })
  ]);
  return { root: root, table: table, tr: tr, updated: updated,
           meeting: meeting, name: name };
}

// --- companies.js 를 그대로 돌린다 ------------------------------------------
function runCompanies(dom) {
  D.resetHandlers();
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: { location: { reload: function () {} }, DealflowFilters: undefined },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    fetch: function () {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(COMPANIES, sandbox, { filename: "companies.js" });
}

// --- inline_edit.js 를 그대로 돌린다 ----------------------------------------
function runInline(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1440, innerHeight: 900,
    addEventListener: function () {}, removeEventListener: function () {}
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {},
    CustomEvent: function (type, init) {
      this.type = type;
      this.detail = init && init.detail;
    },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse((opts && opts.body) || "{}") });
      return Promise.resolve({
        ok: true,
        json: function () { return Promise.resolve({ updated_at: NEW }); }
      });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  return {
    sent: sent,
    pop: function () { return dom.root.querySelector(".cell-pop"); },
    press: function (node) { node.fire("pointerdown"); node.fire("click"); }
  };
}

// inline_edit.js 가 저장 뒤에 쏘는 그 이벤트.
function saved(dom, cell, data) {
  dom.table.fire("inline-saved", { detail: { row: dom.tr, cell: cell, data: data } });
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 눌러도 아무 일이 없다 ───────────────────────────────────────────
  {
    const dom = build();
    const t = runInline(dom);
    t.press(dom.updated);
    await flush();

    assert.strictEqual(t.pop(), null,
      "`수정한 날짜` 를 눌렀더니 편집창이 떴다 ★ 앱이 적는 값이라 고치면 안 된다");
    assert.strictEqual(dom.updated.querySelectorAll("input").length, 0,
      "칸 안에 입력칸이 열렸다 ★ 사람이 고친 시각이 저장된다");
    assert.deepStrictEqual(t.sent, [], "누르기만 했는데 저장 요청이 나갔다");
    assert.strictEqual(dom.updated.textContent, OLD, "누르기만 했는데 글자가 바뀌었다");

    // 옆 칸은 그대로 열려야 한다 — '이 칸만' 안 열리는 것이 맞는지 함께 본다.
    t.press(dom.meeting);
    await flush();
    assert.ok(dom.meeting.querySelector("input"),
      "옆 칸까지 안 열린다 ★ 표 전체가 고장 난 것이지 이 칸의 규칙이 아니다");
  }

  // ── 2. 옆 칸을 고치면 그 자리에서 시각이 바뀐다 ────────────────────────
  {
    const dom = build();
    runCompanies(dom);
    saved(dom, dom.meeting, { updated_at: NEW });

    assert.strictEqual(dom.updated.textContent, NEW,
      "고쳤는데 `수정한 날짜` 가 그대로다 ★ 새로고침해야 보이면 이 칸은 쓸모가 없다");
    assert.ok(!dom.updated.classList.contains("muted"),
      "방금 고쳤는데 '고친 적 없음' 옅은 글씨가 남아 있다");
    assert.strictEqual(dom.updated.title, "마지막으로 고친 시각",
      "짚었을 때 뜨는 말이 옛말 그대로다");
  }

  // ── 3. 응답이 준 값을 쓴다 — 지어내지 않는다 ───────────────────────────
  //
  // 화면에서 `new Date()` 로 만들면 브라우저 시계와 서버 시계가 다른 만큼
  // 어긋나고, 새로고침하는 순간 다른 시각으로 바뀐다.
  {
    const dom = build();
    runCompanies(dom);
    saved(dom, dom.name, { updated_at: "1999-12-31 23:59:59" });
    assert.strictEqual(dom.updated.textContent, "1999-12-31 23:59:59",
      "응답이 준 시각이 아니라 화면이 지어낸 값을 적었다");
  }

  // ── 4. 시각이 안 실린 응답에는 손대지 않는다 ───────────────────────────
  //
  // 이 표의 되그리기는 여럿이고 응답 모양도 자리마다 다르다. 없는 값을 읽어
  // `undefined` 를 적으면 칸이 그 글자로 덮인다.
  {
    const dom = build();
    runCompanies(dom);
    saved(dom, dom.name, { contract_label: "미계약", contract_received: "O" });

    assert.strictEqual(dom.updated.textContent, OLD,
      "시각이 안 실린 응답인데 칸을 덮었다");
    assert.ok(dom.updated.classList.contains("muted"),
      "시각이 안 실린 응답인데 옅은 글씨를 걷어냈다");
  }

  // ── 5. 다른 칸 되그리기가 이 칸을 건드리지 않는다 ──────────────────────
  {
    const dom = build();
    runCompanies(dom);
    saved(dom, dom.name, { updated_at: NEW, contract_label: "미계약",
                           contract_received: "O", introducible: true });

    assert.strictEqual(dom.updated.textContent, NEW);
    assert.strictEqual(dom.name.textContent, "샘플가나헬스",
      "시각을 되그리면서 기업명 칸까지 건드렸다");
    assert.strictEqual(dom.meeting.textContent, "",
      "시각을 되그리면서 옆 칸까지 건드렸다");
  }

  console.log("company_updated_at_test OK");
}

main().catch(function (err) { console.error(err); process.exit(1); });
