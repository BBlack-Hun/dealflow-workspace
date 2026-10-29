// IR 요청 기록의 [지난 회차에서 고르기] — 딜 소싱(Series A 딜 공유)으로 받은 기업도 선다.
// (node tests/js/ir_numbers_sourcing_test.js)
//
//   · 딜 소개 번호 뒤에 머리말을 달고 따로 선다 — 번호가 겹치기 때문이다.
//   · 딜 소개가 없어도 딜 소싱만으로 상자가 열린다.
//   · 누르면 **이름**이 적힌다(번호로 적는 길은 딜 소개 것).
//
// 이름·기업은 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const NUMBERS = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "ir_numbers.js"), "utf8");

function settled(value) {
  return { then: function (fn) { return settled(fn(value)); },
           catch: function () { return this; } };
}

function run(reply) {
  D.resetHandlers();
  const select = D.el("select", { name: "contact_id" });
  select.value = "7";
  const title = D.el("em", { id: "last-batch-title" });
  const pick = D.el("div", { class: "num-pick", id: "num-pick" });
  const box = D.el("div", { id: "last-batch" }, [title, pick]);
  box.hidden = true;
  const textarea = D.el("textarea", { id: "request-companies" });
  const root = D.el("div", {}, [D.el("div", { id: "new-request" }, [select, box, textarea])]);
  const document = D.makeDocument(root);
  const sandbox = {
    document: document, console: console,
    fetch: function () { return settled({ ok: true, json: function () { return reply; } }); }
  };
  vm.createContext(sandbox);
  vm.runInContext(NUMBERS, sandbox, { filename: "ir_numbers.js" });
  return { box: box, title: title, pick: pick, textarea: textarea };
}

const SHARE = { title: "딜 소싱(Series A 딜 공유)", sent_date: "2026-10-22",
                items: [{ label: "[기업1]", name: "샘플비", has_file: false }] };

// ── 1. 딜 소개 번호 뒤에 머리말 + 딜 소싱 칩 ─────────────────────────────
{
  const t = run({ title: "딜 소개", sent_date: "2026-10-01",
                  items: [{ label: "[기업1]", name: "샘플에이", has_file: true }],
                  sourcing: SHARE });
  assert.strictEqual(t.box.hidden, false);
  assert.strictEqual(t.title.textContent, "딜 소개 · 2026-10-01");
  assert.deepStrictEqual(t.pick.children.map(function (c) { return c.tag + ":" + c.textContent; }),
    ["button:[기업1] 샘플에이", "em:딜 소싱(Series A 딜 공유) · 2026-10-22", "button:[기업1] 샘플비"],
    "딜 소싱 기업이 머리말 없이 딜 소개 번호와 섞였다");
  t.pick.children[2].fire("click");
  assert.strictEqual(t.textarea.value, "샘플비", "누르면 이름이 적혀야 한다");
}

// ── 2. 딜 소개가 없어도 딜 소싱만으로 열린다 ─────────────────────────────
{
  const t = run({ title: "", sent_date: "", items: [], sourcing: SHARE });
  assert.strictEqual(t.box.hidden, false, "딜 소싱만 받은 분은 상자가 안 열린다");
  assert.strictEqual(t.title.textContent, "");
  assert.strictEqual(t.pick.children.length, 2);
}

// ── 3. 둘 다 없으면 닫힌 채 ───────────────────────────────────────────────
{
  const t = run({ title: "", items: [], sourcing: { items: [] } });
  assert.strictEqual(t.box.hidden, true);
}

console.log("ir_numbers_sourcing_test: ok");
