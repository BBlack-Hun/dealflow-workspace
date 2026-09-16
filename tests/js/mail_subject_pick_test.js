// 메일 제목을 **문구에서 골라 채우는가.**
// (node tests/js/mail_subject_pick_test.js)
//
// 격주로 나가는 홍보메일의 제목을 매번 손으로 적고 있었다. 문구 화면에는
// `홍보메일 제목`(`mail_subject`) 갈래가 등록만 돼 있고 아무 데서도 읽지
// 않았다 — 만들 수는 있는데 고를 데가 없었다.
//
// 여기서 지키려는 것 넷.
//
//   1. 고른 제목이 **칸에 들어간다** — 그 뒤 손볼 수 있어야 한다. 고른 것을
//      그대로 실어 보내면 회차마다 달라지는 한 마디를 덧붙일 자리가 없다.
//   2. **비우면 아무것도 안 실린다** — 서버가 회차명으로 떨어뜨리는 길
//      (`deals.py` 의 `_mail_subject`)이 살아 있어야 한다. 지금 그렇게 나가는
//      메일이 있다.
//   3. 여러 줄짜리 문구도 **한 줄**로 편다 — 메일 제목은 한 줄이다.
//   4. 고를 것이 없으면 빈 고르개를 세우지 않고 **만들러 가는 길**을 띄운다.
"use strict";
const assert = require("assert");
const deals = require("./_deals_dom.js");

// 문구 화면이 돌려주는 모양 그대로(`/api/templates` — `templates_crud.py`).
// **다른 갈래도 섞어 둔다** — 제목 고르개에 안내문이 딸려 오면 안 된다.
const TEMPLATES = [
  { id: 11, kind: "closing_day1", name: "기본 안내문", body: "핵심 딜 {개수}개사", mine: false },
  { id: 21, kind: "mail_subject", name: "정규 딜소개",
    body: "우리브이씨 딜 소개 드립니다", mine: false },
  { id: 22, kind: "mail_subject", name: "여러 줄 문구",
    body: "{투자사} {직함}\n이번 회차 딜 소개", mine: true }
];

function open(templates) {
  const fetch = deals.fakeFetch([{ ok: true, d: { job_id: 7 } }], templates);
  const dom = deals.run(null, { fetch: fetch, confirm: function () { return true; } });
  dom.fetch = fetch;
  return dom;
}

// 서버로 나간 발송 요청 한 벌.
function sent(dom) {
  const posts = dom.fetch.calls.filter(function (c) { return c.url === "/api/deals/send"; });
  assert.strictEqual(posts.length, 1, "발송 요청이 한 번 나가지 않았다");
  return posts[0].body;
}

function sel(dom) { return dom.document.getElementById("mail-subject-tpl"); }
function box(dom) { return dom.document.getElementById("mail-subject"); }
function optionValues(dom) {
  return sel(dom).children.map(function (o) { return o.value; });
}

// ── 1) 고르개에 서는 것은 제목 문구뿐 ──────────────────────────────────────
{
  const dom = open(TEMPLATES);
  assert.deepStrictEqual(optionValues(dom), ["", "21", "22"],
                         "제목 고르개에 딴 갈래 문구가 섞였다");
  assert.strictEqual(dom.document.getElementById("mail-subject-tpl-wrap").hidden, false,
                     "제목 문구가 있는데 고르개가 숨어 있다");
  assert.strictEqual(dom.document.getElementById("mail-subject-none").hidden, true,
                     "고를 것이 있는데 '만들러 가세요' 가 떠 있다");
  // 첫 항목은 **직접 입력**이다 — 화면을 열자마자 칸이 채워지면 회차명으로
  // 떨어지던 제목이 말없이 달라진다.
  assert.strictEqual(sel(dom).children[0].textContent, "직접 입력");
  assert.strictEqual(box(dom).value, "", "고르기도 전에 칸이 채워졌다");
}

// ── 2) 고르면 칸에 들어가고, 그 값이 그대로 서버로 간다 ────────────────────
{
  const dom = open(TEMPLATES);
  sel(dom).value = "21";
  sel(dom).fire("change");
  assert.strictEqual(box(dom).value, "우리브이씨 딜 소개 드립니다",
                     "고른 제목이 칸에 안 들어갔다");

  // 고른 뒤 **손본다** — 이것이 채워 넣기를 고른 까닭이다.
  box(dom).value = "우리브이씨 딜 소개 드립니다 (9월 3주차)";
  dom.document.getElementById("send-btn").fire("click");
  assert.strictEqual(sent(dom).subject, "우리브이씨 딜 소개 드립니다 (9월 3주차)",
                     "손본 제목이 아니라 딴 것이 실렸다");
}

// ── 3) 여러 줄 문구는 한 줄로 편다 ─────────────────────────────────────────
{
  const dom = open(TEMPLATES);
  sel(dom).value = "22";
  sel(dom).fire("change");
  assert.strictEqual(box(dom).value, "{투자사} {직함} 이번 회차 딜 소개",
                     "줄바꿈이 제목에 그대로 남았다 — 메일 제목은 한 줄이다");
  // 치환 자리는 **글자 그대로** 실어 보낸다 — 받는 사람마다 다른 값이라
  // 채우는 것은 서버 몫이다(`deals.py` 의 `_mail_subject`).
  assert.ok(box(dom).value.indexOf("{투자사}") >= 0,
            "화면이 치환을 미리 해 버렸다 — 받는 사람마다 달라야 한다");
}

// ── 4) 비워 두면 아무것도 안 실린다(서버가 회차명으로 떨어뜨린다) ──────────
{
  const dom = open(TEMPLATES);
  sel(dom).value = "21";
  sel(dom).fire("change");
  box(dom).value = "";                       // 사람이 도로 지웠다
  dom.document.getElementById("send-btn").fire("click");
  assert.strictEqual(sent(dom).subject, null,
                     "빈 칸인데 제목이 실렸다 — 회차명으로 떨어지는 길이 막힌다");
}

// ── 5) '직접 입력' 으로 되돌려도 적어 둔 것을 지우지 않는다 ────────────────
{
  const dom = open(TEMPLATES);
  box(dom).value = "손으로 적은 제목";
  sel(dom).value = "";
  sel(dom).fire("change");
  assert.strictEqual(box(dom).value, "손으로 적은 제목",
                     "'직접 입력' 이 적어 둔 제목을 지웠다");
}

// ── 6) 제목 문구가 하나도 없으면 만들러 가는 길을 띄운다 ───────────────────
{
  const dom = open([TEMPLATES[0]]);          // 안내문만 있고 제목 문구는 없다
  assert.strictEqual(dom.document.getElementById("mail-subject-tpl-wrap").hidden, true,
                     "고를 것이 없는데 빈 고르개가 서 있다");
  assert.strictEqual(dom.document.getElementById("mail-subject-none").hidden, false,
                     "만들러 가는 길이 안 떴다");
}

console.log("ok — 메일 제목 문구 고르기");
