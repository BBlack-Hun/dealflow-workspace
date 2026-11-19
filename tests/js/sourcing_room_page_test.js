// 딜 소싱 카톡방 찾기 화면 — **체크한 분만** 찾기 (`sourcing_room_page.js`).
// (node tests/js/sourcing_room_page_test.js)
//
//   ① 아무도 안 골랐으면 단추가 잠기고 `(0명)`, 실린 줄 번호가 없다
//   ② 체크할 때마다 단추의 인원수 · 폼의 `ids` 가 따라간다
//   ③ 머리줄 전체 선택 — **잠기지 않은 줄만** 고른다(찾는 중 · 찾을 대상이 아닌 줄은 그대로).
//      다 고르면 머리줄도 체크되고, 하나 풀면 풀린다
//   ④ 잠긴 줄은 체크돼 있어도(브라우저가 되살린 값) 싣지 않는다
//   ⑤ 다른 체크 칸이 바뀌어도 건드리지 않는다 · 폼이 없는 화면에서는 아무것도 안 한다
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const el = dom_.el;

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "sourcing_room_page.js"), "utf8");

function box(id, locked) {
  const b = el("input", { type: "checkbox", class: "js-room-pick", value: String(id) });
  b.value = String(id);
  b.disabled = !!locked;
  return b;
}

function setup(boxes, opts) {
  opts = opts || {};
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const btn = el("button", { type: "submit" });
  btn.disabled = true;
  const ids = el("input", { type: "hidden", name: "ids" });
  const all = el("input", { type: "checkbox", id: "room-pick-all" });
  const other = el("input", { type: "checkbox", class: "something-else" });
  if (!opts.noForm) root.appendChild(el("form", { id: "room-pick-form" }, [ids, btn]));
  root.appendChild(all);
  root.appendChild(other);
  boxes.forEach(function (b) { root.appendChild(b); });
  const ctx = { document: dom_.makeDocument(root), console: console };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx, { filename: "sourcing_room_page.js" });
  return { btn: btn, ids: ids, all: all, other: other };
}

function check(b, on) { b.checked = on; b.fire("change"); }

// --- ① · ② 체크를 따라가는 단추 · 줄 번호 ---------------------------------------
{
  const a = box(3), b = box(5), c = box(8);
  const t = setup([a, b, c]);
  assert.strictEqual(t.btn.disabled, true);
  assert.strictEqual(t.btn.textContent, "체크한 분 찾기 (0명)");
  assert.strictEqual(t.ids.value, "");

  check(a, true);
  check(c, true);
  assert.strictEqual(t.btn.disabled, false);
  assert.strictEqual(t.btn.textContent, "체크한 분 찾기 (2명)");
  assert.strictEqual(t.ids.value, "3,8");
  assert.strictEqual(t.all.checked, false);

  check(a, false);
  check(c, false);
  assert.strictEqual(t.btn.disabled, true);
  assert.strictEqual(t.ids.value, "");
}

// --- ③ 전체 선택 — 잠기지 않은 줄만 ---------------------------------------------
{
  const a = box(3), busy = box(4, true), b = box(5);
  const t = setup([a, busy, b]);
  check(t.all, true);
  assert.deepStrictEqual([a.checked, busy.checked, b.checked], [true, false, true]);
  assert.strictEqual(t.ids.value, "3,5");
  assert.strictEqual(t.btn.textContent, "체크한 분 찾기 (2명)");

  check(a, false);                                   // 하나 풀면 머리줄도 풀린다
  assert.strictEqual(t.all.checked, false);
  check(a, true);                                    // 다 고르면 머리줄도 체크된다
  assert.strictEqual(t.all.checked, true);

  check(t.all, false);
  assert.deepStrictEqual([a.checked, b.checked], [false, false]);
  assert.strictEqual(t.btn.disabled, true);
}

// --- ④ 잠긴 줄은 체크돼 있어도 싣지 않는다 ---------------------------------------
{
  const a = box(3), typed = box(9, true);
  typed.checked = true;
  a.checked = true;                                  // 뒤로 가기로 되살아난 체크
  const t = setup([a, typed]);
  assert.strictEqual(t.ids.value, "3");              // 열자마자 그 셈으로 시작한다
  assert.strictEqual(t.btn.textContent, "체크한 분 찾기 (1명)");
  assert.strictEqual(t.btn.disabled, false);
}

// --- ⑤ 남의 체크 칸 · 폼이 없는 화면 ---------------------------------------------
{
  const a = box(3);
  const t = setup([a]);
  check(a, true);
  t.ids.value = "지켜본다";
  check(t.other, true);
  assert.strictEqual(t.ids.value, "지켜본다");

  const u = setup([box(3)], { noForm: true });
  check(u.all, true);                                // 죽지 않는다
  assert.strictEqual(u.btn.textContent, "");
}

console.log("sourcing_room_page_test OK");
