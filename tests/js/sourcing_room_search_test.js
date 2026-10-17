// 딜 소싱 화면의 [방 후보 찾기] — **체크한 `방 없음` 분**만 찾는가.
// (node tests/js/sourcing_room_search_test.js)
//
// 사용자: "딜 소싱의 방 후보 찾기도 선택한걸 기반으로 찾게 해줘."
//
// 고르는 것은 [Series A 딜 소개]와 같은 표 맨 왼쪽 체크박스다(모든 탭에 선다).
//   ① 아무도 안 골랐으면 단추가 잠기고 옆에 `찾을 분을 먼저 고르세요` — 예전처럼
//      그 갈래 전부로 대신하지 않는다. 잠긴 채 보내져도 막는다
//   ② 단추 글자는 `방 후보 찾기 (선택 N명)` — 체크한 분 중 `방 없음` 인 분 수.
//      방이 이미 있는(또는 불참여) 분은 싣지 않고 몇 명 뺐는지 옆에 적는다
//   ③ 누르면 확인창에 몇 명 · 누구인지 — 취소하면 안 나간다. 확인하면 고른 줄 번호를
//      표 차례대로 `ids` 에 싣는다
//   ④ 머리글 체크 = 지금 보이는 줄 모두. 숨은 줄의 체크도 싣고 `일부 숨김` 이라 적는다
//   ⑤ [Series A 딜 소개]가 있는 탭에서는 같은 체크로 두 단추가 함께 바뀐다
//
// 화면 스크립트는 `sourcing.html` 안에 있다 — 그 글을 그대로 읽어 돌린다(Jinja
// 꺾쇠만 걷는다). 이름은 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const el = dom_.el;

const HTML = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "templates", "sourcing.html"), "utf8");
const blocks = HTML.split("{% block scripts %}")[1];
const inline = /<script>([\s\S]*?)<\/script>/.exec(blocks)[1]
  .replace(/\{%[\s\S]*?%\}/g, "").replace(/\{\{[\s\S]*?\}\}/g, "0");

// `noRoom` — 서버가 `방 없음` 으로 그린 줄(`data-no-room`).
function row(id, name, noRoom, hidden) {
  const attrs = { "data-id": String(id), "data-f-participation": "참여" };
  if (noRoom) attrs["data-no-room"] = "";
  const pick = el("input", { type: "checkbox", class: "js-sourcing-pick", value: String(id) });
  const cell = el("b", { class: "cell", "data-field": "name" });
  cell.textContent = name;
  const tr = el("tr", attrs, [el("td", { class: "pick-col" }, [pick]),
                              el("td", { class: "rowno" }), el("td", {}, [cell])]);
  tr.hidden = !!hidden;
  return tr;
}

function setup(rows, opts) {
  opts = opts || {};
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const all = el("input", { type: "checkbox", id: "sourcing-check-all" });
  const table = el("table", { id: "sourcing-table" }, [
    el("thead", {}, [el("tr", {}, [el("th", { class: "pick-col" }, [all])])]),
    el("tbody", {}, rows)]);
  // 서버가 그린 처음 모양 — 잠긴 채, `ids` 는 빈 채.
  const ids = el("input", { type: "hidden", name: "ids", value: "" });
  const btn = el("button", { type: "submit", id: "sourcing-room-btn" });
  btn.disabled = true;
  const form = el("form", { id: "sourcing-room-search" },
                  [el("input", { type: "hidden", name: "tab", value: "all" }), ids, btn]);
  const hint = el("span", { id: "sourcing-room-hint" });
  root.appendChild(table);
  root.appendChild(form);
  root.appendChild(hint);
  let share = null;
  if (opts.share) {
    share = el("a", { id: "sourcing-share-btn", "data-base": "/deals?mode=sourcing",
                      "aria-disabled": "true" });
    root.appendChild(share);
  }
  root.appendChild(el("input", { id: "sourcing-search", type: "search" }));
  let filterOpts = null;
  const asked = [];
  const t = { answer: true };
  const win = {
    DealflowFilters: {
      init: function (o) {
        filterOpts = o;
        return { apply: function () { if (o.onChange) o.onChange(); } };
      }
    },
    location: { reload: function () {} }
  };
  const ctx = { document: dom_.makeDocument(root), window: win, console: console,
                setTimeout: function () { return 0; }, location: win.location,
                fetch: function () {}, alert: function () {},
                confirm: function (m) { asked.push(m); return t.answer; },
                prompt: function () { return ""; } };
  vm.runInNewContext(inline, ctx, { filename: "sourcing.html<script>" });
  return Object.assign(t, {
    btn: btn, hint: hint, all: all, ids: ids, share: share, asked: asked,
    refilter: function () { filterOpts.onChange(); },
    // 단추를 누른 것 — 폼이 보내지려 한다. 막혔으면 true.
    submit: function () {
      let blocked = false;
      form.fire("submit", { preventDefault: function () { blocked = true; } });
      return blocked;
    }
  });
}

function pick(tr, on) {
  const cb = tr.querySelector(".js-sourcing-pick");
  cb.checked = on === undefined ? !cb.checked : on;
  cb.fire("change");
}
function clickAll(t, on) { t.all.checked = on; t.all.fire("change"); }

// --- ① 아무도 안 골랐으면 잠긴다 ----------------------------------------------
{
  const rows = [row(11, "홍길동", true), row(12, "김철수", true)];
  const t = setup(rows);
  assert.strictEqual(t.btn.textContent, "방 후보 찾기 (선택 0명)",
                     "방 없는 분 수가 아니라 고른 수를 적어야 한다");
  assert.strictEqual(t.btn.disabled, true, "아무도 안 골랐는데 단추가 눌린다");
  assert.strictEqual(t.hint.hidden, false);
  assert.strictEqual(t.hint.textContent, "찾을 분을 먼저 고르세요");
  assert.strictEqual(t.submit(), true, "안 골랐는데 보내진다 — 갈래 전부를 찾게 된다");
  assert.strictEqual(t.asked.length, 0, "고를 것도 없는데 확인창을 띄운다");
  assert.strictEqual(t.ids.value, "");
}

// --- ② 체크한 `방 없음` 분만 · 방이 있는 분은 빼고 말한다 ------------------------
{
  const rows = [row(11, "홍길동", true), row(12, "김철수", false), row(13, "박영희", true)];
  const t = setup(rows);
  pick(rows[2]);
  pick(rows[0]);
  assert.strictEqual(t.btn.textContent, "방 후보 찾기 (선택 2명)");
  assert.strictEqual(t.btn.disabled, false, "골랐는데 잠겨 있다");
  assert.strictEqual(t.hint.hidden, true);

  pick(rows[1]);                                       // 방이 이미 있다
  assert.strictEqual(t.btn.textContent, "방 후보 찾기 (선택 2명)",
                     "방이 있는 분까지 셌다");
  assert.strictEqual(t.hint.hidden, false, "방이 있는 분을 뺐다고 말하지 않는다");
  assert.strictEqual(t.hint.textContent, "체크한 분 중 '방 없음' 이 아닌 1명은 빼고 찾습니다");

  // 방 없는 분은 다 풀고 방 있는 분만 남으면 — 잠기고 둘 다 말한다.
  pick(rows[0]);
  pick(rows[2]);
  assert.strictEqual(t.btn.disabled, true);
  assert.strictEqual(t.hint.textContent,
                     "찾을 분을 먼저 고르세요 · 체크한 분 중 '방 없음' 이 아닌 1명은 빼고 찾습니다");
}

// --- ③ 확인창에 몇 명 · 누구 — 취소하면 안 나간다 ---------------------------------
{
  const rows = [row(11, "홍길동", true), row(12, "김철수", false), row(13, "박영희", true)];
  const t = setup(rows);
  pick(rows[2]);
  pick(rows[1]);
  pick(rows[0]);

  t.answer = false;
  assert.strictEqual(t.submit(), true, "취소했는데 보내진다");
  assert.strictEqual(t.asked.length, 1);
  assert.ok(/선택한 2명/.test(t.asked[0]), t.asked[0]);
  assert.ok(/홍길동, 박영희/.test(t.asked[0]), "누구인지 표 차례대로 적어야 한다: " + t.asked[0]);
  assert.ok(!/김철수/.test(t.asked[0]), "빼는 분(방 있음)을 찾는다고 적었다");
  assert.ok(/메시지는 보내지 않습니다/.test(t.asked[0]), t.asked[0]);

  t.answer = true;
  assert.strictEqual(t.submit(), false, "확인했는데 막았다");
  assert.strictEqual(t.ids.value, "11,13", "고른 `방 없음` 줄만 표 차례대로 실어야 한다");
}

// 여럿이면 앞 열 명만 적고 나머지는 수로.
{
  const rows = [];
  for (let i = 1; i <= 12; i += 1) rows.push(row(100 + i, "가상" + i, true));
  const t = setup(rows);
  clickAll(t, true);
  assert.strictEqual(t.btn.textContent, "방 후보 찾기 (선택 12명)");
  t.answer = false;
  t.submit();
  assert.ok(/가상1, 가상2, .*가상10 외 2명/.test(t.asked[0]), t.asked[0]);
  assert.ok(!/가상11/.test(t.asked[0]), t.asked[0]);
}

// --- ④ 머리글 체크 = 보이는 줄 · 숨은 줄의 체크는 남고 실린다 --------------------
{
  const rows = [row(11, "홍길동", true), row(12, "김철수", true, true), row(13, "박영희", true)];
  const t = setup(rows);
  clickAll(t, true);
  assert.strictEqual(rows[1].querySelector(".js-sourcing-pick").checked, false,
                     "걸러진(안 보이는) 줄까지 켰다");
  assert.strictEqual(t.btn.textContent, "방 후보 찾기 (선택 2명)");

  // 다음 검색 — 11 이 가려지고 12 가 보인다. 11 의 체크는 남는다.
  rows[0].hidden = true;
  rows[1].hidden = false;
  t.refilter();
  assert.strictEqual(t.btn.textContent, "방 후보 찾기 (선택 2명 · 일부 숨김)");
  pick(rows[1]);
  assert.strictEqual(t.btn.textContent, "방 후보 찾기 (선택 3명 · 일부 숨김)");
  assert.strictEqual(t.submit(), false);
  assert.strictEqual(t.ids.value, "11,12,13", "숨은 줄에서 고른 분이 빠졌다");
}

// --- ⑤ [Series A 딜 소개]가 있는 탭 — 같은 체크로 두 단추가 함께 ----------------
{
  const rows = [row(11, "홍길동", true), row(12, "김철수", false)];
  const t = setup(rows, { share: true });
  pick(rows[0]);
  pick(rows[1]);
  assert.strictEqual(t.share.textContent, "Series A 딜 소개 (선택 2명)");
  assert.strictEqual(t.btn.textContent, "방 후보 찾기 (선택 1명)");
  assert.strictEqual(t.btn.disabled, false);
}

console.log("sourcing_room_search_test: ok");
