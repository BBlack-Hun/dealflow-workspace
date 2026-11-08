// 자동 발송 알림의 [확인]. (node tests/js/auto_alert_seen_test.js)
//
// 띄울지는 서버가 정한다(`automation_runner.alert_for` — 파이썬 검사가 본다). 여기는
// 브라우저 쪽만 본다 — 실제 파일(`static/js/agent_badge.js`)을 그대로 돌린다.
//
//   · 닫으면 그 알림의 열쇠(`data-key`)를 쿠키에 `|` 로 이어 적는다(앞의 열쇠는 둔다).
//   · [자세히 보기] 로 넘어가도 적는다 — 넘어간 화면에서 또 뜨지 않게.
//   · 창이 없는 화면에서는 아무 일도 안 한다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "agent_badge.js"), "utf8");
const TAIL = "; path=/; max-age=604800; SameSite=Lax";

// 서버가 그리는 것과 같은 모양(`_auto_alert.html`).
function build(withBox, key) {
  const go = D.el("a", { class: "primary-btn guard-go", href: "/jobs/1" });
  const box = D.el("dialog", { class: "auto-alert", "data-key": key }, [
    go, D.el("form", { method: "dialog" }, [D.el("button", { type: "submit" })])
  ]);
  return { root: D.el("div", {}, withBox ? [box] : []), box: box, go: go };
}

function run(dom, cookie) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  document.cookie = cookie || "";
  const sandbox = { document: document, setInterval: function () {},
                    fetch: function () { return Promise.resolve({ ok: false }); },
                    history: {} };
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "agent_badge.js" });
  return document;
}

// 1) 닫으면 열쇠를 적는다.
{
  const dom = build(true, "sourcing_invite:2026-10-19:eve");
  const document = run(dom);
  dom.box.fire("close");
  assert.strictEqual(document.cookie, "auto_alert_seen=sourcing_invite:2026-10-19:eve" + TAIL);
}

// 2) 앞서 확인한 열쇠는 두고 뒤에 잇는다.
{
  const dom = build(true, "sourcing_invite:2026-10-20:ready");
  const document = run(dom, "other=1; auto_alert_seen=sourcing_invite:2026-10-19:eve");
  dom.box.fire("close");
  assert.strictEqual(document.cookie,
    "auto_alert_seen=sourcing_invite:2026-10-19:eve|sourcing_invite:2026-10-20:ready" + TAIL);
}

// 3) [자세히 보기] 로 넘어가도 적는다.
{
  const dom = build(true, "sourcing_invite:2026-10-20:done");
  const document = run(dom);
  dom.go.fire("click");
  assert.strictEqual(document.cookie, "auto_alert_seen=sourcing_invite:2026-10-20:done" + TAIL);
}

// 4) 창이 없는 화면에서는 아무 일도 안 한다.
{
  const document = run(build(false, ""));
  assert.strictEqual(document.cookie, "");
}

console.log("auto_alert_seen_test: ok");
