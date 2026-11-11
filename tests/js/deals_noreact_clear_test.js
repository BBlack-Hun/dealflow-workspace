// [반응 없음에서 빼기] · [되돌리기] — 카드에서 누르면 **딱지가 빠지고 단추 수 · 거르기가
// 그 자리에서 따라온다**(11/11). (node tests/js/deals_noreact_clear_test.js)
//
// 요청: "반응 없는 담당자 사용자가 체크해서 뺄 수 있게". 전화 · 다른 길로 반응이 있었던
// 분을 사람이 뺀다 — 저장과 판정은 서버(`/api/contacts/{id}/no-reaction` ·
// `services/no_reaction`)이고, 화면은 답을 받은 뒤 `data-noreact` 를 고친다.
//
// 지키는 것:
//   ① 누르면 그 번호로 `cleared: true` 를 보내고, 딱지가 [되돌리기] 모양으로 바뀌고,
//      `data-noreact` 가 0 이 되어 [반응 없는 담당자만] 수가 하나 준다.
//   ② 카드의 고르는 체크와 섞이지 않는다 — 기본 동작을 막고(카드가 `<label>` 이다),
//      거르기가 꺼져 있으면 체크를 안 건드린다.
//   ③ [되돌리기] 는 `cleared: false` 를 보내고 원래 모양 · 수로 돌린다.
//   ④ [반응 없는 담당자만] 이 켜져 있으면 뺀 분의 체크를 끄되 카드는 남겨 [되돌리기] 가
//      닿고, 그분은 [전체선택] 에 안 딸려 온다. 되돌리면 다시 골라진다.
//   ⑤ 서버가 거절하면(남의 줄) 화면은 그대로다.
//   ⑥ 서버가 이미 뺀 분은 처음부터 [되돌리기] 모양이고 수에 안 든다.
//   ⑦ 저장 중에 또 눌러도 한 번만 보낸다.
//
// 규칙을 옮겨 적지 않고 **deals.js 를 그대로 실행**한다(`_deals_dom.js`).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const run = deals_.run;
const fakeFetch = deals_.fakeFetch;
const checkedNames = deals_.checkedNames;
const shownNames = deals_.shownNames;
const PEOPLE = deals_.PEOPLE;

const btn = function (dom) { return dom.document.getElementById("select-noreact"); };
const card = function (dom, name) {
  return dom.cards.filter(function (c) {
    return c.querySelector(".contact-cb").getAttribute("data-name") === name;
  })[0];
};
const mark = function (dom, name) { return card(dom, name).querySelector(".noreact-mark"); };
// 지금 보이는 모양의 단추를 누른다 — 사람이 보는 그 단추다.
function toggle(dom, name) {
  const m = mark(dom, name);
  const shown = m.querySelector(m.getAttribute("data-cleared") === "1" ? ".noreact-off"
                                                                       : ".noreact-on");
  assert.ok(!shown.hidden, name + " 의 보이는 모양이 숨어 있다");
  let prevented = false;
  shown.querySelector(".noreact-toggle").fire("click", {
    preventDefault() { prevented = true; }
  });
  return prevented;
}
function looksCleared(dom, name) {
  const m = mark(dom, name);
  return m.getAttribute("data-cleared") === "1" &&
    m.querySelector(".noreact-on").hidden && !m.querySelector(".noreact-off").hidden;
}
function looksListed(dom, name) {
  const m = mark(dom, name);
  return m.getAttribute("data-cleared") === "0" &&
    !m.querySelector(".noreact-on").hidden && m.querySelector(".noreact-off").hidden;
}
function noreactOf(dom, name) {
  return card(dom, name).querySelector(".contact-cb").getAttribute("data-noreact");
}
// 이 단추가 부른 것만 — 화면은 문구 목록(`/api/templates`)도 처음에 부른다.
function sent(fetch) {
  return fetch.calls.filter(function (c) { return /\/no-reaction$/.test(c.url); });
}
// 서버 답 — 보낸 대로 돌려준다(저장은 서버의 일이다).
const echo = function () {
  return fakeFetch(function (url, body) { return { ok: true, d: { ok: true, cleared: body.cleared } }; });
};

// ── ① 빼기 · ② 체크와 안 섞인다 · ③ 되돌리기 ─────────────────────────────────
{
  const fetch = echo();
  const dom = run(undefined, { fetch: fetch });
  assert.ok(/2명/.test(btn(dom).textContent), btn(dom).textContent);

  assert.ok(toggle(dom, "가담당"), "카드가 <label> 인데 기본 동작을 안 막았다 — 체크로 번진다");
  assert.deepStrictEqual(sent(fetch).map(function (c) { return [c.url, c.body]; }),
    [["/api/contacts/1/no-reaction", { cleared: true }]]);
  assert.ok(looksCleared(dom, "가담당"), "뺐는데 딱지가 그대로다");
  assert.strictEqual(noreactOf(dom, "가담당"), "0");
  assert.ok(/1명/.test(btn(dom).textContent),
    "뺐는데 [반응 없는 담당자만] 수가 안 줄었다: " + btn(dom).textContent);
  assert.deepStrictEqual(checkedNames(dom), [], "거르기가 꺼져 있는데 체크가 바뀌었다");

  toggle(dom, "가담당");
  assert.deepStrictEqual(sent(fetch)[1].body, { cleared: false }, "되돌리기가 비우라고 안 보냈다");
  assert.ok(looksListed(dom, "가담당"), "되돌렸는데 딱지가 안 돌아왔다");
  assert.strictEqual(noreactOf(dom, "가담당"), "1");
  assert.ok(/2명/.test(btn(dom).textContent), "되돌렸는데 수가 안 돌아왔다");
}

// ── ④ [반응 없는 담당자만] 을 켠 채 빼고 되돌린다 ──────────────────────────────
{
  const dom = run(undefined, { fetch: echo() });
  btn(dom).fire("click");
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "다담당"]);

  toggle(dom, "가담당");
  assert.deepStrictEqual(checkedNames(dom), ["다담당"],
    "반응 없는 분만 고른 채 뺐는데 그분이 골라진 채다 — 그 글이 나간다");
  assert.deepStrictEqual(shownNames(dom), ["가담당", "다담당"],
    "뺀 분이 사라져 [되돌리기] 가 안 닿는다");
  assert.ok(/1명/.test(btn(dom).textContent), btn(dom).textContent);
  const note = dom.document.getElementById("contact-filter-note");
  assert.ok(!/조건 밖에서 고른/.test(note.textContent), note.textContent);

  // [전체선택] 은 조건에 맞는 분만 켠다 — 남겨 둔 카드는 조건 밖이다.
  dom.document.getElementById("select-all-contacts").fire("click");   // 다담당이 켜져 있어 끈다
  dom.document.getElementById("select-all-contacts").fire("click");
  assert.deepStrictEqual(checkedNames(dom), ["다담당"],
    "[전체선택] 이 반응 없음에서 뺀 분까지 켰다");

  toggle(dom, "가담당");
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "다담당"],
    "되돌렸는데 [반응 없는 담당자만] 으로 골라졌던 체크가 안 돌아왔다");
  assert.ok(/2명/.test(btn(dom).textContent));
}

// ── ⑤ 서버가 거절하면 그대로 ─────────────────────────────────────────────────
{
  const alerts = [];
  const dom = run(undefined, {
    fetch: fakeFetch([{ ok: false, d: { detail: "담당자를 찾을 수 없습니다" } }]),
    alert: function (m) { alerts.push(m); }
  });
  toggle(dom, "가담당");
  assert.deepStrictEqual(alerts, ["담당자를 찾을 수 없습니다"]);
  assert.ok(looksListed(dom, "가담당"), "거절됐는데 딱지가 바뀌었다");
  assert.strictEqual(noreactOf(dom, "가담당"), "1");
  assert.ok(/2명/.test(btn(dom).textContent));
}

// ── ⑥ 서버가 이미 뺀 분 — 처음부터 [되돌리기] · 수에 안 든다 ─────────────────
{
  const people = PEOPLE.map(function (p) { return p.slice(); });
  people[0].push(true);                     // 가담당 — 판정은 반응 없음, 사람이 뺐다
  const fetch = echo();
  const dom = run(people, { fetch: fetch });
  assert.ok(looksCleared(dom, "가담당"));
  assert.ok(/1명/.test(btn(dom).textContent), btn(dom).textContent);
  toggle(dom, "가담당");
  assert.deepStrictEqual(sent(fetch)[0].body, { cleared: false });
  assert.ok(looksListed(dom, "가담당"));
  assert.ok(/2명/.test(btn(dom).textContent));
}

// ── ⑦ 저장 중에 또 눌러도 한 번만 보낸다 ─────────────────────────────────────
{
  const calls = [];
  const dom = run(undefined, { fetch: function (url, init) {
    if (/\/no-reaction$/.test(url)) calls.push(JSON.parse(init.body));
    return { then: function () { return this; }, catch: function () { return this; } };
  } });
  toggle(dom, "가담당");
  toggle(dom, "가담당");
  assert.deepStrictEqual(calls, [{ cleared: true }], "저장 중 두 번째 누름이 또 나갔다");
}

console.log("deals_noreact_clear_test: ok");
