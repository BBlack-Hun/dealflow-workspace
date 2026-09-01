// 칸을 고치면 위 KPI 숫자도 따라오는가. (node tests/js/consulting_kpi_test.js)
//
// 이 화면은 칸을 눌러 그 자리에서 고친다. 칩(관리 중 · 드랍 · 그 외 · 연락 기록 없음)은
// 고친 값을 따라가는데 **위 KPI 는 서버가 그려 준 숫자 그대로** 남아 있었다 —
// `관리 중` 이 14 라고 적힌 채로 칩을 누르면 13곳이 나온다. 어느 쪽이 맞는지
// 화면 어디에도 안 나오므로, 사용자는 새로고침을 해 봐야 안다.
//
// KPI 는 **거른 결과가 아니라 이 탭 전체**를 센다. `드랍` 만 보는 중이라고
// `관리 중` 이 0 이 되면 안 된다 — 그건 필터가 아니라 표의 성질이다.
// (deals.js 가 `data-match` 와 `hidden` 을 갈라 둔 것과 같은 이유: "조건에
//  맞는가" 를 "보이는가" 로 읽으면 안 된다.)
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 실제로
// 돌린다** — 작은 DOM 을 세우고 칸을 눌러 고치는 데까지 흉내 낸다
// (consulting_contacted_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 서버가 그리는 것과 같은 모양의 표 ---------------------------------------
//
// 줄에 남는 갈래 표시는 `data-f-mgmt` 하나다. `관리 중`/`드랍` 칩도 그것을
// 나눠 본다 — 표시를 여러 개 두면 한쪽만 낡는다.
function row(id, opts) {
  const mgmtCell = D.el("td", {
    class: "cell multi", "data-field": "management", "data-filter-key": "mgmt"
  });
  mgmtCell.textContent = opts.management;
  const regionCell = D.el("td", { class: "cell", "data-field": "region" });
  regionCell.textContent = opts.region || "";
  // 지난달 칸. 위 KPI 의 `미완료 기업` 이 이 칸을 센다.
  const prevCell = D.el("td", {
    class: "cell multi", "data-note": "1", "data-prev-note": "1"
  });
  prevCell.textContent = opts.prevNote || "";

  return D.el("tr", {
    "data-id": String(id),
    "data-search": "",
    "data-f-region": opts.region || "",
    "data-f-mgmt": opts.tags,
    "data-contacted": opts.prevNote ? "1" : "0",
    "data-contacted-folded": "0",
    "data-contacted-prev": opts.prevNote ? "1" : "0"
  }, [regionCell, mgmtCell, prevCell]);
}

function kpi(key, value) {
  const span = D.el("span", { class: "kpi-value", "data-kpi": key });
  span.textContent = String(value);
  return span;
}

function chip(value, label) {
  const btn = D.el("button", { "data-cs-filter": value });
  btn.classList.add("chip");
  if (value === "") btn.classList.add("active");
  btn.textContent = label;
  return btn;
}

function build() {
  //  1) 관리 중  · 지난달 기록 있음
  //  2) 관리 중  · 지난달 기록 없음
  //  3) 드랍     · 지난달 기록 없음
  //  4) **아무것도 안 적힌 줄** — `연락 기록 없음` 이 잡는 유일한 모양이다.
  //     그 칩은 `기업 관리` 가 비어 있고 그리고 리마인드도 비어 있는 줄만
  //     받는다. 예전에는 리마인드 칸만 봐서 2·3번도 같이 걸렸는데, 그러면
  //     `관리 중` 인 줄이 `연락 기록 없음` 에도 떠서 두 갈래가 섞여 보였다.
  const rows = [
    row(1, { management: "관리 중", tags: "관리 중", region: "서울", prevNote: "8월 통화" }),
    row(2, { management: "관리 중 : 견적서 발송", tags: "관리 중", region: "부산" }),
    row(3, { management: "드랍 : 연락 두절", tags: "드랍", region: "대구" }),
    row(4, { management: "", tags: "", region: "" })
  ];
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0" }, [
    D.el("tbody", {}, rows)
  ]);
  const chips = [chip("", "전체"), chip("managed", "관리 중"),
                 chip("dropped", "드랍"), chip("other", "그 외"),
                 chip("nocontact", "연락 기록 없음")];
  const kpis = [kpi("total", 4), kpi("managed", 2), kpi("dropped", 1),
                kpi("pending", 3)];

  const root = D.el("div", {}, kpis.concat(chips, [
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]));
  return { root: root, rows: rows, chips: chips, note: root.querySelector("#cs-note") };
}

// --- consulting.js 를 그대로 돌린다 -----------------------------------------
function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const el = made.call(document, tag);
    el.focus = function () {};
    el.setSelectionRange = function () {};
    return el;
  };
  const sandbox = {
    document: document,
    window: { location: { reload: function () {} } },
    setTimeout: setTimeout,
    alert: function () {}, confirm: function () { return true; },
    prompt: function () { return null; },
    fetch: function () {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  // 공통 필터 부품 없이도 칩·검색은 살아 있어야 한다(consulting.js 의 대비 경로).
  sandbox.window.DealflowFilters = undefined;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "consulting.js" });
  return document;
}

function edit(cell, value) {
  cell.fire("click", { target: cell });
  const input = cell.children[0];
  assert.ok(input, "칸을 눌렀는데 입력칸이 안 생겼습니다");
  input.value = value;
  input.fire("blur", { target: input });
  return new Promise(function (r) { setTimeout(r, 0); });
}

function num(document, key) {
  const el = document.querySelector('[data-kpi="' + key + '"]');
  assert.ok(el, "KPI `" + key + "` 에 다시 셀 표식(data-kpi)이 없습니다");
  return Number(el.textContent);
}

function visible(dom) {
  return dom.rows.filter(function (tr) { return !tr.hidden; })
    .map(function (tr) { return tr.getAttribute("data-id"); });
}

(async function () {
  // 1) `관리 중` 한 곳을 `드랍` 으로 고치면 위 숫자가 그 자리에서 따라온다.
  {
    const dom = build();
    const document = run(dom);
    const mgmt = dom.rows[1].querySelector('[data-field="management"]');
    await edit(mgmt, "드랍 : 기업 회생 신청");

    assert.strictEqual(dom.rows[1].getAttribute("data-f-mgmt"), "드랍",
      "고친 값이 줄의 갈래 표시에 안 적혔습니다");
    assert.strictEqual(num(document, "managed"), 1,
      "`관리 중` 을 `드랍` 으로 고쳤는데 위 숫자가 옛것 그대로입니다 — " +
      "칩으로 거르면 1곳인데 위에는 2 라고 적혀 있습니다");
    assert.strictEqual(num(document, "dropped"), 2,
      "`드랍` 숫자가 안 따라왔습니다");
    assert.strictEqual(num(document, "total"), 4, "전체 수가 흔들렸습니다");
  }

  // 2) 거르는 것과 세는 것은 다르다. `드랍` 만 보는 중이어도 `관리 중` 숫자는
  //    이 탭 전체를 센다 — 보이는 줄만 세면 필터를 걸 때마다 KPI 가 0 이 된다.
  {
    const dom = build();
    const document = run(dom);
    dom.chips[2].fire("click", { target: dom.chips[2] });   // 드랍

    assert.deepStrictEqual(visible(dom), ["3"], "칩이 드랍 줄만 남기지 못했습니다");
    assert.strictEqual(num(document, "managed"), 2,
      "거른 결과로 KPI 를 셌습니다 — 드랍만 보는 중이라고 `관리 중` 이 " +
      "0 이 되면 그 숫자는 아무 뜻이 없습니다");
    assert.strictEqual(num(document, "dropped"), 1);
    assert.strictEqual(num(document, "total"), 4);
  }

  // 3) 지난달 칸을 채우면 `미완료 기업` 도 줄어든다.
  {
    const dom = build();
    const document = run(dom);
    const prev = dom.rows[1].querySelector("[data-prev-note]");
    await edit(prev, "8월 카톡 완료");

    assert.strictEqual(dom.rows[1].getAttribute("data-contacted-prev"), "1",
      "지난달 칸을 채웠는데 줄의 표시가 안 바뀌었습니다");
    assert.strictEqual(num(document, "pending"), 2,
      "지난달 칸을 채웠는데 `미완료 기업` 숫자가 그대로입니다");
  }

  // 4) 칩은 **한 번에 하나**다. 넷이 서로 겹치지 않게 나뉘어 있어(관리 중 ·
  //    드랍 · 그 외 · 아무것도 안 적힌 줄) 둘을 함께 고를 이유가 없다 — AND 로
  //    묶으면 늘 0줄이고, OR 로 묶으면 아무도 안 찾는 목록이 된다. 같은 갈래
  //    안에서 값을 여러 개 고르는 일은 머리글 `기업 관리 ▾` 가 이미 한다(OR).
  //    그래서 새로 누르면 앞의 것이 풀린다.
  {
    const dom = build();
    run(dom);
    dom.chips[2].fire("click", { target: dom.chips[2] });   // 드랍
    dom.chips[1].fire("click", { target: dom.chips[1] });   // 관리 중

    assert.ok(!dom.chips[2].classList.contains("active"),
      "앞서 누른 칩이 안 풀렸습니다 — 무엇으로 걸린 목록인지 알 수 없습니다");
    assert.ok(dom.chips[1].classList.contains("active"));
    assert.deepStrictEqual(visible(dom), ["1", "2"]);
  }

  // 5) **무엇으로 걸렀는지 글자로 남아야 한다.** 건수만 적어 두면 `연락 기록
  //    없음`(어느 달이든 기록이 없는 곳)과 위 KPI 의 `미완료 기업`(지난달만
  //    본다)이 서로 다른 숫자인데도 구별할 방법이 없다.
  {
    const dom = build();
    run(dom);
    dom.chips[4].fire("click", { target: dom.chips[4] });   // 연락 기록 없음
    assert.ok(!dom.note.hidden, "걸러 놓고 안내 문구를 안 띄웠습니다");
    assert.ok(dom.note.textContent.indexOf("연락 기록 없음") >= 0,
      "무엇으로 걸렀는지 안 적혀 있습니다: " + JSON.stringify(dom.note.textContent));
    // 아무것도 안 적힌 줄은 4번 하나다. 2·3번은 `기업 관리` 에 적어 둔 것이
    // 있으니 리마인드가 비었어도 여기 안 뜬다.
    assert.ok(dom.note.textContent.indexOf("1 / 4") >= 0,
      "건수가 틀립니다: " + JSON.stringify(dom.note.textContent));
  }

  console.log("consulting_kpi_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
