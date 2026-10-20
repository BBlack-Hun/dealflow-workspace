// 투자사 관리 현황 수정창 — `딜 소싱` 칸(갈래 셋 체크 상자)은 **고쳤을 때만** 보낸다.
// (node tests/js/contacts_sourcing_join_save_test.js)
//
// 이 칸은 줄에 저장되지 않고 딜 소싱 줄을 잇거나 참여/불참여를 바꾼다
// (`services/sourcing_sync.apply_branches`). 체크 상자가 숨은 칸
// (`f-sourcing_branches`)에 `Series A, M&A` 로 모인다. 수정창이 **열 때 읽은 값**을 저장할 때마다
// 다시 보내면, 메모 한 줄만 고쳐도 그 사이 딜 소싱에서 일어난 일을 되돌린다 —
// 불참여로 바꾼 분을 참여로, 지운 줄을 되살리고, 저절로 이어진 분은 빈칸이라
// 400 으로 다른 칸 수정까지 버린다(PR #284 리뷰).
//
// 이름은 지어낸 값이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(JS, name), "utf8");

const CONTACT = { id: 7, name: "홍길동", title: "심사역", firm: "가나다벤처스",
                  memo: "", sourcing_branches: "Series A" };

function box(value) {
  const input = D.el("input", { type: "checkbox", class: "f-branch", value: value });
  return input;
}

function build() {
  const table = D.el("table", { id: "contacts-table" }, [
    D.el("tbody", {}, [D.el("tr", { class: "data-row", "data-id": "7" })])
  ]);
  const panel = D.el("aside", { id: "detail-panel" }, [
    D.el("h2", { id: "detail-title" }),
    D.el("p", { id: "detail-msg" }),
    D.el("input", { id: "f-name" }),
    D.el("input", { id: "f-memo" }),
    D.el("input", { id: "f-sourcing_branches", type: "hidden" }),
    box("Series A"), box("M&A"), box("구주·후속"),
    D.el("ul", { id: "timeline" }),
    D.el("button", { id: "save-btn" }),
    D.el("button", { id: "detail-close" })
  ]);
  panel.hidden = true;
  const backdrop = D.el("div", { id: "detail-backdrop" });
  backdrop.hidden = true;
  return D.el("div", {}, [D.el("div", { class: "table-wrap" }, [table]), backdrop, panel]);
}

function run(contact) {
  D.resetHandlers();
  const document = D.makeDocument(build());
  const sent = [];
  const win = {
    location: { pathname: "/contacts", search: "", reload() {}, href: "" },
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    scrollTo() {}, addEventListener() {}, removeEventListener() {},
    DEALFLOW_OPEN_CONTACT: 7
  };
  const ctx = {
    document: document, console: console, setTimeout: setTimeout,
    alert() {}, confirm() { return true; },
    MutationObserver: function () { this.observe = function () {}; },
    fetch(url, opts) {
      if (opts && opts.method === "PATCH") {
        sent.push(JSON.parse(opts.body));
        return Promise.resolve({ ok: true, json() { return Promise.resolve({ ok: true }); } });
      }
      return Promise.resolve({ ok: true, json() {
        return Promise.resolve({ contact: contact, timeline: [] });
      } });
    }
  };
  ctx.window = win;
  Object.assign(win, ctx);
  win.document = document;
  vm.createContext(ctx);
  vm.runInContext(read("panel_modal.js"), ctx, { filename: "panel_modal.js" });
  vm.runInContext(read("contacts.js"), ctx, { filename: "contacts.js" });
  return {
    sent: sent,
    field(id) { return document.getElementById("f-" + id); },
    box(value) {
      return document.querySelectorAll(".f-branch").filter(function (b) { return b.value === value; })[0];
    },
    save() { document.getElementById("save-btn").fire("click", {}); }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 메모만 고쳐 저장 → 딜 소싱은 안 보낸다 ─────────────────────────
  {
    const t = run(Object.assign({}, CONTACT));
    await flush();
    assert.strictEqual(t.box("Series A").checked, true, "창의 체크 상자가 안 섰다");
    assert.strictEqual(t.box("M&A").checked, false);
    t.field("memo").value = "통화함";
    t.save();
    await flush();
    assert.strictEqual(t.sent.length, 1, "저장이 안 나갔다");
    assert.strictEqual(t.sent[0].memo, "통화함");
    assert.ok(!("sourcing_branches" in t.sent[0]),
      "안 고친 갈래를 다시 보냈다 ★ 그 사이 딜 소싱에서 바뀐 참여가 되돌아간다");
  }

  // ── 2. 체크를 바꿨으면 고른 갈래 전부를 보낸다 ─────────────────────────
  {
    const t = run(Object.assign({}, CONTACT));
    await flush();
    t.box("M&A").checked = true;
    t.save();
    await flush();
    assert.strictEqual(t.sent[0].sourcing_branches, "Series A, M&A", "고른 갈래가 안 나갔다");
  }
  {
    const t = run(Object.assign({}, CONTACT));
    await flush();
    t.box("Series A").checked = false;          // 풀면 빈 글자 — 서버가 불참여로 둔다
    t.save();
    await flush();
    assert.strictEqual(t.sent[0].sourcing_branches, "", "푼 갈래가 안 나갔다");
  }

  // ── 3. 아무 갈래 없이 연 창에서 그대로 저장 → 안 보낸다 ─────────────────
  {
    const t = run(Object.assign({}, CONTACT, { sourcing_branches: "" }));
    await flush();
    t.field("memo").value = "다시 통화";
    t.save();
    await flush();
    assert.ok(!("sourcing_branches" in t.sent[0]),
      "안 고친 빈칸을 보냈다 ★ 그 사이 이어진 분이면 그 갈래를 불참여로 되돌린다");
  }

  console.log("contacts_sourcing_join_save_test: ok");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
