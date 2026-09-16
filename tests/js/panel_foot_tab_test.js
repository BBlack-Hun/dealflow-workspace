// 수정창의 **바닥 줄**([저장]·[삭제])은 탭을 따라 숨는다.
// (node tests/js/panel_foot_tab_test.js)
//
// ── 무엇을 못 박는가 ──────────────────────────────────────────────────────
//
// 단추 줄은 굴러가는 본문(`.detail-body`) **안**에 있었다. 그 자리는 칸이
// 세로로 쌓이는 자리고 칸은 달마다 늘어나서(`services/monthly_columns.py`),
// 달 칸 열둘인 명단에서는 [저장]까지 1495px(폰 2673px)을 굴려야 했다.
// 그래서 줄을 본문 바깥(`.detail-foot`)으로 냈다.
//
// **그 순간 새 실수 하나가 생긴다.** 본문 안에 있을 때는 탭을 바꾸면 본문째
// 숨어서 단추도 같이 사라졌다. 밖으로 내면 그냥 두는 한 `활동 이력` 탭에도
// 계속 서 있다 — 거기에는 저장할 폼이 없고, 화면에는 그 사람의 발송 이력만
// 깔려 있다. 무엇을 저장하고 무엇을 지우는 단추인지 알 수 없는 자리다.
//
// 고침은 줄에 `data-panel="info"` 를 붙이는 것뿐이다. 탭을 바꾸는 코드가
// `[data-panel]` 을 **전부** 훑기 때문이다(`contacts.js` 의 `showTab`).
// 이 검사는 그 한 글자가 빠지는 것을 막는다 — 빠져도 화면은 멀쩡히 그려지고
// 콘솔에 오류도 안 난다.
//
// 이름·회사는 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const ROOT = path.join(__dirname, "..", "..");
const JS = path.join(ROOT, "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(JS, name), "utf8");

const PERSON = { id: 1, name: "가상길동", title: "심사역", firm: "가상벤처스", memo: "메모" };

// 화면(`app/templates/contacts.html`)이 그리는 **차례 그대로** 세운다 —
// 바닥 줄은 두 `.detail-body` 의 **뒤**, 창 안이다.
function build() {
  const row = D.el("tr", { class: "data-row", "data-id": "1" }, [
    D.el("td", { class: "rowno" }),
    D.el("td", { class: "who" })
  ]);
  const table = D.el("table", { id: "contacts-table", "data-inline-url": "/api/contacts" },
    [D.el("tbody", {}, [row])]);

  const backdrop = D.el("div", { class: "panel-backdrop", id: "detail-backdrop" });
  const info = D.el("div", { class: "detail-body", "data-panel": "info" }, [
    D.el("input", { id: "f-name" }),
    D.el("input", { id: "f-firm" }),
    D.el("textarea", { id: "f-memo" }),
    // 달마다 늘어나는 칸. 이것들이 쌓여서 단추가 밀려났다.
    D.el("textarea", { id: "f-note-2026-08", "data-note": "2026-08" }),
    D.el("textarea", { id: "f-note-2026-09", "data-note": "2026-09" })
  ]);
  const timeline = D.el("div", { class: "detail-body", "data-panel": "timeline" },
    [D.el("ul", { id: "timeline" })]);
  const foot = D.el("div", { class: "detail-foot", "data-panel": "info" }, [
    D.el("button", { id: "save-btn" }),
    D.el("button", { id: "hide-btn" }),
    D.el("span", { class: "sep" }),
    D.el("button", { class: "danger-btn", id: "delete-btn" }),
    D.el("p", { class: "hint", id: "detail-msg" })
  ]);
  const panel = D.el("aside", { class: "detail-panel", id: "detail-panel" }, [
    D.el("b", { id: "detail-title" }),
    D.el("button", { id: "detail-close" }),
    D.el("button", { class: "detail-tab", "data-tab": "info" }),
    D.el("button", { class: "detail-tab", "data-tab": "timeline" }),
    info, timeline, foot
  ]);
  panel.hidden = true;
  backdrop.hidden = true;

  const root = D.el("div", {}, [table, D.el("button", { id: "add-btn" }), backdrop, panel]);
  return { root, row, panel, backdrop, info, timeline, foot,
           tabs: panel.querySelectorAll(".detail-tab") };
}

function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const win = { location: { reload() {}, pathname: "/contacts", search: "" } };
  const sandbox = {
    document, console, setTimeout,
    MutationObserver: function () { this.observe = function () {}; },
    alert() {}, confirm() { return true; },
    fetch() {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ contact: PERSON, timeline: [] })
      });
    }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  vm.runInContext(read("inline_edit.js"), sandbox, { filename: "inline_edit.js" });
  vm.runInContext(read("panel_modal.js"), sandbox, { filename: "panel_modal.js" });
  vm.runInContext(read("contacts.js"), sandbox, { filename: "contacts.js" });
  return {
    open: () => dom.row.querySelector(".who").fire("click"),
    tab: (name) => dom.panel.querySelectorAll('.detail-tab[data-tab="' + name + '"]')[0].fire("click")
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  // ── 1. 창을 열면 바닥 줄이 **같이 선다** ────────────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.open();
    await flush();
    assert.strictEqual(dom.panel.hidden, false, "창이 안 열렸다");
    assert.strictEqual(dom.foot.hidden, false,
      "창은 열렸는데 바닥 줄이 안 선다 ★ [저장] 이 어디에도 없다");
    assert.strictEqual(dom.info.hidden, false, "기본 정보가 안 선다");
  }

  // ── 2. 활동 이력으로 넘기면 **같이 숨는다** ─────────────────────────────
  //
  // 거기엔 저장할 폼이 없다. 서 있으면 무엇을 지우는 단추인지 알 수 없다.
  {
    const dom = build();
    const t = run(dom);
    t.open();
    await flush();
    t.tab("timeline");
    assert.strictEqual(dom.timeline.hidden, false, "활동 이력이 안 열렸다");
    assert.strictEqual(dom.info.hidden, true, "기본 정보가 안 숨었다");
    assert.strictEqual(dom.foot.hidden, true,
      "활동 이력 탭에 [저장]·[삭제] 가 그대로 서 있다 ★ " +
      "바닥 줄에 `data-panel=\"info\"` 가 빠졌다 — 화면은 멀쩡히 그려지고 오류도 안 난다");
  }

  // ── 3. 기본 정보로 돌아오면 **다시 선다** ───────────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.open();
    await flush();
    t.tab("timeline");
    t.tab("info");
    assert.strictEqual(dom.foot.hidden, false, "돌아왔는데 바닥 줄이 안 돌아온다");
    assert.strictEqual(dom.info.hidden, false, "돌아왔는데 기본 정보가 안 선다");
  }

  // ── 4. 다른 줄을 열어도 바닥 줄은 그대로 선다 ───────────────────────────
  //
  // 창을 여는 길이 둘이다(줄 누르기 · [담당자 추가]). `showTab("info")` 를
  // 거치지 않는 길이 생기면 바닥 줄만 숨은 채 창이 열린다.
  {
    const dom = build();
    const t = run(dom);
    t.open();
    await flush();
    t.tab("timeline");
    t.open();                 // 같은 줄을 다시 연다 — 탭이 기본 정보로 돌아와야 한다
    await flush();
    assert.strictEqual(dom.foot.hidden, false,
      "창을 다시 열었는데 바닥 줄이 숨어 있다 ★ 저장할 길이 없는 창이 된다");
  }

  // ── 5. **바닥 줄의 칸도 폼의 일부다** ───────────────────────────────────
  //
  // 저장이 읽는 칸(`[data-note]`)을 `panel` 안에서 찾으므로, 줄을 밖으로
  // 낸 것이 폼을 쪼개지 않았는지 본다.
  {
    const dom = build();
    const t = run(dom);
    t.open();
    await flush();
    const notes = dom.panel.querySelectorAll("[data-note]");
    assert.strictEqual(notes.length, 2,
      "창 안에서 달 칸을 못 찾는다 ★ 저장·되읽기가 그 값을 통째로 잃는다");
  }

  console.log("panel_foot_tab_test.js ✔ 5묶음 통과");
})().catch((e) => { console.error(e); process.exit(1); });
