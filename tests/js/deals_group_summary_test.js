// 고른 사람이 여러 그룹에 걸쳐 있을 때, 요약 줄이 **어느 그룹인지 말하는가.**
// (node tests/js/deals_group_summary_test.js)
//
// 그룹 칩은 한 번에 하나만 켜지는데 고르기는 그 위에 쌓인다 — 1군을 고르고
// 2군으로 옮겨 [전체선택]을 누르면 발송 대상에 두 그룹이 함께 있다. 그런데
// 요약 줄은 `곽○○ … 외 119명` 이라고만 적어서, **무엇으로 골랐는지가 화면에서
// 사라졌다.** 필터 칩은 지금 걸린 조건 하나만 말하지, 이미 담아 둔 것을 말해
// 주지 않는다.
//
// 그래서 규칙이 줄마다 다르다.
//   · 그룹 — **하나도 안 줄인다.** 그룹은 `무엇으로 골랐는가` 라서, 하나가
//     가려지면 그 그룹이 통째로 발송에 들어간 사실이 안 보인다.
//   · 이름 — 여섯까지 적고 나머지는 `외 N명`. 이름은 여럿 중 하나이고 수는
//     바로 옆 알약에 적혀 있어, 줄여도 잃는 것이 없다.
//
// 화면은 `_deals_dom.js` 가 세우고, deals.js 는 그대로 돌린다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const EMPTY_GROUP = deals_.EMPTY_GROUP;
const run = deals_.run;
const pickGroup = deals_.pickGroup;
const clickSelectAll = deals_.clickSelectAll;

function summaryHtml(dom) {
  return dom.document.getElementById("contact-summary").innerHTML;
}
// 요약 줄의 **그룹 부분**만. 이름 쪽 `외 N명` 과 섞어 보면 안 된다 —
// 줄이는 규칙이 서로 다른 자리다.
function groupPart(dom) {
  const html = summaryHtml(dom);
  const at = html.indexOf('<span class="pick-groups">');
  if (at < 0) return "";
  return html.slice(at, html.indexOf('<span class="pick-names">'));
}

// ── 1) ★ 두 그룹에 걸쳐 고르면 **두 이름이 다 적힌다** ──────────────────────
{
  const dom = run();
  pickGroup(dom, "1군");
  clickSelectAll(dom);
  pickGroup(dom, "2군");
  clickSelectAll(dom);

  const groups = groupPart(dom);
  assert.ok(groups, "두 그룹에 걸쳐 골랐는데 요약 줄이 그룹을 말하지 않는다");
  assert.ok(groups.indexOf("1군 2명") >= 0,
    "1군이 몇 명인지 안 적혀 있다: " + groups);
  assert.ok(groups.indexOf("2군 2명") >= 0,
    "2군이 몇 명인지 안 적혀 있다: " + groups);
  // 여기가 이 검사의 핵심이다 — 그룹 쪽은 **어떤 이유로도** 뭉개지 않는다.
  assert.ok(groups.indexOf("외") < 0,
    "그룹 이름을 `외 N개` 로 뭉갰다 — 어느 그룹이 발송에 들어갔는지 알 수 없다: " + groups);

  // 사람 이름은 그대로 다 보인다(넷뿐이라 줄일 것이 없다).
  ["가담당", "나담당", "다담당", "라담당"].forEach(function (name) {
    assert.ok(summaryHtml(dom).indexOf(name) >= 0, name + " 이 요약 줄에 없다");
  });
}

// ── 2) 한 그룹뿐이면 적지 않는다 ────────────────────────────────────────────
//
// 섞이지 않았다는 뜻이고, 그건 바로 위 그룹 칩이 이미 말하고 있다
// (같은 자리의 갈래 안내와 같은 규칙: 둘 이상일 때만 말한다).
{
  const dom = run();
  pickGroup(dom, "1군");
  clickSelectAll(dom);
  assert.strictEqual(groupPart(dom), "",
    "한 그룹만 골랐는데 요약 줄이 같은 말을 한 번 더 한다");
  assert.ok(summaryHtml(dom).indexOf("가담당") >= 0, "이름 줄까지 사라졌다");
}

// ── 3) 그룹을 안 정해 둔 사람은 투자사 관리 현황과 같은 말로 묶인다 ──────────
//
// 서버가 실어 보낸 말(`data-empty` ← `sheet_owner.EMPTY_GROUP`)을 그대로 쓴다.
// 여기 한글을 박아 두면 표 쪽 말이 바뀌는 날 두 화면이 다른 말을 하게 된다.
{
  const dom = run();
  clickSelectAll(dom);                       // 다섯 명 전부 — 세 갈래에 걸친다
  const groups = groupPart(dom);
  assert.ok(groups.indexOf("1군 2명") >= 0 && groups.indexOf("2군 2명") >= 0, groups);
  assert.ok(groups.indexOf(EMPTY_GROUP + " 1명") >= 0,
    "그룹을 안 정해 둔 사람이 `" + EMPTY_GROUP + "` 으로 안 묶였다: " + groups);
}

// ── 4) ★ 이름은 줄여도 그룹은 안 줄인다 ─────────────────────────────────────
//
// 일곱 명이면 이름은 `외 1명` 으로 접히는데, 그때도 그룹 이름은 전부 남아야
// 한다. 두 규칙이 한 줄에 붙어 있어서, 한쪽 규칙이 다른 쪽으로 새기 쉽다.
{
  const many = [];
  for (let i = 1; i <= 7; i += 1) many.push([i, "사람" + i, "그룹" + i, false]);
  const dom = run(many);
  clickSelectAll(dom);

  const html = summaryHtml(dom);
  assert.ok(html.indexOf("외 1명") >= 0,
    "일곱 명을 골랐는데 이름 줄이 안 접혔다: " + html);
  const groups = groupPart(dom);
  for (let i = 1; i <= 7; i += 1) {
    assert.ok(groups.indexOf("그룹" + i + " 1명") >= 0,
      "그룹" + i + " 이 요약에서 빠졌다 — 그 그룹이 발송에 든 것을 알 수 없다: " + groups);
  }
  assert.ok(groups.indexOf("외") < 0, "그룹 쪽에 `외` 가 새어 들어왔다: " + groups);
}

// ── 5) 긴 그룹 이름도 잘라 적지 않는다 ──────────────────────────────────────
//
// 이 칸은 3열 그리드의 가운데라 한글 26자 남짓이다. 글자 수로 자르면 이름이
// 반토막 나서 **다른 그룹으로 읽힌다** — 그건 `외 N개` 보다 나쁘다. 줄을
// 넘기는 것은 CSS 가 한다(`.pick-groups`).
{
  const long1 = "후속투자사 찾는 투자사 · 공동투자사 · 앵커투자사";
  const long2 = "시리즈 A 이상 딜소싱 참여 심사역";
  const dom = run([[1, "가담당", long1, false], [2, "나담당", long2, false]]);
  clickSelectAll(dom);

  const groups = groupPart(dom);
  assert.ok(groups.indexOf(long1 + " 1명") >= 0, "긴 그룹 이름이 잘렸다: " + groups);
  assert.ok(groups.indexOf(long2 + " 1명") >= 0, "긴 그룹 이름이 잘렸다: " + groups);
  assert.ok(groups.indexOf("…") < 0 && groups.indexOf("...") < 0,
    "그룹 이름에 말줄임이 붙었다 — 반토막 난 이름은 다른 그룹으로 읽힌다: " + groups);
}

// ── 6) 그룹 이름은 시트에서 온 말이라 **그대로 넣지 않는다** ────────────────
//
// 임포트한 시트의 칸 값이 그대로 화면 조각이 되면, 시트 한 장으로 화면이
// 망가진다.
{
  const dom = run([[1, "가담당", '<b>1군</b>', false], [2, "나담당", "2군", false]]);
  clickSelectAll(dom);
  const groups = groupPart(dom);
  assert.ok(groups.indexOf("&lt;b&gt;1군&lt;/b&gt;") >= 0,
    "그룹 이름이 그대로 화면 조각이 됐다: " + groups);
}

// ── 7) 소싱 명단에서는 그룹이 아니라 **갈래**를 말한다 ──────────────────────
//
// 딜 소싱은 아예 다른 표라 그룹 칸이 없다 — 그쪽에서 그룹을 말하면 없는 값을
// 지어내게 된다. 대신 갈래가 같은 일을 하고, 그건 문구가 갈리는 자리라 더
// 세게 말한다(`bucket-mix-note`).
{
  const dom = run();
  clickSelectAll(dom);
  assert.ok(groupPart(dom), "먼저 그룹 줄이 떠 있어야 이 검사가 뜻이 있다");

  dom.document.querySelector('.mode-tab[data-mode="sourcing"]').fire("click");
  clickSelectAll(dom);                       // 이제 소싱 명단을 고른다
  assert.strictEqual(groupPart(dom), "",
    "소싱 명단을 보는데 그룹 줄이 떠 있다 — 그쪽에는 그룹이라는 칸이 없다");

  const buckets = dom.document.getElementById("bucket-mix-note");
  assert.strictEqual(buckets.hidden, false, "갈래가 섞였는데 아무 말이 없다");
  deals_.SOURCING.forEach(function (s) {
    assert.ok(buckets.textContent.indexOf(s[2]) >= 0,
      "갈래 `" + s[2] + "` 가 안 적혔다: " + buckets.textContent);
  });
}

console.log("deals_group_summary_test: 통과");
