// IR 자료 전달 — **고른 차례는 번호가 아니다.** (node tests/js/deals_ir_number_test.js)
//
// 딜 소개 탭에서는 고른 차례가 곧 문구의 번호라, 카드에 그 번호를 배지로
// 띄운다(`data-pick-order`). 자료 전달은 다르다 — 그때의 번호는 **딜 소개에서
// 이미 붙은 번호**이고(`app/services/deal_numbers.py`), 투자사가 "2번 주세요"
// 라고 답한 그 번호다. 담당자마다 다르므로 카드 하나에 적을 수 있는 값이 아니다.
//
// 그런데도 고른 차례를 배지로 띄우면 화면은 `1`, 나가는 문구는 `2번 기업 …` 이
// 되어 **어느 쪽이 맞는지 알 수 없다.** 그래서 이 탭에서는 배지를 비운다
// (`no-pick-badge` — CSS 가 그 표시를 읽는지는 파이썬 쪽이 따로 본다).
//
// **차례 자체는 그대로 쓴다.** 문구가 기업을 짚는 차례이자 [보낼 자료] 목록의
// 차례라서, 여기서 차례까지 버리면 화면과 문구가 다른 차례로 갈린다.
//
// 화면은 `_deals_dom.js` 가 세우고, deals.js 는 그대로 돌린다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

const A = "가나애그";    // 목록 1번째
const B = "다라헬스";    // 목록 2번째
const C = "마바로보";    // 목록 3번째

function idOf(dom, name) {
  return parseInt(deals_.companyBox(dom, name).value, 10);
}

function irNames(dom) {
  return Array.prototype.slice
    .call(dom.document.getElementById("ir-links").children)
    .map(function (li) { return li.innerHTML; });
}

// ── 1) ★ 자료 전달 탭은 **번호 배지를 비운다** ─────────────────────────────
{
  const dom = deals_.run(null, {});

  deals_.toggleCompany(dom, C);
  deals_.toggleCompany(dom, A);
  assert.ok(!dom.companyPanel.classList.contains("no-pick-badge"),
            "딜 소개 탭에서 배지를 껐다 — 여기서는 고른 차례가 곧 번호다");

  deals_.pickMode(dom, "ir");
  assert.ok(dom.companyPanel.classList.contains("no-pick-badge"),
            "자료 전달 탭에서 고른 차례를 번호처럼 띄우고 있다 — " +
            "화면은 `1`, 문구는 `2번 기업 …` 이 되어 어느 쪽이 맞는지 알 수 없다");

  // 다른 탭으로 돌아오면 다시 켜진다. 한 번 끄고 안 켜면, 딜 소개에서 몇 번으로
  // 나갈지 고르는 사람만 모른다.
  deals_.pickMode(dom, "deal");
  assert.ok(!dom.companyPanel.classList.contains("no-pick-badge"),
            "딜 소개로 돌아왔는데 배지가 꺼진 채다");
}

// ── 2) 문구만 보내는 탭은 건드리지 않는다 ──────────────────────────────────
//
// 리마인드·선호 분야 묻기는 기업 목록 자체가 흐려진다(`dimmed`). 표시가 서로
// 엉키면 흐려야 할 때 안 흐리거나, 그 반대가 된다.
{
  const dom = deals_.run(null, {});
  deals_.pickMode(dom, "remind");
  assert.ok(dom.companyPanel.classList.contains("dimmed"),
            "문구만 보내는 탭인데 기업 칸이 안 흐려졌다");
  assert.ok(!dom.companyPanel.classList.contains("no-pick-badge"),
            "리마인드에서 배지를 껐다 — 여기는 기업을 고르는 자리가 아니다");
}

// ── 3) ★ 배지를 껐다고 **차례까지 버리지는 않는다** ────────────────────────
//
// 문구는 고른 차례로 기업을 짚는다("3번 기업 다라헬스, 2번 기업 가나애그").
// [보낼 자료] 목록이 목록 차례로 서면 화면과 문구가 갈린다.
{
  const fetch = deals_.fakeFetch([]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, B);      // 목록 2번째를 먼저
  deals_.toggleCompany(dom, A);      // 목록 1번째를 나중에

  assert.deepStrictEqual(
    irNames(dom).map(function (html) { return html.indexOf(B) === 0 ? B : A; }),
    [B, A],
    "[보낼 자료] 목록이 **목록 차례**로 섰다 — 고른 차례가 아니다");

  dom.document.getElementById("refresh-preview").fire("click");
  const previews = fetch.calls.filter(function (c) {
    return c.url === "/api/deals/preview";
  });
  assert.ok(previews.length, "미리보기를 부르지 않았다");
  const last = previews[previews.length - 1];
  assert.deepStrictEqual(last.body.company_ids, [idOf(dom, B), idOf(dom, A)],
    "미리보기가 **목록 차례**로 나갔다: " + JSON.stringify(last.body.company_ids));
  assert.strictEqual(last.body.mode, "ir");
}

console.log("ok — 자료 전달 탭은 고른 차례를 번호처럼 띄우지 않는다");
