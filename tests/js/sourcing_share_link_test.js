// 딜 소싱 화면의 [Series A 딜 소개] — 링크가 **체크한 참여 분**만 싣는가.
// (node tests/js/sourcing_share_link_test.js)
//
// 사용자: "Series A 딜소개 (20명) 이렇게 되어있는데 이거 체크박스로 선택해서 나갈 수
// 있게 해줄래?"
//
// 이 단추는 딜 제안 관리 › 딜 소싱 제안을 [Series A 딜 공유]로 열고, 이 표 맨 왼쪽
// 체크박스로 **고른 줄**을 받는 사람으로 미리 골라 둔다(`?contacts=…`).
//   ① 아무도 안 골랐으면 단추가 잠긴다 — 보이는 줄 전부로 슬쩍 대신하지 않는다
//   ② 단추 글자는 `Series A 딜 소개 (선택 N명)` — 체크한 참여 분 수
//   ③ 체크한 불참여 분은 싣지 않고 몇 명 뺐는지 옆에 적는다
//   ④ 머리글 체크 = 지금 보이는 줄 모두(걸러진 줄은 안 켠다) · 다시 누르면 푼다
//   ⑤ 필터 · 검색으로 **안 보이게 된 줄의 체크는 풀린다** — 다시 보여도 안 켜진다
//
// 화면 스크립트는 `sourcing.html` 안에 있다 — 그 글을 그대로 읽어 돌린다(Jinja
// 꺾쇠만 걷는다). 이름 · 번호는 가상값이다(공개 저장소).
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

const BASE = "/deals?mode=sourcing&topic=sourcing_deal_share";

function row(id, participation, hidden) {
  const pick = el("input", { type: "checkbox", class: "js-sourcing-pick", value: String(id) });
  const tr = el("tr", { "data-id": String(id), "data-f-participation": participation },
                [el("td", { class: "pick-col" }, [pick]), el("td", { class: "rowno" })]);
  tr.hidden = !!hidden;
  return tr;
}

function setup(rows) {
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const all = el("input", { type: "checkbox", id: "sourcing-check-all" });
  const table = el("table", { id: "sourcing-table" }, [
    el("thead", {}, [el("tr", {}, [el("th", { class: "pick-col" }, [all])])]),
    el("tbody", {}, rows)]);
  // 서버가 그린 처음 모양 — 잠긴 채(`aria-disabled`), 주소 없이.
  const btn = el("a", { id: "sourcing-share-btn", "data-base": BASE,
                        "aria-disabled": "true" });
  const hint = el("span", { id: "sourcing-share-hint" });
  root.appendChild(table);
  root.appendChild(btn);
  root.appendChild(hint);
  root.appendChild(el("input", { id: "sourcing-search", type: "search" }));
  let filterOpts = null;
  const win = {
    DealflowFilters: {
      init: function (opts) {
        filterOpts = opts;
        return { apply: function () { if (opts.onChange) opts.onChange(); } };
      }
    },
    location: { reload: function () {} }
  };
  const ctx = { document: dom_.makeDocument(root), window: win, console: console,
                setTimeout: function () { return 0; }, location: win.location,
                fetch: function () {}, alert: function () {}, confirm: function () { return false; },
                prompt: function () { return ""; } };
  vm.runInNewContext(inline, ctx, { filename: "sourcing.html<script>" });
  return { btn: btn, hint: hint, all: all,
           refilter: function () { filterOpts.onChange(); } };
}

function pick(tr, on) {
  const cb = tr.querySelector(".js-sourcing-pick");
  cb.checked = on === undefined ? !cb.checked : on;
  cb.fire("change");
}
function clickAll(t, on) { t.all.checked = on; t.all.fire("change"); }
function locked(btn) { return btn.getAttribute("aria-disabled") === "true"; }

// --- ① 아무도 안 골랐으면 잠긴다 ----------------------------------------------
{
  const rows = [row(11, "참여"), row(12, "불참여"), row(13, "참여", true), row(14, "참여")];
  const t = setup(rows);
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (선택 0명)",
                     "보이는 줄 수가 아니라 고른 수를 적어야 한다");
  assert.ok(locked(t.btn), "아무도 안 골랐는데 단추가 눌린다");
  assert.strictEqual(t.btn.getAttribute("href"), null,
                     "보이는 줄 전부로 대신 열면 안 된다 — 주소가 없어야 한다");
  assert.strictEqual(t.hint.hidden, false);
  assert.ok(/체크박스로 받을 분을 고르세요/.test(t.hint.textContent), t.hint.textContent);
  // 잠긴 단추를 눌러도 아무 데도 안 간다.
  let blocked = false;
  t.btn.fire("click", { preventDefault: function () { blocked = true; } });
  assert.ok(blocked, "잠긴 단추가 눌림을 막지 않는다");
}

// --- ② 고른 참여 분만 · ③ 불참여는 빼고 말한다 ---------------------------------
{
  const rows = [row(11, "참여"), row(12, "불참여"), row(13, "참여"), row(14, "참여")];
  const t = setup(rows);
  pick(rows[2]);
  pick(rows[0]);
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11,13",
                     "체크한 줄만 표 차례대로 실어야 한다");
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (선택 2명)");
  assert.ok(!locked(t.btn), "골랐는데 잠겨 있다");
  assert.strictEqual(t.hint.hidden, true);
  let blocked = false;
  t.btn.fire("click", { preventDefault: function () { blocked = true; } });
  assert.ok(!blocked, "고른 뒤에도 눌림을 막는다");

  pick(rows[1]);                                       // 불참여
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11,13",
                     "불참여 분이 실렸다 — 딜 제안 관리에도 안 뜨고 발송도 막힌다");
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (선택 2명)");
  assert.strictEqual(t.hint.hidden, false, "불참여를 뺐다고 말하지 않는다");
  assert.strictEqual(t.hint.textContent, "체크한 불참여 1명은 빼고 엽니다");

  // 참여는 다 풀고 불참여만 남으면 — 잠기고 둘 다 말한다.
  pick(rows[0]);
  pick(rows[2]);
  assert.ok(locked(t.btn));
  assert.strictEqual(t.btn.getAttribute("href"), null);
  assert.strictEqual(t.hint.textContent,
                     "왼쪽 체크박스로 받을 분을 고르세요 · 체크한 불참여 1명은 빼고 엽니다");
}

// --- ④ 머리글 체크 = 지금 보이는 줄 모두 ---------------------------------------
{
  const rows = [row(11, "참여"), row(12, "불참여"), row(13, "참여", true), row(14, "참여")];
  const t = setup(rows);
  clickAll(t, true);
  assert.strictEqual(rows[2].querySelector(".js-sourcing-pick").checked, false,
                     "걸러진(안 보이는) 줄까지 켰다");
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11,14");
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (선택 2명)");
  assert.strictEqual(t.all.checked, true);
  assert.strictEqual(t.all.indeterminate, false);

  // 하나를 풀면 머리글은 `일부` 표시.
  pick(rows[3], false);
  assert.strictEqual(t.all.checked, false);
  assert.strictEqual(t.all.indeterminate, true);

  // 다시 머리글을 끄면 보이는 줄이 모두 풀린다.
  clickAll(t, false);
  assert.ok(rows.every(function (r) { return !r.querySelector(".js-sourcing-pick").checked; }));
  assert.ok(locked(t.btn));
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (선택 0명)");
}

// --- ⑤ 필터로 안 보이게 된 줄의 체크는 풀린다 -----------------------------------
{
  const rows = [row(11, "참여"), row(12, "참여"), row(13, "참여")];
  const t = setup(rows);
  pick(rows[0]);
  pick(rows[1]);
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11,12");

  // 필터가 12 를 숨겼다 — 남은 줄의 체크는 그대로, 숨은 줄의 체크는 풀린다.
  rows[1].hidden = true;
  t.refilter();
  assert.strictEqual(rows[0].querySelector(".js-sourcing-pick").checked, true,
                     "필터를 바꿨다고 보이는 줄의 고른 것까지 풀렸다");
  assert.strictEqual(rows[1].querySelector(".js-sourcing-pick").checked, false,
                     "안 보이는 줄의 체크가 남았다 — 안 보이는 분께 나간다");
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11");
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (선택 1명)");

  // 다시 보여도 저절로 켜지지 않는다.
  rows[1].hidden = false;
  t.refilter();
  assert.strictEqual(rows[1].querySelector(".js-sourcing-pick").checked, false);
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11");
  assert.strictEqual(t.all.indeterminate, true);
}

console.log("sourcing_share_link_test: ok");
