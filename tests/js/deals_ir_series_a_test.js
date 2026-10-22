// 딜 제안 관리 › IR 자료 전달 — **Series A 이상 딜 소싱** 기업도 함께 고른다(0118).
// (node tests/js/deals_ir_series_a_test.js)
//
// 사용자 요청(10/22): "Series A 이상 딜 소싱에 있는 기업도 IR 자료가 있어서 등록 가능하게
// 해줘". 그 탭에 IR 자료 파일 이름을 적은 기업은 딜 진행 관리의 [자료 보내기]가 IR 기업처럼
// 붙여 보낸다. 자동 첨부를 켠 계정은 그 단추가 이 화면을 연다
// (`/deals?mode=ir&contacts=…&companies=…&series_a=…`) — 그래서 여기서도:
//
//   ① 자료 전달 탭에서 Series A 고르개가 IR 기업 목록과 **함께** 선다(Series A 딜 공유
//      전용 칸 — 사람당 N개 · `아직 공유 안 한 것만` — 은 숨는다)
//   ② 주소의 `series_a` 를 켠다
//   ③ 미리보기 · 발송에 **칸을 나눠** 싣는다 — IR 기업은 `company_ids`, Series A 는
//      `series_a_ids`(다른 표의 번호다 — 섞으면 번호만 같은 남의 기업이 나간다)
//   ④ 두 상자를 합쳐 센다(한도 · 알약)
//
// 기업 · 사람은 전부 지어낸 것이다(공개 저장소).
"use strict";

const assert = require("assert");
const deals_ = require("./_deals_dom.js");

function postTo(fetch, url) {
  return fetch.calls.filter(function (c) { return c.url === url; });
}

function saBox(dom, id) {
  const cb = dom.document.getElementById("sacb-" + id);
  assert.ok(cb, "Series A 카드가 없다: " + id);
  return cb;
}

// ── ① · ② 링크로 열면 두 상자가 켜지고 고르개가 선다 ─────────────────────────
{
  const fetch = deals_.fakeFetch([{ ok: true, d: { job_id: 9, total: 1 } }]);
  const dom = deals_.run(null, {
    fetch: fetch, confirm: function () { return true; },
    search: "?mode=ir&contacts=1&companies=201&series_a=302&attach=1"
  });
  const picker = dom.document.getElementById("series-a-picker");

  assert.strictEqual(picker.hidden, false, "자료 전달인데 Series A 고르개가 숨어 있다");
  assert.strictEqual(dom.document.getElementById("company-list").hidden, false,
                     "IR 기업 목록이 사라졌다 — 자료 전달은 두 목록을 함께 본다");
  assert.strictEqual(dom.document.getElementById("sa-per-person-line").hidden, true,
                     "Series A 딜 공유의 `사람당 N개` 칸이 자료 전달에 섰다");
  assert.strictEqual(picker.querySelector('[data-only="ir"]').hidden, false,
                     "자료 전달 안내가 안 섰다");
  assert.strictEqual(saBox(dom, 302).checked, true, "주소의 series_a 를 안 켰다");
  assert.strictEqual(deals_.companyBox(dom, "가나애그").checked, true);
  assert.ok(dom.document.getElementById("company-pill").innerHTML.indexOf("<b>2</b>") === 0,
            "두 상자를 합쳐 세지 않았다: " + dom.document.getElementById("company-pill").innerHTML);

  // ③ 발송 — 칸을 나눠 싣는다.
  dom.document.getElementById("send-btn").fire("click");
  const sends = postTo(fetch, "/api/deals/send");
  assert.strictEqual(sends.length, 1, "발송을 부르지 않았다");
  assert.strictEqual(sends[0].body.mode, "ir");
  assert.deepStrictEqual(sends[0].body.company_ids, [201],
                         "IR 기업 칸에 Series A 번호가 섞였다: " + JSON.stringify(sends[0].body));
  assert.deepStrictEqual(sends[0].body.series_a_ids, [302],
                         "Series A 기업이 안 실렸다: " + JSON.stringify(sends[0].body));
}

// ── ③ 미리보기도 같은 손 — 손으로 고른 Series A 기업 ─────────────────────────
{
  const fetch = deals_.fakeFetch([]);
  const dom = deals_.run(null, { fetch: fetch });
  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, "다라헬스");
  const cb = saBox(dom, 304);
  cb.checked = true;
  cb.fire("change");

  dom.document.getElementById("refresh-preview").fire("click");
  const previews = postTo(fetch, "/api/deals/preview");
  assert.ok(previews.length, "미리보기를 부르지 않았다");
  const body = previews[previews.length - 1].body;
  assert.deepStrictEqual([body.company_ids, body.series_a_ids], [[202], [304]],
                         "미리보기 칸이 갈렸다: " + JSON.stringify(body));
}

// ── 다른 탭에서는 Series A 상자를 안 센다 · 고르개도 숨는다 ─────────────────────
{
  const fetch = deals_.fakeFetch([]);
  const dom = deals_.run(null, { fetch: fetch, search: "?mode=ir&series_a=302" });
  deals_.pickMode(dom, "deal");
  assert.strictEqual(dom.document.getElementById("series-a-picker").hidden, true,
                     "딜 소개에 Series A 고르개가 섰다");
  deals_.toggleCompany(dom, "가나애그");
  dom.document.getElementById("refresh-preview").fire("click");
  const body = postTo(fetch, "/api/deals/preview").pop().body;
  assert.deepStrictEqual([body.company_ids, body.series_a_ids], [[201], []],
                         "딜 소개에 Series A 기업이 실렸다: " + JSON.stringify(body));
}

console.log("deals_ir_series_a_test.js OK");
