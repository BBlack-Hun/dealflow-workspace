// 회차명 — **방식을 바꾸면 회차명도 따라 바뀐다.**
// (node tests/js/deals_batch_title_test.js)
//
// 회차명은 서버가 화면을 그릴 때 한 번 채워 준다. 그 값은 **딜 소개 것**이라,
// 탭만 눌러 리마인드로 바꾸면 `09/16 (9월 3주차)` 라는 딜소개 이름을 단 채
// 리마인드가 나갔다. 발송 이력에 남는 것은 그 이름 하나뿐이라, 나중에는
// 무엇을 보낸 회차인지 이름으로 갈라지지 않는다.
//
// 그렇다고 아무 때나 갈아 끼우면 안 된다 — **사람이 손으로 고친 이름은 그대로
// 둔다.** 회차명은 고쳐 쓰라고 열어 둔 칸이고, 탭 한 번에 날아가면 고칠 수가
// 없다.
//
// 괄호 안에 무엇을 적는지는 여기서 정하지 않는다. 서버가 방식마다 한 벌씩
// 만들어 `data-titles` 에 실어 주고(`pages.py`), 여기서는 그 중 지금 방식
// 것으로 갈아 끼우는지만 본다 — 날짜·주차 규칙을 화면에서 또 세면 두 벌이 된다.
//
// 화면은 `_deals_dom.js` 가 세우고, deals.js 는 그대로 돌린다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const TITLES = deals_.BATCH_TITLES;

function titleBox(dom) { return dom.document.getElementById("batch-title"); }

// ── 1) ★ 탭을 바꾸면 그 방식의 이름으로 바뀐다 ────────────────────────────
{
  const dom = deals_.run();
  assert.strictEqual(titleBox(dom).value, TITLES.deal,
                     "처음에는 딜 소개 이름이어야 한다");

  // 후속 문구 넷 — 전부 주차 대신 무엇을 보내는지가 들어간다.
  ["remind", "meeting", "review", "ask", "ir", "sourcing"].forEach(function (m) {
    deals_.pickMode(dom, m);
    assert.strictEqual(titleBox(dom).value, TITLES[m],
                       m + " 탭인데 회차명이 " + titleBox(dom).value);
  });
}

// ── 2) 딜 소개로 돌아오면 주차 이름으로 되돌아온다 ────────────────────────
//
// 한 번 리마인드로 바꾼 뒤 되돌아왔을 때 리마인드 이름이 남아 있으면,
// 정규 발송이 `09/09 (리마인드)` 라는 이름으로 나간다.
{
  const dom = deals_.run();
  deals_.pickMode(dom, "remind");
  deals_.pickMode(dom, "deal");
  assert.strictEqual(titleBox(dom).value, TITLES.deal,
                     "딜 소개로 돌아왔는데 회차명이 " + titleBox(dom).value);
}

// ── 3) ★ 사람이 고친 이름은 덮어쓰지 않는다 ───────────────────────────────
{
  const dom = deals_.run();
  titleBox(dom).value = "가상 회차";
  deals_.pickMode(dom, "meeting");
  assert.strictEqual(titleBox(dom).value, "가상 회차",
                     "손으로 고친 이름을 덮어썼다: " + titleBox(dom).value);

  // 한 번 고쳤으면 그 뒤로도 계속 그 사람 것이다 — 탭을 두 번 더 눌러도.
  deals_.pickMode(dom, "deal");
  deals_.pickMode(dom, "remind");
  assert.strictEqual(titleBox(dom).value, "가상 회차",
                     "탭을 더 누르니 고친 이름이 날아갔다: " + titleBox(dom).value);
}

// ── 4) 앞뒤 공백만 다른 것은 '고친 것'이 아니다 ───────────────────────────
//
// 칸을 눌렀다 놓는 사이에 공백이 붙는 일이 있다. 그것까지 사람이 고친 것으로
// 보면 회차명이 딜소개 이름에 굳어 버린다.
{
  const dom = deals_.run();
  titleBox(dom).value = "  " + TITLES.deal + " ";
  deals_.pickMode(dom, "remind");
  assert.strictEqual(titleBox(dom).value, TITLES.remind,
                     "공백만 다른데 안 바뀌었다: " + titleBox(dom).value);
}

// ── 5) 주소로 방식을 지정해 들어와도 그 방식 이름이다 ─────────────────────
//
// IR 진행 관리에서 `?mode=ir` 로 넘어온다. 이때도 화면에 처음 채워진 것은
// 딜 소개 이름이라, 넘어오자마자 갈아 끼워야 한다.
{
  const dom = deals_.run(null, { search: "?mode=ir" });
  assert.strictEqual(titleBox(dom).value, TITLES.ir,
                     "?mode=ir 로 들어왔는데 회차명이 " + titleBox(dom).value);
}

console.log("deals_batch_title_test.js OK");
