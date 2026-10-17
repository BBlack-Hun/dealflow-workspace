// IR 기업 현황 › `Series A 이상 딜 소싱` 탭의 **공유 심사역 확정** — 브라우저 쪽.
// (node tests/js/series_a_sharer_test.js)
//
// `공유 심사역` 칸은 사람이 시트에 적은 글자라 이름 맞추기가 틀릴 수 있다. 칸 아래에
// 딜 소싱 명단에서 이름이 같은 분을 후보로 띄우고, 사람이 [이 분으로 확정]을 누르면
// 그 뒤로는 그 분만 본인으로 본다(`series_a_companies.shared_by_contact_id`).
//
//   ① 서버가 실어 준 값(`data-sharer`)으로 후보 · 확정을 그린다 — 후보가 없으면 숨는다
//   ② [이 분으로 확정] · [해제] 가 PUT 을 보내고 응답대로 다시 그린다
//   ③ 칸을 고쳐 저장하면(`inline-saved`) 응답의 `sharer` 로 다시 그린다
//
// 파일을 그대로 돌린다(`series_a.js`). 이름 · 회사는 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "series_a.js");

const CANDIDATES = {
  confirmed: null,
  candidates: [
    { id: 11, label: "홍길동 이사 (가나벤처스)", auto: true },
    { id: 12, label: "홍길동 팀장 (마바캐피탈)", auto: false }
  ]
};
const CONFIRMED = {
  confirmed: { id: 12, label: "홍길동 팀장 (마바캐피탈)" },
  candidates: CANDIDATES.candidates
};

function build(info) {
  const cell = D.el("div", { class: "cell", "data-field": "shared_by" });
  cell.textContent = "홍길동 이사";
  const box = D.el("div", { class: "cell-sub sa-sharer",
                            "data-sharer": JSON.stringify(info) });
  const tr = D.el("tr", { "data-id": "5", "data-search": "홍길동" },
                  [D.el("td", { class: "rowno" }), D.el("td", {}, [cell, box])]);
  const table = D.el("table", { id: "sa-table", "data-inline-url": "/api/series-a-companies" },
                     [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [D.el("input", { id: "sa-search" }),
                                D.el("button", { id: "sa-add" }),
                                D.el("p", { id: "sa-note" }), table]);
  return { root: root, table: table, tr: tr, cell: cell, box: box };
}

function run(dom, reply) {
  D.resetHandlers();
  const calls = [];
  const alerts = [];
  const sandbox = {
    document: D.makeDocument(dom.root), console: console,
    alert: function (m) { alerts.push(m); },
    confirm: function () { return false; },
    prompt: function () { return ""; },
    setTimeout: setTimeout, encodeURIComponent: encodeURIComponent,
    fetch: function (url, init) {
      const body = init && init.body ? JSON.parse(init.body) : null;
      calls.push({ url: url, method: init && init.method, body: body });
      const out = reply(url, body);
      return Promise.resolve({ ok: out.ok !== false,
                               json: function () { return Promise.resolve(out.d || {}); } });
    }
  };
  sandbox.window = Object.assign({ location: { reload: function () {} } }, sandbox);
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox, { filename: "series_a.js" });
  return { calls: calls, alerts: alerts };
}

function tick() { return new Promise(function (r) { setImmediate(r); }); }
function texts(box, sel) {
  return D.queryAll(box, sel).map(function (n) { return n.textContent; });
}

(async function () {
  // --- ① 후보를 그린다 ----------------------------------------------------------
  {
    const dom = build(CANDIDATES);
    run(dom, function () { return { d: {} }; });
    assert.strictEqual(dom.box.hidden, false);
    assert.deepStrictEqual(texts(dom.box, ".sa-sharer-name"), [
      "홍길동 이사 (가나벤처스) · 이름 · 회사 같음",
      "홍길동 팀장 (마바캐피탈) · 이름만 같음"]);
    const picks = D.queryAll(dom.box, ".js-sharer-pick");
    assert.deepStrictEqual(picks.map(function (b) { return b.getAttribute("data-contact"); }),
                           ["11", "12"]);
    assert.deepStrictEqual(picks.map(function (b) { return b.textContent; }),
                           ["이 분으로 확정", "이 분으로 확정"]);
    // 칸(124px)보다 긴 후보는 `…` 로 잘린다(app.css `.sa-sharer-name`) — 끝까지
    // 읽을 길은 풍선말이다. 딱지에 적은 글 전체를 싣는다.
    assert.deepStrictEqual(D.queryAll(dom.box, ".sa-sharer-name").map(function (n) {
      return n.getAttribute("title");
    }), texts(dom.box, ".sa-sharer-name"));
  }
  {
    const dom = build({ confirmed: null, candidates: [] });
    run(dom, function () { return { d: {} }; });
    assert.strictEqual(dom.box.hidden, true, "후보가 없는데 빈 줄이 선다");
  }

  // --- ② 확정 · 해제 ------------------------------------------------------------
  {
    const dom = build(CANDIDATES);
    const t = run(dom, function (url, body) {
      return { d: { sharer: body && body.contact_id ? CONFIRMED : CANDIDATES } };
    });
    D.queryAll(dom.box, ".js-sharer-pick")[1].fire("click");
    await tick();
    const put = t.calls.filter(function (c) { return c.method === "PUT"; });
    assert.strictEqual(put.length, 1);
    assert.strictEqual(put[0].url, "/api/series-a-companies/5/sharer");
    assert.deepStrictEqual(put[0].body, { contact_id: 12 });
    assert.deepStrictEqual(texts(dom.box, ".sa-sharer-name"), ["확정 · 홍길동 팀장 (마바캐피탈)"]);
    assert.strictEqual(D.queryAll(dom.box, ".sa-sharer-name")[0].getAttribute("title"),
                       "확정 · 홍길동 팀장 (마바캐피탈)", "확정 딱지에도 풍선말이 없다");
    assert.strictEqual(D.queryAll(dom.box, ".js-sharer-pick").length, 0,
                       "확정했는데 후보 단추가 남았다");
    const clear = D.queryAll(dom.box, ".js-sharer-clear");
    assert.strictEqual(clear.length, 1);
    assert.strictEqual(clear[0].textContent, "해제");

    clear[0].fire("click");
    await tick();
    assert.deepStrictEqual(t.calls.pop().body, { contact_id: null });
    assert.strictEqual(D.queryAll(dom.box, ".js-sharer-pick").length, 2);
  }
  {
    // 서버가 거절하면 그 말을 띄우고 그대로 둔다
    const dom = build(CANDIDATES);
    const t = run(dom, function () { return { ok: false, d: { detail: "거절한 까닭" } }; });
    D.queryAll(dom.box, ".js-sharer-pick")[0].fire("click");
    await tick();
    assert.deepStrictEqual(t.alerts, ["거절한 까닭"]);
    assert.strictEqual(D.queryAll(dom.box, ".js-sharer-pick").length, 2);
  }

  // --- ③ 칸을 고쳐 저장하면 다시 그린다 ------------------------------------------
  {
    const dom = build(CONFIRMED);
    run(dom, function () { return { d: {} }; });
    dom.table.fire("inline-saved", { detail: {
      row: dom.tr, cell: dom.cell,
      data: { id: 5, sharer: { confirmed: null, candidates: [
        { id: 21, label: "김철수 심사역 (다라인베스트먼트)", auto: true }] } } } });
    assert.deepStrictEqual(texts(dom.box, ".sa-sharer-name"),
                           ["김철수 심사역 (다라인베스트먼트) · 이름 · 회사 같음"]);
  }

  console.log("series_a_sharer_test: ok");
})().catch(function (e) { console.error(e); process.exit(1); });
