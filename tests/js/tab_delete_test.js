"use strict";
/* 탭 지우기 — 브라우저에서만 잴 수 있는 자리.
 * (node tests/js/tab_delete_test.js)
 *
 * 서버 쪽(누가 지울 수 있나 · 무엇이 지워지고 남나 · 로그)은 파이썬 검사가
 * 본다(`tests/test_tab_delete.py`). 여기서 보는 것은 셋이다.
 *
 *   · 확인 전에 서버에 묻는 부름이 `confirm: false` 인가 — 참으로 가면
 *     세어 보기가 곧 삭제가 된다.
 *   · 확인창이 **몇 명이 지워지고 몇 명이 남는지 · 함께 지워지는 이력(활동 ·
 *     발송 기록 · IR 요청 · 미팅) 몇 건**과 지난 보고 숫자가 준다는 말을 하는가.
 *   · [취소] · 나가는 중인 회차가 막을 때 **한 건도 안 나가는가.**
 *
 * 규칙을 옮겨 적지 않는다 — 진짜 `tab_delete.js` 를 vm 으로 돌린다.
 * 이름은 전부 지어낸 것이다(공개 저장소).
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js",
                      "tab_delete.js");
const src = fs.readFileSync(SRC, "utf8");
const LABEL = "가나다벤처스 시험 탭";

function run(replies, opts) {
  D.resetHandlers();
  const root = D.el("div", {}, [
    D.el("button", { id: "tab-delete-btn", "data-label": LABEL })
  ]);
  const calls = [];
  const alerted = [];
  const asked = [];
  const sandbox = {
    document: D.makeDocument(root),
    window: { location: { pathname: "/contacts", href: "" } },
    alert(m) { alerted.push(String(m)); },
    confirm(m) { asked.push(String(m)); return !(opts && opts.cancel); },
    encodeURIComponent: encodeURIComponent,
    fetch(url, o) {
      const body = o && o.body ? JSON.parse(o.body) : null;
      calls.push({ url: url, body: body });
      const next = replies.shift();
      if (!next) throw new Error("예상보다 많이 불렀습니다: " + url);
      return Promise.resolve({
        ok: next.ok !== false,
        json() { return Promise.resolve(next.d); }
      });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "tab_delete.js" });
  return { calls, alerted, asked, win: sandbox.window,
           btn: root.querySelector("#tab-delete-btn") };
}

const tick = () => new Promise((r) => setImmediate(r));

function plan(over) {
  return Object.assign({ label: LABEL, only: 3, shared: 2, activities: 7,
                         sends: 5, sequences: 1, ir_requests: 2, meetings: 1,
                         live_jobs: [], blocked: [] }, over || {});
}

(async function () {
  // ── 1) 먼저 세어 보고, 수를 보여 주고, 그 다음에 지운다 ──────────────────
  {
    const t = run([
      { d: { ok: false, confirmed: false, plan: plan() } },
      { d: { ok: true, confirmed: true, plan: plan(), deleted: 3, kept: 2,
             back: "/contacts",
             snapshot: "snapshot-before-tab-delete-x-20261007-120000.db" } }
    ]);
    t.btn.fire("click");
    await tick(); await tick(); await tick();

    assert.strictEqual(t.calls.length, 2, "부름이 두 번이 아니다");
    assert.strictEqual(t.calls[0].url, "/api/contacts/sheets/delete");
    assert.strictEqual(t.calls[0].body.confirm, false,
      "세어 보는 부름이 `confirm: true` 로 나갔다 — 세어 보기가 곧 삭제가 된다");
    assert.strictEqual(t.calls[0].body.label, LABEL);

    assert.strictEqual(t.asked.length, 1, "확인창을 안 띄웠다");
    const q = t.asked[0];
    assert.ok(/되돌릴 수 없/.test(q), "되돌릴 수 없다는 말이 없다: " + q);
    assert.ok(/함께 지워지는 투자사 3명/.test(q), "지워지는 사람 수가 없다: " + q);
    assert.ok(/남는 2명/.test(q), "남는 사람 수가 없다: " + q);
    assert.ok(/활동 이력 7건/.test(q), "함께 지워지는 활동 이력 수가 없다: " + q);
    assert.ok(/발송 기록 5건/.test(q), "함께 지워지는 발송 기록 수가 없다: " + q);
    assert.ok(/IR 요청 2건/.test(q), "함께 지워지는 IR 요청 수가 없다: " + q);
    assert.ok(/미팅 1건/.test(q), "함께 지워지는 미팅 수가 없다: " + q);
    assert.ok(/지난 보고·대시보드 숫자가 줄어듭니다/.test(q),
      "지난 보고 숫자가 바뀐다는 경고가 없다: " + q);

    assert.strictEqual(t.calls[1].body.confirm, true);
    assert.strictEqual(t.calls[1].body.label, LABEL);
    assert.ok(t.win.location.href.indexOf("/contacts?msg=") === 0,
      "지운 뒤 그 화면으로 돌아가지 않는다: " + t.win.location.href);
    assert.ok(!/sheet=/.test(t.win.location.href),
      "지운 탭을 다시 열려고 한다 — 없는 탭이다");
    assert.ok(/snapshot-before-tab-delete/.test(decodeURIComponent(t.win.location.href)),
      "지우기 직전 백업 파일 이름을 안 알려 준다");
  }

  // ── 2) ★ [취소]를 누르면 한 건도 안 나간다 ───────────────────────────────
  {
    const t = run([{ d: { ok: false, confirmed: false, plan: plan() } }],
                  { cancel: true });
    t.btn.fire("click");
    await tick(); await tick();

    assert.strictEqual(t.calls.length, 1,
      "확인창에서 [취소]를 눌렀는데 삭제가 나갔다 — 확인창이 장식이다");
    assert.strictEqual(t.win.location.href, "", "취소했는데 화면을 옮겼다");
    assert.strictEqual(t.btn.disabled, false, "취소한 뒤 단추가 잠긴 채로 남았다");
  }

  // ── 3) 이력이 걸린 사람이 있어도 막지 않는다(사용자 결정) ────────────────
  {
    const t = run([{ d: { ok: false, confirmed: false,
                          plan: plan({ blocked: [] }) } }], { cancel: true });
    t.btn.fire("click");
    await tick(); await tick();
    assert.strictEqual(t.alerted.length, 0, "이력이 있다고 막았다");
    assert.strictEqual(t.asked.length, 1, "확인창을 안 띄웠다");
  }

  // ── 3-1) 나가는 중인 회차가 있으면 어느 회차인지 말하고 멈춘다 ───────────
  {
    const t = run([{ d: { ok: false, confirmed: false,
                          plan: plan({ live_jobs: [{ job_id: 42, kind: "deal_intro",
                                                     status: "running",
                                                     items: 2 }] }) } }]);
    t.btn.fire("click");
    await tick(); await tick();

    assert.strictEqual(t.calls.length, 1, "나가는 중인데 삭제가 나갔다");
    assert.strictEqual(t.asked.length, 0, "막혔는데 확인창을 띄웠다");
    assert.strictEqual(t.alerted.length, 1, "왜 막혔는지 말하지 않는다");
    assert.ok(/#42/.test(t.alerted[0]) && /running/.test(t.alerted[0]),
      "어느 회차 때문에 막혔는지 안 적혀 있다: " + t.alerted[0]);
  }

  // ── 4) 서버가 거절하면 그 말을 그대로 보여 준다(403 등) ───────────────────
  {
    const t = run([{ ok: false, d: { detail: "관리자만 사용할 수 있습니다" } }]);
    t.btn.fire("click");
    await tick(); await tick();
    assert.strictEqual(t.calls.length, 1);
    assert.ok(/관리자만/.test(t.alerted[0] || ""), "거절 사유가 안 보인다");
  }

  console.log("tab_delete: ok");
})().catch(function (e) { console.error(e); process.exit(1); });
