// IR 기업 현황 `컨설팅 상태` · `컨설팅 미팅일` 을 표에서 고친다(#166).
// (node tests/js/company_consulting_edit_test.js)
//
// 두 칸의 값은 IR 줄이 아니라 **이어진 투자컨설턴트 줄**에 산다. 그래서
//
//   ① 저장은 칸에 적힌 주소(`data-save-url` → `PATCH /api/consulting/{id}`)로 간다 —
//      IR 줄의 주소(`/api/companies/{id}`)로 가면 IR 에 모르는 칸을 보낸 것이 된다.
//   ② 보기는 세 마디뿐이다(`data-fixed-choices`) — 다른 줄에 적힌 문장이 보기로 서면 안 된다.
//   ③ 보기를 고르면 `상태 : 상세` 의 머리만 바뀐다(`data-pick-head`) — 적어 둔 상세가 산다.
//   ④ 안 고치고 나오면 보이던 글자 그대로다 — 칸에는 갈래, 편집창은 적힌 글에서 시작한다.
//   ⑤ 저장 뒤 companies.js 가 응답의 갈래(`management_tag`)로 칸을 다시 그린다.
//   ⑥ 이어진 줄이 없는 기업(11/07 — "데이터가 들어가야지만 수정이 가능")은 **빈 칸도 열리고**
//      IR 쪽 주소(`/api/companies/{id}/consulting`)로 저장한다. 줄이 새로 섰다는 응답이 오면
//      그 줄의 두 칸이 그 줄의 저장 길(`/api/consulting/{새 번호}`)로 바뀐다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const INLINE = fs.readFileSync(path.join(JS, "inline_edit.js"), "utf8");
const COMPANIES = fs.readFileSync(path.join(JS, "companies.js"), "utf8");
const MODAL = fs.readFileSync(path.join(JS, "panel_modal.js"), "utf8");

const CHOICES = "관리 중,드랍,백업팀 전환";
const flush = () => new Promise((r) => setTimeout(r, 0));

function status(raw, shown, id) {
  const td = D.el("td", {
    class: "cell", "data-field": "management", "data-type": "pick",
    "data-fixed-choices": "", "data-pick-head": "", "data-choices": CHOICES,
    "data-value": raw, "data-save-url": "/api/consulting/" + id
  });
  td.textContent = shown;
  return td;
}

function build() {
  const a = status("관리 중 : 미팅 완", "관리 중", 42);
  const b = status("관리중", "관리 중", 43);
  const c = status("연락 안 됨", "기타 메모", 44);
  const meet = D.el("td", {
    class: "cell", "data-field": "meeting_at", "data-type": "date",
    "data-value": "2025-09-16", "data-save-url": "/api/consulting/42"
  });
  meet.textContent = "2025.09.16";
  const rows = [
    D.el("tr", { "data-id": "7" }, [D.el("td", {}), a, meet]),
    D.el("tr", { "data-id": "8" }, [D.el("td", {}), b]),
    D.el("tr", { "data-id": "9" }, [D.el("td", {}), c])
  ];
  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
                     [D.el("tbody", {}, rows)]);
  // companies.js 가 붙는 자리들(검색 · 수정창) — 없으면 그 파일이 처음부터 죽는다.
  const page = ["co-search", "co-note", "co-status", "co-panel", "co-backdrop", "co-add",
                "co-close", "co-cancel", "co-save"].map(function (id) {
    return D.el(id === "co-search" ? "input" : "div", { id: id });
  });
  return { root: D.el("div", {}, [table].concat(page)), table: table, a: a, b: b, c: c,
           meet: meet, tr: rows[0] };
}

function runInline(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = { innerWidth: 1400, innerHeight: 900,
                addEventListener: function () {}, removeEventListener: function () {} };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function (m) { throw new Error("alert: " + m); },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, method: opts.method, body: JSON.parse(opts.body || "{}") });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  return sent;
}

function open(dom, cell) {
  cell.fire("pointerdown");
  cell.fire("click");
  const pop = dom.root.querySelector(".cell-pop");
  assert.ok(pop, "칸을 눌렀는데 고르기 창이 안 떴다");
  return pop;
}

function chips(pop) {
  return Array.prototype.map.call(pop.querySelectorAll(".cell-pop-choice"),
    function (b) { return b.textContent; });
}

function choose(dom, cell, value) {
  const pop = open(dom, cell);
  const chip = Array.prototype.find.call(pop.querySelectorAll(".cell-pop-choice"),
    function (b) { return b.textContent === value; });
  assert.ok(chip, "보기에 " + value + " 가 없다: " + chips(pop));
  chip.fire("mousedown");
}

async function main() {
  // ①② 보기는 세 마디뿐 · 저장은 컨설턴트 줄로 · ③ 머리만 바뀐다
  {
    const dom = build();
    const sent = runInline(dom);
    const pop = open(dom, dom.a);
    assert.deepStrictEqual(chips(pop), ["관리 중", "드랍", "백업팀 전환"],
      "다른 줄에 적힌 글이 보기로 섰다(`data-fixed-choices`)");
    assert.strictEqual(pop.querySelector(".cell-pop-input").value, "관리 중 : 미팅 완",
      "편집창이 적힌 글이 아니라 칸의 갈래에서 시작했다");
    dom.root.fire("keydown", { key: "Escape" });
    await flush();

    choose(dom, dom.a, "드랍");
    await flush();
    assert.deepStrictEqual(sent, [{ url: "/api/consulting/42", method: "PATCH",
                                    body: { management: "드랍 : 미팅 완" } }],
      "저장이 컨설턴트 줄로 안 갔거나 상세가 사라졌다: " + JSON.stringify(sent));
  }

  // ③ 상태만 적힌 칸은 보기로 갈아 끼우고, 구분 없는 글은 상세로 남긴다
  {
    const dom = build();
    const sent = runInline(dom);
    choose(dom, dom.b, "백업팀 전환");
    await flush();
    choose(dom, dom.c, "드랍");
    await flush();
    assert.deepStrictEqual(sent.map((s) => [s.url, s.body.management]), [
      ["/api/consulting/43", "백업팀 전환"],
      ["/api/consulting/44", "드랍 : 연락 안 됨"]
    ]);
  }

  // ④ 안 고치고 나오면 보이던 글자 그대로 — 저장도 없다
  {
    const dom = build();
    const sent = runInline(dom);
    open(dom, dom.a);
    dom.root.fire("keydown", { key: "Escape" });
    await flush();
    assert.strictEqual(dom.a.textContent, "관리 중", "취소했는데 칸에 적힌 글이 그려졌다");

    dom.meet.fire("pointerdown");
    dom.meet.fire("click");
    const input = dom.meet.querySelector("input");
    assert.ok(input, "미팅일 칸에 입력이 안 열렸다");
    assert.strictEqual(input.type, "date", "날짜뿐인 값인데 날짜 입력으로 안 열렸다");
    assert.strictEqual(input.value, "2025-09-16");
    input.blur();
    await flush();
    assert.strictEqual(dom.meet.textContent, "2025.09.16",
      "안 고쳤는데 칸 글자가 편집창의 꼴로 바뀌었다");
    assert.deepStrictEqual(sent, [], "안 고쳤는데 저장이 나갔다");
  }

  // ⑤ 저장 뒤 companies.js 가 응답으로 다시 그린다
  {
    const dom = build();
    D.resetHandlers();
    const sandbox = {
      document: D.makeDocument(dom.root),
      window: { location: { reload: function () {} }, DealflowFilters: undefined },
      setTimeout: setTimeout, alert: function () {}, confirm: function () { return true; },
      fetch: function () {
        return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
      }
    };
    vm.createContext(sandbox);
    vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
    vm.runInContext(COMPANIES, sandbox, { filename: "companies.js" });

    dom.a.textContent = "드랍 : 미팅 완";               // inline_edit.js 가 그려 둔 것
    dom.table.fire("inline-saved", { detail: { row: dom.tr, cell: dom.a, data: {
      id: 42, stamps: {}, values: { management: "드랍 : 미팅 완" }, management_tag: "드랍" } } });
    assert.strictEqual(dom.a.textContent, "드랍", "저장 뒤 칸에 갈래가 아니라 글이 남았다");
    assert.strictEqual(dom.a.getAttribute("data-value"), "드랍 : 미팅 완");
    assert.strictEqual(dom.a.title, "드랍 : 미팅 완", "칸을 짚으면 적힌 글 전체가 떠야 한다");

    dom.table.fire("inline-saved", { detail: { row: dom.tr, cell: dom.meet, data: {
      id: 42, stamps: {}, values: { meeting_at: "2025-10-01" } } } });
    assert.strictEqual(dom.meet.textContent, "2025-10-01");
    assert.strictEqual(dom.meet.getAttribute("data-value"), "2025-10-01");
  }

  // ⑥ 이어진 줄이 없는 기업 — 빈 칸이 열리고, IR 쪽 주소로 저장하고, 새 줄이 서면 주소가 바뀐다
  {
    const fresh = "/api/companies/7/consulting";
    const st = D.el("td", {
      class: "cell", "data-field": "management", "data-type": "pick",
      "data-fixed-choices": "", "data-pick-head": "", "data-choices": CHOICES,
      "data-value": "", "data-save-url": fresh
    });
    const day = D.el("td", {
      class: "cell", "data-field": "meeting_at", "data-type": "date",
      "data-value": "", "data-save-url": fresh
    });
    const tr = D.el("tr", { "data-id": "7" }, [D.el("td", {}), st, day]);
    const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
                       [D.el("tbody", {}, [tr])]);
    const page = ["co-search", "co-note", "co-status", "co-panel", "co-backdrop", "co-add",
                  "co-close", "co-cancel", "co-save"].map(function (id) {
      return D.el(id === "co-search" ? "input" : "div", { id: id });
    });
    const dom = { root: D.el("div", {}, [table].concat(page)), table: table };
    const sent = runInline(dom);

    choose(dom, st, "드랍");
    await flush();
    assert.deepStrictEqual(sent, [{ url: fresh, method: "PATCH", body: { management: "드랍" } }],
      "빈 칸에서 고른 값이 IR 쪽 주소로 안 갔다: " + JSON.stringify(sent));

    day.fire("pointerdown");
    day.fire("click");
    const input = day.querySelector("input");
    assert.ok(input, "빈 미팅일 칸이 안 열렸다");
    assert.strictEqual(input.type, "date", "빈 미팅일 칸이 날짜 입력으로 안 열렸다");
    input.blur();
    await flush();
    assert.strictEqual(sent.length, 1, "안 고쳤는데 저장이 나갔다");

    // 저장 응답 — 줄이 새로 섰다(`save_consulting` 의 `created`).
    D.resetHandlers();
    const sandbox = {
      document: D.makeDocument(dom.root),
      window: { location: { reload: function () {} }, DealflowFilters: undefined },
      setTimeout: setTimeout, alert: function () {}, confirm: function () { return true; },
      fetch: function () {
        return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
      }
    };
    vm.createContext(sandbox);
    vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
    vm.runInContext(COMPANIES, sandbox, { filename: "companies.js" });
    st.textContent = "드랍";
    table.fire("inline-saved", { detail: { row: tr, cell: st, data: {
      id: 501, created: true, values: { management: "드랍" }, management_tag: "드랍" } } });
    assert.strictEqual(st.getAttribute("data-save-url"), "/api/consulting/501",
      "새 줄이 섰는데 상태 칸이 계속 IR 쪽 주소를 든다");
    assert.strictEqual(day.getAttribute("data-save-url"), "/api/consulting/501",
      "새 줄이 섰는데 옆 칸(미팅일)이 계속 IR 쪽 주소를 든다 — 다음 저장이 같은 줄에 안 담긴다");
    assert.strictEqual(st.textContent, "드랍");
    assert.strictEqual(st.getAttribute("data-value"), "드랍");
  }

  console.log("ok — company_consulting_edit");
}

main().catch(function (err) { console.error(err); process.exit(1); });
