// 수정창에서 저장한 뒤 **표가 서 있던 자리를 잃지 않는다.**
// (node tests/js/contacts_scroll_keep_test.js)
//
// ── 무엇이 고장이었나 ────────────────────────────────────────────────────
//
// [저장] 한 번에 표의 스크롤이 `(1200, 900) → (0, 0)` 이 됐다. 담당 줄이
// 여든인 사람이 예순째 줄을 고칠 때마다, 저장할 때마다 그 줄을 **처음부터 다시
// 찾아야** 했다. 가로로도 1,900px 넘게 밀어 둔 표라 두 방향 다 잃는다.
//
// ── 왜 새로고침 자체를 안 없앴나 — 여기서 **정하고 잠그는** 것 ──────────
//
// 표에 선 값 중에 **서버가 만드는 것**이 있다: 최근 딜소개·반응 같은 집계,
// 방 상태, 연결 상태, 그리고 서버가 저 혼자 바꾸는 값(방 이름을 지우면 따라
// 바뀌는 연결 상태 — `routers/contacts.py` 의 `update_contact`). 저장 응답에는
// 그것들이 안 실려 오므로, 화면에서 그 줄만 고쳐 그리면 **서버가 바꾼 값이
// 옛것으로 남는다.** 그래서 다시 받는 것은 그대로 두고, **자리만 들고 간다.**
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const SRC = fs.readFileSync(path.join(JS, "contacts.js"), "utf8");
const MODAL_SRC = fs.readFileSync(path.join(JS, "panel_modal.js"), "utf8");

const AT = { x: 1200, y: 900 };        // 사람이 밀어 둔 자리

function build() {
  const table = D.el("table", { id: "contacts-table" }, [
    D.el("tbody", {}, [D.el("tr", { class: "data-row", "data-id": "7" })])
  ]);
  const wrap = D.el("div", { class: "table-wrap wide" }, [table]);
  wrap.scrollLeft = AT.x;
  wrap.scrollTop = AT.y;

  const panel = D.el("aside", { id: "detail-panel" }, [
    D.el("h2", { id: "detail-title" }),
    D.el("p", { id: "detail-msg" }),
    D.el("input", { id: "f-name" }),
    D.el("input", { id: "f-kakao_room_name" }),
    D.el("ul", { id: "timeline" }),
    D.el("button", { id: "save-btn" }),
    D.el("button", { id: "detail-close" })
  ]);
  panel.hidden = true;
  const backdrop = D.el("div", { id: "detail-backdrop" });
  backdrop.hidden = true;

  const root = D.el("div", {}, [wrap, backdrop, panel]);
  return { root: root, wrap: wrap, panel: panel };
}

function run(dom, stored) {
  D.resetHandlers();
  const box = {};                       // 가짜 sessionStorage
  if (stored !== undefined) box[Object.keys(stored)[0]] = stored[Object.keys(stored)[0]];
  const sent = [];
  const told = [];
  let reloads = 0;
  let scrolledTo = null;
  const loadHandlers = [];

  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1400, innerHeight: 900, pageYOffset: 40,
    location: { pathname: "/startup", search: "?sheet=가 명단",
                reload() { reloads += 1; }, href: "" },
    sessionStorage: {
      getItem(k) { return k in box ? box[k] : null; },
      setItem(k, v) { box[k] = String(v); },
      removeItem(k) { delete box[k]; }
    },
    scrollTo(x, y) { scrolledTo = [x, y]; },
    addEventListener(type, fn) { if (type === "load") loadHandlers.push(fn); },
    removeEventListener() {}
  };
  const ctx = {
    document: document, console: console, setTimeout: setTimeout,
    alert(t) { told.push(String(t)); },
    confirm() { return true; },
    MutationObserver: function () { this.observe = function () {}; },
    fetch(url, opts) {
      sent.push({ url: url, opts: opts || {} });
      return Promise.resolve({
        ok: true,
        json() {
          // 서버가 **저 혼자 바꾼 것**을 알리는 자리. 이 말이 지나가면
          // 대시보드에 `지금 연결 중` 으로 남는 까닭을 아무도 알 수 없다.
          return Promise.resolve({ ok: true, connect_note: "방 이름이 비어 연결 상태를 되돌렸습니다" });
        }
      });
    }
  };
  ctx.window = win;
  Object.assign(win, ctx);
  win.document = document;
  vm.createContext(ctx);
  vm.runInContext(MODAL_SRC, ctx, { filename: "panel_modal.js" });
  vm.runInContext(SRC, ctx, { filename: "contacts.js" });

  return {
    box: box, sent: sent, told: told,
    reloads() { return reloads; },
    scrolledTo() { return scrolledTo; },
    // 화면이 다 선 뒤(`load`)에 한 번 더 넣는 자리.
    finishLoading() { loadHandlers.forEach(function (fn) { fn(); }); },
    save() {
      document.getElementById("f-name").value = "가상길동";
      document.getElementById("save-btn").fire("click", {});
    }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

function keys(box) { return Object.keys(box); }

async function main() {
  // ── 1. 저장하면 **자리를 적어 두고** 다시 받는다 ──────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.save();
    await flush();

    assert.strictEqual(t.sent.length, 1, "저장이 안 나갔다");
    assert.strictEqual(t.reloads(), 1,
      "다시 안 받았다 ★ 서버가 만드는 값(집계·방 상태·연결 상태)이 옛것으로 남는다");
    // 서버가 저 혼자 바꾼 것은 **여전히 멈춰 세워 알린다.**
    assert.strictEqual(t.told.length, 1,
      "서버가 저 혼자 바꾼 값을 안 알렸다 ★ 왜 바뀌었는지 물을 자리가 없어진다");

    const saved = keys(t.box);
    assert.strictEqual(saved.length, 1, "자리를 안 적어 뒀다 ★ 표가 (0,0) 으로 돌아간다");
    // **이 주소 몫으로만** 적는다 — 명단마다 탭이 다르다.
    assert.ok(saved[0].indexOf("/startup") >= 0 && saved[0].indexOf("?sheet=") >= 0,
      "자리를 주소와 상관없이 적어 뒀다 ★ 다른 명단을 열면 엉뚱한 자리로 간다\n  적힌 이름 "
      + saved[0]);
    const at = JSON.parse(t.box[saved[0]]);
    assert.strictEqual(at.x, AT.x, "가로 자리가 안 적혔다");
    assert.strictEqual(at.y, AT.y, "세로 자리가 안 적혔다");
  }

  // ── 2. 다시 받은 화면은 **그 자리로 돌아간다**, 그리고 자리는 지워진다 ─
  {
    const dom = build();
    dom.wrap.scrollLeft = 0;              // 막 받은 화면은 맨 위·맨 왼쪽이다
    dom.wrap.scrollTop = 0;
    const key = "dealflow:list-scroll:/startup?sheet=가 명단";
    const t = run(dom, { [key]: JSON.stringify({ x: AT.x, y: AT.y, page: 40 }) });

    assert.strictEqual(dom.wrap.scrollLeft, AT.x,
      "가로 자리가 안 돌아왔다 ★ 밀어 둔 칸을 다시 찾아야 한다");
    assert.strictEqual(dom.wrap.scrollTop, AT.y,
      "세로 자리가 안 돌아왔다 ★ 여든 줄에서 예순째 줄을 다시 찾아야 한다");
    assert.deepStrictEqual(t.scrolledTo(), [0, 40], "페이지 자리가 안 돌아왔다");

    assert.deepStrictEqual(keys(t.box), [],
      "적어 둔 자리를 안 지웠다 ★ 다음에 그 화면을 열 때 엉뚱한 자리로 간다");

    // **한 번으로는 모자란다.** 표 키는 `table_fit.js` 가 나중에 정하고
    // (`--head`), 글꼴이 늦게 오면 한 번 더 바뀐다 — 키가 정해지기 전에 넣은
    // 세로 자리는 브라우저가 0 으로 깎는다.
    dom.wrap.scrollTop = 0;               // 깎인 셈 치고
    t.finishLoading();
    assert.strictEqual(dom.wrap.scrollTop, AT.y,
      "화면이 다 선 뒤에 한 번 더 안 넣는다 ★ 표 키가 늦게 정해지면 세로 자리를 잃는다");
  }

  // ── 3. 적어 둔 자리가 없으면 **아무 데도 안 민다** ────────────────────
  //
  // 주소를 쳐서 그냥 들어온 화면까지 옮기면, 사람이 보려던 맨 윗줄이 아니라
  // 지난번 자리에서 시작한다.
  {
    const dom = build();
    dom.wrap.scrollLeft = 0;
    dom.wrap.scrollTop = 0;
    const t = run(dom);
    assert.strictEqual(dom.wrap.scrollLeft, 0, "적어 둔 자리가 없는데 표를 밀었다");
    assert.strictEqual(dom.wrap.scrollTop, 0, "적어 둔 자리가 없는데 표를 밀었다");
    assert.strictEqual(t.scrolledTo(), null, "적어 둔 자리가 없는데 페이지를 밀었다");
  }

  console.log("contacts_scroll_keep_test: 통과");
}

main().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
