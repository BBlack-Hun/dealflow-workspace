// IR 자료 전달 — **고른 차례는 번호가 아니다.** (node tests/js/deals_ir_number_test.js)
//
// 딜 소개 탭에서는 고른 차례가 곧 문구의 번호라, 카드에 그 번호를 배지로
// 띄운다(`data-pick-order`). 자료 전달은 다르다 — 그때의 번호는 **딜 소개에서
// 이미 붙은 번호**이고(`app/services/deal_numbers.py`), 투자사가 "2번 주세요"
// 라고 답한 그 번호다. 담당자마다 다르므로 카드 하나에 적을 수 있는 값이 아니다.
//
// 그런데도 고른 차례를 배지로 띄우면 화면은 `1`, 나가는 문구는 `2번 기업 …` 이
// 되어 **어느 쪽이 맞는지 알 수 없다.** 그래서 카드 배지는 비운다
// (`no-pick-badge` — CSS 가 그 표시를 읽는지는 파이썬 쪽이 따로 본다).
//
// **차례 자체는 그대로 쓴다.** 문구가 기업을 짚는 차례이자 [보낼 자료] 목록의
// 차례라서, 여기서 차례까지 버리면 화면과 문구가 다른 차례로 갈린다.
//
// ## 그러면 번호는 어디에 적나 — **[보낼 자료] 목록에**
//
// 자료는 사람이 PC 카톡에 손으로 붙이는데, 번호 차례대로 붙여야 한다. 화면에
// 번호가 없으면 어느 것이 몇 번인지 알 수가 없다. 카드에는 못 적지만
// (담당자마다 다르다) 미리보기는 **담당자별로 한 통씩** 보여 주므로, 그 옆의
// [보낼 자료] 목록은 지금 열어 둔 담당자의 번호를 적을 수 있다 — 서버가 문구와
// 같은 응답에 실어 준 값이다(`attachments[].no`).
//
// **화면과 문구가 갈리면 이 일을 한 뜻이 없다.** 그래서 아래 검사들은 화면에
// 뜬 번호를 문구에서 뽑은 번호와 직접 맞대 본다.
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

function irRows(dom) {
  return Array.prototype.slice
    .call(dom.document.getElementById("ir-links").children)
    .map(function (li) { return li.innerHTML; });
}

function irNames(dom) {
  return irRows(dom).map(function (row) {
    return [A, B, C].filter(function (n) { return row.indexOf(n) >= 0; })[0];
  });
}

// 목록에 **보이는** 번호 — `{기업명: 번호}`. 번호가 없으면 넣지 않는다.
function irNumbers(dom) {
  const out = {};
  irRows(dom).forEach(function (row) {
    const name = [A, B, C].filter(function (n) { return row.indexOf(n) >= 0; })[0];
    const m = /(\d+)번/.exec(row);
    if (name && m) out[name] = parseInt(m[1], 10);
  });
  return out;
}

// 문구가 짚는 번호 — `{기업명: 번호}`. 서버가 만든 그 문장에서 그대로 읽는다
// (규칙을 옮겨 적으면 두 벌이 되어, 둘 다 틀려도 통과한다).
function messageNumbers(text) {
  const out = {};
  [A, B, C].forEach(function (name) {
    const m = new RegExp("(\\d+)번 기업 " + name).exec(text || "");
    if (m) out[name] = parseInt(m[1], 10);
  });
  return out;
}

// 서버가 돌려주는 한 통. `pairs` 는 `[[기업명, 번호|null], …]` 이고 **고른
// 차례**다 — 문구도 이 차례로 짚는다(번호가 오름차순이 아닐 수 있다).
function person(name, pairs) {
  return {
    contact_id: name.length,
    name: name,
    title: "심사역",
    room_name: name + " 심사역님",
    message: pairs.map(function (pair) {
      return pair[1] ? pair[1] + "번 기업 " + pair[0] : pair[0];
    }).join(", ") + " IR deck 먼저 전달드리겠습니다.",
    parts: [],
    warnings: [],
    attachments: pairs.map(function (pair) {
      return { name: pair[0], file: pair[0] + "_IR.pdf", no: pair[1] };
    })
  };
}

function reply(previews) { return deals_.previewReply(previews); }

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
  const fetch = deals_.fakeFetch([reply([person("가담당", [[B, 3], [A, 2]])])]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, B);      // 목록 2번째를 먼저
  deals_.toggleCompany(dom, A);      // 목록 1번째를 나중에

  const previews = fetch.calls.filter(function (c) {
    return c.url === "/api/deals/preview";
  });
  assert.ok(!previews.length, "손이 멈추기 전에 미리보기를 불렀다");

  dom.document.getElementById("refresh-preview").fire("click");
  const sent = fetch.calls.filter(function (c) {
    return c.url === "/api/deals/preview";
  });
  assert.ok(sent.length, "미리보기를 부르지 않았다");
  const last = sent[sent.length - 1];
  assert.deepStrictEqual(last.body.company_ids, [idOf(dom, B), idOf(dom, A)],
    "미리보기가 **목록 차례**로 나갔다: " + JSON.stringify(last.body.company_ids));
  assert.strictEqual(last.body.mode, "ir");

  assert.deepStrictEqual(irNames(dom), [B, A],
    "[보낼 자료] 목록이 **목록 차례**로 섰다 — 고른 차례가 아니다");
}

// ── 4) ★★ 목록의 번호가 **문구의 번호와 같은가** ──────────────────────────
//
// 이 일의 알맹이다. 자료는 사람이 PC 카톡에 손으로 붙이는데, 화면에 적힌
// 번호가 곧 붙이는 차례다. 화면이 `1·2` 라고 적는데 문구가 "3번 기업 다라헬스,
// 2번 기업 가나애그" 라고 하면 **엉뚱한 자료가 3번 자리에 붙는다.**
//
// 그래서 화면에 뜬 번호를 문구에서 뽑은 번호와 **직접 견준다** — 규칙을 옮겨
// 적어 견주면 두 벌이 되어, 둘 다 틀려도 통과한다.
{
  // 서버가 돌려준 값. 번호는 딜 소개에서 붙은 것이라 고른 차례와 다르다
  // (다라헬스를 먼저 골랐지만 3번이다).
  const fetch = deals_.fakeFetch([reply([person("가담당", [[B, 3], [A, 2]])])]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, B);
  deals_.toggleCompany(dom, A);
  dom.document.getElementById("refresh-preview").fire("click");

  const shown = irNumbers(dom);
  assert.deepStrictEqual(shown, { [B]: 3, [A]: 2 },
    "[보낼 자료] 목록에 번호가 안 적혔거나 딴 번호다: " + JSON.stringify(shown));

  // ★ 화면과 문구를 맞대 본다.
  const said = messageNumbers(dom.document.getElementById("bubble-edit").value);
  assert.deepStrictEqual(shown, said,
    "화면의 번호와 문구의 번호가 갈렸다 — 화면 " + JSON.stringify(shown) +
    " · 문구 " + JSON.stringify(said));
}

// ── 5) ★ 담당자를 바꾸면 번호도 바뀐다 ─────────────────────────────────────
//
// 같은 기업이 A 담당자에겐 2번, B 담당자에겐 5번이다. 목록에 하나로 적을 수
// 없어서 **지금 열어 둔 미리보기 탭**을 따른다. 탭을 바꿨는데 번호가 그대로면,
// 앞 담당자의 번호로 자료를 붙인다.
{
  const fetch = deals_.fakeFetch([reply([
    person("가담당", [[B, 3], [A, 2]]),
    person("나담당", [[B, 1], [A, 5]])
  ])]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, B);
  deals_.toggleCompany(dom, A);
  dom.document.getElementById("refresh-preview").fire("click");

  assert.deepStrictEqual(irNumbers(dom), { [B]: 3, [A]: 2 },
    "첫 탭(가담당)의 번호가 아니다");

  deals_.pickPreviewTab(dom, 1);
  assert.deepStrictEqual(irNumbers(dom), { [B]: 1, [A]: 5 },
    "탭을 바꿨는데 [보낼 자료] 목록이 앞 담당자의 번호를 그대로 달고 있다");
  assert.deepStrictEqual(
    irNumbers(dom),
    messageNumbers(dom.document.getElementById("bubble-edit").value),
    "탭을 바꾼 뒤 화면과 문구의 번호가 갈렸다");

  // 되돌아와도 마찬가지다.
  deals_.pickPreviewTab(dom, 0);
  assert.deepStrictEqual(irNumbers(dom), { [B]: 3, [A]: 2 },
    "탭을 되돌렸는데 번호가 안 돌아왔다");
}

// ── 6) ★ 번호가 없는 기업은 **지어내지 않는다** ────────────────────────────
//
// 지난 딜 소개에 없던 기업이다. 문구도 그 기업만 이름으로 나가므로(번호 없이)
// 목록도 그래야 한다 — 여기서 `1` 을 붙이면 받는 쪽이 자기 목록에서 찾다가
// 못 찾는다. 자리를 비워 두지도 않는다(덜 그려진 것으로 읽힌다).
{
  const fetch = deals_.fakeFetch([reply([person("가담당", [[B, 3], [C, null]])])]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, B);
  deals_.toggleCompany(dom, C);
  dom.document.getElementById("refresh-preview").fire("click");

  const rows = irRows(dom);
  assert.ok(/3번/.test(rows[0]), "번호가 있는 기업에 번호가 안 붙었다: " + rows[0]);
  assert.ok(!/\d번/.test(rows[1]),
    "지난 회차에 없던 기업에 번호를 지어냈다: " + rows[1]);
  assert.ok(/번호 없음/.test(rows[1]),
    "번호가 없다는 것이 화면에 안 보인다: " + rows[1]);
  assert.deepStrictEqual(irNumbers(dom),
    messageNumbers(dom.document.getElementById("bubble-edit").value),
    "번호 없는 기업이 섞이자 화면과 문구가 갈렸다");

  const note = dom.document.getElementById("ir-no-note");
  assert.ok(note && !note.hidden && /번호 없음/.test(note.textContent),
    "왜 번호가 없는지 아무 데도 안 적혀 있다");
}

// ── 7) 아직 담당자를 안 골랐으면 번호를 적지 않는다 ────────────────────────
//
// 기본 문구에는 번호가 없다 — 번호는 담당자를 알아야 나온다. 그것을 "지난
// 회차에 없는 기업" 과 같은 말로 적으면, 있는 번호를 없다고 읽는다.
{
  const sample = person("○○○", [[B, null], [A, null]]);
  sample.sample = true;
  const fetch = deals_.fakeFetch([reply([sample])]);
  const dom = deals_.run(null, { fetch: fetch });

  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, B);
  deals_.toggleCompany(dom, A);
  dom.document.getElementById("refresh-preview").fire("click");

  const rows = irRows(dom);
  assert.strictEqual(rows.length, 2, "기본 문구에서 목록이 비었다");
  rows.forEach(function (row) {
    assert.ok(!/번호 없음/.test(row),
      "담당자를 안 골랐을 뿐인데 '번호 없음' 이라고 적었다: " + row);
  });
  const note = dom.document.getElementById("ir-no-note");
  assert.ok(note && !note.hidden && /담당자/.test(note.textContent),
    "번호가 왜 안 뜨는지 안 적혀 있다: " + (note && note.textContent));
}

console.log("ok — [보낼 자료] 목록의 번호가 문구의 번호와 같다");
