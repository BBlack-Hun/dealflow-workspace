// 옛 발송기 알림의 [오늘 하루 보지 않기]. (node tests/js/agent_update_skip_test.js)
//
// 띄울지는 서버가 정한다(`services/agent_update.HIDE_COOKIE` — 파이썬 검사가 본다).
// 여기는 브라우저 쪽 한 줄만 본다 — 실제 파일(`static/js/agent_badge.js`)을 그대로 돌린다.
//
//   · 고르고 닫으면 쿠키에 **서버가 실어 준 날짜**(`data-today`)를 적는다.
//   · 안 고르고 닫으면 아무것도 안 적는다 — 그 화면에서만 닫힌다.
//   · 고르기만 하고 닫지 않으면(내려받기로 가면) 안 적는다.
//   · 창이 없는 화면에서는 아무 일도 안 한다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "agent_badge.js"), "utf8");
const DAY = "2026-11-05";

// 서버가 그리는 것과 같은 모양(`_agent_update.html`).
function build(withBox) {
  const skip = D.el("input", { type: "checkbox", id: "agent-update-skip" });
  const box = D.el("dialog", { class: "agent-update", "data-testid": "agent-update",
                               "data-today": DAY }, [
    D.el("form", { method: "dialog", class: "agent-update-later" }, [
      D.el("label", { class: "agent-update-skip" }, [skip]),
      D.el("button", { type: "submit", class: "linkbtn" })
    ])
  ]);
  return { root: D.el("div", {}, withBox ? [box] : []), box: box, skip: skip };
}

function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  document.cookie = "";
  const sandbox = {
    document: document,
    setInterval: function () {},
    fetch: function () { return Promise.resolve({ ok: false }); },
    history: {}
  };
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "agent_badge.js" });
  return document;
}

// 1) 고르고 닫으면 오늘 날짜를 적는다 — 내일이면 서버가 날짜가 어긋난 것을 보고 다시 띄운다.
{
  const dom = build(true);
  const document = run(dom);
  dom.skip.checked = true;
  dom.box.fire("close");
  assert.strictEqual(document.cookie,
    "agent_update_hide=" + DAY + "; path=/; max-age=86400; SameSite=Lax",
    "고르고 닫았는데 오늘 날짜가 쿠키에 안 남았습니다");
}

// 2) 안 고르고 닫으면 그 화면에서만 닫힌다 — 아무것도 안 적는다.
{
  const dom = build(true);
  const document = run(dom);
  dom.box.fire("close");
  assert.strictEqual(document.cookie, "", "고르지 않았는데 쿠키를 적었습니다");
}

// 3) 고르기만 하고 닫지 않으면 안 적는다 — 닫을 때 정한다.
{
  const dom = build(true);
  const document = run(dom);
  dom.skip.checked = true;
  dom.skip.fire("change");
  assert.strictEqual(document.cookie, "", "닫기도 전에 쿠키를 적었습니다");
}

// 4) 창이 없는 화면에서는 아무 일도 안 한다(그리고 죽지 않는다).
{
  const document = run(build(false));
  assert.strictEqual(document.cookie, "");
}

console.log("agent_update_skip_test: ok");
