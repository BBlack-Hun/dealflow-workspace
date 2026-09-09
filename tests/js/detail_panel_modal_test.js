// 수정창은 **모달**이다 — 뒷막 · Escape · 미저장 확인.
// (node tests/js/detail_panel_modal_test.js)
//
// ── 무엇을 못 박는가 ──────────────────────────────────────────────────────
//
// 투자사 관리 현황(`/contacts` · `/startup`)의 수정창은 뒷막도 Escape 도 없이
// 표 위에 그냥 얹혀 있었다. 그래서 두 가지가 함께 났다:
//
//   1. **겹친다.** 창(z-40) 위에 칸 편집창(`.cell-pop`, z-60)이 그려졌다.
//   2. **써 놓은 값이 조용히 사라진다.** 같은 칸 열한 개를 창(폼 전체를 [저장]
//      때 한 번에)과 표(칸 하나를 누르는 즉시)가 서로 다른 시점에 저장했다.
//      창을 열어 둔 채 표에서 고치고 [저장]을 누르면 옛 값으로 되돌아갔고,
//      창에 타이핑만 해 두고 다른 줄을 누르면 폼이 확인 없이 덮였다.
//
// 뒷막을 세우면 창이 열린 동안 표를 누를 수 없어 1·2 의 앞쪽이 원인에서
// 사라진다. 남는 것은 "적어 둔 것을 확인 없이 버리지 않는가" 다 — 그것이
// 이 검사의 대부분이다.
//
// **부품은 하나여야 한다.** 딜 기업 DB(`/companies`)에 이미 뒷막이 있었지만
// 거기서는 뒷막을 누르면 그대로 닫혀 적던 값이 사라졌다. 여기서 뒷막만 하나
// 더 만들면 같은 판단이 세 벌이 된다 — 그래서 두 화면이 `panel_modal.js`
// 하나를 함께 쓰고, 이 파일이 두 화면을 **같은 자리에서** 눌러 본다.
//
// 이름·회사는 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const ROOT = path.join(__dirname, "..", "..");
const JS = path.join(ROOT, "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(JS, name), "utf8");

const MODAL = read("panel_modal.js");
const CONTACTS = read("contacts.js");
const COMPANIES = read("companies.js");
const INLINE = read("inline_edit.js");

const PEOPLE = {
  1: { id: 1, name: "가상길동", title: "심사역", firm: "가상벤처스", memo: "첫 줄 메모" },
  2: { id: 2, name: "가상순신", title: "이사", firm: "가상캐피탈", memo: "둘째 줄 메모" }
};

// ── 투자사 관리 현황 화면 세우기 ─────────────────────────────────────────
//
// 화면(`app/templates/contacts.html`)이 그리는 만큼만 세운다.
function buildContacts() {
  const rows = [1, 2].map(function (id) {
    return D.el("tr", { class: "data-row", "data-id": String(id) }, [
      D.el("td", { class: "rowno" }),
      // 눌러서 **창을 여는** 자리(칸이 아니다)
      D.el("td", { class: "who" }),
      // 눌러서 **바로 고치는** 칸 — 뒷막이 막는 것이 이 길이다
      D.el("td", { class: "cell", "data-field": "memo", "data-type": "long" })
    ]);
  });
  const table = D.el("table", { id: "contacts-table", "data-inline-url": "/api/contacts" },
    [D.el("tbody", {}, rows)]);

  const backdrop = D.el("div", { class: "panel-backdrop", id: "detail-backdrop" });
  const panel = D.el("aside", { class: "detail-panel", id: "detail-panel" }, [
    D.el("b", { id: "detail-title" }),
    D.el("button", { id: "detail-close" }),
    D.el("button", { class: "detail-tab", "data-tab": "info" }),
    D.el("button", { class: "detail-tab", "data-tab": "timeline" }),
    D.el("div", { class: "detail-body", "data-panel": "info" }, [
      D.el("input", { id: "f-name" }),
      D.el("input", { id: "f-firm" }),
      D.el("textarea", { id: "f-memo" }),
      // 그 명단에만 있는 칸(달마다 늘어나는 칸)도 폼의 일부다 — 이것만 고쳐도
      // 물어야 한다. 이름을 손으로 적지 않고 `data-note` 로 찾는 그 길이다.
      D.el("textarea", { id: "f-note-2026-08", "data-note": "2026-08" }),
      D.el("button", { id: "save-btn" }),
      D.el("button", { id: "delete-btn" }),
      D.el("p", { class: "hint", id: "detail-msg" })
    ]),
    D.el("div", { class: "detail-body", "data-panel": "timeline" }, [
      D.el("ul", { id: "timeline" })
    ])
  ]);
  const add = D.el("button", { id: "add-btn" });

  const root = D.el("div", {}, [table, add, backdrop, panel]);
  // 화면은 창과 뒷막을 `hidden` 으로 세워 둔다 — 그 상태에서 시작해야
  // "열렸다" 를 잴 수 있다.
  panel.hidden = true;
  backdrop.hidden = true;
  return { root: root, table: table, rows: rows, panel: panel, backdrop: backdrop,
           add: add, close: panel.querySelector("#detail-close") };
}

function runContacts(dom) {
  D.resetHandlers();
  const asked = [];          // 확인창에 뜬 글
  const asked_answer = { yes: true };
  const urls = [];
  const document = D.makeDocument(dom.root);
  const win = { location: { reload: function () {}, pathname: "/contacts", search: "" } };
  const sandbox = {
    document: document, console: console,
    setTimeout: setTimeout,
    MutationObserver: function () { this.observe = function () {}; },
    alert: function () {},
    confirm: function (t) { asked.push(String(t)); return asked_answer.yes; },
    fetch: function (url) {
      urls.push(url);
      const id = parseInt(String(url).split("/").pop(), 10);
      return Promise.resolve({
        ok: true,
        json: function () {
          return Promise.resolve({ contact: PEOPLE[id] || PEOPLE[1], timeline: [] });
        }
      });
    }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  // 화면이 부르는 차례 그대로다(contacts.html) — 부품이 뒤에 오면
  // contacts.js 가 `window.PanelModal` 을 못 본다.
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(CONTACTS, sandbox, { filename: "contacts.js" });
  return {
    asked: asked, urls: urls, document: document,
    answer: function (v) { asked_answer.yes = v; },
    el: function (id) { return document.getElementById(id); },
    // 줄을 눌러 창을 연다(칸이 아닌 자리를 누른다 — 칸은 그 자리에서 고치는 길이다).
    openRow: function (i) { dom.rows[i].querySelector(".who").fire("click"); },
    escape: function () { dom.root.fire("keydown", { key: "Escape" }); }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function contactsChecks() {
  // ── 1. 창이 열리면 **뒷막이 선다** ─────────────────────────────────────
  //
  // 뒷막이 표를 덮는 것이 겹침 고침의 전부다. 이것이 안 서면 창(z-40) 위에
  // 칸 편집창(`.cell-pop`, z-60)이 다시 그려진다.
  {
    const dom = buildContacts();
    const t = runContacts(dom);
    assert.strictEqual(dom.panel.hidden, true, "창이 처음부터 열려 있다");
    assert.strictEqual(dom.backdrop.hidden, true, "뒷막이 처음부터 깔려 있다");

    t.openRow(0);
    await flush();
    assert.strictEqual(dom.panel.hidden, false, "줄을 눌렀는데 창이 안 열렸다");
    assert.strictEqual(dom.backdrop.hidden, false,
      "창은 열렸는데 뒷막이 안 깔렸다 ★ 표의 칸을 그대로 누를 수 있어 편집창이 창 위에 겹친다");
    assert.ok(dom.backdrop.classList.contains("panel-backdrop"),
      "뒷막이 딜 기업 DB 와 같은 `.panel-backdrop` 이 아니다 — 뒷막이 두 벌이 된다");
  }

  // ── 2. 안 고쳤으면 **묻지 않는다** ─────────────────────────────────────
  //
  // 안 고쳐도 묻는 창이 되면 사람은 곧 확인창을 안 읽고 누른다 — 그러면
  // 정작 고쳤을 때도 그냥 눌러 값이 사라진다.
  {
    const dom = buildContacts();
    const t = runContacts(dom);
    t.openRow(0);
    await flush();

    dom.backdrop.fire("click");
    assert.deepStrictEqual(t.asked, [], "아무것도 안 고쳤는데 물었다");
    assert.strictEqual(dom.panel.hidden, true, "뒷막을 눌렀는데 창이 안 닫혔다");
    assert.strictEqual(dom.backdrop.hidden, true, "창은 닫혔는데 뒷막이 남았다");
  }
  {
    const dom = buildContacts();
    const t = runContacts(dom);
    t.openRow(0);
    await flush();
    t.escape();
    assert.deepStrictEqual(t.asked, [], "아무것도 안 고쳤는데 물었다(Escape)");
    assert.strictEqual(dom.panel.hidden, true, "Escape 로 창이 안 닫혔다");
  }

  // ── 3. 고쳤으면 **묻는다** — 뒷막 · Escape · [닫기] 셋 다 ──────────────
  //
  // 닫는 길이 셋인데 확인이 그중 하나에만 걸려 있으면 나머지 둘로 값이 샌다.
  for (const [what, hit] of [
    ["뒷막", (dom) => dom.backdrop.fire("click")],
    ["Escape", null],
    ["[닫기 ✕]", (dom) => dom.close.fire("click")]
  ]) {
    const dom = buildContacts();
    const t = runContacts(dom);
    t.openRow(0);
    await flush();
    t.el("f-memo").value = "적다 만 메모";      // 아직 [저장] 을 안 눌렀다

    t.answer(false);                            // 사람이 [취소] 를 누른다
    if (hit) hit(dom); else t.escape();
    assert.strictEqual(t.asked.length, 1, what + " 로 닫는데 안 물었다 ★ 적던 값이 조용히 사라진다");
    assert.strictEqual(dom.panel.hidden, false, what + ": [취소] 를 눌렀는데 창이 닫혔다");
    assert.strictEqual(t.el("f-memo").value, "적다 만 메모",
      what + ": [취소] 를 눌렀는데 적던 값이 사라졌다");

    t.answer(true);                             // 이번엔 버리기로 한다
    if (hit) hit(dom); else t.escape();
    assert.strictEqual(t.asked.length, 2, what + ": 두 번째에는 안 물었다");
    assert.strictEqual(dom.panel.hidden, true, what + ": 버리기로 했는데 창이 안 닫혔다");
    assert.strictEqual(dom.backdrop.hidden, true, what + ": 창은 닫혔는데 뒷막이 남았다");
  }

  // ── 4. 그 명단에만 있는 칸(달마다 늘어나는 칸)도 폼의 일부다 ───────────
  //
  // 기준선을 `FIELDS` 만 보고 잡으면 월별 기록을 적다 만 채로 닫아도 안 묻는다 —
  // 이 저장소가 되풀이한 사고가 그것이다(칸 이름을 손으로 적어 두면 하나가 샌다).
  {
    const dom = buildContacts();
    const t = runContacts(dom);
    t.openRow(0);
    await flush();
    t.el("f-note-2026-08").value = "8월에 딜 3건";
    t.answer(false);
    dom.backdrop.fire("click");
    assert.strictEqual(t.asked.length, 1,
      "월별 기록 칸만 고쳤더니 안 물었다 ★ 기준선이 폼 전체를 안 보고 있다");
  }

  // ── 5. **다른 줄을 눌러도 확인 없이 덮이지 않는다** ────────────────────
  //
  // 창에 타이핑만 해 두고 표의 다른 줄을 누르면 `loadContact` → `fillForm` 이
  // 폼을 통째로 갈아 끼운다. 그 길에도 같은 확인이 걸려 있어야 한다.
  {
    const dom = buildContacts();
    const t = runContacts(dom);
    t.openRow(0);
    await flush();
    assert.deepStrictEqual(t.urls, ["/api/contacts/1"]);
    t.el("f-name").value = "적다 만 이름";

    t.answer(false);
    t.openRow(1);
    await flush();
    assert.strictEqual(t.asked.length, 1, "다른 줄을 눌렀는데 안 물었다");
    assert.deepStrictEqual(t.urls, ["/api/contacts/1"],
      "[취소] 를 눌렀는데 다른 줄을 불러왔다 ★ 확인창이 장식이 된다");
    assert.strictEqual(t.el("f-name").value, "적다 만 이름",
      "[취소] 를 눌렀는데 폼이 덮였다");

    t.answer(true);
    t.openRow(1);
    await flush();
    assert.deepStrictEqual(t.urls, ["/api/contacts/1", "/api/contacts/2"],
      "버리기로 했는데 다른 줄이 안 열렸다");
    assert.strictEqual(t.el("f-name").value, PEOPLE[2].name, "다른 줄의 값으로 안 바뀌었다");
  }

  // ── 6. [담당자 추가] 도 같은 확인을 거친다 ─────────────────────────────
  //
  // 새 줄로 넘어가는 것도 폼을 갈아 끼우는 일이다.
  {
    const dom = buildContacts();
    const t = runContacts(dom);
    t.openRow(0);
    await flush();
    t.el("f-firm").value = "적다 만 회사";
    t.answer(false);
    dom.add.fire("click");
    assert.strictEqual(t.asked.length, 1, "[담당자 추가] 로 넘어가는데 안 물었다");
    assert.strictEqual(t.el("f-firm").value, "적다 만 회사",
      "[취소] 를 눌렀는데 폼이 비워졌다");
  }

  // ── 7. 창을 새로 열면 **기준선도 새로 잡힌다** ─────────────────────────
  //
  // 닫을 때 기준선을 안 놓으면, 다음에 연 창은 열자마자 '고쳐진 것'이 되어
  // 아무것도 안 건드리고 닫아도 묻는다.
  {
    const dom = buildContacts();
    const t = runContacts(dom);
    t.openRow(0);
    await flush();
    t.el("f-memo").value = "적다 만 메모";
    t.answer(true);
    dom.backdrop.fire("click");            // 버리고 닫는다 (1번 물음)

    t.openRow(1);
    await flush();
    dom.backdrop.fire("click");
    assert.strictEqual(t.asked.length, 1,
      "새로 연 창을 안 건드리고 닫는데 물었다 ★ 기준선이 옛 창 것으로 남아 있다");
    assert.strictEqual(dom.panel.hidden, true, "안 고친 창이 안 닫혔다");
  }
}

// ── 딜 기업 DB — **같은 부품을 쓰므로 여기 결함도 함께 고쳐진다** ────────
//
// 이 화면에는 뒷막이 원래 있었는데 누르면 **그대로 닫혔다.** 창을 다 채워 놓고
// 표를 한 번 보려고 옆을 눌렀을 뿐인데 적은 것이 통째로 사라졌다.
function buildCompanies() {
  const rows = [7, 9].map(function (id) {
    return D.el("tr", { "data-id": String(id), "data-search": "" }, [
      D.el("td", { class: "rowno" }),
      D.el("td", {}, [D.el("button", { class: "linkbtn js-co-edit" })])
    ]);
  });
  const table = D.el("table", { id: "co-table" }, [D.el("tbody", {}, rows)]);
  const backdrop = D.el("div", { class: "panel-backdrop", id: "co-backdrop" });
  const panel = D.el("aside", { class: "detail-panel wide", id: "co-panel" }, [
    D.el("h2", { id: "co-title" }),
    D.el("button", { id: "co-close" }),
    D.el("input", { id: "f-name" }),
    D.el("input", { id: "f-note" }),
    D.el("input", { id: "f-is_top_deal" }),
    D.el("button", { id: "co-save" }),
    D.el("button", { id: "co-cancel" })
  ]);
  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "co-search" }),
    D.el("p", { id: "co-note" }),
    D.el("p", { id: "co-status" }),
    D.el("button", { id: "co-add" }),
    backdrop, panel
  ]);
  panel.hidden = true;
  backdrop.hidden = true;
  return { root: root, rows: rows, panel: panel, backdrop: backdrop,
           cancel: panel.querySelector("#co-cancel") };
}

function runCompanies(dom) {
  D.resetHandlers();
  const asked = [];
  const answer = { yes: true };
  const document = D.makeDocument(dom.root);
  const win = { location: { reload: function () {}, search: "", pathname: "/companies" } };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {},
    confirm: function (t) { asked.push(String(t)); return answer.yes; },
    fetch: function () {
      return Promise.resolve({
        ok: true,
        json: function () { return Promise.resolve({ id: 7, name: "가상다라에너지" }); }
      });
    }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(COMPANIES, sandbox, { filename: "companies.js" });
  return {
    asked: asked, answer: function (v) { answer.yes = v; },
    el: function (id) { return document.getElementById(id); },
    escape: function () { dom.root.fire("keydown", { key: "Escape" }); }
  };
}

async function companiesChecks() {
  // ── 뒷막을 눌러도 **적던 값이 조용히 사라지지 않는다** ─────────────────
  {
    const dom = buildCompanies();
    const t = runCompanies(dom);
    dom.rows[0].querySelector(".js-co-edit").fire("click");
    await flush();
    assert.strictEqual(dom.panel.hidden, false, "[수정] 을 눌렀는데 창이 안 열렸다");
    assert.strictEqual(dom.backdrop.hidden, false, "창은 열렸는데 뒷막이 안 깔렸다");

    // 안 고쳤으면 그냥 닫힌다 — 예전 동작 그대로다.
    dom.backdrop.fire("click");
    assert.deepStrictEqual(t.asked, [], "아무것도 안 고쳤는데 물었다");
    assert.strictEqual(dom.panel.hidden, true, "뒷막을 눌렀는데 창이 안 닫혔다");
  }
  {
    const dom = buildCompanies();
    const t = runCompanies(dom);
    dom.rows[0].querySelector(".js-co-edit").fire("click");
    await flush();
    t.el("f-note").value = "적다 만 메모";

    t.answer(false);
    dom.backdrop.fire("click");
    assert.strictEqual(t.asked.length, 1,
      "뒷막을 눌렀는데 안 물었다 ★ 여기 있던 '값 증발' 결함이 그대로다");
    assert.strictEqual(dom.panel.hidden, false, "[취소] 를 눌렀는데 창이 닫혔다");
    assert.strictEqual(t.el("f-note").value, "적다 만 메모", "적던 값이 사라졌다");

    // Escape · [취소] 단추도 같은 길을 지난다.
    t.escape();
    assert.strictEqual(t.asked.length, 2, "Escape 로 닫는데 안 물었다");
    dom.cancel.fire("click");
    assert.strictEqual(t.asked.length, 3, "[취소] 단추로 닫는데 안 물었다");

    t.answer(true);
    dom.backdrop.fire("click");
    assert.strictEqual(dom.panel.hidden, true, "버리기로 했는데 창이 안 닫혔다");
    assert.strictEqual(dom.backdrop.hidden, true, "창은 닫혔는데 뒷막이 남았다");
  }
}

// ── 여는/닫는 부품이 **하나**인가 ────────────────────────────────────────
//
// 두 벌로 갈리는 순간 한쪽이 낡는다 — 이 저장소가 되풀이한 사고다.
// 그래서 소스를 직접 본다: 두 화면 모두 부품을 쓰고, **자기 손으로**
// 뒷막을 여닫거나 Escape 를 듣지 않아야 한다.
function onePartCheck() {
  // 주석은 빼고 본다 — 무엇을 안 하기로 했는지 적어 둔 말에 걸리면 안 된다.
  const strip = (src) => src.replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");

  [["contacts.js", CONTACTS], ["companies.js", COMPANIES]].forEach(function (pair) {
    const name = pair[0];
    const code = strip(pair[1]);
    assert.ok(/PanelModal\.init\(/.test(code),
      name + " 이(가) 공통 부품을 안 쓴다 — 여닫는 판단이 또 한 벌 생겼다");
    assert.ok(!/"Escape"/.test(code),
      name + " 이(가) Escape 를 직접 듣는다 ★ 닫는 판단이 두 벌이다 — " +
      "미저장 확인이 한쪽에만 붙어 값이 샌다");
    assert.ok(!/backdrop.{0,40}hidden\s*=/.test(code),
      name + " 이(가) 뒷막을 직접 여닫는다 ★ 뒷막을 세우는 자리가 두 벌이다");
  });

  const modal = strip(MODAL);
  assert.strictEqual((modal.match(/"Escape"/g) || []).length, 1,
    "부품 안에서도 Escape 를 듣는 자리가 하나가 아니다");
}

async function main() {
  await contactsChecks();
  await companiesChecks();
  onePartCheck();
  console.log("detail_panel_modal_test: 통과");
}

main().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
