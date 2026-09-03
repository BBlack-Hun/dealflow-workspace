// 표의 **번호(NO)를 누르면 [수정] 창이 열리는가.**
// (node tests/js/company_no_opens_edit_test.js)
//
// 표는 2,030px 라 오른쪽 끝의 [수정] 단추까지 가로로 밀어야 닿는데, 줄을 짚는
// 손은 이미 왼쪽 번호에 있다. 그래서 번호도 같은 창을 연다.
//
// **여는 길이 하나인지**가 이 검사의 핵심이다. 번호 칸에 handler 를 따로 달면
// 그날은 되지만, 다음에 창 여는 규칙이 바뀔 때 한쪽만 고쳐지고 조용히 갈린다
// (이 저장소가 되풀이한 사고다). 그래서 번호 칸은 [수정] 단추와 **같은 class**
// 를 달아 companies.js 의 그 handler 를 그대로 탄다 — 여기서는 그 짝이
// 템플릿과 스크립트 사이에서 안 갈렸는지, 그리고 두 입구가 정말 같은 창을
// 여는지를 본다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const ROOT = path.join(__dirname, "..", "..");
const HTML = fs.readFileSync(
  path.join(ROOT, "app", "templates", "companies.html"), "utf8");
const src = fs.readFileSync(
  path.join(ROOT, "app", "static", "js", "companies.js"), "utf8");

// --- ⓪ 템플릿과 스크립트가 **한 벌**인가 -------------------------------------
//
// 스크립트가 기다리는 class 를 **스크립트에서 읽는다**. 여기에 손으로 한 벌 더
// 적으면, 이름이 바뀌는 날 검사만 옛 이름을 붙들고 통과한다.
const listened = /classList\.contains\("([\w-]+)"\)/.exec(src);
assert.ok(listened, "companies.js 에서 여는 class 를 못 찾았습니다");
const OPEN_CLASS = listened[1];

// 번호 칸은 두 탭(IR 기업 현황 · 스타트업DB)에 하나씩 있다. **둘 다** 열려야
// 한다 — 같은 창을 쓰는데 한쪽 탭에서만 되면 고장으로 읽힌다.
const ROWNO = [];
HTML.replace(/<td class="(rowno[^"]*)"/g, function (_all, cls) {
  ROWNO.push(cls);
  return _all;
});
assert.strictEqual(ROWNO.length, 2,
  "companies.html 의 번호 칸이 둘이 아닙니다(탭마다 하나): " + JSON.stringify(ROWNO));
ROWNO.forEach(function (cls, i) {
  assert.ok(cls.split(/\s+/).indexOf(OPEN_CLASS) >= 0,
    "번호 칸 " + (i + 1) + " 에 `" + OPEN_CLASS + "` 이 없습니다 ★ 눌러도 창이 안 열립니다: " + cls);
});

// --- 창을 세운다 -------------------------------------------------------------
//
// 창의 칸은 템플릿에서 읽는다(company_edit_fields_test.js 와 같은 이유다).
const SHOWN = [];
HTML.replace(/id="f-([a-z_0-9]+)"/g, function (_all, f) {
  if (SHOWN.indexOf(f) < 0) SHOWN.push(f);
  return _all;
});

function row(id, rownoClass) {
  const no = D.el("td", { class: rownoClass });
  const oneLiner = D.el("div", { class: "cell clamp2", "data-field": "one_liner" });
  const btn = D.el("button", { class: "linkbtn js-co-edit" });
  const tr = D.el("tr", { "data-id": String(id), "data-search": "" },
                  [no, D.el("td", {}, [oneLiner]), D.el("td", {}, [btn])]);
  return { tr: tr, no: no, oneLiner: oneLiner, btn: btn };
}

function build() {
  const rows = ROWNO.map(function (cls, i) { return row(7 + i * 2, cls); });
  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
                     [D.el("tbody", {}, rows.map(function (r) { return r.tr; }))]);

  const kids = [
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
    D.el("div", { id: "f-desc_backup-box" }, [D.el("div", { id: "f-desc_backup" })]),
    D.el("div", { id: "f-one_liner-note" }, [
      D.el("span", { id: "one-liner-state" }),
      D.el("button", { id: "one-liner-auto" })
    ])
  ].concat(SHOWN.map(function (f) {
    const node = D.el("input", { id: "f-" + f });
    node.focus = function () {};          // 이 DOM 에는 초점이 없다
    return node;
  }));

  const root = D.el("div", {}, kids);
  // 템플릿은 창과 뒷막을 `hidden` 으로 세워 둔다 — 그 상태에서 시작해야
  // "열렸다" 를 잴 수 있다.
  root.querySelector("#co-panel").hidden = true;
  root.querySelector("#co-backdrop").hidden = true;
  return { root: root, rows: rows, panel: root.querySelector("#co-panel"),
           backdrop: root.querySelector("#co-backdrop"),
           title: root.querySelector("#co-title") };
}

let asked = [];

function run(dom, name) {
  D.resetHandlers();
  asked = [];
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: { location: { reload: function () {} }, DealflowFilters: undefined },
    setTimeout: setTimeout,
    alert: function (m) { throw new Error("alert: " + m); },
    confirm: function () { return true; },
    fetch: function (url) {
      asked.push(url);
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 1, name: name }) });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "companies.js" });
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 번호를 누르면 **그 줄의** 창이 열린다 ───────────────────────────
  //
  // 탭마다 한 벌씩 — 번호 칸 두 개를 각각 눌러 본다.
  for (let i = 0; i < ROWNO.length; i += 1) {
    const dom = build();
    run(dom, "샘플가나헬스");
    const target = dom.rows[i];

    assert.strictEqual(dom.panel.hidden, true, "창이 처음부터 열려 있습니다");
    target.no.fire("click");
    await flush();

    assert.deepStrictEqual(asked, ["/api/companies/" + target.tr.getAttribute("data-id")],
      "번호 칸 " + (i + 1) + ": 누른 줄이 아닌 것을 불러왔습니다");
    assert.strictEqual(dom.panel.hidden, false, "번호 칸 " + (i + 1) + ": 창이 안 열렸습니다");
    assert.strictEqual(dom.backdrop.hidden, false, "번호 칸 " + (i + 1) + ": 뒷막이 안 깔렸습니다");
    assert.strictEqual(dom.title.textContent, "샘플가나헬스",
      "번호 칸 " + (i + 1) + ": 창에 그 기업 이름이 안 떴습니다");
  }

  // ── 2. 번호와 [수정] 단추는 **같은 창**을 연다 ─────────────────────────
  //
  // 여기가 갈리면 한쪽만 고쳐진 채로 남는다.
  {
    const dom = build();
    run(dom, "샘플나다물류");
    dom.rows[0].btn.fire("click");
    await flush();
    const viaButton = asked.slice();

    const dom2 = build();
    run(dom2, "샘플나다물류");
    dom2.rows[0].no.fire("click");
    await flush();

    assert.deepStrictEqual(asked, viaButton,
      "번호와 [수정] 단추가 서로 다른 곳을 부릅니다 ★ 여는 길이 둘로 갈렸습니다");
  }

  // ── 3. 눌러서 고치는 칸은 창을 열지 않는다 ─────────────────────────────
  //
  // `한줄 소개` 처럼 그 자리에서 고치는 칸(inline_edit.js)까지 창을 열어 버리면,
  // 고치려고 누를 때마다 창이 튀어나와 고칠 수가 없다. 줄 전체를 누를 수 있게
  // 넓히고 싶어질 때 여기서 막힌다.
  {
    const dom = build();
    run(dom, "샘플다라에너지");
    dom.rows[0].oneLiner.fire("click");
    await flush();
    assert.deepStrictEqual(asked, [], "한줄 소개를 눌렀는데 창이 열렸습니다");
    assert.strictEqual(dom.panel.hidden, true, "한줄 소개를 눌렀는데 창이 열렸습니다");
  }

  console.log("ok — 번호 칸이 [수정] 창을 연다 (탭 " + ROWNO.length + "곳)");
}

main().catch(function (e) { console.error(e); process.exit(1); });
