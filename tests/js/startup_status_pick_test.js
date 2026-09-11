// 스타트업 화면의 **골라 넣는 칸** — 보기가 뜨고, 옛 값이 안 사라진다.
// (node tests/js/startup_status_pick_test.js)
//
// ── 여기서 잠그는 것 ────────────────────────────────────────────────────
//
// 1. 정해 둔 보기가 **전부** 칩으로 뜬다(`data-choices`).
// 2. **목록에 없는 옛 값이 같이 뜬다.** 이번 판에서 제일 중요하다 — 자료를
//    옮기는 일은 하지 않기로 했으므로, `대표님이 초대해주심` 처럼 사람이
//    자유롭게 적어 둔 말이 다른 줄에 남아 있다. 그 값을 고를 수 없게 되면
//    담당자는 옛 줄을 고칠 때마다 새로 타이핑하게 되고, 그 순간 같은 뜻이
//    `대표님 초대` · `대표님이 초대` 로 또 갈린다.
// 3. **목록에 없는 말을 그냥 쳐도 저장된다.** 고르는 칸은 적을 수 있는 값을
//    좁히는 장치가 아니라 고를 거리를 주는 장치다. 여기서 `<select>` 로
//    바꾸거나 값을 목록에 가두면 걸린다.
// 4. 값은 **`notes` 묶음으로** 나간다(`data-note`) — 이 칸들은 그 명단에만
//    있는 칸이라 담당자 모델의 칸이 아니다. 묶음이 빠지면 서버가 200 을
//    주면서 아무것도 안 넣는다.
// 5. 칸마다 **자기 보기**를 뜬다. 통화 결과 칸에 문자 발송 보기가 뜨면
//    `통화 완료` 와 `발송 완료` 가 한 목록에 섞여 세지 못한다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "inline_edit.js"), "utf8");

// 제안서에 적힌 보기. **여기 다시 적는다** — 앱에서 읽어 오면 앱이 바뀔 때
// 검사도 같이 바뀌어 아무것도 못 막는다. (파이썬 쪽은
// `tests/test_startup_status_choices.py` 가 같은 목록으로 잰다.)
const SEND = ["미발송", "발송 예정", "발송 완료", "발송 실패", "발송 제외"];
const CALL = ["미시도", "통화 예정", "통화 완료", "부재중",
              "통화 중 / 재시도 필요", "재통화 요청", "연락처 오류", "통화 거절"];
const COLLAB = ["확인 전", "협업 논의 중", "당사 통한 진행 희망", "자체 진행 예정",
                "타사 통한 진행 중", "당사 협업 보류", "당사 협업 의사 없음", "협업 종료"];

// 표 두 줄. 2번 줄에 **목록에 없는 옛 글**이 남아 있다 — 원본 시트에 실제로
// 그런 식으로 적혀 있었다(한 칸에 결과와 할 일과 사람이 섞인다).
const OLD_SEND = "7/30 문자 및 명함 발송";
const OLD_COLLAB = "당분간 자체 진행 예정";

function cell(field, choices, text) {
  const div = D.el("div", {
    class: "cell", "data-field": field, "data-note": "",
    "data-type": "pick", "data-choices": choices.join(",")
  });
  div.textContent = text || "";
  return div;
}

function build() {
  const send1 = cell("c12", SEND, "");
  const call1 = cell("c13", CALL, "");
  const collab1 = cell("collab_status", COLLAB, "");
  // 옛 글이 남아 있는 줄.
  const send2 = cell("c12", SEND, OLD_SEND);
  const collab2 = cell("collab_status", COLLAB, OLD_COLLAB);

  const plain = D.el("td", { class: "who" });        // 바깥
  const rows = [
    D.el("tr", { "data-id": "11" }, [
      D.el("td", {}, [send1]), D.el("td", {}, [call1]),
      D.el("td", {}, [collab1]), plain
    ]),
    D.el("tr", { "data-id": "12" }, [
      D.el("td", {}, [send2]), D.el("td", {}, [cell("c13", CALL, "")]),
      D.el("td", {}, [collab2])
    ])
  ];
  const table = D.el("table",
    { id: "contacts-table", "data-inline-url": "/api/contacts" },
    [D.el("tbody", {}, rows)]);
  return { root: D.el("div", {}, [table]),
           send1: send1, call1: call1, collab1: collab1, plain: plain };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1600, innerHeight: 900,
    addEventListener: function () {}, removeEventListener: function () {}
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {},
    CustomEvent: function (type, init) {
      this.type = type;
      this.detail = init && init.detail;
    },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse((opts && opts.body) || "{}") });
      return Promise.resolve({
        ok: true, json: function () { return Promise.resolve({}); }
      });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "inline_edit.js" });
  return {
    sent: sent,
    pop: function () { return dom.root.querySelector(".cell-pop"); },
    chips: function () {
      const pop = dom.root.querySelector(".cell-pop");
      return Array.prototype.map.call(
        pop.querySelectorAll(".cell-pop-choice"),
        function (b) { return b.textContent; });
    },
    press: function (node) { node.fire("pointerdown"); node.fire("click"); }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── 1. 정해 둔 보기가 전부 뜬다 ────────────────────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.call1);
    assert.ok(t.pop(), "칸을 눌렀는데 편집창이 안 떴다");
    const chips = t.chips();
    CALL.forEach(function (v) {
      assert.ok(chips.indexOf(v) >= 0,
        "통화 결과의 보기가 안 뜬다: " + v + "\n  뜬 것 " + JSON.stringify(chips));
    });
    // **차례도 그대로다** — 일이 진행되는 순서라 가나다순으로 다시 세우면
    // 목록에서 지금 자리를 짚을 수가 없다.
    assert.deepStrictEqual(chips.slice(0, CALL.length), CALL,
      "보기의 차례가 제안서와 다르다");
  }

  // ── 2. **목록에 없는 옛 값이 같이 뜬다** ───────────────────────────────
  //
  // 다른 줄에 남아 있는 자유 표기를 표에서 모아 붙인다
  // (`inline_edit.js` 의 `knownValues`). 이 줄이 빠지면 옛 값은 고를 수
  // 없어지고, 담당자는 그때마다 새로 타이핑하게 된다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.send1);
    const chips = t.chips();
    assert.ok(chips.indexOf(OLD_SEND) >= 0,
      "다른 줄의 옛 값이 고를 거리에 안 뜬다 ★ 옛 값이 화면에서 사라진다\n" +
      "  뜬 것 " + JSON.stringify(chips));
    SEND.forEach(function (v) {
      assert.ok(chips.indexOf(v) >= 0, "정해 둔 보기가 밀려났다: " + v);
    });

    t.press(dom.collab1);
    assert.ok(t.chips().indexOf(OLD_COLLAB) >= 0,
      "달에 매이지 않는 칸에서도 옛 값이 안 뜬다: " + OLD_COLLAB);
  }

  // ── 3. 칸마다 **자기 보기**가 뜬다 ─────────────────────────────────────
  //
  // 월별 칸 셋은 열쇠가 달라(`c12`·`c13`) 다른 칸의 값을 모아 오지 않는다.
  // 섞이면 `통화 완료` 와 `발송 완료` 가 한 목록에 서서 세지 못한다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.call1);
    const chips = t.chips();
    SEND.forEach(function (v) {
      if (CALL.indexOf(v) >= 0) return;
      assert.ok(chips.indexOf(v) < 0,
        "통화 결과 칸에 문자 발송 보기가 섞였다: " + v);
    });
    assert.ok(chips.indexOf(OLD_SEND) < 0,
      "통화 결과 칸에 문자 칸의 옛 값이 섞였다: " + OLD_SEND);
  }

  // ── 4. 목록에 없는 말을 **그냥 쳐도 저장된다** ─────────────────────────
  //
  // `<select>` 로 묶거나 값을 목록에 가두면 여기서 걸린다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.collab1);
    t.pop().querySelector(".cell-pop-input").value = "목록에 없는 말";
    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent.length, 1, "친 값이 저장되지 않았다");
    assert.strictEqual(dom.collab1.textContent, "목록에 없는 말",
      "친 값이 칸에 안 그려졌다");
  }

  // ── 5. 값은 `notes` 묶음으로 나간다 ────────────────────────────────────
  //
  // 이 칸들은 그 명단에만 있는 칸이라 담당자 모델의 칸이 아니다. 묶음이
  // 빠지면 서버가 200 을 주면서 아무것도 안 넣는다 — 증상이 조용하다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.send1);
    t.pop().querySelectorAll(".cell-pop-choice")[SEND.indexOf("발송 완료")]
      .fire("mousedown");
    await flush();
    assert.strictEqual(t.sent.length, 1, "보기를 골랐는데 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].url, "/api/contacts/11");
    assert.deepStrictEqual(t.sent[0].body, { notes: { c12: "발송 완료" } },
      "값이 `notes` 묶음으로 안 나갔다 ★ 서버가 200 을 주면서 아무것도 안 넣는다");
  }

  console.log("startup_status_pick_test: 통과");
}

main().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
