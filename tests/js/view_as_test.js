"use strict";
/* 팀원 화면으로 보는 중의 발송 단추 끄기. (node tests/js/view_as_test.js)
 *
 * 서버 쪽(403)은 파이썬 검사가 본다(`tests/test_view_as.py`). 여기는 화면이
 * **누르기 전에** 막는지만 본다 — 실제 파일(`static/js/view_as.js`)을 그대로 돌린다.
 *
 *   · `data-send` 단추를 누르면 페이지 스크립트까지 가지 않고 사유가 뜬다.
 *   · `data-send` 폼은 제출만 막고, 안의 칸을 누르는 것은 막지 않는다.
 *   · 보는 중이 아니면(띠 속성이 없으면) 아무것도 하지 않는다.
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "view_as.js"), "utf8");
const NOTE = "팀원 화면으로 보는 중에는 발송·예약·방 확인을 할 수 없습니다";

function el(tag, attrs, parent) {
  const a = Object.assign({}, attrs);
  return {
    tagName: tag, parent: parent || null,
    getAttribute(k) { return k in a ? a[k] : null; },
    setAttribute(k, v) { a[k] = v; },
    closest(sel) {
      for (let n = this; n; n = n.parent) {
        if (sel === "[data-send]" && n.getAttribute("data-send") !== null) return n;
      }
      return null;
    },
  };
}

function run(note, marked) {
  const handlers = {};
  const alerts = [];
  const body = el("BODY", note ? { "data-view-as-note": note } : {});
  const document = {
    body: body,
    addEventListener(type, fn, capture) {
      assert.strictEqual(capture, true, type + " 는 잡는 단계에서 들어야 한다");
      handlers[type] = fn;
    },
    querySelectorAll() { return { forEach(fn) { marked.forEach(fn); } }; },
  };
  vm.runInNewContext(SRC, { document: document, alert(m) { alerts.push(m); } });
  function fire(type, target) {
    const ev = { target: target, prevented: false, stopped: false,
                 preventDefault() { this.prevented = true; },
                 stopImmediatePropagation() { this.stopped = true; } };
    if (handlers[type]) handlers[type](ev);
    return ev;
  }
  return { fire: fire, alerts: alerts, handlers: handlers };
}

// ── 보는 중: 단추는 막히고 사유가 뜬다 ──────────────────────────────────────
{
  const button = el("BUTTON", { "data-send": "" });
  const form = el("FORM", { "data-send": "" });
  const field = el("SELECT", {}, form);
  const plain = el("BUTTON", {});
  const page = run(NOTE, [button, form]);

  assert.strictEqual(button.title, NOTE, "올리면 사유가 떠야 한다");
  assert.strictEqual(button.getAttribute("aria-disabled"), "true");

  const click = page.fire("click", button);
  assert.ok(click.prevented && click.stopped, "발송 단추가 페이지 스크립트까지 갔다");
  assert.deepStrictEqual(page.alerts, [NOTE]);

  const inside = page.fire("click", field);
  assert.ok(!inside.prevented, "폼 안의 칸을 누르는 것까지 막았다");

  const sent = page.fire("submit", form);
  assert.ok(sent.prevented && sent.stopped, "발송 폼이 제출됐다");

  const other = page.fire("click", plain);
  assert.ok(!other.prevented, "발송과 상관없는 단추까지 막았다");
}

// ── 보는 중이 아니면 아무것도 하지 않는다 ────────────────────────────────────
{
  const button = el("BUTTON", { "data-send": "" });
  const page = run(null, [button]);
  assert.deepStrictEqual(Object.keys(page.handlers), [], "보는 중이 아닌데 단추를 막는다");
  assert.strictEqual(button.title, undefined);
}

console.log("view_as ok");
