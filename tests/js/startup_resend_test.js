// 스타트업 월간 발송 — **이미 받은 기업을 켜면 묻고, [확인] 이어야 함께 간다.**
// (node tests/js/startup_resend_test.js)
//
//  1. [확인] → 체크가 남고 그 줄의 `resend_ids` 가 살아난다(서버가 넣는다).
//  2. [취소] → 도로 꺼지고 `resend_ids` 는 죽은 채다(서버가 뺀다).
//  3. 다시 끄면 `resend_ids` 도 죽는다 — 끈 줄이 확인 값만 남겨 딸려 가지 않게.
//  4. 이미 받지 않은 줄은 묻지 않는다.
//  5. 표가 없는 화면에서도 터지지 않는다.
//  6. [취소] 로 도로 끈 것을 change 로 다시 알린다(전체 선택 머리가 다시 센다) — 그 change
//     가 다시 묻지는 않는다.
//
// 체크칸 · 숨은 칸의 모양이 실제 화면과 같은지는 파이썬 쪽이 본다
// (`tests/test_startup_monthly_dedupe.py`).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

function sentRow(id) {
  const box = el("input", { type: "checkbox", name: "company_ids", value: String(id),
                            "data-sent-this-month": "10/30" });
  const ok = el("input", { type: "hidden", name: "resend_ids", value: String(id) });
  ok.disabled = true;
  return el("tr", {}, [el("td", {}, [box, ok])]);
}

function plainRow(id) {
  const box = el("input", { type: "checkbox", name: "company_ids", value: String(id) });
  box.checked = true;
  return el("tr", {}, [el("td", {}, [box])]);
}

function build(answer) {
  dom_.resetHandlers();
  const form = el("form", { method: "post" }, [
    el("table", {}, [el("tbody", {}, [sentRow(1), plainRow(2)])])
  ]);
  const root = el("div", {}, [form]);
  const asked = [];
  const win = { confirm: function (msg) { asked.push(msg); return answer; } };
  const Event = function (type, init) { this.type = type; this.bubbles = !!(init && init.bubbles); };
  const ctx = { document: dom_.makeDocument(root), window: win, console: console, Event: Event };
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  vm.runInNewContext(fs.readFileSync(path.join(JS, "startup_resend.js"), "utf8"),
                     ctx, { filename: "startup_resend.js" });
  const rows = root.querySelectorAll("tr");
  return {
    form: form,
    asked: asked,
    box: function (i) { return rows[i].querySelector('input[name="company_ids"]'); },
    ok: function () { return rows[0].querySelector('input[name="resend_ids"]'); },
    toggle: function (i, on) { const b = this.box(i); b.checked = on; b.fire("change"); }
  };
}

(function 확인하면함께간다() {
  const s = build(true);
  s.toggle(0, true);
  assert.strictEqual(s.asked.length, 1, "켰는데 묻지 않았다");
  assert.ok(s.asked[0].indexOf("10/30") >= 0, "보낸 날을 안 보여 줬다: " + s.asked[0]);
  assert.strictEqual(s.box(0).checked, true, "[확인] 했는데 꺼졌다");
  assert.strictEqual(s.ok().disabled, false, "[확인] 했는데 확인 값이 안 간다 — 서버가 뺀다");

  s.toggle(0, false);
  assert.strictEqual(s.ok().disabled, true, "끈 줄의 확인 값이 남았다");
}());

(function 취소하면도로끈다() {
  const s = build(false);
  s.toggle(0, true);
  assert.strictEqual(s.box(0).checked, false, "[취소] 했는데 켜진 채다");
  assert.strictEqual(s.ok().disabled, true, "[취소] 했는데 확인 값이 간다");
}());

(function 취소하면다시알린다() {
  const s = build(false);
  const seen = [];   // 폼이 들은 change 마다 그 칸이 켜져 있었는가 — 전체 선택 머리가 폼에서 듣는다
  s.form.addEventListener("change", function (ev) { seen.push(ev.target.checked); });
  s.toggle(0, true);
  assert.deepStrictEqual(seen, [true, false], "[취소] 로 끈 것을 다시 알리지 않았다");
  assert.strictEqual(s.asked.length, 1, "다시 알린 change 가 또 물었다");
  assert.strictEqual(s.box(0).checked, false);
  assert.strictEqual(s.ok().disabled, true);
}());

(function 안받은줄은묻지않는다() {
  const s = build(false);
  s.toggle(1, false);
  s.toggle(1, true);
  assert.strictEqual(s.asked.length, 0, "이미 받지 않은 줄에서 물었다");
  assert.strictEqual(s.box(1).checked, true);
}());

(function 표가없으면조용하다() {
  dom_.resetHandlers();
  const root = el("div", {});
  const ctx = { document: dom_.makeDocument(root), window: { confirm: function () {
    throw new Error("물을 것이 없다"); } }, console: console };
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  vm.runInNewContext(fs.readFileSync(path.join(JS, "startup_resend.js"), "utf8"),
                     ctx, { filename: "startup_resend.js" });
  root.fire("change");
}());

console.log("startup_resend_test.js OK");
