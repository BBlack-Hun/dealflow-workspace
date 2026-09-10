"use strict";
/* 감춘 줄 골라 지우기 — 브라우저에서만 잴 수 있는 자리.
 * (node tests/js/hidden_delete_test.js)
 *
 * 서버 쪽(누가 지울 수 있나 · 무엇이 막히나 · 로그에 남나)은 파이썬 검사가
 * 본다(`tests/test_contacts_bulk_delete.py`). 여기서 보는 것은 넷이다.
 *
 *   · [전체 선택]이 **화면에 보이는 줄에만** 걸리는가 — 검색·필터로 감춰 둔
 *     줄까지 딸려 오면, 사람이 못 보는 줄이 그대로 사라진다.
 *   · 확인창에서 [취소]를 누르면 **한 건도 안 나가는가** — 확인창을 띄워
 *     놓고 이미 보내 버리면 확인창은 장식이다.
 *   · 확인 전에 서버에 묻는 부름이 `confirm: false` 인가 — 그 부름이 참으로
 *     가면 세어 보기가 곧 삭제가 된다.
 *   · 못 지우는 줄이 있으면 **체크를 풀고 멈추는가.**
 *
 * 규칙을 옮겨 적지 않는다 — 진짜 `hidden_delete.js` 를 vm 으로 돌린다.
 * 이름은 전부 지어낸 것이다(공개 저장소).
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js",
                      "hidden_delete.js");
const src = fs.readFileSync(SRC, "utf8");

// 감춘 줄 셋(상자 있음) + 보이는 줄 하나(상자 없음).
const HIDDEN = [[11, "가담당"], [12, "나담당"], [13, "다담당"]];

function build() {
  const rows = HIDDEN.map(function (pair) {
    const cb = D.el("input", { type: "checkbox", class: "hidden-del-cb",
                               value: String(pair[0]), "data-name": pair[1] });
    return D.el("tr", { class: "data-row", "data-name": pair[1] },
                [D.el("td", {}, [cb])]);
  });
  // 감추지 않은 줄 — 상자가 없다(contacts.html 이 안 세운다).
  rows.push(D.el("tr", { class: "data-row", "data-name": "라담당" },
                 [D.el("td", {})]));

  const root = D.el("div", {}, [
    D.el("div", { class: "assign-bar delete-bar", id: "hidden-del-bar",
                  "data-sheet": "투자사 시험 명단" }, [
      D.el("input", { type: "checkbox", id: "pick-all-hidden" }),
      D.el("span", { id: "hidden-del-count" }),
      D.el("button", { id: "hidden-del-btn" })
    ]),
    D.el("table", { id: "contacts-table" }, [D.el("tbody", {}, rows)])
  ]);
  root.querySelector("#hidden-del-btn").disabled = true;
  return root;
}

function run(replies, opts) {
  D.resetHandlers();
  const root = build();
  const calls = [];
  const alerted = [];
  const asked = [];
  const sandbox = {
    document: D.makeDocument(root),
    window: { location: { pathname: "/contacts", href: "" } },
    alert(m) { alerted.push(String(m)); },
    confirm(m) { asked.push(String(m)); return !(opts && opts.cancel); },
    fetch(url, o) {
      const body = o && o.body ? JSON.parse(o.body) : null;
      calls.push({ url: url, method: (o && o.method) || "GET", body: body });
      const next = replies.shift();
      if (!next) throw new Error("예상보다 많이 불렀습니다: " + url);
      return Promise.resolve({
        ok: next.ok !== false,
        json() { return Promise.resolve(next.d); }
      });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "hidden_delete.js" });
  return { root, calls, alerted, asked, win: sandbox.window,
           doc: sandbox.document,
           boxes: root.querySelectorAll(".hidden-del-cb"),
           btn: root.querySelector("#hidden-del-btn"),
           count: root.querySelector("#hidden-del-count"),
           all: root.querySelector("#pick-all-hidden") };
}

const tick = () => new Promise((r) => setImmediate(r));

function plan(over) {
  return Object.assign({ total: 2, deletable: 2, blocked: [], activities: 0,
                         sends: 0, sequences: 0, ir_requests: 0,
                         meetings: 0 }, over || {});
}

function checkedIds(t) {
  return t.boxes.filter(function (cb) { return cb.checked; })
    .map(function (cb) { return parseInt(cb.value, 10); });
}

(async function () {
  // ── 1) 아무 것도 안 골랐으면 눌리지 않는다 ────────────────────────────────
  {
    const t = run([]);
    assert.strictEqual(t.count.textContent, "0줄 선택");
    assert.strictEqual(t.btn.disabled, true,
      "아무 것도 안 골랐는데 [선택 삭제]가 눌린다");
    assert.strictEqual(t.btn.textContent, "선택 삭제");
  }

  // ── 2) 고른 수가 셈과 단추에 함께 적힌다 ─────────────────────────────────
  //
  // 80줄과 8줄은 다른 일이다. 확인창을 보기 전에 몇 줄이 걸린 일인지 알아야 한다.
  {
    const t = run([]);
    t.boxes[0].checked = true;
    t.boxes[0].fire("change");
    assert.strictEqual(t.count.textContent, "1줄 선택");
    assert.strictEqual(t.btn.textContent, "선택 삭제 (1줄)");
    assert.strictEqual(t.btn.disabled, false);
  }

  // ── 3) ★ [전체 선택]은 **보이는 줄에만** 걸린다 ──────────────────────────
  //
  // 검색·필터가 줄을 `tr.hidden` 으로 감춘다. 그 줄까지 켜지면 화면에 없는
  // 사람이 사라진다 — 되돌릴 수가 없다.
  {
    const t = run([]);
    t.boxes[2].closest("tr").hidden = true;      // 검색으로 감춰 둔 줄

    t.all.checked = true;
    t.all.fire("change");
    assert.deepStrictEqual(checkedIds(t), [11, 12],
      "검색으로 감춘 줄까지 [전체 선택]에 딸려 왔다");
    assert.strictEqual(t.count.textContent, "2줄 선택");

    t.all.checked = false;
    t.all.fire("change");
    assert.deepStrictEqual(checkedIds(t), [],
      "[전체 선택]을 되돌렸는데 체크가 남았다");
  }

  // ── 4) 먼저 세어 보고, 확인을 받고, 그 다음에 지운다 ─────────────────────
  {
    const t = run([
      { d: { ok: false, confirmed: false, deleted: 0,
             plan: plan({ activities: 5 }) } },
      { d: { ok: true, confirmed: true, deleted: 2, plan: plan() } }
    ]);
    t.boxes[0].checked = true;
    t.boxes[1].checked = true;
    t.boxes[0].fire("change");
    t.btn.fire("click");
    await tick(); await tick();

    assert.strictEqual(t.calls.length, 2, "부름이 두 번이 아니다");
    assert.strictEqual(t.calls[0].url, "/api/contacts/bulk-delete");
    assert.strictEqual(t.calls[0].body.confirm, false,
      "세어 보는 부름이 `confirm: true` 로 나갔다 — 세어 보기가 곧 삭제가 된다");
    assert.deepStrictEqual(t.calls[0].body.contact_ids, [11, 12],
      "고른 줄 말고 다른 줄이 실려 나갔다");

    assert.strictEqual(t.asked.length, 1, "확인창을 안 띄웠다");
    assert.ok(/되돌릴 수 없/.test(t.asked[0]),
      "확인창이 되돌릴 수 없다는 말을 안 한다: " + t.asked[0]);
    assert.ok(/2줄/.test(t.asked[0]), "몇 줄을 지우는지 안 적혀 있다");
    assert.ok(/활동 이력 5건/.test(t.asked[0]),
      "함께 사라지는 것을 확인창이 말하지 않는다: " + t.asked[0]);

    assert.strictEqual(t.calls[1].body.confirm, true);
    assert.deepStrictEqual(t.calls[1].body.contact_ids, [11, 12]);
    assert.ok(/hidden=1/.test(t.win.location.href),
      "지운 뒤 [함께 보기] 를 잃었다 — 남은 감춘 줄을 다시 찾아 들어가야 한다");
    assert.ok(/sheet=/.test(t.win.location.href), "보던 명단 탭을 잃었다");
  }

  // ── 5) ★ [취소]를 누르면 한 건도 안 나간다 ───────────────────────────────
  {
    const t = run([{ d: { ok: false, confirmed: false, deleted: 0,
                          plan: plan({ total: 1, deletable: 1 }) } }],
                  { cancel: true });
    t.boxes[0].checked = true;
    t.boxes[0].fire("change");
    t.btn.fire("click");
    await tick(); await tick();

    assert.strictEqual(t.calls.length, 1,
      "확인창에서 [취소]를 눌렀는데 삭제가 나갔다 — 확인창이 장식이다");
    assert.strictEqual(t.win.location.href, "", "취소했는데 화면을 옮겼다");
    assert.strictEqual(t.btn.disabled, false,
      "취소한 뒤 단추가 잠긴 채로 남았다 — 다시 고를 수가 없다");
  }

  // ── 6) 못 지우는 줄이 있으면 **체크를 풀고 멈춘다** ──────────────────────
  //
  // 그대로 나머지를 지워 버리면 사람이 고른 것과 사라진 것이 달라진다.
  {
    const t = run([{ d: { ok: false, confirmed: false, deleted: 0,
                          plan: plan({ total: 2, deletable: 1, sends: 3,
                                       blocked: [{ id: 11, name: "가담당",
                                                   why: ["발송 기록", "미팅"] }] }) } }]);
    t.boxes[0].checked = true;
    t.boxes[1].checked = true;
    t.boxes[0].fire("change");
    t.btn.fire("click");
    await tick(); await tick();

    assert.strictEqual(t.calls.length, 1, "막힌 줄이 있는데 삭제가 나갔다");
    assert.strictEqual(t.asked.length, 0, "막힌 줄이 있는데 확인창부터 띄웠다");
    assert.deepStrictEqual(checkedIds(t), [12],
      "막힌 줄의 체크를 안 풀었다 — 사람이 목록에서 찾아 헤매게 된다");
    assert.strictEqual(t.count.textContent, "1줄 선택", "셈이 안 따라왔다");
    assert.ok(/가담당/.test(t.alerted[0]) && /발송 기록/.test(t.alerted[0]),
      "무엇이 왜 막혔는지 말해 주지 않는다: " + t.alerted[0]);
  }

  // ── 7) 서버가 막으면 그 말을 그대로 보여 준다 ────────────────────────────
  //
  // 화면이 스스로 지어낸 말을 띄우면, 서버가 왜 막았는지가 사라진다.
  {
    const t = run([{ ok: false, d: { detail: "감춘 줄만 지울 수 있습니다" } }]);
    t.boxes[0].checked = true;
    t.boxes[0].fire("change");
    t.btn.fire("click");
    await tick(); await tick();

    assert.strictEqual(t.calls.length, 1);
    assert.deepStrictEqual(t.alerted, ["감춘 줄만 지울 수 있습니다"]);
    assert.strictEqual(t.btn.disabled, false, "단추가 잠긴 채로 남았다");
  }

  console.log("hidden_delete_test: 통과");
})();
