// 업무 보고 `소개 후보` — 체크한 기업이 딜 제안 관리에 **담겨** 열리는가(#164).
// (node tests/js/report_intro_pick_test.js)
//
// 팀원 요청: "딜소개 안한기업 … 체크박스 클릭해서 > 딜 소개를 할수 있게".
//   ① 아무것도 안 골랐으면 잠긴다(주소 없음 · 눌러도 안 간다)
//   ② 고르면 `딜 소개 (선택 N개)` · 주소 `/deals?companies=…` — 표의 차례 그대로
//   ③ 한 번에 담을 수 있는 수(`data-max`)를 넘으면 잠그고 몇 개를 풀지 말한다
//   ④ 그 주소로 연 딜 제안 관리(deals.js 그대로)가 그 기업들을 **그 차례로** 켜 둔다
//
// 화면은 `_report_intros.html` 과 같은 아이디 · 클래스로 세운다(파이썬 쪽
// `tests/test_report_intro_counts.py` 가 실제 화면의 그 모양을 본다). 번호 · 이름은 가상값이다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const deals_ = require("./_deals_dom.js");
const el = dom_.el;

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "report_intro_pick.js"), "utf8");

// 표의 차례(금액 높은 순) — `_deals_dom.js` 의 기업 번호를 쓴다(④에서 그 화면에 넘긴다).
const ROWS = [203, 201, 202];

function setup(max) {
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const btn = el("a", { id: "intro-left-send", class: "primary-btn inline",
                        "aria-disabled": "true", "data-base": "/deals",
                        "data-max": String(max || 10) });
  btn.textContent = "딜 소개 (선택 0개)";
  const hint = el("span", { id: "intro-left-hint" });
  const boxes = ROWS.map(function (id) {
    return el("input", { type: "checkbox", class: "js-intro-pick", value: String(id) });
  });
  const table = el("table", {}, [el("tbody", {}, boxes.map(function (b) {
    return el("tr", {}, [el("td", { class: "pick-col" }, [b])]);
  }))]);
  root.appendChild(btn);
  root.appendChild(hint);
  root.appendChild(table);
  const document = dom_.makeDocument(root);
  vm.runInNewContext(SRC, { document: document, window: {}, console: console },
                     { filename: "report_intro_pick.js" });
  return { btn: btn, hint: hint, boxes: boxes };
}

function tick(box, on) {
  box.checked = on;
  box.fire("change");
}

// ── ① 처음엔 잠겨 있다 ──────────────────────────────────────────────────────
{
  const v = setup();
  assert.strictEqual(v.btn.getAttribute("aria-disabled"), "true");
  assert.strictEqual(v.btn.getAttribute("href"), null, "안 골랐는데 주소가 있다");
  assert.strictEqual(v.btn.textContent, "딜 소개 (선택 0개)");
  let stopped = false;
  v.btn.fire("click", { preventDefault: function () { stopped = true; } });
  assert.ok(stopped, "잠긴 단추를 누르면 막혀야 한다");
}

// ── ② 고르면 표의 차례로 주소가 선다 — 풀면 다시 잠긴다 ─────────────────────
{
  const v = setup();
  tick(v.boxes[2], true);      // 202 를 먼저 골라도
  tick(v.boxes[0], true);      // 203
  assert.strictEqual(v.btn.textContent, "딜 소개 (선택 2개)");
  assert.strictEqual(v.btn.getAttribute("aria-disabled"), null);
  assert.strictEqual(v.btn.getAttribute("href"), "/deals?companies=203,202",
                     "주소는 표의 차례(금액 높은 순)여야 한다");
  let stopped = false;
  v.btn.fire("click", { preventDefault: function () { stopped = true; } });
  assert.ok(!stopped, "고른 뒤에는 링크가 그대로 열려야 한다");

  tick(v.boxes[0], false);
  tick(v.boxes[2], false);
  assert.strictEqual(v.btn.getAttribute("aria-disabled"), "true");
  assert.strictEqual(v.btn.getAttribute("href"), null);
}

// ── ③ 한 번에 담을 수 있는 수를 넘으면 잠근다 ───────────────────────────────
{
  const v = setup(2);
  v.boxes.forEach(function (b) { tick(b, true); });
  assert.strictEqual(v.btn.textContent, "딜 소개 (선택 3개)");
  assert.strictEqual(v.btn.getAttribute("aria-disabled"), "true");
  assert.strictEqual(v.btn.getAttribute("href"), null);
  assert.ok(/2개까지/.test(v.hint.textContent) && /1개를 풀어/.test(v.hint.textContent),
            "몇 개까지인지 · 몇 개를 풀지 말해야 한다: " + v.hint.textContent);
}

// ── ④ 그 주소로 연 딜 제안 관리가 그 기업들을 그 차례로 켠다 ─────────────────
{
  const v = setup();
  tick(v.boxes[1], true);      // 201
  tick(v.boxes[0], true);      // 203
  const href = v.btn.getAttribute("href");
  assert.strictEqual(href, "/deals?companies=203,201");
  const dom = deals_.run(null, { search: href.slice(href.indexOf("?")) });
  const on = deals_.COMPANIES.filter(function (c) {
    return deals_.companyBox(dom, c[1]).checked;
  }).map(function (c) { return c[0]; });
  assert.deepStrictEqual(on.sort(), [201, 203], "고른 기업이 딜 제안 관리에 안 담겼다");
  const order = deals_.pickNumbers(dom);
  assert.deepStrictEqual(order, { "가나애그": "2", "다라헬스": null, "마바로보": "1" },
                         "담긴 차례가 업무 보고 표의 차례가 아니다: " + JSON.stringify(order));
}

console.log("report_intro_pick_test.js OK");
