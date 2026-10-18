"use strict";
/* [딜소개 메모 → 활동 이력] (#52) — 브라우저에서만 잴 수 있는 자리.
 * (node tests/js/memo_intro_test.js)
 *
 * 서버 쪽(무엇을 적고 거두나 · 권한)은 `tests/test_memo_intro.py` 가 본다.
 * 여기서는 세어 보는 부름이 `confirm: false` 인지, 확인창이 새로 적을 회차 ·
 * 건너뜀 · 거둘 줄을 말하는지, [취소] · 반영할 것 없음일 때 두 번째 부름이
 * 안 나가는지를 본다. 진짜 `memo_intro.js` 를 vm 으로 돌린다.
 * 이름은 전부 지어낸 것이다(공개 저장소).
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const D = require("./_dom.js");

const src = fs.readFileSync(path.join(__dirname, "..", "..", "app", "static",
                                      "js", "memo_intro.js"), "utf8");
const SHEET = "시험 탭";

function run(replies, opts) {
  D.resetHandlers();
  const root = D.el("div", {}, [
    D.el("button", { id: "memo-intro-btn", "data-sheet": SHEET })
  ]);
  const calls = [], alerted = [], asked = [];
  const sandbox = {
    document: D.makeDocument(root),
    window: { location: { pathname: "/contacts", href: "" } },
    alert(m) { alerted.push(String(m)); },
    confirm(m) { asked.push(String(m)); return !(opts && opts.cancel); },
    encodeURIComponent: encodeURIComponent,
    fetch(url, o) {
      calls.push({ url: url, body: JSON.parse(o.body) });
      const next = replies.shift();
      if (!next) throw new Error("예상보다 많이 불렀습니다: " + url);
      return Promise.resolve({ ok: next.ok !== false,
                               json() { return Promise.resolve(next.d); } });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "memo_intro.js" });
  return { calls, alerted, asked, win: sandbox.window,
           btn: root.querySelector("#memo-intro-btn") };
}

const tick = () => new Promise((r) => setImmediate(r));

function plan(over) {
  return Object.assign({
    start: "2026-10-01",
    add: [{ name: "가담당" }, { name: "나담당" }],
    rounds: [{ column: "10월 1차 딜소개", day: "2026-10-05", people: 2 }],
    already: [{}], undone: [], before_start: [{}], future: [],
    no_date: [{ name: "가담당", column: "10월 1차 딜소개", raw: "머리 줄" }],
    no_company: [],
    retract: [{ name: "다담당", day: "2026-10-12", companies: ["샘플다"] }]
  }, over || {});
}

(async function () {
  // 1) 세어 보고 → 묻고 → 반영
  {
    const t = run([{ d: { plan: plan() } },
                   { d: { plan: plan(), note: "2줄 적음 · 1줄 거둠" } }]);
    t.btn.fire("click");
    await tick(); await tick(); await tick();
    assert.strictEqual(t.calls.length, 2);
    assert.deepStrictEqual(t.calls[0].body, { sheet: SHEET, confirm: false });
    assert.deepStrictEqual(t.calls[1].body, { sheet: SHEET, confirm: true });
    const text = t.asked[0];
    for (const want of ["새로 적을 회차 2줄", "10월 1차 딜소개 2026-10-05 — 2명",
                        "이미 있음 1줄", "날짜 없음 1", "시작 달 이전 1",
                        "머리 줄", "거둘 줄(메모에서 지워진 회차) 1줄",
                        "다담당 · 2026-10-12 · 샘플다"]) {
      assert.ok(text.includes(want), "확인창에 없다: " + want + "\n" + text);
    }
    assert.ok(t.win.location.href.includes("2%EC%A4%84%20%EC%A0%81%EC%9D%8C"),
              t.win.location.href);
  }

  // 2) [취소] 면 두 번째 부름이 없다
  {
    const t = run([{ d: { plan: plan() } }], { cancel: true });
    t.btn.fire("click");
    await tick(); await tick();
    assert.strictEqual(t.calls.length, 1);
    assert.strictEqual(t.btn.disabled, false);
  }

  // 3) 반영할 것이 없으면 묻지 않고 알리기만 한다
  {
    const t = run([{ d: { plan: plan({ add: [], rounds: [], retract: [] }) } }]);
    t.btn.fire("click");
    await tick(); await tick();
    assert.strictEqual(t.calls.length, 1);
    assert.strictEqual(t.asked.length, 0);
    assert.ok(t.alerted[0].includes("반영할 것이 없습니다"));
  }

  // 4) 서버가 막으면(남의 탭) 그 말을 띄운다
  {
    const t = run([{ ok: false, d: { detail: "이 탭의 담당자와 관리자만 반영할 수 있습니다" } }]);
    t.btn.fire("click");
    await tick(); await tick();
    assert.strictEqual(t.calls.length, 1);
    assert.ok(t.alerted[0].includes("담당자와 관리자만"));
  }

  console.log("memo_intro_test: ok");
})().catch((e) => { console.error(e); process.exit(1); });
