// 예약 큐의 [시작] — **화면이 지금 말하고 있는 수를 함께 보내고, 서버가
// 되물으면 그 말을 그대로 띄우는가.** (node tests/js/deals_queue_test.js)
//
// 여기가 이 기능에서 제일 위험한 자리다. 예약에는 받는 사람이 담겨 있지 않고
// 서버가 누를 때 다시 세는데, 화면이 **그때 적혀 있던 수**(`data-count`)를 안
// 보내면 서버는 달라진 것을 알 방법이 없다 — 조용히 다른 수로 나가고, 몇
// 명에게 나갔는지 아무도 모르는 채로 되돌릴 수 없는 일이 끝나 있다.
//
// 확인창의 말도 여기서 본다. **서버가 만든 문장을 그대로** 띄워야 한다 —
// 화면이 같은 말을 다시 지어내면 두 벌이 되고, 사람이 마지막으로 읽는 자리라
// 어긋나도 아무도 모른다.
//
// 화면은 `_deals_dom.js` 가 세우고, deals.js 는 그대로 돌린다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

// 아주 작은 fetch 대역. 오간 요청을 그대로 모아 두고, 미리 정해 둔 답을
// 차례대로 돌려준다(약속은 곧바로 풀린다 — 검사가 기다릴 것이 없다).
function fakeFetch(replies) {
  const calls = [];
  // `.then()` 이 또 약속을 돌려주면 **펴 준다**(진짜 Promise 처럼). deals.js 가
  // `r.json().then(...)` 을 바깥 `.then` 에서 돌려주는데, 안 펴 주면 다음
  // 단계가 값 대신 약속을 받아 엉뚱한 곳에서 죽는다.
  function settled(value) {
    return {
      __settled: true,
      then: function (fn) {
        const next = fn(value);
        return (next && next.__settled) ? next : settled(next);
      },
      catch: function () { return this; }
    };
  }
  const fn = function (url, init) {
    const body = JSON.parse((init && init.body) || "{}");
    calls.push({ url: url, body: body });
    // 문구 목록·미리보기(GET)는 이 검사와 무관하다 — 안 풀리는 약속을 준다.
    if (!init || init.method !== "POST") {
      return { then: function () { return this; }, catch: function () { return this; } };
    }
    const reply = replies.length ? replies.shift() : { ok: true, d: {} };
    return settled({
      ok: reply.ok !== false,
      json: function () { return settled(reply.d); }
    });
  };
  fn.calls = calls;
  return fn;
}

function startCalls(fetch) {
  return fetch.calls.filter(function (c) { return c.url.indexOf("/start") >= 0; });
}

function clickStart(dom) {
  dom.queueRows[0].querySelector(".queue-start").fire("click");
}

// ── 1) ★ [시작] 은 화면에 적혀 있던 수를 함께 보낸다 ────────────────────────
{
  const fetch = fakeFetch([{ ok: true, d: { ok: true, job_id: 12, total: 24 } }]);
  const dom = deals_.run(null, { fetch: fetch, confirm: function () { return true; } });
  clickStart(dom);

  const calls = startCalls(fetch);
  assert.strictEqual(calls.length, 1, "[시작] 이 서버를 부르지 않았다");
  assert.strictEqual(calls[0].url, "/api/deals/queue/7/start",
    "누른 줄의 예약 번호로 가지 않았다: " + calls[0].url);
  // 여기가 핵심 — 이 값이 빠지면 서버는 수가 달라진 것을 알 방법이 없다.
  assert.strictEqual(calls[0].body.shown, 24,
    "화면에 적혀 있던 수(data-count)를 안 보냈다: " + JSON.stringify(calls[0].body));
  assert.strictEqual(calls[0].body.confirmed, false,
    "첫 요청부터 `확인함` 으로 보내면 서버가 되물을 기회가 없다");
}

// ── 2) ★ 서버가 되물으면, **서버가 만든 말을 그대로** 띄운다 ────────────────
{
  const MESSAGE =
    "[1군] 예약을 걸어 둔 뒤 대상이 달라졌습니다.\n" +
    "화면에는 24명 · 지금은 21명입니다 (3명이 줄었습니다 — 그사이 카톡방을 " +
    "나갔거나 검토중단 이 된 분은 빠집니다.)\n" +
    "지금 기준 21명에게 보냅니다. 진행할까요?";
  const asked = [];
  const fetch = fakeFetch([
    { ok: true, d: { ok: false, needs_confirm: true, shown: 24, now: 21,
                     message: MESSAGE } },
    { ok: true, d: { ok: true, job_id: 12, total: 21 } }
  ]);
  const dom = deals_.run(null, {
    fetch: fetch,
    confirm: function (text) { asked.push(text); return true; }
  });
  clickStart(dom);

  // 확인창은 둘이다: 누를 때 한 번, 수가 달라졌을 때 한 번.
  assert.ok(asked.length >= 2, "수가 달라졌는데 되묻지 않았다: " + JSON.stringify(asked));
  assert.strictEqual(asked[asked.length - 1], MESSAGE,
    "서버가 준 말을 그대로 띄우지 않았다 — 화면이 다시 지어내면 두 벌이 된다:\n" +
    asked[asked.length - 1]);

  const calls = startCalls(fetch);
  assert.strictEqual(calls.length, 2, "확인한 뒤 다시 보내지 않았다");
  assert.strictEqual(calls[1].body.confirmed, true,
    "두 번째 요청이 `확인함` 이 아니면 서버가 또 되묻는다 — 무한히 돈다");
  assert.strictEqual(calls[1].body.shown, 24,
    "두 번째 요청에서 화면의 수가 바뀌면 서버가 다른 차이를 본다");
  // 확인을 마치면 그 회차의 진행 화면으로 넘어간다 — 무엇이 나가는지 바로
  // 보여야, 프로그램이 꺼져 있어 한 통도 안 나가는 것을 그 자리에서 안다.
  assert.strictEqual(dom.window.location.href, "/jobs/12",
    "시작한 뒤 진행 화면으로 안 넘어갔다: " + dom.window.location.href);
}

// ── 3) ★ 되물었을 때 `아니오` 면 **아무것도 안 나간다** ─────────────────────
{
  const fetch = fakeFetch([
    { ok: true, d: { ok: false, needs_confirm: true, shown: 24, now: 21,
                     message: "달라졌습니다" } }
  ]);
  let seen = 0;
  const dom = deals_.run(null, {
    fetch: fetch,
    // 첫 확인창(누를 때)은 예, 두 번째(차이)는 아니오.
    confirm: function () { seen += 1; return seen === 1; }
  });
  clickStart(dom);

  assert.strictEqual(startCalls(fetch).length, 1,
    "차이를 보고 물러섰는데 그대로 보냈다 — 되돌릴 수 없는 일이다");
  // 물러섰으면 단추가 다시 눌려야 한다. 잠긴 채로 두면 새로고침 말고는 길이 없다.
  assert.strictEqual(dom.queueRows[0].querySelector(".queue-start").disabled, false,
    "물러선 뒤 [시작] 이 잠긴 채로 남았다");
}

// ── 4) 누를 때의 확인창에서 물러서면 서버를 부르지도 않는다 ─────────────────
{
  const fetch = fakeFetch([]);
  const dom = deals_.run(null, { fetch: fetch, confirm: function () { return false; } });
  clickStart(dom);
  assert.strictEqual(startCalls(fetch).length, 0,
    "확인창에서 물러섰는데 서버를 불렀다");
}

// ── 5) [취소] 는 다른 주소로 간다 — 시작과 섞이면 안 나갈 것이 나간다 ───────
{
  const fetch = fakeFetch([{ ok: true, d: { ok: true, status: "canceled" } }]);
  const dom = deals_.run(null, { fetch: fetch, confirm: function () { return true; } });
  dom.queueRows[0].querySelector(".queue-cancel").fire("click");

  const posts = fetch.calls.filter(function (c) { return c.url.indexOf("/queue/") >= 0; });
  assert.strictEqual(posts.length, 1);
  assert.strictEqual(posts[0].url, "/api/deals/queue/7/cancel",
    "취소가 엉뚱한 곳으로 갔다: " + posts[0].url);
  assert.strictEqual(startCalls(fetch).length, 0, "취소를 눌렀는데 발송이 시작됐다");
}

// ── 6) 예약 큐는 **딜 소개 탭**에만 선다 ────────────────────────────────────
//
// 후속 문구(리마인드·미팅 요청 …)와 소싱은 그때그때 사람을 골라 보내는 일이라
// 줄 세울 것이 없다. 큐가 그대로 떠 있으면 그 탭에서 누른 [시작] 이 그 탭의
// 문구를 보내는 줄로 읽히는데, 실제로 나가는 것은 딜 소개다.
{
  const dom = deals_.run();
  const panel = dom.document.getElementById("deal-queue");
  assert.strictEqual(panel.hidden, false, "딜 소개 탭인데 예약 큐가 안 보인다");

  dom.document.querySelector('.mode-tab[data-mode="remind"]').fire("click");
  assert.strictEqual(panel.hidden, true, "후속 문구 탭에서도 예약 큐가 그대로 떠 있다");

  dom.document.querySelector('.mode-tab[data-mode="sourcing"]').fire("click");
  assert.strictEqual(panel.hidden, true, "딜 소싱 탭에서도 예약 큐가 그대로 떠 있다");

  dom.document.querySelector('.mode-tab[data-mode="deal"]').fire("click");
  assert.strictEqual(panel.hidden, false, "딜 소개로 돌아왔는데 예약 큐가 안 돌아온다");
}

console.log("deals_queue_test: 통과");
