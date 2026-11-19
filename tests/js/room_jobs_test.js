// 방 찾기 화면의 **아직 도는 회차** — 진행 셈과 [중단] (`room_jobs.js` · `_room_jobs.html`).
// (node tests/js/room_jobs_test.js)
//
//   ① 2초마다 `/api/jobs/{id}` 를 물어 돈 건수(찾음 + 못 찾음)를 고친다
//   ② 회차가 끝나면(다 돌았거나 중단) 화면을 새로 열고 더 묻지 않는다
//   ③ [중단] — 확인창을 지나야 `/api/jobs/{id}/cancel` 로 보내고, 되면 화면을 새로 연다.
//      취소하면 아무것도 안 보낸다
//   ④ 중단이 막히면(남의 회차 — 404) 알리고 단추를 다시 연다
//   ⑤ [중단] 단추가 없는 회차(남의 계정 것)도 셈은 따라간다
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const el = dom_.el;

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "room_jobs.js"), "utf8");

function setup(withStop) {
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const done = el("b", { class: "js-room-job-done" });
  done.textContent = "0";
  const stop = el("button", { type: "button", class: "danger-btn js-room-job-stop" });
  root.appendChild(el("p", { class: "warn-box js-room-job", "data-job": "7" },
                      withStop ? [done, stop] : [done]));
  const t = { answer: true, reloads: 0, timers: [], alerts: [], asked: [], calls: [],
              done: done, stop: stop };
  const location = { reload: function () { t.reloads += 1; } };
  const ctx = {
    document: dom_.makeDocument(root), location: location, console: console,
    setTimeout: function (fn) { t.timers.push(fn); return 0; },
    alert: function (m) { t.alerts.push(m); },
    confirm: function (m) { t.asked.push(m); return t.answer; },
    fetch: function (url, init) {
      let resolve;
      const p = new Promise(function (res) { resolve = res; });
      t.calls.push({ url: url, init: init, resolve: resolve });
      return p;
    }
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx, { filename: "room_jobs.js" });
  return t;
}

function settle() { return new Promise(function (r) { setImmediate(r); }); }
function answer(call, status, body) {
  call.resolve({ ok: status < 400, status: status,
                 json: function () { return Promise.resolve(body); } });
  return settle();
}

(async function () {
  // --- ① · ② 셈을 따라가다 끝나면 새로 연다 -------------------------------------
  {
    const t = setup(true);
    assert.strictEqual(t.calls.length, 0);            // 열자마자 묻지 않는다 — 2초 뒤
    t.timers.shift()();
    assert.strictEqual(t.calls[0].url, "/api/jobs/7");
    await answer(t.calls[0], 200, { status: "running", counts: { sent: 2, failed: 1 } });
    assert.strictEqual(t.done.textContent, 3);
    assert.strictEqual(t.reloads, 0);
    t.timers.shift()();
    await answer(t.calls[1], 200, { status: "canceled", counts: { sent: 2, failed: 1 } });
    assert.strictEqual(t.reloads, 1);
    assert.strictEqual(t.timers.length, 0);           // 끝난 뒤에는 더 묻지 않는다
  }

  // --- ③ [중단] — 확인창 → cancel → 새로 열기 ------------------------------------
  {
    const t = setup(true);
    t.answer = false;
    t.stop.fire("click");
    assert.strictEqual(t.asked.length, 1);
    assert.ok(t.asked[0].indexOf("찾기 전 그대로") >= 0);
    assert.strictEqual(t.calls.length, 0);            // 취소 — 아무것도 안 보낸다

    t.answer = true;
    t.stop.fire("click");
    assert.strictEqual(t.calls[0].url, "/api/jobs/7/cancel");
    assert.strictEqual(t.calls[0].init.method, "POST");
    assert.strictEqual(t.stop.disabled, true);
    await answer(t.calls[0], 200, { status: "canceled" });
    assert.strictEqual(t.reloads, 1);
  }

  // --- ④ 막힌 중단 — 알리고 단추를 다시 연다 --------------------------------------
  {
    const t = setup(true);
    t.stop.fire("click");
    await answer(t.calls[0], 404, { detail: "발송 잡 없음" });
    assert.strictEqual(t.reloads, 0);
    assert.strictEqual(t.alerts.length, 1);
    assert.strictEqual(t.stop.disabled, false);
  }

  // --- ⑤ 단추가 없어도 셈은 따라간다 · 볼 수 없는 회차는 그만 묻는다 ----------------
  {
    const t = setup(false);
    t.timers.shift()();
    await answer(t.calls[0], 404, {});
    assert.strictEqual(t.timers.length, 0);
    assert.strictEqual(t.reloads, 0);
  }

  console.log("room_jobs_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
