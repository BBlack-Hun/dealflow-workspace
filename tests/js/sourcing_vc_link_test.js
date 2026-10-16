// 딜 소싱 › 시리즈 A 갈래의 **[이 분으로 확정]** — 브라우저 쪽(#28).
// (node tests/js/sourcing_vc_link_test.js)
//
// 이름 · 번호가 둘 다 같은 투자사 줄이 딱 하나일 때만 저절로 잇고, 나머지는 서버가
// 후보를 실어 준다(`data-vc-picks` — `sourcing_sync.link_candidates`).
//
//   ① 실어 준 후보를 그린다 — 이름 · 회사 · 명단 · 무엇이 같은지. 없으면 숨는다
//   ② [이 분으로 확정] — 누구를 어느 줄과 잇는지 묻고, POST 하고, 그 자리에 연결
//      표시(`🔗 투자사 관리 현황: ○○ 명단`)를 그린다. 이으며 채워진 빈 칸도 맞춘다
//   ③ 확인창에서 물리면 아무것도 안 보낸다 · 서버가 거절하면 그 말을 띄우고 그대로
//   ④ 이름 · 번호를 고쳐 저장하면(`inline-saved`) 응답대로 후보나 연결 표시를 다시 그린다
//   ⑤ [연결 풀기] — 관리자 · 그 줄의 담당에게만 선다(`can_unlink`). 묻고, POST 하고,
//      서버가 그린 연결 표시를 걷고 그 자리에 후보를 다시 그린다
//
// 파일을 그대로 돌린다(`sourcing_vc_link.js`). 이름 · 회사는 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "sourcing_vc_link.js");

const CANDS = [
  { id: 11, label: "홍길동 심사역 (가나벤처스)", sheet: "강민준 투자사",
    name_match: true, phone_match: true },
  { id: 12, label: "김서연 팀장 (마바벤처스)", sheet: "윤서아 투자사",
    name_match: false, phone_match: true },
  { id: 13, label: "홍길동 이사 (샘플바이오)", sheet: "강민준 투자사",
    name_match: true, phone_match: false }
];
const LINKED = {
  id: 5,
  vc_link: { contact_id: 11, sheet: "강민준 투자사", href: "/contacts?sheet=x",
             diff: ["회사"], title: "두 화면이 같이 바뀌는 칸: 이름 · 회사 (메모는 따로)",
             can_unlink: true },
  fields: { name: "홍길동", title: "심사역", firm: "가나벤처스(주)", phone: "010-0000-0001",
            email: "hong@example.com", sectors: "AI", round_size: "" }
};

function build(cands, serverLink) {
  const name = D.el("b", { class: "cell", "data-field": "name" });
  name.textContent = "홍길동";
  const box = D.el("div", { class: "cell-sub sourcing-vc-picks",
                            "data-testid": "sourcing-vc-picks",
                            "data-vc-picks": JSON.stringify(cands) });
  box.hidden = true;
  // 서버가 그린 연결 표시 · [연결 풀기](`sourcing.html`) — 이어진 줄에는 후보 자리가 없다.
  const nameKids = [name];
  let linkLine = null;
  let unlinkBtn = null;
  if (serverLink) {
    linkLine = D.el("div", { class: "cell-sub", "data-testid": "sourcing-vc-link" },
                    [D.el("a", { class: "tag soft" })]);
    unlinkBtn = D.el("button", { type: "button", class: "linkbtn danger js-vc-unlink",
                                 "data-sheet": "강민준 투자사" });
    unlinkBtn.textContent = "연결 풀기";
    nameKids.push(linkLine, D.el("div", { class: "cell-sub", "data-testid": "sourcing-vc-unlink" },
                                 [unlinkBtn]));
  } else {
    nameKids.push(box);
  }
  const nameTd = D.el("td", {}, nameKids);
  const phone = D.el("td", { class: "cell", "data-field": "phone" });
  phone.textContent = "010-0000-0001";
  const email = D.el("td", { class: "cell ellipsis", "data-field": "email", title: "" });
  const sectors = D.el("div", { class: "cell clamp2", "data-field": "sectors" });
  const sectorsTd = D.el("td", { title: "" }, [sectors]);
  const title = D.el("td", { class: "cell", "data-field": "title" });
  const tr = D.el("tr", { "data-id": "5", "data-f-title": "", "data-f-sectors": "" },
                  [D.el("td", { class: "rowno" }), nameTd,
                   phone, title, email, sectorsTd]);
  const table = D.el("table", { id: "sourcing-table", "data-inline-url": "/api/sourcing" },
                     [D.el("tbody", {}, [tr])]);
  const root = D.el("div", {}, [table]);
  return { root, table, tr, box, name, nameTd, linkLine, unlinkBtn, phone, email,
           sectors, sectorsTd, title };
}

function run(dom, reply, answer) {
  D.resetHandlers();
  const calls = [];
  const alerts = [];
  const asked = [];
  const sandbox = {
    document: D.makeDocument(dom.root), console: console,
    alert: function (m) { alerts.push(m); },
    confirm: function (m) { asked.push(m); return answer !== false; },
    setTimeout: setTimeout,
    fetch: function (url, init) {
      const body = init && init.body ? JSON.parse(init.body) : null;
      calls.push({ url: url, method: init && init.method, body: body });
      const out = reply(url, body);
      return Promise.resolve({ ok: out.ok !== false,
                               json: function () { return Promise.resolve(out.d || {}); } });
    }
  };
  sandbox.document.createElement = function (tag) { return D.makeEl(tag); };
  sandbox.window = Object.assign({ location: { reload: function () {} } }, sandbox);
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox, { filename: "sourcing_vc_link.js" });
  return { calls, alerts, asked };
}

function tick() { return new Promise(function (r) { setImmediate(r); }); }
function texts(box, sel) {
  return D.queryAll(box, sel).map(function (n) { return n.textContent; });
}
function titles(box, sel) {
  return D.queryAll(box, sel).map(function (n) { return n.getAttribute("title"); });
}

(async function () {
  // --- ① 후보를 그린다 ----------------------------------------------------------
  {
    const dom = build(CANDS);
    run(dom, function () { return { d: {} }; });
    assert.strictEqual(dom.box.hidden, false);
    // 좁은 이름 칸에서 읽히게 — 한 분이 세 줄(누구 · 무엇이 같고 어느 명단 · 단추),
    // 줄마다 잘리면 `…`(CSS) 이고 풍선말에 다 있다(#28 화면 점검).
    assert.deepStrictEqual(texts(dom.box, ".vc-pick-name"), [
      "홍길동 심사역 (가나벤처스)", "김서연 팀장 (마바벤처스)", "홍길동 이사 (샘플바이오)"]);
    assert.deepStrictEqual(texts(dom.box, ".vc-pick-why"), [
      "이름 · 번호 같음 · 강민준 투자사 명단", "번호만 같음 · 윤서아 투자사 명단",
      "이름만 같음 · 강민준 투자사 명단"]);
    const full = [
      "홍길동 심사역 (가나벤처스) · 강민준 투자사 명단 · 이름 · 번호 같음",
      "김서연 팀장 (마바벤처스) · 윤서아 투자사 명단 · 번호만 같음",
      "홍길동 이사 (샘플바이오) · 강민준 투자사 명단 · 이름만 같음"];
    assert.deepStrictEqual(titles(dom.box, ".vc-pick-name"), full);
    assert.deepStrictEqual(titles(dom.box, ".vc-pick-why"), full);
    assert.strictEqual(D.queryAll(dom.box, ".vc-pick").length, 3);
    const picks = D.queryAll(dom.box, ".js-vc-pick");
    assert.deepStrictEqual(picks.map(function (b) { return b.getAttribute("data-contact"); }),
                           ["11", "12", "13"]);
    assert.deepStrictEqual(picks.map(function (b) { return b.textContent; }),
                           ["이 분으로 확정", "이 분으로 확정", "이 분으로 확정"]);
  }
  {
    const dom = build([]);
    run(dom, function () { return { d: {} }; });
    assert.strictEqual(dom.box.hidden, true, "후보가 없는데 빈 줄이 선다");
    assert.strictEqual(D.queryAll(dom.box, ".js-vc-pick").length, 0);
  }

  // --- ② 확정하면 잇고 연결 표시를 그린다 ------------------------------------------
  {
    const dom = build(CANDS);
    const t = run(dom, function () { return { d: LINKED }; });
    D.queryAll(dom.box, ".js-vc-pick")[0].fire("click");
    await tick();
    assert.strictEqual(t.asked.length, 1);
    assert.ok(t.asked[0].indexOf("'홍길동' 님") === 0, t.asked[0]);
    assert.ok(t.asked[0].indexOf("강민준 투자사 명단 줄(홍길동 심사역 (가나벤처스))") > 0,
              "누구를 어느 줄과 잇는지 확인창에 없다: " + t.asked[0]);
    assert.deepStrictEqual(t.calls, [{ url: "/api/sourcing/5/link", method: "POST",
                                       body: { contact_id: 11 } }]);
    const link = D.queryAll(dom.box, "a.tag")[0];
    assert.strictEqual(link.textContent, "🔗 투자사 관리 현황: 강민준 투자사 명단");
    assert.strictEqual(link.getAttribute("href"), "/contacts?sheet=x");
    assert.strictEqual(link.getAttribute("title"), LINKED.vc_link.title);
    assert.deepStrictEqual(texts(dom.box, '[data-testid="sourcing-vc-diff"]'), ["다른 칸: 회사"]);
    assert.strictEqual(D.queryAll(dom.box, ".js-vc-pick").length, 0, "이었는데 후보 단추가 남았다");
    assert.strictEqual(dom.box.hidden, false);
    assert.strictEqual(dom.box.getAttribute("data-testid"), "sourcing-vc-link");
    // 관리자 · 그 줄의 담당이면 바로 [연결 풀기]도 선다(`can_unlink`).
    assert.deepStrictEqual(texts(dom.box, ".js-vc-unlink"), ["연결 풀기"]);
    // 이으며 채워진 빈 칸 — 칸 · 풍선말 · 거를 값
    assert.strictEqual(dom.email.textContent, "hong@example.com");
    assert.strictEqual(dom.email.getAttribute("title"), "hong@example.com");
    assert.strictEqual(dom.title.textContent, "심사역");
    assert.strictEqual(dom.tr.getAttribute("data-f-title"), "심사역");
    assert.strictEqual(dom.sectors.textContent, "AI");
    assert.strictEqual(dom.sectorsTd.getAttribute("title"), "AI");
    assert.strictEqual(dom.tr.getAttribute("data-f-sectors"), "AI");
  }

  // --- ③ 물리면 안 보낸다 · 서버가 거절하면 그대로 ---------------------------------
  {
    const dom = build(CANDS);
    const t = run(dom, function () { return { d: LINKED }; }, false);
    D.queryAll(dom.box, ".js-vc-pick")[1].fire("click");
    await tick();
    assert.strictEqual(t.calls.length, 0, "확인창에서 물렸는데 보냈다");
    assert.strictEqual(D.queryAll(dom.box, ".js-vc-pick").length, 3);
  }
  {
    const dom = build(CANDS);
    const t = run(dom, function () { return { ok: false, d: { detail: "이 줄의 후보가 아닙니다" } }; });
    const btn = D.queryAll(dom.box, ".js-vc-pick")[2];
    btn.fire("click");
    await tick();
    assert.deepStrictEqual(t.alerts, ["이 줄의 후보가 아닙니다"]);
    assert.strictEqual(D.queryAll(dom.box, ".js-vc-pick").length, 3);
    assert.strictEqual(btn.disabled, false, "거절된 뒤 단추가 잠긴 채다");
    assert.strictEqual(dom.email.textContent, "");
  }

  // --- ④ 이름 · 번호를 고쳐 저장하면 다시 그린다 -----------------------------------
  {
    const dom = build([]);
    run(dom, function () { return { d: {} }; });
    dom.table.fire("inline-saved", { detail: {
      row: dom.tr, cell: dom.phone, data: { ok: true, vc_picks: [CANDS[1]] } } });
    assert.strictEqual(dom.box.hidden, false);
    assert.deepStrictEqual(texts(dom.box, ".vc-pick-name"), ["김서연 팀장 (마바벤처스)"]);
    assert.deepStrictEqual(texts(dom.box, ".vc-pick-why"), ["번호만 같음 · 윤서아 투자사 명단"]);

    // 저절로 이어졌다 — 연결 표시. 방금 고친 칸은 `inline_edit.js` 가 그렸으니 안 건드린다
    dom.phone.textContent = "010 0000 0001";
    dom.table.fire("inline-saved", { detail: {
      row: dom.tr, cell: dom.phone, data: Object.assign({ ok: true }, LINKED) } });
    assert.strictEqual(texts(dom.box, "a.tag")[0], "🔗 투자사 관리 현황: 강민준 투자사 명단");
    assert.strictEqual(D.queryAll(dom.box, ".js-vc-pick").length, 0);
    assert.strictEqual(dom.phone.textContent, "010 0000 0001");
    assert.strictEqual(dom.email.textContent, "hong@example.com");

    // 그 값이 없는 응답(다른 칸을 고쳤다)은 아무것도 안 건드린다
    dom.table.fire("inline-saved", { detail: { row: dom.tr, cell: dom.email, data: { ok: true } } });
    assert.strictEqual(texts(dom.box, "a.tag")[0], "🔗 투자사 관리 현황: 강민준 투자사 명단");

    // 풀 수 없는 사람에게는 [연결 풀기]가 안 선다
    const noUnlink = Object.assign({ ok: true }, LINKED, {
      vc_link: Object.assign({}, LINKED.vc_link, { can_unlink: false }) });
    dom.table.fire("inline-saved", { detail: { row: dom.tr, cell: dom.phone, data: noUnlink } });
    assert.strictEqual(D.queryAll(dom.box, ".js-vc-unlink").length, 0);
  }

  // --- ⑤ [연결 풀기] ----------------------------------------------------------------
  {
    // 서버가 그린 연결 표시에서 — 묻고, 보내고, 표시를 걷고, 후보를 새로 그린다
    const dom = build([], true);
    const t = run(dom, function () { return { d: { id: 5, vc_picks: [CANDS[0]] } }; });
    dom.unlinkBtn.fire("click");
    await tick();
    assert.strictEqual(t.asked.length, 1);
    assert.ok(t.asked[0].indexOf("'홍길동' 님과 투자사 관리 현황의 강민준 투자사 명단 줄") === 0,
              t.asked[0]);
    assert.ok(t.asked[0].indexOf("지우지 않습니다") > 0, t.asked[0]);
    assert.deepStrictEqual(t.calls, [{ url: "/api/sourcing/5/unlink", method: "POST", body: null }]);
    assert.strictEqual(D.queryAll(dom.nameTd, '[data-testid="sourcing-vc-link"]').length, 0,
                       "풀었는데 연결 표시가 남았다");
    assert.strictEqual(D.queryAll(dom.nameTd, ".js-vc-unlink").length, 0);
    const box = dom.nameTd.querySelector(".sourcing-vc-picks");
    assert.ok(box, "후보 자리가 안 섰다");
    assert.strictEqual(box.hidden, false);
    assert.deepStrictEqual(texts(box, ".vc-pick-name"), ["홍길동 심사역 (가나벤처스)"]);
    assert.strictEqual(box.getAttribute("data-testid"), "sourcing-vc-picks");
  }
  {
    // [이 분으로 확정] 으로 막 이은 자리에서 — 같은 상자에 후보가 돌아온다
    const dom = build(CANDS);
    let step = 0;
    const t = run(dom, function () {
      step += 1;
      return step === 1 ? { d: LINKED } : { d: { id: 5, vc_picks: CANDS } };
    });
    D.queryAll(dom.box, ".js-vc-pick")[0].fire("click");
    await tick();
    D.queryAll(dom.box, ".js-vc-unlink")[0].fire("click");
    await tick();
    assert.strictEqual(t.calls[1].url, "/api/sourcing/5/unlink");
    assert.strictEqual(D.queryAll(dom.box, ".js-vc-pick").length, 3);
    assert.strictEqual(D.queryAll(dom.box, "a.tag").length, 0);
    assert.strictEqual(dom.box.getAttribute("data-testid"), "sourcing-vc-picks");
  }
  {
    // 물리면 안 보낸다 · 서버가 막으면 그 말을 띄우고 그대로
    const dom = build([], true);
    const t = run(dom, function () { return { d: {} }; }, false);
    dom.unlinkBtn.fire("click");
    await tick();
    assert.strictEqual(t.calls.length, 0);
    const dom2 = build([], true);
    const t2 = run(dom2, function () {
      return { ok: false, d: { detail: "연결은 관리자나 이 줄의 담당만 풀 수 있습니다." } };
    });
    dom2.unlinkBtn.fire("click");
    await tick();
    assert.deepStrictEqual(t2.alerts, ["연결은 관리자나 이 줄의 담당만 풀 수 있습니다."]);
    assert.strictEqual(D.queryAll(dom2.nameTd, '[data-testid="sourcing-vc-link"]').length, 1);
    assert.strictEqual(dom2.unlinkBtn.disabled, false);
  }

  console.log("sourcing_vc_link_test: ok");
})().catch(function (e) { console.error(e); process.exit(1); });
