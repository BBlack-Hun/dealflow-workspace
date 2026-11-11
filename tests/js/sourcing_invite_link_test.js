// 딜 소싱 화면의 [검토 가능 심사역 참여 안내] — 링크가 **체크한 참여 안내 대상**만 싣는가.
// (node tests/js/sourcing_invite_link_test.js)
//
// 11/11 요청: 시리즈 A 탭의 [참여 심사역 딜 발송 요청]처럼, 왼쪽 체크박스로 고른 분께
// 참여 안내를 여는 단추. 딜 제안 관리 › 딜 소싱 제안을 [검토 가능 심사역 참여 안내]로
// 열고 고른 분을 받는 사람으로 미리 골라 둔다(`?topic=sourcing_intro&contacts=…`).
//   ① 아무도 안 골랐으면 잠긴다 — 보이는 줄 전부로 슬쩍 대신하지 않는다
//   ② 체크한 분 중 참여 안내를 받는 분(`data-invite="1"` — 서버의
//      `sourcing_sync.can_get_invite`: 제안 대기중 · 물어보는 중)만 싣는다.
//      참여 · 불참여 · 직접 문구는 빼고 몇 명인지 옆에 적는다
//   ③ 숨은 줄의 체크도 싣고 단추에 `일부 숨김` 이라 적는다(시리즈 A 단추와 같다)
//   ④ `참여` 칸을 고치면 서버가 준 `invite_ok` 로 그 줄을 다시 센다
//   ⑤ 시리즈 A 단추와 **같은 체크**로 두 단추가 함께 바뀐다
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

const BASE = "/deals?mode=sourcing&topic=sourcing_intro";
const SHARE_BASE = "/deals?mode=sourcing&topic=sourcing_deal_share";
const OFFER = "딜 소싱 참여 제안 대기중";
const ASKING = "참여 의사를 물어보는 중";

// 서버가 싣는 두 값 — `data-part-kind`(`sourcing_sync.kind_of`) · `data-invite`
// (`sourcing_sync.can_get_invite`). 규칙은 서버 한 곳이고, 여기서는 그 결과를 흉내 낸다.
function kindOf(participation) {
  if (participation === "참여") return "joined";
  if (participation === "불참여") return "left";
  return "pending";
}
function inviteOf(participation) {
  return participation === OFFER || participation === ASKING ? "1" : "0";
}

function row(id, participation, hidden) {
  const pick = el("input", { type: "checkbox", class: "js-sourcing-pick", value: String(id) });
  const cell = el("b", { class: "cell", "data-field": "participation" });
  cell.textContent = participation;
  const tr = el("tr", { "data-id": String(id), "data-f-participation": participation,
                        "data-part-kind": kindOf(participation),
                        "data-invite": inviteOf(participation) },
                [el("td", { class: "pick-col" }, [pick]), el("td", { class: "rowno" }),
                 el("td", {}, [cell])]);
  tr.hidden = !!hidden;
  return tr;
}

function setup(rows, withShare) {
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const all = el("input", { type: "checkbox", id: "sourcing-check-all" });
  const table = el("table", { id: "sourcing-table" }, [
    el("thead", {}, [el("tr", {}, [el("th", { class: "pick-col" }, [all])])]),
    el("tbody", {}, rows)]);
  // 서버가 그린 처음 모양 — 잠긴 채(`aria-disabled`), 주소 없이.
  const btn = el("a", { id: "sourcing-invite-btn", "data-base": BASE, "aria-disabled": "true" });
  const hint = el("span", { id: "sourcing-invite-hint" });
  root.appendChild(table);
  root.appendChild(btn);
  root.appendChild(hint);
  let share = null;
  if (withShare) {
    share = el("a", { id: "sourcing-share-btn", "data-base": SHARE_BASE, "aria-disabled": "true" });
    root.appendChild(share);
    root.appendChild(el("span", { id: "sourcing-share-hint" }));
  }
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
  return { btn: btn, hint: hint, all: all, share: share, table: table,
           refilter: function () { filterOpts.onChange(); } };
}

function pick(tr, on) {
  const cb = tr.querySelector(".js-sourcing-pick");
  cb.checked = on === undefined ? !cb.checked : on;
  cb.fire("change");
}
function locked(btn) { return btn.getAttribute("aria-disabled") === "true"; }

// --- ① 아무도 안 골랐으면 잠긴다 ----------------------------------------------
{
  const rows = [row(11, OFFER), row(12, ASKING), row(13, "참여")];
  const t = setup(rows);
  assert.strictEqual(t.btn.textContent, "검토 가능 심사역 참여 안내 (선택 0명)",
                     "보이는 줄 수가 아니라 고른 수를 적어야 한다");
  assert.ok(locked(t.btn), "아무도 안 골랐는데 단추가 눌린다");
  assert.strictEqual(t.btn.getAttribute("href"), null,
                     "보이는 줄 전부로 대신 열면 안 된다 — 주소가 없어야 한다");
  assert.strictEqual(t.hint.hidden, false);
  assert.strictEqual(t.hint.textContent, "왼쪽 체크박스로 받을 분을 고르세요");
  let blocked = false;
  t.btn.fire("click", { preventDefault: function () { blocked = true; } });
  assert.ok(blocked, "잠긴 단추가 눌림을 막지 않는다");
}

// --- ② 참여 안내 대상만 싣고, 나머지는 갈래별로 몇 명 뺐는지 -----------------------
{
  const rows = [row(11, "참여"), row(12, OFFER), row(13, "불참여"), row(14, ASKING),
                row(15, "11월 재연락"), row(16, "참여")];
  const t = setup(rows);
  pick(rows[3]);
  pick(rows[1]);
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=12,14",
                     "체크한 참여 안내 대상만 표 차례대로 실어야 한다");
  assert.strictEqual(t.btn.textContent, "검토 가능 심사역 참여 안내 (선택 2명)");
  assert.ok(!locked(t.btn), "골랐는데 잠겨 있다");
  assert.strictEqual(t.hint.hidden, true);
  let blocked = false;
  t.btn.fire("click", { preventDefault: function () { blocked = true; } });
  assert.ok(!blocked, "고른 뒤에도 눌림을 막는다");

  [0, 2, 4, 5].forEach(function (i) { pick(rows[i], true); });
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=12,14",
                     "참여 · 불참여 · 직접 문구가 참여 안내로 실렸다");
  assert.strictEqual(t.btn.textContent, "검토 가능 심사역 참여 안내 (선택 2명)");
  assert.strictEqual(t.hint.hidden, false, "뺀 분을 말하지 않는다");
  assert.strictEqual(t.hint.textContent,
                     "체크한 참여 중 2명 · 불참여 1명 · 직접 문구 1명은 참여 안내 대상이 아니라 빼고 엽니다");

  // 대상은 다 풀고 뺄 분만 남으면 — 잠기고 둘 다 말한다.
  pick(rows[1], false);
  pick(rows[3], false);
  assert.ok(locked(t.btn));
  assert.strictEqual(t.btn.getAttribute("href"), null);
  assert.strictEqual(t.btn.textContent, "검토 가능 심사역 참여 안내 (선택 0명)");
  assert.ok(/^왼쪽 체크박스로 받을 분을 고르세요 · 체크한 참여 중 2명/.test(t.hint.textContent),
            t.hint.textContent);
}

// --- ③ 숨은 줄의 체크도 싣고 `일부 숨김` --------------------------------------
{
  const rows = [row(11, OFFER), row(12, ASKING), row(13, OFFER)];
  const t = setup(rows);
  pick(rows[0]);
  rows[0].hidden = true;          // 다음 검색에 가렸다
  t.refilter();
  pick(rows[1]);
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11,12",
                     "숨은 줄에서 고른 분이 빠졌다");
  assert.strictEqual(t.btn.textContent, "검토 가능 심사역 참여 안내 (선택 2명 · 일부 숨김)");
  assert.ok(/체크한 1명은 지금 검색 · 필터에 가려 있습니다 — 함께 엽니다/.test(t.hint.textContent),
            t.hint.textContent);
  rows[0].hidden = false;
  t.refilter();
  assert.strictEqual(t.btn.textContent, "검토 가능 심사역 참여 안내 (선택 2명)");
  assert.strictEqual(t.hint.hidden, true);
}

// --- ④ `참여` 칸을 고치면 서버가 준 `invite_ok` 로 다시 센다 -------------------
{
  const rows = [row(11, OFFER), row(12, "참여")];
  const t = setup(rows);
  pick(rows[0]);
  pick(rows[1]);
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11");
  function saved(tr, participation, kind, inviteOk) {
    t.table.fire("inline-saved", { detail: {
      row: tr, cell: tr.querySelector(".cell"),
      data: { ok: true, participation: participation, participation_kind: kind,
              invite_ok: inviteOk } } });
  }
  // 제안 대기중이던 분이 동의해 `참여` 가 됐다 — 참여 안내에서 빠진다.
  saved(rows[0], "참여", "joined", false);
  assert.strictEqual(rows[0].getAttribute("data-invite"), "0");
  assert.ok(locked(t.btn), "참여가 된 분이 참여 안내에 남았다");
  assert.strictEqual(t.btn.textContent, "검토 가능 심사역 참여 안내 (선택 0명)");
  // 참여였던 분을 `물어보는 중` 으로 — 참여 안내 대상이 된다.
  saved(rows[1], ASKING, "pending", true);
  assert.strictEqual(rows[1].getAttribute("data-invite"), "1");
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=12");
}

// --- ⑤ 시리즈 A 탭 — 같은 체크로 두 단추가 함께 바뀐다 --------------------------
{
  const rows = [row(11, "참여"), row(12, OFFER), row(13, "참여")];
  const t = setup(rows, true);
  rows.forEach(function (r) { pick(r, true); });
  assert.strictEqual(t.share.getAttribute("href"), SHARE_BASE + "&contacts=11,13");
  assert.strictEqual(t.share.textContent, "참여 심사역 딜 발송 요청 (선택 2명)");
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=12");
  assert.strictEqual(t.btn.textContent, "검토 가능 심사역 참여 안내 (선택 1명)");
  assert.strictEqual(t.hint.textContent,
                     "체크한 참여 중 2명은 참여 안내 대상이 아니라 빼고 엽니다");
}

console.log("ok - 딜 소싱 [검토 가능 심사역 참여 안내] · 체크한 대상만 · 뺀 수 · 일부 숨김 · 칸 고침 · 두 단추");
