// `사업분야 대분류`·`소분류` 는 **이미 쓰는 값에서 고르거나, 그냥 친다.**
// (node tests/js/company_field_options_test.js)
//
// ── 여기서 잠그는 것 ────────────────────────────────────────────────────
//
// 1. 이미 쓰고 있는 값이 **목록에 뜬다** — 창에서도, 표에서 눌러 고칠 때도.
// 2. **목록에 없는 값도 그대로 저장된다.** 갈래는 사람이 계속 새로 만든다 —
//    못 넣게 막으면 새 갈래가 생긴 날부터 그 기업을 창에서 아예 못 적는다.
//    (`<select>` 로 바꾸는 순간 여기서 걸린다.)
// 3. 목록을 모으는 자리가 **한 곳**이다. 창의 목록 · 표의 보기 · 머리글
//    필터가 **같은 값**을 보여야 한다. 셋 중 하나라도 제 목록을 따로 모으기
//    시작하면 — 서버에 한 벌 두거나, 템플릿에 박아 두거나 — 갈래를 고친 날
//    세 곳이 서로 다른 말을 한다. 그 어긋남이 여기서 걸린다.
// 4. **두 길 다** 된다. 표에서 칸을 눌러 고치는 길과 [수정] 창, 어느 쪽으로
//    들어와도 같은 목록이 뜬다.
// 5. 값이 **하나도 없어도** 화면이 안 깨진다(이제 채우기 시작하는 저장소).
//
// ── 여기서 일부러 **안 하는** 것 ────────────────────────────────────────
//
// 소분류를 대분류에 맞춰 좁히지 않는다. 둘은 서로를 모르는 두 칸이고, 딜
// 추천도 둘을 나란한 분야 둘로 본다(services/matcher.py) — 좁히면 실제로
// 쓰이고 있는 짝을 화면에서 지우게 된다. 아래 3번이 그것까지 잠근다:
// 소분류 목록은 **대분류를 무엇으로 고르든** 그대로다.
//
// 이메일에는 목록을 안 붙인다. 이유는 companies.html 의 그 칸에 적혀 있다
// (채워진 값이 전부 서로 달라 후보가 전부 남의 회사 주소가 된다).
// 붙인 적 없는 것을 검사가 지킬 수는 없으니, 여기서는 **안 붙어 있음**만
// 확인한다 — 나중에 아무 근거 없이 붙이면 걸린다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const ROOT = path.join(__dirname, "..", "..");

function read(...bits) {
  return fs.readFileSync(path.join(ROOT, ...bits), "utf8");
}

const HTML = read("app", "templates", "companies.html");
const COMPANIES = read("app", "static", "js", "companies.js");
const FILTERS = read("app", "static", "js", "filters.js");
const INLINE = read("app", "static", "js", "inline_edit.js");
const MODAL = read("app", "static", "js", "panel_modal.js");

// 창에 실제로 세워진 칸. **템플릿에서 읽는다** — 손으로 한 벌 더 적으면
// 칸이 늘 때 고칠 곳이 하나 더 생긴다(company_edit_fields_test.js 와 같은 뜻).
const SHOWN = [];
HTML.replace(/id="f-([a-z_0-9]+)"/g, function (all, f) {
  if (SHOWN.indexOf(f) < 0) SHOWN.push(f);
  return all;
});

// ── 표에 실려 있는 값 (지어낸 것) ─────────────────────────────────────────
//
// 일부러 이렇게 섞어 둔다:
//   · 같은 대분류가 **두 줄**에 있다  → 목록에 한 번만 떠야 한다
//   · 빈 칸이 대분류에도 소분류에도 있다 → 목록에 `(비어 있음)` 이 새면 안 된다
//     (필터에서는 뜻이 있지만, 적어 넣는 칸에서 고르면 그 글자가 저장된다)
const ROWS = [
  { id: 1, major: "헬스케어", minor: "의료AI" },
  { id: 2, major: "핀테크", minor: "결제" },
  { id: 3, major: "헬스케어", minor: "" },
  { id: 4, major: "", minor: "의료AI" },
  { id: 5, major: "애그테크", minor: "B2B 유통" }
];

// 한글 차례(`localeCompare(…, "ko")`)로 세운 것. 화면이 이대로 보여야 한다.
// 로마자로 시작하는 값(`B2B 유통`)은 그 차례에서 **한글 뒤**로 간다.
const MAJORS = ["애그테크", "핀테크", "헬스케어"];
const MINORS = ["결제", "의료AI", "B2B 유통"];

// 필터 창의 보기 한 줄에서 **값 글자**를 읽는다.
//
// 그 줄은 `체크상자 + 글자`로 만들어진다(`filters.js` 의 `openFor`). 이 DOM 에서
// 글자는 `document.createTextNode` 로 선 **글자 노드 자식**에 담기므로, 줄 자체의
// `textContent` 를 읽으면 늘 빈 글자다 — 글자 노드만 골라 이어 붙여야 한다.
// `tests/js/startup_filters_test.js` 의 `optionText` 와 **같은 규칙**이다(둘 다
// 같은 창을 읽는다 — 규칙이 갈리면 한쪽만 고쳐진다).
//
// `" 헬스케어 (2)"` → `"헬스케어"`. 뒤의 건수는 그 컬럼에 남는 줄 수라 값이 아니다.
function optionText(label) {
  return label.children
    .filter(function (n) { return n.nodeType === 3; })
    .map(function (n) { return n.textContent; })
    .join("")
    .trim()
    .replace(/\s*\(\d+\)$/, "");
}

function cell(field, filterKey, text) {
  const node = D.el("div", {
    class: "cell clamp2", "data-field": field, "data-type": "pick",
    "data-filter-key": filterKey
  });
  node.textContent = text;
  return node;
}

// 화면 그대로의 뼈대: 머리글에 필터, 줄에 `data-f-*`, 칸에 눌러 고치는 `pick`.
function build(rows) {
  const majorTh = D.el("th", { "data-filters": "sector:사업분야 대분류" },
    [D.el("div", { class: "th-filters" })]);
  const minorTh = D.el("th", { "data-filters": "minor:소분류" },
    [D.el("div", { class: "th-filters" })]);

  const cells = {};
  const trs = (rows || ROWS).map(function (r) {
    const major = cell("sector_major", "sector", r.major);
    const minor = cell("sector_minor", "minor", r.minor);
    cells[r.id] = { major: major, minor: minor };
    return D.el("tr", {
      "data-id": String(r.id), "data-search": "",
      "data-f-sector": r.major, "data-f-minor": r.minor
    }, [
      D.el("td", {}, [major]),
      D.el("td", {}, [minor]),
      D.el("td", {}, [D.el("button", { class: "linkbtn js-co-edit" })])
    ]);
  });

  const table = D.el("table",
    { id: "co-table", "data-inline-url": "/api/companies" },
    [D.el("thead", {}, [D.el("tr", {}, [majorTh, minorTh])]),
     D.el("tbody", {}, trs)]);

  const inputs = {};
  SHOWN.forEach(function (f) { inputs[f] = D.el("input", { id: "f-" + f }); });

  // 화면이 그려 주는 목록(`companies.html` 의 `<datalist>`)을 그대로 흉내 낸다.
  // 차례는 **파이썬 차례**로 둔다 — Jinja 의 `sort` 는 로마자를 한글 앞에 두어서,
  // 창이 한글 차례로 다시 세우지 않으면 표·필터와 어긋난다. 그 다시 세우는
  // 일이 실제로 일어나는지를 아래 1번이 잰다.
  function serverList(id, field) {
    const values = Array.from(new Set((rows || ROWS)
      .map(function (r) { return r[field]; })
      .filter(function (v) { return v; }))).sort();
    return D.el("datalist", { id: id },
      values.map(function (v) { return D.el("option", { value: v }); }));
  }
  const lists = {
    sector_major: serverList("opts-sector_major", "major"),
    sector_minor: serverList("opts-sector_minor", "minor")
  };

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
    ]),
    lists.sector_major, lists.sector_minor
  ].concat(SHOWN.map(function (f) { return inputs[f]; }));

  return { root: D.el("div", {}, kids), table: table,
           majorTh: majorTh, minorTh: minorTh,
           cells: cells, inputs: inputs, lists: lists };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1400, innerHeight: 900,
    // 주소는 안 건드린다 — `history` 가 없으면 filters.js 가 그냥 넘어간다.
    location: { search: "", pathname: "/companies", hash: "", reload: function () {} },
    addEventListener: function () {}, removeEventListener: function () {},
    setTimeout: setTimeout
  };
  // 필터 창이 화면 밖으로 안 나가게 자리를 다듬는 자리가 쓴다
  // (`filters.js` 의 `clampIntoView`). 이 DOM 에는 그림이 없으니 **안 밀린
  // 상자**를 준다 — 좌표는 여기서 볼 것이 아니고, 없으면 그 코드가 검사에서만
  // 죽어 정작 봐야 할 것(무슨 값을 고르라고 내놓는가)을 못 본다.
  document.documentElement = { clientWidth: 1400 };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    getComputedStyle: function () { return { overflowX: "visible", left: "0px" }; },
    alert: function (m) { throw new Error("alert: " + m); },
    confirm: function () { return true; },
    CustomEvent: function (type, init) {
      this.type = type;
      this.detail = init && init.detail;
    },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse((opts && opts.body) || "{}") });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  // 화면(`companies.html`)이 부르는 차례 그대로.
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  vm.runInContext(FILTERS, sandbox, { filename: "filters.js" });
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(COMPANIES, sandbox, { filename: "companies.js" });

  return {
    sent: sent,
    // 창을 연다 — [기업 추가] 길이라 서버에 안 묻는다.
    openPanel: function () { dom.root.querySelector("#co-add").fire("click"); },
    save: function () { dom.root.querySelector("#co-save").fire("click"); },
    // 창의 목록에 뜨는 값.
    listed: function (field) {
      return dom.lists[field].children.map(function (o) { return o.value; });
    },
    // 표에서 칸을 눌렀을 때 뜨는 보기.
    picked: function (node) {
      node.fire("pointerdown");
      node.fire("click");
      const pop = dom.root.querySelector(".cell-pop");
      assert.ok(pop, "칸을 눌렀는데 편집창이 안 떴다");
      return pop.querySelectorAll(".cell-pop-choice")
        .map(function (c) { return c.textContent; });
    },
    // 머리글 필터가 고르라고 내놓는 값. **단추를 실제로 누른다** —
    // `filters.js` 는 단추에서 전파를 끊어(`e.stopPropagation()`) 문서에 걸린
    // "바깥을 누르면 닫는다" 가 방금 연 창을 되닫지 못하게 하는데, 이 DOM 은
    // 그 말을 정말로 듣는다(`_dom.js` 의 `fire`).
    filtered: function (th) {
      th.querySelector(".filter-btn").fire("click");
      const panel = th.querySelector(".filter-panel");
      assert.ok(panel, "머리글 단추를 눌렀는데 필터 창이 안 떴다");
      return panel.querySelectorAll(".filter-option").map(optionText);
    }
  };
}

function main() {
  // ── 0. 창의 칸이 **고르거나 치거나** 인가 (템플릿) ──────────────────────
  //
  // `<select>` 로 바꾸면 목록 밖의 갈래를 아예 못 넣는다. `list=` 가 빠지면
  // 고를 것이 안 뜬다. 둘 다 화면을 열어 봐야만 보이는 종류의 고장이라
  // 여기서 글자로 못 박는다.
  {
    ["sector_major", "sector_minor"].forEach(function (f) {
      const tag = new RegExp('<(\\w+)[^>]*\\sid="f-' + f + '"', "s").exec(HTML);
      assert.ok(tag, f + ": 창에 그 칸이 없습니다");
      assert.strictEqual(tag[1], "input",
        f + ": `<input>` 이 아닙니다 ★ `<select>` 면 목록에 없는 갈래를 못 넣습니다");
      const opening = /<input[^>]*>/.exec(HTML.slice(tag.index))[0];
      assert.ok(/\slist="opts-/.test(opening),
        f + ": `list=` 가 없습니다 ★ 고를 목록이 안 뜹니다");
    });

    // 목록을 템플릿에 **박아 두지 않았는가.** 박아 두면 갈래가 늘 때마다
    // 이 줄을 같이 고쳐야 하고, 안 고친 날부터 창과 필터가 다른 말을 한다.
    // (자료에서 모으는지까지는 화면을 그려 봐야 보인다 —
    //  tests/test_company_edit_panel.py 가 두 탭을 실제로 그려서 잰다.)
    ["sector_major", "sector_minor"].forEach(function (f) {
      const block = new RegExp(
        '<datalist id="opts-' + f + '">(.*?)</datalist>', "s").exec(HTML);
      assert.ok(block, f + ": 고를 목록이 없습니다");
      assert.ok(/\{%\s*for .*\brows\b/.test(block[1]),
        f + ": 목록을 `rows` 에서 안 모읍니다 ★ 박아 둔 갈래는 늘어난 날 필터와 갈립니다");
      assert.ok(!/<option value="[^{]/.test(block[1]),
        f + ": 갈래가 템플릿에 박혀 있습니다 ★ 갈래가 늘면 그날로 필터와 갈립니다");
    });

    // 이메일에는 안 붙인다(근거는 companies.html 의 그 칸에 적혀 있다).
    const mail = /<input[^>]*\sid="f-contact_email"[^>]*>/.exec(HTML);
    assert.ok(mail, "창에 이메일 칸이 없습니다");
    assert.ok(!/\slist=/.test(mail[0]),
      "이메일 칸에 목록이 붙었습니다 ★ 채워진 값이 전부 서로 달라, 뜨는 후보가 "
      + "전부 남의 회사 주소가 됩니다 — 붙이려면 먼저 재고 그 숫자를 적으세요");
  }

  // ── 1. 이미 쓰고 있는 값이 창의 목록에 뜬다 ────────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.openPanel();

    assert.deepStrictEqual(t.listed("sector_major"), MAJORS,
      "창의 대분류 목록이 표에 실린 값과 다릅니다");
    assert.deepStrictEqual(t.listed("sector_minor"), MINORS,
      "창의 소분류 목록이 표에 실린 값과 다릅니다");

    // 두 번 열어도 값이 두 벌로 쌓이지 않는다.
    t.openPanel();
    assert.deepStrictEqual(t.listed("sector_major"), MAJORS,
      "창을 다시 열었더니 목록이 쌓였습니다");
  }

  // ── 2. **목록에 없는 값도 저장된다** (직접 입력) ───────────────────────
  //
  // 이게 막히면 새 갈래가 생긴 날부터 그 기업을 창에서 못 적는다.
  {
    const dom = build();
    const t = run(dom);
    t.openPanel();

    dom.inputs.name.value = "샘플기업가나";
    dom.inputs.sector_major.value = "우주항공";     // 표에 없던 갈래
    dom.inputs.sector_minor.value = "위성부품";     // 표에 없던 갈래
    t.save();

    assert.strictEqual(t.sent.length, 1, "저장 요청이 안 나갔습니다");
    assert.strictEqual(t.sent[0].body.sector_major, "우주항공",
      "목록에 없는 대분류가 저장되지 않았습니다 ★ 새 갈래를 못 적습니다");
    assert.strictEqual(t.sent[0].body.sector_minor, "위성부품",
      "목록에 없는 소분류가 저장되지 않았습니다 ★ 새 갈래를 못 적습니다");
  }

  // ── 3. 목록을 모으는 자리가 **한 곳**이다 ──────────────────────────────
  //
  // 창 · 표 · 머리글 필터가 같은 값을 말해야 한다. 어느 하나가 제 목록을
  // 따로 모으기 시작하면 여기서 갈린다.
  {
    const dom = build();
    const t = run(dom);
    t.openPanel();

    // (1) 표에서 칸을 눌러 고칠 때 뜨는 보기
    assert.deepStrictEqual(t.picked(dom.cells[1].major), MAJORS,
      "표에서 고칠 때 뜨는 대분류 보기가 창의 목록과 다릅니다");
    assert.deepStrictEqual(t.picked(dom.cells[1].minor), MINORS,
      "표에서 고칠 때 뜨는 소분류 보기가 창의 목록과 다릅니다");

    // (2) 머리글 필터. 필터는 `(비어 있음)` 을 **더** 보여 준다 — 안 적은
    //     줄을 걸러 보는 뜻이 있어서다. 적어 넣는 칸에서는 고를 값이 아니라
    //     창의 목록에는 없어야 한다(고르면 그 글자가 값으로 저장된다).
    const EMPTY = "(비어 있음)";
    const majorFacets = t.filtered(dom.majorTh);
    assert.ok(majorFacets.indexOf(EMPTY) >= 0,
      "대분류가 빈 줄이 있는데 필터에 `(비어 있음)` 이 없습니다 — 검사 전제가 틀렸습니다");
    assert.deepStrictEqual(majorFacets.filter(function (v) { return v !== EMPTY; }),
      MAJORS,
      "머리글 필터가 내놓는 대분류가 창의 목록과 다릅니다 ★ 목록을 따로 모으고 있습니다");
    assert.strictEqual(t.listed("sector_major").indexOf(EMPTY), -1,
      "창의 목록에 `(비어 있음)` 이 샜습니다 ★ 고르면 그 글자가 저장됩니다");

    const minorFacets = t.filtered(dom.minorTh);
    assert.deepStrictEqual(minorFacets.filter(function (v) { return v !== EMPTY; }),
      MINORS,
      "머리글 필터가 내놓는 소분류가 창의 목록과 다릅니다 ★ 목록을 따로 모으고 있습니다");
    assert.strictEqual(t.listed("sector_minor").indexOf(EMPTY), -1,
      "창의 목록에 `(비어 있음)` 이 샜습니다 ★ 고르면 그 글자가 저장됩니다");
  }

  // ── 3-1. 소분류는 **대분류에 딸린 값이 아니다** ────────────────────────
  //
  // 대분류를 무엇으로 고르든 소분류 목록은 그대로다. 좁히도록 고치면
  // 여기서 걸린다 — 좁히는 순간 실제로 쓰이고 있는 짝이 화면에서 사라진다
  // (둘은 서로를 모르는 두 칸이고, 딜 추천도 나란한 분야 둘로 본다).
  {
    const dom = build();
    const t = run(dom);
    t.openPanel();
    const before = t.listed("sector_minor");

    dom.inputs.sector_major.value = "핀테크";
    dom.inputs.sector_major.fire("change");
    dom.inputs.sector_major.fire("input");

    assert.deepStrictEqual(t.listed("sector_minor"), before,
      "대분류를 골랐더니 소분류 목록이 좁아졌습니다 ★ 둘은 딸린 값이 아닙니다");
    assert.deepStrictEqual(before, MINORS, "소분류 목록이 처음부터 달랐습니다");
  }

  // ── 4. 표에서 고친 값이 **곧바로** 창의 목록에 뜬다 ────────────────────
  //
  // 목록을 한 번만 모아 두면, 표에 새 갈래를 적고 곧바로 [수정]을 연 사람
  // 에게는 방금 적은 그 말이 없다.
  {
    const dom = build();
    const t = run(dom);

    // 표에서 칸을 눌러 새 갈래로 고친다.
    const target = dom.cells[2].major;
    target.fire("pointerdown");
    target.fire("click");
    dom.root.querySelector(".cell-pop .cell-pop-input").value = "우주항공";
    dom.root.querySelector("#co-search").fire("pointerdown");   // 바깥을 누른다

    return Promise.resolve().then(function () {
      assert.strictEqual(
        dom.root.querySelector("tbody tr[data-id=\"2\"]").getAttribute("data-f-sector"),
        "우주항공", "표에서 고친 값이 줄에 안 적혔습니다");

      t.openPanel();
      assert.ok(t.listed("sector_major").indexOf("우주항공") >= 0,
        "표에서 방금 적은 갈래가 창의 목록에 없습니다 ★ 목록을 한 번만 모으고 있습니다");
    });
  }
}

function emptyTable() {
  // ── 5. 값이 **하나도 없어도** 안 깨진다 ────────────────────────────────
  //
  // 이제 채우기 시작하는 저장소. 고를 것이 없을 뿐, 창은 열리고 친 값은
  // 그대로 저장되어야 한다.
  const dom = build([]);
  const t = run(dom);
  t.openPanel();

  assert.deepStrictEqual(t.listed("sector_major"), [],
    "표가 비었는데 목록에 뭔가 떴습니다");
  assert.deepStrictEqual(t.listed("sector_minor"), [], "표가 비었는데 목록에 뭔가 떴습니다");

  dom.inputs.name.value = "샘플기업다라";
  dom.inputs.sector_major.value = "우주항공";
  t.save();
  assert.strictEqual(t.sent.length, 1, "표가 비었을 때 저장이 안 나갔습니다");
  assert.strictEqual(t.sent[0].body.sector_major, "우주항공",
    "표가 비었을 때 친 값이 저장되지 않았습니다");
}

Promise.resolve()
  .then(main)
  .then(emptyTable)
  .then(function () { console.log("company_field_options_test: 통과"); })
  .catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
