// 대표 카톡방 맞추기 — **후보를 누르면 그 줄의 칸에 들어가는가.**
// (node tests/js/startup_room_test.js)
//
// 지킬 것은 넷이고, 넷 다 **오발송에 바로 닿는다.**
//
//  1. 들어가는 글자가 **후보 그대로**여야 한다. 한 글자라도 다르면 발송기가
//     방을 못 찾는다(`agent/sender/base.py` 의 never guess).
//  2. **그 줄의 칸**에 들어가야 한다. 표 전체에서 첫 칸을 찾으면 어느 줄을
//     눌러도 맨 윗줄이 바뀌고, 그것은 A 기업 방으로 B 기업 글이 가는 길이다.
//  3. 누르는 것이 **폼을 보내지 않아야** 한다. 후보 단추는 저장 폼 안에 선다 —
//     전송되면 사람이 보려던 후보가 그대로 저장된다.
//  4. **저절로 채우지 않는다.** 후보가 하나뿐인 줄도 사람이 눌러야 들어간다.
//     채워 두면 확인된 값으로 읽히고, 그대로 저장된다.
//
// 아이디·클래스가 실제로 그려진 화면과 같은지는 파이썬 쪽이 본다
// (`tests/test_startup_room_match.py`).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

// 전부 지어낸 값이다 — 저장소가 공개다. **띄어쓰기가 다른 짝**을 일부러 둔다.
const ROOM_A = "가나다 대표 샘플가 , 라마바 팀장";
const ROOM_B = "마바사 대표 샘플나";
const DRAFT_B = "마바사 대표 샘플나초안";

function row(id, picks) {
  const input = el("input", { type: "text", class: "room-input", name: "rooms" });
  input.value = "";
  const box = el("div", { class: "room-picks" },
    picks.map(function (room) {
      const b = el("button", { type: "button", class: "chip room-pick",
                               "data-room": room });
      b.textContent = room;
      return b;
    }));
  return el("tr", { "data-id": String(id) }, [
    el("td", {}, [el("input", { type: "hidden", name: "company_ids",
                                value: String(id) })]),
    el("td", {}, [input, box])
  ]);
}

function build() {
  dom_.resetHandlers();
  const form = el("form", { id: "room-match", method: "post" }, [
    el("table", { class: "grid-table" }, [
      el("tbody", {}, [row(1, [ROOM_A]), row(2, [ROOM_B, DRAFT_B])])
    ])
  ]);
  const root = el("div", { class: "layout" }, [form]);
  const document = dom_.makeDocument(root);
  const win = { location: { search: "", href: "" } };
  const ctx = {
    document: document, console: console, window: win,
    navigator: {}, setTimeout: function () { return 0; },
    clearTimeout: function () {}
  };
  win.document = document;
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  vm.runInNewContext(fs.readFileSync(path.join(JS, "startup_room.js"), "utf8"),
                     ctx, { filename: "startup_room.js" });

  const rows = root.querySelectorAll("tr");
  return {
    form: form,
    rows: rows,
    picks: function (i) { return rows[i].querySelectorAll(".room-pick"); },
    value: function (i) { return rows[i].querySelector(".room-input").value; }
  };
}

// ── 1 · 2. 후보 그대로, 그리고 **그 줄의** 칸에 ────────────────────────────
(function 그줄에그대로() {
  const s = build();
  s.picks(1)[0].fire("click", { target: s.picks(1)[0] });

  assert.strictEqual(s.value(1), ROOM_B,
    "누른 후보가 그대로 안 들어갔다 — 한 글자만 달라도 발송기가 방을 못 찾는다");
  assert.strictEqual(s.value(0), "",
    "다른 줄의 칸이 바뀌었다 — A 기업 방으로 B 기업 글이 가는 길이다");
}());

// ── 3. 누르는 것이 저장으로 이어지지 않는다 ─────────────────────────────────
(function 누르는것이저장이되지않는다() {
  const s = build();
  let prevented = 0;
  const pick = s.picks(0)[0];
  pick.fire("click", { target: pick,
                       preventDefault: function () { prevented += 1; } });

  assert.strictEqual(prevented, 1,
    "기본 동작을 안 막았다 — 폼 안의 단추라 누르면 그대로 저장된다");
  assert.strictEqual(s.value(0), ROOM_A, "그래도 글자는 들어가야 한다");
}());

// ── 4. 저절로 채우지 않는다  ★ ─────────────────────────────────────────────
(function 저절로채우지않는다() {
  const s = build();

  // 첫 줄은 후보가 **하나뿐**이다. 그래도 비어 있어야 한다 — 채워 두면 사람은
  // 이미 확인된 값으로 읽고 그대로 저장한다. 회사명이 든 방이 꼭 그 대표와의
  // 방인 것은 아니라서, 그 한 번이 엉뚱한 방으로 가는 발송이 된다.
  assert.strictEqual(s.picks(0).length, 1, "밑판이 깨졌다");
  assert.strictEqual(s.value(0), "",
    "후보가 하나뿐이라고 저절로 채웠다 — 고르는 것은 사람이어야 한다");
  assert.strictEqual(s.value(1), "", "저절로 채웠다");
}());

// ── 5. 두 번째 후보를 누르면 **갈아탄다** ──────────────────────────────────
(function 갈아탄다() {
  const s = build();
  s.picks(1)[0].fire("click", { target: s.picks(1)[0] });
  s.picks(1)[1].fire("click", { target: s.picks(1)[1] });

  assert.strictEqual(s.value(1), DRAFT_B,
    "나중에 누른 것으로 안 바뀌었다 — 잘못 누른 것을 되돌릴 길이 없어진다");
}());

// ── 6. 표가 없는 화면에서는 아무 일도 하지 않는다 ───────────────────────────
(function 표가없으면조용하다() {
  dom_.resetHandlers();
  const root = el("div", { class: "layout" });
  const ctx = {
    document: dom_.makeDocument(root), console: console,
    window: { location: { search: "", href: "" } },
    navigator: {}, setTimeout: function () { return 0; },
    clearTimeout: function () {}
  };
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  // 터지면 **같은 파일을 쓰는 다른 화면이 통째로 멈춘다**(스크립트 하나가
  // 죽으면 그 뒤가 안 돌아간다).
  vm.runInNewContext(fs.readFileSync(path.join(JS, "startup_room.js"), "utf8"),
                     ctx, { filename: "startup_room.js" });
}());

console.log("ok");
