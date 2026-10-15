// 딜 소싱 제안의 [보낼 문구 › Series A 딜 공유] — 화면 쪽.
// (node tests/js/series_a_share_test.js)
//
// 여기서 못 박는 것.
//   ① [Series A 딜 공유] 를 누르면 ① 칸이 `Series A 이상 기업` 고르개로 바뀌고
//      (IR 기업 목록은 숨는다), 다른 갈래 카드는 빠진다(숨고 체크가 꺼진다)
//   ② 고른 차례가 곧 번호다 — 미리보기 · 발송이 `series_a_ids` 를 고른 차례로
//      싣고, IR 기업 칸(`company_ids`)은 비운다
//   ③ 고르개 카드마다 `이미 받은 분 N명` — 지금 고른 받는 분 중 그 기업을 받은 분
//   ④ [이미 이 기업들을 받은 분 제외](기본 켬) — 고른 기업을 **모두** 받은 분은
//      체크를 남긴 채 보내지 않고(흐리게 · 딱지), 일부만 받은 분은 그대로 보낸다
//      (서버가 받은 기업을 뺀다). 끄면 `include_shared` 가 실린다
//   ⑤ 딜 소싱 화면의 [Series A 딜 소개] 링크(`?mode=sourcing&topic=…&contacts=…`)로
//      열면 그 분들이 골라져 있다 — 투자사 담당자 목록에는 안 켜진다
//   ⑥ 다른 글로 돌아가면 IR 기업 목록이 다시 선다
//
// 누가 무엇을 받았는지 · 어떤 글이 나가는지는 서버가 정한다(파이썬 쪽
// `tests/test_series_a_deal_share.py`). 이름은 전부 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const run = deals_.run;
const fakeFetch = deals_.fakeFetch;
const pickMode = deals_.pickMode;
const BATCH_TITLES = deals_.BATCH_TITLES;

const SHARE = "sourcing_deal_share";

function now(fn) { fn(); return 0; }

function setup(opts) {
  const fetch = fakeFetch([]);
  const dom = run(null, Object.assign({ fetch: fetch, setTimeout: now }, opts || {}));
  return { dom: dom, fetch: fetch };
}

function pickTopic(dom, value) {
  const chip = dom.document.querySelector('#sourcing-topic .chip[data-value="' + value + '"]');
  assert.ok(chip, "[보낼 문구] 칩이 없다: " + value);
  chip.fire("click");
}

function sCard(dom, name) {
  return dom.sourcingCards.filter(function (c) {
    return c.querySelector(".contact-cb").getAttribute("data-name") === name;
  })[0];
}
function sBox(dom, name) { return sCard(dom, name).querySelector(".contact-cb"); }
function saCard(dom, name) {
  return dom.seriesACards.filter(function (c) {
    return c.querySelector(".sa-cb").getAttribute("data-name") === name;
  })[0];
}
function toggleSeriesA(dom, name) {
  const cb = saCard(dom, name).querySelector(".sa-cb");
  cb.checked = !cb.checked;
  cb.fire("change");
}
function toggleSourcing(dom, name) {
  const cb = sBox(dom, name);
  cb.checked = !cb.checked;
  cb.fire("change");
}
function calls(fetch, url) { return fetch.calls.filter(function (c) { return c.url === url; }); }
function lastPreview(fetch) { return calls(fetch, "/api/deals/preview").pop(); }
function selectAll(dom) { dom.document.getElementById("select-all-contacts").fire("click"); }

// --- ① 글을 고르면 ① 칸이 Series A 이상 기업 고르개로 -------------------------
{
  const t = setup();
  pickMode(t.dom, "sourcing");
  selectAll(t.dom);                                   // 처음 안내에서 셋 다 고른 채로
  assert.strictEqual(t.dom.seriesAPicker.hidden, true, "처음에는 IR 기업 목록이어야 한다");
  pickTopic(t.dom, SHARE);

  assert.strictEqual(t.dom.seriesAPicker.hidden, false, "Series A 이상 기업 고르개가 안 섰다");
  assert.strictEqual(t.dom.document.getElementById("company-list").hidden, true,
                     "IR 기업 목록이 그대로 떠 있다 — 어느 목록에서 고르는지 헷갈린다");
  assert.strictEqual(t.dom.document.getElementById("company-picker-search").hidden, true);
  assert.strictEqual(t.dom.companyPanel.classList.contains("dimmed"), false,
                     "기업을 골라야 하는 글인데 ① 칸이 흐리다");

  // 다른 갈래(M&A) 분은 이 글을 받을 자리가 아니다 — 숨고 체크도 꺼진다.
  assert.strictEqual(sCard(t.dom, "나소싱").hidden, true, "다른 갈래 카드가 보인다");
  assert.strictEqual(sBox(t.dom, "나소싱").checked, false,
                     "숨기기만 하고 체크가 남았다 — 안 보이는 사람에게 나간다");
  assert.strictEqual(t.dom.document.getElementById("shared-note").hidden, false,
                     "[이미 이 기업들을 받은 분 제외] 줄이 안 섰다");

  // 회차명도 이 글의 이름으로(서버가 실어 준 `sourcing_deal_share` 이름표).
  assert.strictEqual(t.dom.document.getElementById("batch-title").value,
                     BATCH_TITLES.sourcing_deal_share);

  const body = lastPreview(t.fetch).body;
  assert.strictEqual(body.topic, SHARE);
  assert.deepStrictEqual(body.company_ids, [], "IR 기업 칸에 무언가 실렸다");
  assert.deepStrictEqual(body.series_a_ids, []);
  assert.strictEqual(body.bucket, deals_.SHARE_BUCKET, "기본 문구가 이 갈래 문구가 아니다");
  assert.strictEqual(body.include_shared, false, "제외가 기본으로 켜져 있어야 한다");
}

// --- ② 고른 차례가 곧 번호 · ③ `이미 받은 분 N명` --------------------------------
{
  const t = setup();
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  toggleSeriesA(t.dom, "나샘플로보");                 // 302 먼저
  toggleSeriesA(t.dom, "가샘플바이오");               // 301 나중
  assert.strictEqual(saCard(t.dom, "나샘플로보").getAttribute("data-pick-order"), "1");
  assert.strictEqual(saCard(t.dom, "가샘플바이오").getAttribute("data-pick-order"), "2");
  assert.deepStrictEqual(lastPreview(t.fetch).body.series_a_ids, [302, 301],
                         "고른 차례대로 실리지 않았다");

  // 아직 받는 분을 안 골랐다 — `이미 받은 분` 딱지는 없다.
  assert.strictEqual(saCard(t.dom, "가샘플바이오").querySelector(".sa-got").hidden, true);
  toggleSourcing(t.dom, "가소싱");                    // 101 — 301 · 303 을 받은 분
  const got = saCard(t.dom, "가샘플바이오").querySelector(".sa-got");
  assert.strictEqual(got.hidden, false, "고른 분이 이미 받은 기업인데 말하지 않는다");
  assert.strictEqual(got.textContent, "이미 받은 분 1명");
  assert.strictEqual(saCard(t.dom, "나샘플로보").querySelector(".sa-got").hidden, true);
  // 고르지 않은 기업에도 센다 — 고르기 전에 보여야 고를지 정한다.
  assert.strictEqual(saCard(t.dom, "다샘플푸드").querySelector(".sa-got").textContent,
                     "이미 받은 분 1명");

  // 일부만 받은 분은 그대로 보낸다(받은 기업은 서버가 그 분 문구에서 뺀다).
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids, [101]);
  const tag = sCard(t.dom, "가소싱").querySelector(".share-tag");
  assert.strictEqual(tag.hidden, false);
  assert.ok(/1곳 이미 받음 — 그 기업은 빼고 보냅니다/.test(tag.textContent), tag.textContent);
  assert.ok(/일부 받은 분 1명/.test(t.dom.document.getElementById("shared-count").textContent));
}

// --- ④ 고른 기업을 모두 받은 분 — 체크를 남긴 채 안 보낸다 ------------------------
{
  const confirms = [];
  const t = setup({ confirm: function (m) { confirms.push(m); return true; } });
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  selectAll(t.dom);                                   // 가소싱 · 다소싱(같은 갈래 둘)
  toggleSeriesA(t.dom, "다샘플푸드");                 // 303 — 둘 다 이미 받았다

  assert.strictEqual(sBox(t.dom, "가소싱").checked, true,
                     "체크를 꺼 버리면 기업을 바꿨을 때 다시 골라야 한다");
  assert.ok(sCard(t.dom, "가소싱").classList.contains("share-covered"), "흐리게 표시되지 않았다");
  assert.strictEqual(sCard(t.dom, "가소싱").hidden, false, "고른 사람은 보여야 한다");
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids, [],
                         "이미 다 받은 분께 또 보낸다");
  assert.strictEqual(t.dom.document.getElementById("send-btn").disabled, true,
                     "보낼 분이 없는데 발송 단추가 눌린다");
  assert.ok(/모두 받은 분 2명 제외/.test(
    t.dom.document.getElementById("shared-count").textContent));
  assert.ok(/모두 이미 받음/.test(sCard(t.dom, "다소싱").querySelector(".share-tag").textContent));
  assert.strictEqual(saCard(t.dom, "다샘플푸드").querySelector(".sa-got").textContent,
                     "이미 받은 분 2명");

  // [전체선택]은 빠지는 분을 켜지 않는다(조건에 안 맞는 것으로 친다).
  t.dom.document.getElementById("clear-all-contacts").fire("click");
  selectAll(t.dom);
  assert.strictEqual(sBox(t.dom, "가소싱").checked, false, "[전체선택]이 이미 받은 분을 켰다");

  // 기업을 하나 더 고르면(아무도 안 받은 302) 다시 보낼 분이 된다.
  toggleSourcing(t.dom, "가소싱");
  toggleSeriesA(t.dom, "나샘플로보");
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids, [101],
                         "기업을 더 골랐는데 다시 들어오지 않는다 — 체크가 남아 있어야 한다");

  // 제외를 끄면 고른 기업 그대로 다 간다 — `include_shared`.
  const box = t.dom.document.getElementById("exclude-shared");
  toggleSourcing(t.dom, "다소싱");
  box.checked = false;
  box.fire("change");
  const body = lastPreview(t.fetch).body;
  assert.strictEqual(body.include_shared, true);
  assert.deepStrictEqual(body.contact_ids.slice().sort(), [101, 103]);
  assert.ok(/그대로 다시 보냅니다/.test(t.dom.document.getElementById("shared-count").textContent));

  // 발송 — 고른 기업 · 글 · 받는 분이 그대로 실린다.
  t.dom.document.getElementById("send-btn").fire("click");
  const sent = calls(t.fetch, "/api/deals/send").pop();
  assert.ok(sent, "발송 요청이 안 나갔다");
  assert.strictEqual(sent.body.topic, SHARE);
  assert.deepStrictEqual(sent.body.series_a_ids, [303, 302]);
  assert.deepStrictEqual(sent.body.company_ids, []);
  assert.strictEqual(sent.body.include_shared, true);
  assert.ok(/Series A 딜 공유 — 2개 기업/.test(confirms.pop()),
            "확인창이 무엇을 보내는지 말하지 않는다");
}

// --- ⑤ 딜 소싱 화면의 [Series A 딜 소개] 링크로 열면 ---------------------------
{
  // 1 은 투자사 담당자 번호와 같은 숫자다 — 그 목록에 켜지면 안 된다.
  const t = setup({ search: "?mode=sourcing&topic=sourcing_deal_share&contacts=101,102,103,1&series_a=303,999" });
  assert.strictEqual(t.dom.seriesAPicker.hidden, false, "Series A 딜 공유로 열리지 않았다");
  assert.strictEqual(sBox(t.dom, "가소싱").checked, true);
  assert.strictEqual(sBox(t.dom, "다소싱").checked, true);
  assert.strictEqual(sBox(t.dom, "나소싱").checked, false, "다른 갈래 분이 골라졌다");
  assert.strictEqual(t.dom.cards[0].querySelector(".contact-cb").checked, false,
                     "딜 소싱 번호로 투자사 담당자가 켜졌다 — 다른 탭으로 가면 그 분께 나간다");
  assert.strictEqual(saCard(t.dom, "다샘플푸드").querySelector(".sa-cb").checked, true);
  const warn = t.dom.document.getElementById("send-warnings").innerHTML;
  assert.ok(/딜 소싱 대상 2명은 고르지 않았습니다/.test(warn), warn);
  assert.ok(/Series A 이상 기업 1개를 목록에서 찾지 못했습니다/.test(warn), warn);
}

// --- ⑥ 다른 글로 돌아가면 IR 기업 목록 ------------------------------------------
{
  const t = setup();
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  toggleSeriesA(t.dom, "가샘플바이오");
  pickTopic(t.dom, "sourcing_intro");
  assert.strictEqual(t.dom.seriesAPicker.hidden, true);
  assert.strictEqual(t.dom.document.getElementById("company-list").hidden, false);
  assert.strictEqual(t.dom.companyPanel.classList.contains("dimmed"), true,
                     "처음 안내는 기업 없이 문구만 나간다");
  const body = lastPreview(t.fetch).body;
  assert.deepStrictEqual(body.series_a_ids, [], "처음 안내에 Series A 기업이 실렸다");
  assert.strictEqual(t.dom.document.getElementById("shared-note").hidden, true);

  // 다른 탭에 갔다 오면 처음 안내로 — 고르개도 IR 기업 목록으로.
  pickTopic(t.dom, SHARE);
  pickMode(t.dom, "deal");
  assert.strictEqual(t.dom.seriesAPicker.hidden, true);
  pickMode(t.dom, "sourcing");
  assert.strictEqual(lastPreview(t.fetch).body.topic, "sourcing_intro");
}

console.log("series_a_share_test: ok");
