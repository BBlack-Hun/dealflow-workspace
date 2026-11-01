"use strict";
/* 투자사 관리 현황 — 고른 줄 한 번에 이관. (node tests/js/bulk_transfer_test.js)
 *
 * 서버 쪽(누가 넘길 수 있나 · 건너뛰는 줄 · 수정 기록)은 파이썬 검사가 본다
 * (`tests/test_contacts_bulk_transfer.py`). 여기서 보는 것은 브라우저에서만 잴 수
 * 있는 자리다.
 *
 *   · 하나라도 골라야 막대와 [선택한 N명 이관] 이 선다
 *   · 머리글 [전체 선택]은 **보이는 줄만** 고른다 — 가린 줄의 체크는 끈다
 *   · 받을 담당자를 안 고르거나 확인창에서 [취소]하면 한 건도 안 나간다
 *   · 결과(성공 · 건너뜀과 이유)를 알리고 화면을 다시 받는다
 *   · 체크 칸을 눌러도 수정창이 안 열린다(`contacts.js` 의 줄 누름)
 *
 * 진짜 파일을 vm 으로 돌린다. 이름은 전부 지어낸 것이다(공개 저장소).
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const D = require("./_dom.js");

const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const SRC = fs.readFileSync(path.join(JS, "bulk_transfer.js"), "utf8");
const CONTACTS_SRC = fs.readFileSync(path.join(JS, "contacts.js"), "utf8");
const MODAL_SRC = fs.readFileSync(path.join(JS, "panel_modal.js"), "utf8");

const ROWS = [[11, "가담당"], [12, "나담당"], [13, "다담당"]];

function build() {
  const rows = ROWS.map(function (pair) {
    const cb = D.el("input", { type: "checkbox", class: "transfer-cb",
                               value: String(pair[0]), "data-name": pair[1] });
    return D.el("tr", { class: "data-row", "data-id": String(pair[0]) }, [
      D.el("td", { class: "stick stick-lead" }, [cb]),
      D.el("td", { class: "rowno muted js-detail stick stick-a" })
    ]);
  });
  const pickAll = D.el("input", { type: "checkbox", id: "transfer-pick-all" });
  const opts = [D.el("option", { value: "" }),
                D.el("option", { value: "라 명단", "data-owner": "라팀원" })];
  const select = D.el("select", { id: "bulk-transfer-target" }, opts);
  select.options = opts;
  select.selectedIndex = 0;
  const bar = D.el("div", { class: "assign-bar", id: "transfer-bar" }, [
    D.el("span", { id: "transfer-count" }), select,
    D.el("button", { id: "transfer-bulk-btn" })
  ]);
  bar.hidden = true;
  const table = D.el("table", { id: "contacts-table" }, [
    D.el("thead", {}, [D.el("tr", {}, [D.el("th", { class: "stick stick-lead" }, [pickAll])])]),
    D.el("tbody", {}, rows)
  ]);
  // 수정창 — `contacts.js` 가 줄을 누르면 여는 자리(`contacts_scroll_keep_test.js` 와 같은 뼈대).
  const panel = D.el("aside", { id: "detail-panel" }, [
    D.el("h2", { id: "detail-title" }), D.el("p", { id: "detail-msg" }),
    D.el("input", { id: "f-name" }), D.el("ul", { id: "timeline" }),
    D.el("button", { id: "save-btn" }), D.el("button", { id: "detail-close" })
  ]);
  panel.hidden = true;
  const backdrop = D.el("div", { id: "detail-backdrop" });
  backdrop.hidden = true;
  return D.el("div", {}, [bar, D.el("div", { class: "table-wrap wide" }, [table]),
                          backdrop, panel]);
}

function run(replies, opts) {
  D.resetHandlers();
  const root = build();
  const calls = [], alerted = [], asked = [];
  let reloads = 0;
  const sandbox = {
    document: D.makeDocument(root), console: console, setTimeout: setTimeout,
    window: { location: { pathname: "/contacts", search: "", href: "",
                          reload() { reloads += 1; } },
              addEventListener() {}, removeEventListener() {} },
    alert(m) { alerted.push(String(m)); },
    confirm(m) { asked.push(String(m)); return !(opts && opts.cancel); },
    MutationObserver: function () { this.observe = function () {}; },
    fetch(url, o) {
      calls.push({ url: url, body: o && o.body ? JSON.parse(o.body) : null });
      const next = (replies || []).shift() || { d: {} };
      return Promise.resolve({ ok: next.ok !== false,
                               json() { return Promise.resolve(next.d); } });
    }
  };
  vm.createContext(sandbox);
  if (opts && opts.withContacts) {
    sandbox.window.document = sandbox.document;
    vm.runInContext(MODAL_SRC, sandbox, { filename: "panel_modal.js" });
    vm.runInContext(CONTACTS_SRC, sandbox, { filename: "contacts.js" });
  }
  vm.runInContext(SRC, sandbox, { filename: "bulk_transfer.js" });
  const q = function (s) { return root.querySelector(s); };
  return { calls, alerted, asked, reloads: function () { return reloads; },
           boxes: root.querySelectorAll(".transfer-cb"),
           all: q("#transfer-pick-all"), bar: q("#transfer-bar"),
           btn: q("#transfer-bulk-btn"), count: q("#transfer-count"),
           select: q("#bulk-transfer-target") };
}

const tick = () => new Promise((r) => setImmediate(r));
function pick(t, i) { t.boxes[i].checked = true; t.boxes[i].fire("change"); }
function checkedIds(t) {
  return t.boxes.filter(function (cb) { return cb.checked; })
    .map(function (cb) { return parseInt(cb.value, 10); });
}

(async function () {
  // ── 1) 고르기 전에는 막대가 없고, 하나 고르면 선다 ──────────────────────
  {
    const t = run();
    assert.strictEqual(t.bar.hidden, true, "아무도 안 골랐는데 이관 막대가 떠 있다");
    assert.strictEqual(t.btn.disabled, true);
    pick(t, 0);
    assert.strictEqual(t.bar.hidden, false, "골랐는데 이관 막대가 안 선다");
    assert.strictEqual(t.btn.textContent, "선택한 1명 이관");
    assert.strictEqual(t.count.textContent, "1명 선택");
    assert.strictEqual(t.btn.disabled, false);
    t.boxes[0].checked = false; t.boxes[0].fire("change");
    assert.strictEqual(t.bar.hidden, true, "다 풀었는데 막대가 남았다");
  }

  // ── 2) ★ [전체 선택]은 보이는 줄만 — 가린 줄의 체크는 끈다 ───────────────
  {
    const t = run();
    pick(t, 2);                                   // 먼저 고른 줄을
    t.boxes[2].closest("tr").hidden = true;       // 검색이 가렸다
    t.all.checked = true; t.all.fire("change");
    assert.deepStrictEqual(checkedIds(t), [11, 12],
      "검색으로 가린 줄까지 [전체 선택]에 걸렸다 — 화면에 없는 사람이 넘어간다");
    assert.strictEqual(t.btn.textContent, "선택한 2명 이관");
    t.all.checked = false; t.all.fire("change");
    assert.deepStrictEqual(checkedIds(t), [], "[전체 선택]을 풀었는데 체크가 남았다");
    assert.strictEqual(t.bar.hidden, true);
  }

  // ── 3) 받을 담당자를 안 고르면 안 나간다 ─────────────────────────────────
  {
    const t = run();
    pick(t, 0);
    t.btn.fire("click");
    await tick();
    assert.strictEqual(t.calls.length, 0, "받을 담당자 없이 이관이 나갔다");
    assert.ok(/받을 담당자/.test(t.alerted[0] || ""), "왜 안 되는지 안 알린다");
  }

  // ── 4) [취소]하면 한 건도 안 나간다 ──────────────────────────────────────
  {
    const t = run([], { cancel: true });
    pick(t, 0);
    t.select.selectedIndex = 1; t.select.value = "라 명단";
    t.btn.fire("click");
    await tick();
    assert.strictEqual(t.asked.length, 1);
    assert.strictEqual(t.calls.length, 0, "확인창에서 [취소]했는데 이관이 나갔다");
  }

  // ── 5) 묻고, 보내고, 결과를 알리고, 다시 받는다 ──────────────────────────
  {
    const t = run([{ d: { ok: true, label: "라 명단", owner: "라팀원",
                          moved: [{ id: 11, name: "가담당", moved: "가 명단 → 라 명단" }],
                          skipped: [{ id: 12, name: "나담당", why: "이미 그 명단에 있습니다" }] } }]);
    pick(t, 0); pick(t, 1);
    t.select.selectedIndex = 1; t.select.value = "라 명단";
    t.btn.fire("click");
    await tick(); await tick();
    assert.ok(/2명을 라팀원 님에게 이관합니다/.test(t.asked[0]),
      "확인창이 몇 명을 누구에게 넘기는지 안 적는다: " + t.asked[0]);
    assert.ok(/가담당, 나담당/.test(t.asked[0]), "확인창에 누구를 넘기는지 없다");
    assert.ok(/월별 기록/.test(t.asked[0]), "확인창이 월별 기록 이야기를 안 한다");
    assert.strictEqual(t.calls[0].url, "/api/contacts/bulk-transfer");
    assert.deepStrictEqual(t.calls[0].body, { contact_ids: [11, 12], label: "라 명단" });
    assert.ok(/성공 1명 · 건너뜀 1명/.test(t.alerted[0]), "결과 수를 안 알린다: " + t.alerted[0]);
    assert.ok(/나담당 — 이미 그 명단/.test(t.alerted[0]), "건너뛴 이유를 안 알린다");
    assert.strictEqual(t.reloads(), 1, "넘긴 뒤 표를 다시 안 받았다");
  }

  // ── 6) 서버가 거절하면 알리고 단추를 되살린다 ────────────────────────────
  {
    const t = run([{ ok: false, d: { detail: "담당자를 찾을 수 없습니다" } }]);
    pick(t, 0);
    t.select.selectedIndex = 1; t.select.value = "라 명단";
    t.btn.fire("click");
    await tick(); await tick();
    assert.ok(/찾을 수 없습니다/.test(t.alerted[0] || ""));
    assert.strictEqual(t.reloads(), 0);
    assert.strictEqual(t.btn.disabled, false, "거절된 뒤 단추가 잠긴 채로 남았다");
  }

  // ── 7) ★ 체크 칸을 눌러도 수정창이 안 열린다 — 줄의 다른 칸은 연다 ────────
  {
    const t = run([], { withContacts: true });
    t.boxes[0].fire("click");
    t.boxes[0].parent.fire("click");              // 체크 칸 둘레(td)를 눌러도
    await tick();
    assert.strictEqual(t.calls.length, 0,
      "체크 칸을 눌렀는데 수정창을 열었다 — 여러 줄을 고를 수가 없다");
    t.boxes[0].closest("tr").children[1].fire("click");   // NO 칸
    await tick();
    assert.strictEqual(t.calls[0] && t.calls[0].url, "/api/contacts/11",
      "줄의 다른 칸을 눌렀는데 수정창이 안 열린다");
  }

  console.log("bulk_transfer_test: ok");
})().catch(function (e) { console.error(e); process.exit(1); });
