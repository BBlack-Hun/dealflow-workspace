// 투자사 관리 현황 — `카톡방 참여여부` 를 고치면 옆 `카톡방` 칸이 **그 자리에서**
// 바뀌는가. (node tests/js/contacts_room_sync_test.js)
//
// 사용자 원문: "카톡방 컬럼의 확인됨이랑 카톡방 참여여부랑 동기화 되게 해줘".
//
// 서버는 참여여부를 `X` 로 고치면 `확인됨` 을 푼다(`services/room_joined`). 표에서
// 칸 하나를 고치는 길은 화면을 다시 받지 않으므로(`inline_edit.js`), 응답이 실어
// 온 두 칸을 화면이 고쳐 그리지 않으면 새로고침 전까지 **옛 `확인됨` 이 그대로**
// 서 있다 — 서버에서는 맞췄는데 화면에서는 안 맞은 것처럼 보인다.
//
// 이름·회사는 지어낸 값이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const read = (name) => fs.readFileSync(path.join(JS, name), "utf8");

// 화면(`app/templates/contacts.html`)이 그리는 만큼만 세운다.
function build() {
  const joined = D.el("td", { class: "cell", "data-field": "kakao_joined",
                              "data-type": "pick", "data-filter-key": "joined" });
  joined.textContent = "O";
  const badge = D.el("span", { class: "room-badge ok" });
  badge.textContent = "확인됨";
  const roomCell = D.el("td", { class: "ellipsis room-cell", title: "확인됨" }, [badge]);
  const memo = D.el("div", { class: "cell clamp2", "data-field": "memo" });
  const row = D.el("tr", {
    class: "data-row", "data-id": "7", "data-name": "홍길동",
    "data-f-room": "확인됨", "data-f-joined": "O"
  }, [D.el("td", { class: "rowno" }), joined, D.el("td", {}, [memo]), roomCell]);
  const body = D.el("tbody", {}, [row]);
  const table = D.el("table", { id: "contacts-table" }, [D.el("thead"), body]);
  const root = D.el("div", {}, [D.el("div", {}, [table])]);
  return { root: root, table: table, row: row, joined: joined, badge: badge,
           roomCell: roomCell, memo: memo };
}

// 필터 부품은 **가짜**를 넣는다 — 여기서 볼 것은 필터가 다시 읽을 때 행 값이
// 이미 바뀌어 있는가(차례)뿐이다.
function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const seenByFilter = [];
  const win = { location: { pathname: "/contacts", search: "" },
                history: { replaceState: function () {} } };
  const sandbox = {
    document: document, console: console,
    MutationObserver: function () { this.observe = function () {}; },
    alert: function () {}, confirm: function () { return false; },
    setTimeout: setTimeout,
    fetch: function () { return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } }); }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  win.DealflowFilters = {
    init: function () {
      return {
        apply: function () {},
        refresh: function () { seenByFilter.push(dom.row.getAttribute("data-f-room")); }
      };
    }
  };
  vm.createContext(sandbox);
  ["panel_modal.js", "contacts.js"].forEach(function (name) {
    vm.runInContext(read(name), sandbox, { filename: name });
  });
  return { seenByFilter: seenByFilter };
}

function saved(dom, cell, value, data) {
  dom.table.dispatchEvent({ type: "inline-saved",
    detail: { row: dom.row, cell: cell, value: value, data: data } });
}

// --- 1) 참여여부를 `X` 로 → `확인됨` 이 그 자리에서 `미확인` 이 된다 -----------
{
  const dom = build();
  const at = run(dom);
  dom.joined.textContent = "X";            // inline_edit.js 가 이미 그린 값
  saved(dom, dom.joined, "X", {
    ok: true, room_verified: "unverified", kakao_joined: "X",
    send_state: "unverified", send_label: "미확인", send_class: "warn"
  });
  assert.strictEqual(dom.badge.textContent, "미확인",
    "참여여부를 X 로 바꿨는데 카톡방 칸이 그대로 `확인됨` 이다");
  assert.ok(dom.badge.classList.contains("warn") && !dom.badge.classList.contains("ok"),
    "글자만 바뀌고 색은 `확인됨` 색으로 남았다");
  assert.ok(dom.badge.classList.contains("room-badge"), "배지 모양이 사라졌다");
  assert.strictEqual(dom.roomCell.getAttribute("title"), "미확인");
  assert.strictEqual(dom.row.getAttribute("data-f-room"), "미확인",
    "칸은 `미확인` 인데 `확인됨` 으로 거르면 이 줄이 걸린다");
  assert.strictEqual(dom.row.getAttribute("data-f-joined"), "X");
  assert.strictEqual(dom.joined.textContent, "X");
  assert.deepStrictEqual(at.seenByFilter, ["미확인"],
    "필터가 옛 값으로 목록을 만든 뒤에 행 값이 바뀌었다 — 손을 거는 차례가 거꾸로다");
}

// --- 2) 다른 칸을 고쳐도 서버가 준 두 칸으로 맞춘다 -----------------------------
//
// 사람이 고친 칸이 아니면 참여여부 칸도 응답 값으로 다시 그린다.
{
  const dom = build();
  run(dom);
  saved(dom, dom.memo, "통화함", {
    ok: true, kakao_joined: "O", send_state: "verified", send_label: "확인됨",
    send_class: "ok"
  });
  assert.strictEqual(dom.badge.textContent, "확인됨");
  assert.strictEqual(dom.joined.textContent, "O");
}

// --- 3) 응답에 그 칸이 없으면(다른 표의 응답) 아무것도 안 건드린다 ----------------
{
  const dom = build();
  run(dom);
  saved(dom, dom.memo, "x", { ok: true });
  saved(dom, dom.memo, "x", undefined);
  assert.strictEqual(dom.badge.textContent, "확인됨");
  assert.strictEqual(dom.row.getAttribute("data-f-room"), "확인됨");
  assert.strictEqual(dom.joined.textContent, "O");
}

console.log("contacts_room_sync_test: ok");
