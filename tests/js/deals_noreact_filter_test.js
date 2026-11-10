// [반응 없는 담당자만] — 누르면 **목록이 그분들만 남고, 몇 명인지 단추에 보인다**(#211).
// (node tests/js/deals_noreact_filter_test.js)
//
// 예전에는 체크만 켜고 목록은 그대로였다. 116명 사이에 켜진 체크가 흩어져 있어
// 누가 반응 없는 분인지, 몇 명인지 화면에서 알 수 없었다(팀원 요청 11/10).
//
// 지키는 것:
//   ① 누르면 반응 없는 분만 보이고 그분들이 골라진다 — 그룹으로 추려 놓았으면 그 안에서만
//      (실제 투자사 방으로 나가는 자리라, 추린 밖이 딸려 오면 안 된다).
//   ② 다시 누르면 거르기와 고른 것이 함께 풀린다(예전 두 번째 누름과 같다).
//   ③ 단추에 지금 조건 안의 반응 없는 분 수가 적힌다 — 판정은 서버가 준 `data-noreact`
//      그대로다(`services/no_reaction`).
//   ④ 딜 소싱 탭으로 가면 거르기가 풀린다 — 그 탭에서는 단추가 숨는다.
//
// 규칙을 옮겨 적지 않고 **deals.js 를 그대로 실행**한다(`_deals_dom.js`).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const run = deals_.run;
const checkedNames = deals_.checkedNames;
const shownNames = deals_.shownNames;
const pickGroup = deals_.pickGroup;
const pickMode = deals_.pickMode;

const ALL = ["가담당", "나담당", "다담당", "라담당", "마담당"];
const btn = function (dom) { return dom.document.getElementById("select-noreact"); };
const click = function (dom) { btn(dom).fire("click"); };

// ── ③ 처음부터 단추에 몇 명인지 적힌다 ─────────────────────────────────────
{
  const dom = run();
  assert.ok(/2명/.test(btn(dom).textContent),
    "단추에 반응 없는 분 수가 안 적혔다: " + btn(dom).textContent);
  assert.deepStrictEqual(shownNames(dom), ALL, "누르기 전부터 누가 숨겨져 있다");
}

// ── ① 누르면 그분들만 보이고 골라진다 · ② 다시 누르면 함께 풀린다 ──────────
{
  const dom = run();
  click(dom);
  assert.deepStrictEqual(shownNames(dom), ["가담당", "다담당"],
    "눌렀는데 목록이 반응 없는 분만으로 걸러지지 않았다");
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "다담당"],
    "걸러진 분들이 골라지지 않았다");
  assert.strictEqual(btn(dom).getAttribute("aria-pressed"), "true",
    "켜졌는지 단추에서 알 수 없다");
  assert.ok(btn(dom).classList.contains("active"), "켜진 단추가 켜진 모양이 아니다");
  const note = dom.document.getElementById("contact-filter-note");
  assert.ok(!note.hidden && /반응 없음만/.test(note.textContent),
    "무엇으로 걸렀는지 목록 위 안내에 없다: " + note.textContent);

  click(dom);
  assert.deepStrictEqual(shownNames(dom), ALL, "다시 눌렀는데 거르기가 안 풀렸다");
  assert.deepStrictEqual(checkedNames(dom), [], "다시 눌렀는데 고른 것이 남았다");
  assert.strictEqual(btn(dom).getAttribute("aria-pressed"), "false");
  assert.ok(!btn(dom).classList.contains("active"));
  assert.ok(/2명/.test(btn(dom).textContent), "풀고 나서 수가 사라졌다");
}

// ── ① 그룹으로 추려 놓았으면 그 안에서만 · ③ 수도 그 안의 수 ────────────────
{
  const dom = run();
  pickGroup(dom, "2군");
  assert.ok(/1명/.test(btn(dom).textContent),
    "2군으로 추렸는데 단추 수가 전체 수 그대로다: " + btn(dom).textContent);
  click(dom);
  assert.deepStrictEqual(shownNames(dom), ["다담당"],
    "2군으로 추려 놓고 눌렀는데 다른 그룹이 보인다");
  assert.deepStrictEqual(checkedNames(dom), ["다담당"],
    "2군으로 추려 놓고 눌렀는데 다른 그룹의 반응 없는 분까지 켜졌다");
}

// ── ④ 딜 소싱 탭에 갔다 오면 거르기가 풀려 있다 ────────────────────────────
{
  const dom = run();
  click(dom);
  pickMode(dom, "sourcing");
  assert.ok(btn(dom).hidden, "딜 소싱 탭에서 [반응 없는 담당자만] 이 보인다");
  pickMode(dom, "deal");
  assert.strictEqual(btn(dom).getAttribute("aria-pressed"), "false",
    "다른 탭에 갔다 왔는데 반응 없음 거르기가 켜진 채다 — 왜 사람이 적은지 모른다");
}

console.log("deals_noreact_filter_test: ok");
