// 딜 소싱 제안의 [보낼 문구 › Series A 딜 공유] — 화면 쪽.
// (node tests/js/series_a_share_test.js)
//
// 여기서 못 박는 것.
//   ① [Series A 딜 공유] 를 누르면 ① 칸이 `Series A 이상 기업` 고르개로 바뀌고
//      (IR 기업 목록은 숨는다), 다른 갈래 카드는 빠진다(숨고 체크가 꺼진다)
//   ② 고른 차례가 곧 번호다 — 미리보기 · 발송이 `series_a_ids` 를 고른 차례로
//      싣고, IR 기업 칸(`company_ids`)은 비운다
//   ③ 고르개 카드마다 `이미 받은 분 N명` — 지금 고른 받는 분 중 그 기업을 받은 분
//   ④ [이미 이 기업들을 받은 분 제외](기본 켬) — 보낼 기업이 안 남는 분은
//      체크를 남긴 채 보내지 않고(흐리게 · 딱지), 일부만 받은 분은 그대로 보낸다
//      (서버가 받은 기업을 뺀다). 끄면 `include_shared` 가 실린다
//   ⑦ 본인이 공유한 딜 — 고르개 카드의 `본인 공유 N명 제외`, 받는 분 딱지,
//      제외를 꺼도 본인 공유는 빠진다(본인 공유만 남으면 그 분은 빠진다)
//   ⑧ 사람당 보낼 기업 수 — 기본 2 · 안내 글 · 바꾸면 `per_person` · 딱지가 따라온다,
//      빈 값 · 범위 밖은 되돌려 적는다
//   ⑨ 미리보기 위 `보내는 기업` · `뺀 기업(까닭)` 줄 — 서버가 지은 그대로
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
  assert.strictEqual(body.per_person, 2, "사람당 기본 2개가 아니다");
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
  assert.strictEqual(tag.textContent, "이미 받은 1곳 빼고 — 1곳 보냅니다");
  assert.ok(/이미 받은 분 1명은 받은 기업을 빼고/.test(
    t.dom.document.getElementById("shared-count").textContent));
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
  assert.ok(/보낼 기업 없는 분 2명 제외/.test(
    t.dom.document.getElementById("shared-count").textContent));
  assert.strictEqual(sCard(t.dom, "다소싱").querySelector(".share-tag").textContent,
                     "보낼 기업 없음 (본인 공유/이미 받음) — 이번엔 빠집니다");
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
  assert.ok(/이미 받은 분 2명에게도 받은 기업을 다시/.test(
    t.dom.document.getElementById("shared-count").textContent));

  // 발송 — 고른 기업 · 글 · 받는 분이 그대로 실린다.
  t.dom.document.getElementById("send-btn").fire("click");
  const sent = calls(t.fetch, "/api/deals/send").pop();
  assert.ok(sent, "발송 요청이 안 나갔다");
  assert.strictEqual(sent.body.topic, SHARE);
  assert.deepStrictEqual(sent.body.series_a_ids, [303, 302]);
  assert.deepStrictEqual(sent.body.company_ids, []);
  assert.strictEqual(sent.body.include_shared, true);
  assert.strictEqual(sent.body.per_person, 2);
  assert.ok(/Series A 딜 공유 — 2개 기업 중 사람마다 2개씩/.test(confirms.pop()),
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

// --- ⑦ 본인이 공유한 딜 -----------------------------------------------------------
{
  const t = setup();
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  // 아직 받는 분이 없다 — `본인 공유` 딱지는 없다.
  assert.strictEqual(saCard(t.dom, "라샘플헬스").querySelector(".sa-own").hidden, true);
  selectAll(t.dom);                                   // 가소싱(101) · 다소싱(103)
  // 고르기 전에도 센다 — 고를지 정하는 자리다.
  const own304 = saCard(t.dom, "라샘플헬스").querySelector(".sa-own");
  assert.strictEqual(own304.hidden, false, "이 딜을 공유해 준 분이 골라졌는데 말하지 않는다");
  assert.strictEqual(own304.textContent, "본인 공유 1명 제외");
  assert.strictEqual(saCard(t.dom, "마샘플에너지").querySelector(".sa-own").textContent,
                     "본인 공유 1명 제외");
  assert.strictEqual(saCard(t.dom, "나샘플로보").querySelector(".sa-own").hidden, true);

  // 넷을 고른다 — 사람마다 본인 공유를 빼고 앞에서부터 2개.
  ["라샘플헬스", "마샘플에너지", "나샘플로보", "바샘플소재"].forEach(function (n) {
    toggleSeriesA(t.dom, n);
  });
  const body = lastPreview(t.fetch).body;
  assert.deepStrictEqual(body.series_a_ids, [304, 305, 302, 306]);
  assert.deepStrictEqual(body.contact_ids.slice().sort(), [101, 103],
                         "본인 공유가 하나 든 분은 그대로 보낸다");
  assert.strictEqual(sCard(t.dom, "가소싱").querySelector(".share-tag").textContent,
                     "본인 공유 1곳 빼고 — 2곳 보냅니다");
  assert.strictEqual(sCard(t.dom, "다소싱").querySelector(".share-tag").textContent,
                     "본인 공유 1곳 빼고 — 2곳 보냅니다");
  assert.strictEqual(t.dom.document.getElementById("shared-count").textContent,
                     "본인 공유 딜이 든 분 2명은 그 기업을 빼고 — 사람마다 앞에서부터 2개씩 보냅니다");
}
{
  // 본인 공유만 고르면 그 분은 빠진다 — 제외를 꺼도(그 칸은 이미 받은 기업만 다룬다).
  const t = setup();
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  selectAll(t.dom);
  toggleSeriesA(t.dom, "마샘플에너지");               // 305 — 가소싱(101)이 공유
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids, [103],
                         "자기가 공유한 딜을 그 분께 다시 보낸다");
  assert.ok(sCard(t.dom, "가소싱").classList.contains("share-covered"));
  assert.strictEqual(sBox(t.dom, "가소싱").checked, true, "체크는 남긴다");
  const box = t.dom.document.getElementById("exclude-shared");
  box.checked = false;
  box.fire("change");
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids, [103],
                         "제외를 껐다고 본인 공유 딜이 그 분께 간다");
  // 본인 공유 + 이미 받음 — 제외를 켜면 남는 게 없고, 끄면 이미 받은 것은 다시 간다.
  box.checked = true;
  box.fire("change");
  toggleSeriesA(t.dom, "가샘플바이오");               // 301 — 가소싱이 이미 받음
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids, [103]);
  assert.strictEqual(sCard(t.dom, "가소싱").querySelector(".share-tag").textContent,
                     "보낼 기업 없음 (본인 공유/이미 받음) — 이번엔 빠집니다");
  box.checked = false;
  box.fire("change");
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids.slice().sort(), [101, 103]);
  assert.strictEqual(sCard(t.dom, "가소싱").querySelector(".share-tag").textContent,
                     "본인 공유 1곳 빼고 · 이미 받은 1곳도 다시 — 1곳 보냅니다");
}

// --- ⑧ 사람당 보낼 기업 수 --------------------------------------------------------
{
  const confirms = [];
  const t = setup({ confirm: function (m) { confirms.push(m); return true; } });
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  const box = t.dom.document.getElementById("sa-per-person");
  const hint = t.dom.document.getElementById("sa-per-person-hint");
  toggleSourcing(t.dom, "가소싱");
  ["나샘플로보", "바샘플소재", "가샘플바이오", "라샘플헬스"].forEach(function (n) {
    toggleSeriesA(t.dom, n);
  });
  // 가소싱은 301 을 이미 받았다 — 남는 셋 중 앞의 둘.
  assert.strictEqual(sCard(t.dom, "가소싱").querySelector(".share-tag").textContent,
                     "이미 받은 1곳 빼고 — 2곳 보냅니다");
  assert.ok(/앞에서부터 2개씩 나갑니다/.test(t.dom.document.getElementById("ss-note").textContent));

  box.value = "3";
  box.fire("input");
  assert.strictEqual(lastPreview(t.fetch).body.per_person, 3);
  assert.strictEqual(hint.textContent,
                     "기업을 3~6개 고르면 사람마다 본인 공유·이미 받은 기업을 빼고 앞에서부터 3개씩 나갑니다.");
  assert.strictEqual(sCard(t.dom, "가소싱").querySelector(".share-tag").textContent,
                     "이미 받은 1곳 빼고 — 3곳 보냅니다");

  // 남는 것보다 크면 남은 만큼만 — 그래도 보낸다.
  box.value = "5";
  box.fire("change");
  assert.strictEqual(sCard(t.dom, "가소싱").querySelector(".share-tag").textContent,
                     "이미 받은 1곳 빼고 — 3곳 보냅니다");
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids, [101]);

  // 빈 값 · 범위 밖 — 손을 떼면 읽은 값으로 되돌려 적는다(서버는 1~10 밖이면 멈춘다).
  box.value = "";
  box.fire("change");
  assert.strictEqual(box.value, "2");
  assert.strictEqual(lastPreview(t.fetch).body.per_person, 2);
  box.value = "99";
  box.fire("change");
  assert.strictEqual(box.value, "10");
  assert.strictEqual(hint.textContent,
                     "기업을 10개 고르면 사람마다 본인 공유·이미 받은 기업을 빼고 앞에서부터 10개씩 나갑니다.");
  box.value = "2";
  box.fire("change");

  t.dom.document.getElementById("send-btn").fire("click");
  const sent = calls(t.fetch, "/api/deals/send").pop();
  assert.strictEqual(sent.body.per_person, 2);
  assert.deepStrictEqual(sent.body.series_a_ids, [302, 306, 301, 304], "고른 차례가 아니다");
  assert.ok(/4개 기업 중 사람마다 2개씩/.test(confirms.pop()));
}

// --- ⑨ 미리보기 위 `보내는 기업` · `뺀 기업` ----------------------------------------
{
  const plan = {
    send: [{ id: 302, name: "나샘플로보", label: "[기업1]" },
           { id: 306, name: "바샘플소재", label: "[기업2]" }],
    dropped: [{ id: 305, name: "마샘플에너지", reason: "본인이 공유한 딜" },
              { id: 301, name: "가샘플바이오", reason: "이미 받음" },
              { id: 304, name: "라샘플헬스", reason: "사람당 2개 — 이번엔 안 보냄" }]
  };
  const fetch = fakeFetch([deals_.previewReply([
    { contact_id: 101, name: "가소싱", title: "", message: "글", warnings: [],
      series_a: plan },
    { contact_id: 103, name: "다소싱", title: "", message: "글", warnings: [],
      series_a: { send: [], dropped: [{ id: 304, name: "라샘플헬스",
                                        reason: "본인이 공유한 딜" }] } }
  ])]);
  const dom = run(null, { fetch: fetch });
  pickMode(dom, "sourcing");
  pickTopic(dom, SHARE);
  dom.document.getElementById("refresh-preview").fire("click");
  const area = dom.document.getElementById("preview-area").innerHTML;
  assert.ok(/data-testid="sa-plan"/.test(area), "보내는 기업 · 뺀 기업 줄이 없다");
  assert.ok(area.indexOf("<b>보내는 기업</b> [기업1] 나샘플로보 · [기업2] 바샘플소재") >= 0, area);
  assert.ok(area.indexOf('<span class="sa-drop own">마샘플에너지 — 본인이 공유한 딜</span>') >= 0,
            "본인이 공유한 딜이라 뺀 것을 말하지 않는다");
  assert.ok(area.indexOf("가샘플바이오 — 이미 받음") >= 0);
  assert.ok(area.indexOf("라샘플헬스 — 사람당 2개 — 이번엔 안 보냄") >= 0);
  deals_.pickPreviewTab(dom, 1);
  const second = dom.document.getElementById("preview-area").innerHTML;
  assert.ok(/보내는 기업<\/b> <span class="sa-drop own">없음/.test(second), second);
}

// ── PR #287 · #288 리뷰 ──────────────────────────────────────────────────────

// 미리보기 서버 — 요청마다 **받은 것을 그대로 적은 글**을 돌려준다(고친 글이
// 버려졌는지 · 무엇으로 다시 지었는지 보려고).
function previewServer(url, body) {
  if (url !== "/api/deals/preview") return { ok: true, d: { job_id: 1, skipped: [] } };
  return deals_.previewReply((body.contact_ids || []).map(function (id) {
    return { contact_id: id, name: "n" + id, title: "", warnings: [],
             message: "글 " + (body.series_a_ids || []).join(",") + " / " + body.per_person +
                      " / " + body.include_shared };
  }));
}
function edit(dom, text) {
  const ta = dom.document.getElementById("bubble-edit");
  assert.ok(ta, "미리보기 글 칸이 없다");
  ta.value = text;
  ta.fire("input");
}
function warnText(dom) { return dom.document.getElementById("send-warnings").innerHTML; }
function sendOverrides(dom, fetch) {
  dom.document.getElementById("send-btn").fire("click");
  const sent = calls(fetch, "/api/deals/send").pop();
  assert.ok(sent, "발송 요청이 안 나갔다");
  return sent.body.overrides;
}
function yes() { return true; }

// --- ⑩ 고친 글은 기업 · 사람당 N · 제외 칸이 바뀌면 버린다(그리고 말한다) -------
{
  const fetch = fakeFetch(previewServer);
  const dom = run(null, { fetch: fetch, setTimeout: now, confirm: yes });
  pickMode(dom, "sourcing");
  pickTopic(dom, SHARE);
  toggleSourcing(dom, "가소싱");
  toggleSeriesA(dom, "나샘플로보");
  edit(dom, "고친 글");
  // 받는 분을 더 고르는 것은 상관없다 — 그 분 글은 남의 선택과 무관하다
  toggleSourcing(dom, "다소싱");
  assert.deepStrictEqual(sendOverrides(dom, fetch), [{ contact_id: 101, message: "고친 글" }]);

  // 기업을 바꾸면 고친 글의 기업 덩어리와 실제로 고른 기업이 갈린다 — 버린다
  toggleSeriesA(dom, "바샘플소재");
  assert.ok(/고쳐 둔 문구 1건을 버렸습니다/.test(warnText(dom)), warnText(dom));
  assert.strictEqual(dom.document.getElementById("bubble-edit").value, "글 302,306 / 2 / false");
  assert.deepStrictEqual(sendOverrides(dom, fetch), [], "기업을 바꿨는데 예전에 고친 글이 나간다");

  // 사람당 N 을 바꿔도
  edit(dom, "또 고친 글");
  const per = dom.document.getElementById("sa-per-person");
  per.value = "3";
  per.fire("input");
  assert.deepStrictEqual(sendOverrides(dom, fetch), [], "사람당 개수를 바꿨는데 고친 글이 나간다");
  assert.ok(/버렸습니다/.test(warnText(dom)));
  // 같은 값으로 손을 떼는 것은 바꾼 것이 아니다
  edit(dom, "세 번째 고친 글");
  per.fire("change");
  assert.deepStrictEqual(sendOverrides(dom, fetch),
                         [{ contact_id: 101, message: "세 번째 고친 글" }]);
  // [이미 이 기업들을 받은 분 제외]를 바꿔도
  const ex = dom.document.getElementById("exclude-shared");
  ex.checked = false;
  ex.fire("change");
  assert.deepStrictEqual(sendOverrides(dom, fetch), [], "제외 칸을 바꿨는데 고친 글이 나간다");
}
{
  // 미리보기가 아직 안 왔을 때(손이 멈추길 기다리는 0.4초) 눌러도 고친 글은 안 나간다
  const timers = [];
  const fetch = fakeFetch(previewServer);
  const dom = run(null, { fetch: fetch, confirm: yes,
                          setTimeout: function (fn) { timers.push(fn); return timers.length; } });
  const flush = function () { while (timers.length) timers.shift()(); };
  pickMode(dom, "sourcing");
  pickTopic(dom, SHARE);
  toggleSourcing(dom, "가소싱");
  toggleSeriesA(dom, "나샘플로보");
  flush();
  edit(dom, "고친 글");
  toggleSeriesA(dom, "바샘플소재");
  // 보이는 칸도 곧바로 원래 글로 — 고친 글이 떠 있는데 안 나가면 헷갈린다
  assert.strictEqual(dom.document.getElementById("bubble-edit").value, "글 302 / 2 / false");
  assert.deepStrictEqual(sendOverrides(dom, fetch), [],
                         "다시 그리기 전의 옛 미리보기에서 고친 글을 집어 보냈다");
}

// --- ⑪ [전체해제] — 고른 분이 모두 '보낼 기업 없음' 이어도 눌린다 -------------------
{
  const t = setup();
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  selectAll(t.dom);
  toggleSeriesA(t.dom, "다샘플푸드");                 // 303 — 둘 다 이미 받았다
  const clear = t.dom.document.getElementById("clear-all-contacts");
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids, []);
  assert.strictEqual(clear.disabled, false, "체크가 남아 있는데 [전체해제]가 꺼졌다");
  clear.fire("click");
  assert.strictEqual(sBox(t.dom, "가소싱").checked, false);
  assert.strictEqual(sBox(t.dom, "다소싱").checked, false);
  assert.strictEqual(clear.disabled, true);
}

// --- ⑫ '다시 보냅니다' 의 N 은 고른 분만 ------------------------------------------
{
  const t = setup();
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  const ex = t.dom.document.getElementById("exclude-shared");
  ex.checked = false;
  ex.fire("change");
  toggleSourcing(t.dom, "가소싱");                    // 다소싱(103)도 303 을 받았지만 안 골랐다
  toggleSeriesA(t.dom, "다샘플푸드");
  const note = t.dom.document.getElementById("shared-count").textContent;
  assert.ok(/이미 받은 분 1명에게도 받은 기업을 다시/.test(note), note);
}

// --- ⑬ 사람당 N 바깥의 이미 받은 기업은 '다시 보냄' 에 안 든다 -----------------------
{
  const t = setup();
  pickMode(t.dom, "sourcing");
  pickTopic(t.dom, SHARE);
  const per = t.dom.document.getElementById("sa-per-person");
  per.value = "1";
  per.fire("change");
  const ex = t.dom.document.getElementById("exclude-shared");
  ex.checked = false;
  ex.fire("change");
  toggleSourcing(t.dom, "가소싱");
  toggleSeriesA(t.dom, "나샘플로보");                 // 302 — [기업1]
  toggleSeriesA(t.dom, "다샘플푸드");                 // 303 — 가소싱이 받았지만 1개 바깥
  const tag = sCard(t.dom, "가소싱").querySelector(".share-tag");
  assert.ok(tag.hidden || !/다시/.test(tag.textContent), tag.textContent);
  const note = t.dom.document.getElementById("shared-count").textContent;
  assert.ok(!/다시/.test(note), note);
  // 2개로 늘리면 303 이 들어온다 — 그때는 다시 간다고 말한다
  per.value = "2";
  per.fire("change");
  assert.strictEqual(tag.textContent, "이미 받은 1곳도 다시 — 2곳 보냅니다");
  assert.ok(/이미 받은 분 1명에게도/.test(
    t.dom.document.getElementById("shared-count").textContent));
}

// --- ⑭ 새로고침 뒤 칸 값과 안내가 같다 ---------------------------------------------
{
  const fetch = fakeFetch([]);
  const dom = run(null, { fetch: fetch, setTimeout: now, prepare: function (d) {
    d.document.getElementById("sa-per-person").value = "3";   // 브라우저가 되살린 값
  } });
  assert.strictEqual(dom.document.getElementById("sa-per-person-hint").textContent,
                     "기업을 3~6개 고르면 사람마다 본인 공유·이미 받은 기업을 빼고 앞에서부터 3개씩 나갑니다.");
}

// --- ⑮ 잠깐 [Series A 딜 공유]를 눌렀다 돌아가면 다른 갈래 체크가 돌아온다 ------------
{
  const t = setup();
  pickMode(t.dom, "sourcing");
  selectAll(t.dom);                                   // 처음 안내 — 셋 다
  pickTopic(t.dom, SHARE);
  assert.strictEqual(sBox(t.dom, "나소싱").checked, false);
  pickTopic(t.dom, "sourcing_intro");
  assert.strictEqual(sBox(t.dom, "나소싱").checked, true, "다른 갈래 분 체크가 사라졌다");
  assert.deepStrictEqual(lastPreview(t.fetch).body.contact_ids.slice().sort(), [101, 102, 103]);

  // 다른 탭에 갔다 와도(처음 안내로 돌아온다) 같다
  pickTopic(t.dom, SHARE);
  pickMode(t.dom, "deal");
  pickMode(t.dom, "sourcing");
  assert.strictEqual(sBox(t.dom, "나소싱").checked, true, "탭을 옮겼더니 다른 갈래 체크가 사라졌다");

  // Series A 딜 공유에서 [전체해제]를 눌렀으면 돌아와도 비어 있다(사람이 다 푼 것이다)
  pickTopic(t.dom, SHARE);
  t.dom.document.getElementById("clear-all-contacts").fire("click");
  pickTopic(t.dom, "sourcing_intro");
  assert.strictEqual(sBox(t.dom, "나소싱").checked, false);
}

// --- ⑯ 이미 받은 분 · 본인 공유는 고를 때 서버에서 읽고, 창으로 돌아오면 다시 읽는다 ---
{
  let state = { companies: [{ id: 302, sent_to: [101], own_by: [] },
                            { id: 301, sent_to: [], own_by: [103] }] };
  const fetch = fakeFetch([], null, { "/api/series-a-share/state": function () { return state; } });
  const dom = run(null, { fetch: fetch, setTimeout: now });
  pickMode(dom, "sourcing");
  assert.strictEqual(calls(fetch, "/api/series-a-share/state").length, 0,
                     "Series A 딜 공유를 고르기 전에 읽었다");
  pickTopic(dom, SHARE);
  assert.strictEqual(calls(fetch, "/api/series-a-share/state").length, 1);
  toggleSourcing(dom, "가소싱");
  toggleSourcing(dom, "다소싱");
  toggleSeriesA(dom, "나샘플로보");                   // 302
  assert.strictEqual(saCard(dom, "나샘플로보").querySelector(".sa-got").textContent,
                     "이미 받은 분 1명");
  const count = saCard(dom, "나샘플로보").querySelector(".sa-count");
  assert.strictEqual(count.hidden, false);
  assert.strictEqual(count.textContent, "공유 1명");
  // 그린 때의 값(301 을 가소싱이 받음)은 서버가 읽어 준 값으로 바뀐다
  assert.strictEqual(saCard(dom, "가샘플바이오").querySelector(".sa-got").hidden, true);
  assert.strictEqual(saCard(dom, "가샘플바이오").querySelector(".sa-own").textContent,
                     "본인 공유 1명 제외");
  assert.deepStrictEqual(lastPreview(fetch).body.contact_ids, [103]);

  // 창으로 돌아오면 다시 읽는다 — 그 사이 회차를 [중단]해 302 를 안 받은 것이 됐다
  state = { companies: [{ id: 302, sent_to: [], own_by: [] }] };
  dom.root.fire("visibilitychange");
  assert.strictEqual(calls(fetch, "/api/series-a-share/state").length, 2);
  assert.strictEqual(saCard(dom, "나샘플로보").querySelector(".sa-got").hidden, true);
  assert.strictEqual(count.hidden, true);
  assert.deepStrictEqual(lastPreview(fetch).body.contact_ids.slice().sort(), [101, 103]);
}

console.log("series_a_share_test: ok");
