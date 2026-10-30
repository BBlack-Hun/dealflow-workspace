// 월간 스타트업 발송(`/deals/startup-ir`)의 [보냄] 머리 체크 — 전체 선택.
// (node tests/js/startup_send_check_all_test.js)
//
// 사용자: "월간 스타트업 리스트 체크할 때 전체 체크박스도 필요한 거 같아."
//
//   ① 처음엔 줄이 다 켜져 있으니 머리도 켜져 있다 — 줄을 풀면 `일부` → `없음`
//   ② 머리를 누르면 보낼 수 있는 줄을 다 켜고, 다시 누르면 다 끈다
//   ③ 꺼진 칸(disabled)과 폼 밖(미계약 구역)은 건드리지 않는다
//   ④ 숨은 줄은 켜지 않고, 숨은 줄에 체크가 남으면 머리는 `일부`
//      (`sourcing.html` 의 `syncCheckAll` 과 같은 규칙)
//   ⑤ 보낼 수 있는 줄이 없으면 머리가 잠긴다
//
// 화면 스크립트는 `startup_send.html` 안에 있다 — 그 글을 그대로 읽어 돌린다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const el = dom_.el;

const HTML = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "templates", "startup_send.html"), "utf8");
const inline = /<script>([\s\S]*?)<\/script>/.exec(HTML.split("{% block scripts %}")[1])[1];

// 머리 체크가 폼 **안**에 서야 한다 — 밖이면 `closest("form")` 이 비어 아무것도 안 한다.
const form = HTML.slice(HTML.indexOf('<form method="post" action="/deals/startup-ir/send"'),
                        HTML.indexOf("</form>"));
assert.ok(form.includes('id="startup-check-all"'), "머리 체크가 발송 폼 밖에 있다");

function row(id, opts) {
  opts = opts || {};
  const cb = el("input", { type: "checkbox", name: "company_ids", value: String(id) });
  cb.checked = opts.checked !== false;
  cb.disabled = !!opts.disabled;
  const tr = el("tr", {}, [el("td", {}, [cb])]);
  tr.hidden = !!opts.hidden;
  return tr;
}
// 못 보내는 줄 — 체크칸 없이 `—` 만 있다.
function offRow() { return el("tr", { class: "ir-row-off" }, [el("td", { class: "muted" })]); }

function setup(rows) {
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const all = el("input", { type: "checkbox", id: "startup-check-all" });
  const f = el("form", { method: "post", action: "/deals/startup-ir/send" }, [
    el("table", {}, [
      el("thead", {}, [el("tr", {}, [el("th", {}, [el("label", {}, [all])])])]),
      el("tbody", {}, rows)])]);
  // 폼 밖 미계약 구역에 같은 이름의 칸이 있어도 닿으면 안 된다(실제로는 칸이 없다).
  const outside = el("input", { type: "checkbox", name: "company_ids", value: "999" });
  root.appendChild(f);
  root.appendChild(el("section", { "data-testid": "startup-uncontracted" }, [outside]));
  vm.runInNewContext(inline, { document: dom_.makeDocument(root), console: console },
                     { filename: "startup_send.html<script>" });
  return { all: all, outside: outside };
}

function box(tr) { return tr.querySelector('input[name="company_ids"]'); }
function pick(tr, on) { const cb = box(tr); cb.checked = on; cb.fire("change"); }
function clickAll(t) { t.all.checked = !t.all.checked; t.all.indeterminate = false; t.all.fire("change"); }
function state(all) { return all.checked ? "all" : all.indeterminate ? "some" : "none"; }

// --- ① 처음 · 줄 하나씩 ---------------------------------------------------------
{
  const rows = [row(1), offRow(), row(2), row(3)];
  const t = setup(rows);
  assert.strictEqual(state(t.all), "all", "다 켜진 채로 열렸는데 머리가 안 켜졌다");
  assert.strictEqual(t.all.disabled, false);
  pick(rows[2], false);
  assert.strictEqual(state(t.all), "some", "하나 풀면 `일부` 여야 한다");
  pick(rows[0], false);
  pick(rows[3], false);
  assert.strictEqual(state(t.all), "none", "다 풀면 `없음` 이어야 한다");
  pick(rows[0], true);
  assert.strictEqual(state(t.all), "some");
  pick(rows[2], true);
  pick(rows[3], true);
  assert.strictEqual(state(t.all), "all", "다시 다 켜면 머리도 켜져야 한다");
}

// --- ② 머리를 누르면 다 켜고 · 다 끈다 ----------------------------------------
{
  const rows = [row(1, { checked: false }), row(2), offRow(), row(3, { checked: false })];
  const t = setup(rows);
  assert.strictEqual(state(t.all), "some");
  clickAll(t);                                         // 일부 → 전부
  assert.deepStrictEqual([0, 1, 3].map(function (i) { return box(rows[i]).checked; }),
                         [true, true, true]);
  assert.strictEqual(state(t.all), "all");
  clickAll(t);                                         // 전부 → 없음
  assert.deepStrictEqual([0, 1, 3].map(function (i) { return box(rows[i]).checked; }),
                         [false, false, false]);
  assert.strictEqual(state(t.all), "none");
}

// --- ③ 꺼진 칸 · 폼 밖은 그대로 --------------------------------------------------
{
  const rows = [row(1, { checked: false }), row(2, { checked: false, disabled: true }),
                row(3, { checked: true, disabled: true })];
  const t = setup(rows);
  t.outside.checked = false;
  clickAll(t);
  assert.strictEqual(box(rows[0]).checked, true);
  assert.strictEqual(box(rows[1]).checked, false, "꺼진 칸을 켰다");
  assert.strictEqual(state(t.all), "all", "꺼진 칸은 셈에서 빠져야 한다");
  assert.strictEqual(t.outside.checked, false, "폼 밖(미계약 구역)의 칸을 켰다");
  clickAll(t);
  assert.strictEqual(box(rows[2]).checked, true, "꺼진 칸을 껐다");
  t.outside.checked = true;
  clickAll(t);
  clickAll(t);
  assert.strictEqual(t.outside.checked, true, "폼 밖(미계약 구역)의 칸을 껐다");
}

// --- ④ 숨은 줄 ------------------------------------------------------------------
{
  const rows = [row(1), row(2, { hidden: true }), row(3)];
  const t = setup(rows);
  assert.strictEqual(state(t.all), "some", "숨은 줄에 체크가 남았는데 `전부` 라 한다");
  clickAll(t);
  assert.strictEqual(box(rows[1]).checked, false, "켤 때 숨은 줄의 체크를 남겼다");
  assert.strictEqual(box(rows[0]).checked && box(rows[2]).checked, true);
  assert.strictEqual(state(t.all), "all");
  clickAll(t);
  clickAll(t);
  assert.strictEqual(box(rows[1]).checked, false, "숨은 줄을 켰다");
}

// --- ⑤ 보낼 줄이 없으면 잠긴다 ---------------------------------------------------
{
  const t = setup([offRow(), offRow()]);
  assert.strictEqual(t.all.disabled, true, "고를 줄이 없는데 머리가 눌린다");
  assert.strictEqual(state(t.all), "none");
}

console.log("startup_send_check_all_test: ok");
