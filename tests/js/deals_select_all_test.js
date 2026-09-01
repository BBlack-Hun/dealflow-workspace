// 그룹으로 추린 뒤 [전체선택]·[전체해제]가 **누구에게 걸리는가.**
// (node tests/js/deals_select_all_test.js)
//
// 이 화면에서 가장 위험한 자리다. 목록에서 안 보이는 사람까지 체크되면 그대로
// **실제 투자사 카톡방으로 문구가 나간다** — 되돌릴 수가 없다.
//
// 눈에 안 띄는 함정이 하나 있다. 이 화면은 **고른 사람을 조건에서 벗어나도
// 계속 보여 준다**(몇 명 골랐는지 알아야 하므로). 그래서 `안 숨겨졌다 = 조건에
// 맞다` 로 읽으면, 그룹 A 에서 몇 명 고른 뒤 그룹 B 로 추리고 [전체선택]을
// 누르는 순간 A 의 그 사람들까지 함께 켜진다. 화면은 "그룹 B" 라고 적혀 있는데
// 발송 대상에는 A 가 섞여 있다.
//
// 규칙을 옮겨 적어 검사하면 두 벌이 되어 어긋나도 모른다. 그래서 **deals.js 를
// 그대로 실행**한다 — 화면은 `_deals_dom.js` 가 세운다(여러 검사가 그 한 벌을
// 같이 쓴다).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const EMPTY_GROUP = deals_.EMPTY_GROUP;
const run = deals_.run;
const checkedNames = deals_.checkedNames;
const shownNames = deals_.shownNames;
const pickGroup = deals_.pickGroup;
const clickSelectAll = deals_.clickSelectAll;
const clickClearAll = deals_.clickClearAll;

// ── 1) 그룹 필터가 실제로 줄을 거른다 ───────────────────────────────────────
{
  const dom = run();
  assert.deepStrictEqual(shownNames(dom),
    ["가담당", "나담당", "다담당", "라담당", "마담당"],
    "아무 것도 안 골랐는데 누가 숨겨져 있다");

  pickGroup(dom, "1군");
  assert.deepStrictEqual(shownNames(dom), ["가담당", "나담당"],
    "그룹으로 추렸는데 다른 그룹이 그대로 보인다");

  pickGroup(dom, EMPTY_GROUP);
  assert.deepStrictEqual(shownNames(dom), ["마담당"],
    "`(비어 있음)` 은 그룹을 안 정해 둔 사람만이어야 한다");

  pickGroup(dom, "");
  assert.deepStrictEqual(shownNames(dom).length, 5, "[전체] 로 돌아오지 않는다");
}

// ── 2) [전체선택]은 걸러진 사람에게만 걸린다 ────────────────────────────────
{
  const dom = run();
  pickGroup(dom, "2군");
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["다담당", "라담당"],
    "그룹으로 추려 놓고 [전체선택]을 눌렀는데 다른 그룹까지 켜졌다 — " +
    "그대로 실제 투자사 방으로 문구가 나간다");
}

// ── 3) ★ 이미 고른 사람이 있어도 마찬가지다 ─────────────────────────────────
//
// 여기가 진짜 함정이다. 고른 사람은 조건에서 벗어나도 계속 **보인다** —
// `보인다 = 조건에 맞다` 로 읽으면 아까 고른 1군이 2군 전체선택에 딸려 온다.
{
  const dom = run();
  pickGroup(dom, "1군");
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "나담당"]);

  pickGroup(dom, "2군");
  // 고른 1군은 계속 보인다(몇 명 골랐는지 알아야 한다) — 그건 그대로 둔다.
  assert.ok(shownNames(dom).indexOf("가담당") >= 0,
    "고른 사람이 사라지면 몇 명 골랐는지 알 수 없다");

  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "나담당", "다담당", "라담당"],
    "2군을 켜는 조작이 1군을 건드렸거나, 2군이 안 켜졌다");

  // 한 번 더 누르면 **2군만** 꺼진다. 1군은 이 조작의 대상이 아니다.
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "나담당"],
    "[전체선택]을 되돌리는데 조건 밖 사람까지 껐다");
}

// ── 4) 검색으로 좁혀도 같은 규칙 ────────────────────────────────────────────
{
  const dom = run();
  const search = dom.document.getElementById("contact-search");
  search.value = "가담당";
  search.fire("input");
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당"],
    "검색으로 좁혀 놓고 누른 [전체선택]에 안 보이는 사람이 딸려 왔다");
}

// ── 5) [반응 없는 담당자만] 도 추린 안에서만 ────────────────────────────────
{
  const dom = run();
  pickGroup(dom, "2군");
  dom.document.getElementById("select-noreact").fire("click");
  assert.deepStrictEqual(checkedNames(dom), ["다담당"],
    "그룹으로 추려 놓았는데 다른 그룹의 '반응 없음' 까지 켜졌다");
}

// ── 6) 조건 밖에서 고른 사람이 있으면 화면이 말해 준다 ──────────────────────
//
// 그 사람들도 그대로 발송에 들어간다. 숫자만 줄어든 줄 알고 보내면 안 된다.
{
  const dom = run();
  pickGroup(dom, "1군");
  clickSelectAll(dom);
  pickGroup(dom, "2군");
  const note = dom.document.getElementById("contact-filter-note");
  assert.ok(/조건 밖에서 고른 2명/.test(note.textContent),
    "조건 밖에서 고른 사람이 발송에 남아 있는데 화면이 말하지 않는다: " + note.textContent);
}

// ── 7) ★ 연결이 안 끝나 목록에 없는 사람은 **어떤 조작으로도 안 골라진다** ──
//
// 화면은 "연결이 안 끝난 19명" 을 이름까지 보여 준다 — 안 보여 주면 누가 빠졌는지
// 알 수가 없어 손을 쓸 수 없기 때문이다. 그런데 **보이는 것과 고를 수 있는 것은
// 달라야 한다.** 연결이 안 된 사람은 보낼 방이 없다.
//
// 막는 방법은 두 겹이다. ① 화면이 그 자리에 입력칸을 아예 안 그린다(그건
// `tests/test_deals_recipients.py` 가 본다) ② deals.js 가 고르는 상자를
// `#contact-list` 안으로 좁혀 둔다. 여기서는 ②를 본다 — 위 `blockedBlock` 이
// 일부러 체크박스를 달아 두었으므로, 좁힘이 풀리면 이 검사가 바로 빨개진다.
{
  const dom = run();
  assert.ok(dom.blockedCb, "검사용 체크박스가 안 세워졌다 — 검사가 헛돈다");

  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom),
    ["가담당", "나담당", "다담당", "라담당", "마담당"],
    "[전체선택]이 목록 안 사람을 다 켜지 않았다");
  assert.strictEqual(dom.blockedCb.checked, false,
    "연결이 안 끝나 목록에 없는 사람이 [전체선택]에 딸려 왔다 — " +
    "보낼 방도 없는 사람에게 문구가 나간다");

  // [반응 없는 담당자만] 도 마찬가지다. 그 사람은 `data-noreact="1"` 이라
  // 조건만 보면 딱 걸리는데, 애초에 고를 수 있는 사람이 아니다.
  dom.document.getElementById("select-noreact").fire("click");
  assert.strictEqual(dom.blockedCb.checked, false,
    "'반응 없음' 이라는 이유로 연결 전 사람이 켜졌다");

  // **[전체해제]도 같은 상자만 훑는다.** 켜는 쪽만 좁혀 두고 끄는 쪽을 넓히면,
  // 접힌 칸의 체크는 켜지지도 꺼지지도 않는 채로 남는다 — 그 상태로 손댈 수
  // 없는 체크가 발송으로 새어 나가는 길이 열린다.
  dom.blockedCb.checked = true;              // 어떻게든 켜졌다고 치고
  clickClearAll(dom);
  assert.strictEqual(dom.blockedCb.checked, true,
    "[전체해제]가 목록 밖(접힌 칸)까지 건드렸다 — 켜는 쪽과 끄는 쪽의 범위가 다르다");
}

// ── 8) 소싱 탭으로 가면 그 설명은 사라진다 ──────────────────────────────────
//
// `연결이 안 끝나 빠졌다` 는 **투자사 담당자 목록의 사정**이다. 딜 소싱은 아예
// 다른 표라 연결 단계라는 것이 없는데, 그 위에 이 줄이 남아 있으면 지금 보이는
// 명단에서 몇 명이 빠진 것으로 읽힌다.
{
  const dom = run();
  const missBox = dom.document.getElementById("blocked-contacts");
  assert.strictEqual(missBox.hidden, false, "딜 소개 탭에서 설명이 감춰져 있다");

  dom.document.querySelector('.mode-tab[data-mode="sourcing"]').fire("click");
  assert.strictEqual(missBox.hidden, true,
    "소싱 명단을 보는데 투자사 담당자의 '연결이 안 끝나 빠진 사람' 이 그대로 떠 있다");

  dom.document.querySelector('.mode-tab[data-mode="deal"]').fire("click");
  assert.strictEqual(missBox.hidden, false,
    "딜 소개로 돌아왔는데 빠진 사람 설명이 안 돌아온다 — 누가 빠졌는지 다시 알 수 없다");
}

// ── 9) ★ [전체해제]는 **조건 밖에서 고른 사람까지** 푼다 ────────────────────
//
// 여기가 이 단추가 생긴 이유다. [전체선택]은 지금 걸러진 범위만 되돌리므로
// (위 3번), 1군에서 고르고 2군으로 옮긴 뒤에는 두 번을 눌러도 1군이 남는다 —
// 필터를 되돌리거나 새로고침하는 수밖에 없었다. 그게 사용자가 말한 "전체
// 해제가 없다" 이고, 그래서 훑는 범위가 다른 단추를 따로 세웠다.
{
  const dom = run();
  pickGroup(dom, "1군");
  clickSelectAll(dom);
  pickGroup(dom, "2군");
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "나담당", "다담당", "라담당"]);

  // [전체선택]을 다시 눌러도 2군만 꺼진다 — 1군에는 손이 닿지 않는다.
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "나담당"],
    "[전체선택]의 범위가 넓어졌다 — 그 좁힘이 이 화면의 안전장치다");

  clickClearAll(dom);
  assert.deepStrictEqual(checkedNames(dom), [],
    "[전체해제]를 눌렀는데 조건 밖에서 고른 사람이 그대로 남았다 — " +
    "화면은 비어 보이는데 발송에는 들어간다");
}

// ── 10) 세는 자리와 어긋나지 않는다 ─────────────────────────────────────────
//
// `0명` 이라고 적혀 있는데 체크가 남아 있거나, 반대로 셈만 0 이 되고 체크는
// 그대로면 그 차이가 그대로 발송으로 간다. 알약 · 발송 요약 · 이 단추의
// 눌림 상태는 전부 `updateCounts()` 한 곳에서 나와야 한다.
{
  const dom = run();
  const pill = dom.document.getElementById("contact-pill");
  const ss = dom.document.getElementById("ss-contacts");
  const summary = dom.document.getElementById("contact-summary");
  const clearBtn = dom.document.getElementById("clear-all-contacts");

  assert.strictEqual(clearBtn.disabled, true,
    "아무도 안 골랐는데 [전체해제]가 눌린다 — 눌러도 아무 일이 없다");

  clickSelectAll(dom);
  assert.strictEqual(pill.innerHTML, "<b>5</b>명");
  assert.strictEqual(ss.textContent, 5);
  assert.strictEqual(clearBtn.disabled, false, "고른 사람이 있는데 [전체해제]가 잠겨 있다");

  clickClearAll(dom);
  assert.deepStrictEqual(checkedNames(dom), []);
  assert.strictEqual(pill.innerHTML, "<b>0</b>명",
    "체크는 다 풀렸는데 알약이 아직 사람을 세고 있다");
  assert.strictEqual(ss.textContent, 0, "발송 요약이 아직 사람을 세고 있다");
  assert.strictEqual(summary.hidden, true,
    "고른 사람이 없는데 요약 줄이 남아 있다 — 누가 들어가는지 잘못 읽힌다");
  assert.strictEqual(clearBtn.disabled, true,
    "풀 것이 없는데 [전체해제]가 계속 눌린다");
}

// ── 11) 소싱 명단에서도 그 명단만 푼다 ─────────────────────────────────────
//
// 대상 목록이 둘이다(투자사 담당자 / 딜 소싱). 감춰진 쪽의 체크까지 풀면,
// 탭을 돌아왔을 때 골라 둔 것이 말없이 사라진다.
{
  const dom = run();
  clickSelectAll(dom);
  assert.strictEqual(checkedNames(dom).length, 5);

  dom.document.querySelector('.mode-tab[data-mode="sourcing"]').fire("click");
  clickSelectAll(dom);
  assert.ok(dom.sourcingCards.every(function (c) {
    return c.querySelector(".contact-cb").checked;
  }), "소싱 명단에서 [전체선택]이 안 걸렸다 — 이 검사가 헛돈다");

  clickClearAll(dom);
  assert.ok(dom.sourcingCards.every(function (c) {
    return !c.querySelector(".contact-cb").checked;
  }), "지금 보고 있는 소싱 명단이 [전체해제]로 안 풀렸다");

  dom.document.querySelector('.mode-tab[data-mode="deal"]').fire("click");
  assert.strictEqual(checkedNames(dom).length, 5,
    "소싱 탭에서 누른 [전체해제]가 감춰져 있던 투자사 담당자 선택을 지웠다");
}

console.log("deals_select_all_test: 통과");
