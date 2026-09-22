// 칸마다의 `수정한 날짜` 가 **값을 안 먹고**, 고친 그 자리에서 바뀌는가.
// (node tests/js/consulting_field_stamp_test.js)
//
// 사용자 요청은 "딜 소개문구랑 카톡 연결 여부 컬럼, 당월 리마인드 컬럼에 각각
// 수정한 날짜를 붙여주고 시간 까지만 보이게" 였다. 칸을 다섯 개 더 세우면 이미
// 2,900px 인 표를 못 보므로, 값 **아래 잔글씨**로 붙였다(`cell-main`/`cell-sub`).
//
// 그러면 값과 날짜가 **한 `td` 안에** 같이 선다. 이 표는 칸을 눌러 그 자리에서
// 고치는데(`startEdit`), 전에는 `td` 의 글자를 통째로 읽었다 — 그대로 두면
//
//   · 칸을 누르는 순간 입력칸에 `한 줄 소개2026-09-21 14:30` 이 들어가고
//   · 저장하면 그 글자가 값이 되어 **날짜가 값에 눌어붙는다**
//   · `data-search`·`연락 기록 없음`·갈래 태그가 전부 날짜를 값으로 센다
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 실제로
// 돌린다** (consulting_contacted_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

const OLD = "2026-09-01 09:00";
const NEW = "2026-09-21 14:30";

// --- 표 한 줄. 날짜를 단 칸 셋과 안 단 칸 하나 ------------------------------
//
// 화면이 그리는 모양 그대로다(consulting.html 의 `stamped` 매크로) —
// 값은 `.cell-main`, 날짜는 `.cell-sub`. **날짜가 없는 칸에는 `.cell-sub` 가
// 아예 없다**(344줄짜리 표에서 빈 상자를 늘 세우면 모든 줄의 키가 오른다).
function stamped(attrs, value, at) {
  const kids = [D.el("div", { class: "cell-main" })];
  kids[0].textContent = value;
  if (at) {
    const sub = D.el("div", { class: "cell-sub muted" });
    sub.textContent = at;
    kids.push(sub);
  }
  return D.el("td", attrs, kids);
}

function build() {
  // 날짜를 안 단 칸 — 값이 `td` 에 바로 있다. 두 모양이 한 표에 섞여 있으므로
  // `valueBox` 가 둘 다 받아야 한다.
  const mgmt = D.el("td", { class: "cell multi", "data-field": "management",
                            "data-filter-key": "mgmt" });
  mgmt.textContent = "관리 중";

  const pitch = stamped(
    { class: "cell multi", "data-field": "deal_pitch" }, "스마트팜 관제", OLD);
  const kakao = stamped(
    { class: "cell", "data-field": "kakao_joined", "data-filter-key": "joined",
      "data-choices": "O,X" }, "O", OLD);
  // 월별 리마인드 — **달마다 제 날짜다.** 석 달치가 서므로 날짜도 석 달치다.
  const sep = stamped({ class: "cell multi", "data-note": "31" }, "9월 통화함", OLD);
  const aug = stamped({ class: "cell multi", "data-note": "30" }, "", "");
  const jul = stamped({ class: "cell multi", "data-note": "29" }, "7월 부재중", OLD);

  const tr = D.el("tr", {
    "data-id": "7", "data-search": "", "data-contacted": "1",
    "data-contacted-folded": "0", "data-contacted-prev": "0",
    "data-f-mgmt": "관리 중", "data-f-joined": "O"
  }, [mgmt, pitch, kakao, sep, aug, jul]);

  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0" }, [
    D.el("tbody", {}, [tr])
  ]);
  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]);
  return { root, tr, mgmt, pitch, kakao, sep, aug, jul };
}

// --- consulting.js 를 그대로 돌린다 -----------------------------------------
function run(dom, stamps) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const el = made.call(document, tag);
    el.focus = function () {};
    el.setSelectionRange = function () {};
    return el;
  };

  const calls = [];
  const sandbox = {
    document: document,
    window: { location: { reload: function () {} } },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    prompt: function () { return null; },
    fetch: function (url, opt) {
      calls.push({ url: url, opt: opt, body: JSON.parse(opt.body || "{}") });
      // 서버가 돌려주는 것 — 고친 칸의 **새 날짜**다
      // (`routers/consulting.py` 의 `update_company`).
      return Promise.resolve({
        ok: true,
        json: function () { return Promise.resolve({ id: 7, stamps: stamps || {} }); }
      });
    }
  };
  sandbox.window.DealflowFilters = undefined;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "consulting.js" });
  return calls;
}

function valueOf(cell) {
  const main = cell.querySelector(".cell-main");
  return (main || cell).textContent;
}

function stampOf(cell) {
  const sub = cell.querySelector(".cell-sub");
  return sub ? sub.textContent : null;
}

// 칸을 하나 고친다 (누르기 → 값 넣기 → 칸 밖으로)
function edit(cell, value) {
  cell.fire("click", { target: cell });
  const box = cell.querySelector(".cell-main") || cell;
  const input = box.children[0];
  assert.ok(input, "칸을 눌렀는데 입력칸이 안 생겼습니다");
  return { input: input, run: function () {
    input.value = value;
    input.fire("blur", { target: input });
    return new Promise(function (r) { setTimeout(r, 0); });
  } };
}

(async function () {
  // 1) **누를 때 날짜가 입력칸에 안 딸려 온다.**
  //    이것이 안 되면 고치는 순간 값 뒤에 날짜가 눌어붙는다.
  {
    const dom = build();
    run(dom, {});
    const e = edit(dom.pitch, "새 소개");
    assert.strictEqual(
      e.input.value, "스마트팜 관제",
      "칸을 눌렀는데 입력칸에 `수정한 날짜` 까지 들어왔습니다 — " +
      "그대로 저장하면 날짜가 값에 눌어붙습니다");
  }

  // 2) **고치면 값만 바뀌고, 날짜는 서버가 준 새 값으로 그 자리에서 바뀐다.**
  {
    const dom = build();
    const calls = run(dom, { deal_pitch: NEW });
    await edit(dom.pitch, "새 소개").run();
    assert.strictEqual(calls.length, 1, "저장 요청이 안 나갔습니다");
    assert.deepStrictEqual(calls[0].body, { deal_pitch: "새 소개" },
                           "보낸 값에 날짜가 섞였습니다");
    assert.strictEqual(valueOf(dom.pitch), "새 소개");
    assert.strictEqual(
      stampOf(dom.pitch), NEW,
      "고친 칸의 날짜가 옛 값 그대로입니다 — 새로고침해야 따라오면 " +
      "방금 고친 칸 밑에 거짓말이 적혀 있는 셈입니다");
  }

  // 3) **옆 칸의 날짜는 안 건드린다.** 줄 전체의 `updated_at` 을 쓰면 여기서
  //    걸린다 — 딜 소개문구만 고쳤는데 카톡 칸 날짜까지 바뀌어 보인다.
  {
    const dom = build();
    run(dom, { deal_pitch: NEW });
    await edit(dom.pitch, "새 소개").run();
    assert.strictEqual(stampOf(dom.kakao), OLD, "안 고친 칸의 날짜가 바뀌었습니다");
    assert.strictEqual(stampOf(dom.sep), OLD, "안 고친 달의 날짜가 바뀌었습니다");
    assert.strictEqual(stampOf(dom.jul), OLD, "안 고친 달의 날짜가 바뀌었습니다");
  }

  // 4) **월별 리마인드는 달마다 제 날짜다.** 9월 칸을 고치면 9월 밑만 바뀐다.
  {
    const dom = build();
    const calls = run(dom, { "note:31": NEW });
    await edit(dom.sep, "9월 다시 통화").run();
    assert.deepStrictEqual(calls[0].body, { notes: { "31": "9월 다시 통화" } });
    assert.strictEqual(stampOf(dom.sep), NEW);
    assert.strictEqual(stampOf(dom.jul), OLD, "7월 칸의 날짜까지 같이 바뀌었습니다");
  }

  // 5) **날짜가 없던 칸에는 상자를 만들어 붙인다.** 서버는 날짜가 있을 때만
  //    상자를 세우므로, 처음 고치는 칸에는 쓸 자리가 없다.
  {
    const dom = build();
    assert.strictEqual(stampOf(dom.aug), null, "빈 칸에 미리 상자가 서 있습니다");
    run(dom, { "note:30": NEW });
    await edit(dom.aug, "8월 통화함").run();
    assert.strictEqual(stampOf(dom.aug), NEW, "처음 고친 칸에 날짜가 안 붙었습니다");
    assert.strictEqual(valueOf(dom.aug), "8월 통화함");
  }

  // 6) **날짜를 값으로 안 센다.** 검색 재료(`data-search`)·갈래(`data-f-*`)·
  //    `연락 기록 없음`(`data-contacted`) 셋 다 값만 본다.
  {
    const dom = build();
    run(dom, { deal_pitch: NEW });
    await edit(dom.pitch, "새 소개").run();
    const search = dom.tr.getAttribute("data-search");
    assert.ok(search.indexOf("새 소개") >= 0, "고친 값이 검색 재료에 없습니다");
    assert.ok(search.indexOf("2026-") < 0,
              "`수정한 날짜` 가 검색 재료에 섞였습니다 — " +
              "날짜로 기업이 검색되고, 서버가 적는 값과도 갈립니다");
    assert.strictEqual(dom.tr.getAttribute("data-f-mgmt"), "관리 중",
                       "잔글씨가 없는 칸의 갈래까지 흔들렸습니다");
  }

  // 7) **달 칸을 비우면 `연락 기록 없음` 으로 돌아간다.** 날짜를 기록으로
  //    세면 여기서 걸린다 — 값을 지워도 잔글씨가 남아 `연락했다` 로 읽힌다.
  {
    const dom = build();
    run(dom, {});
    await edit(dom.sep, "").run();
    await edit(dom.jul, "").run();
    assert.strictEqual(
      dom.tr.getAttribute("data-contacted"), "0",
      "달 칸을 다 비웠는데 `연락 기록 있음` 으로 남았습니다 — " +
      "`수정한 날짜` 잔글씨를 기록으로 세고 있습니다");
  }

  // 8) **고르는 칸도 같다.** `O`/`X` 칩을 눌러 고쳐도 날짜만 바뀌고 값이
  //    안 눌어붙는다.
  {
    const dom = build();
    const calls = run(dom, { kakao_joined: NEW });
    dom.kakao.fire("click", { target: dom.kakao });
    const chips = dom.kakao.querySelector(".cell-pop-choices");
    assert.ok(chips, "고르는 칩이 안 섰습니다");
    // `O` · `X` · `비움` 셋. `X` 를 고른다.
    const x = chips.children[1];
    assert.strictEqual(x.textContent, "X");
    x.fire("mousedown", { target: x, preventDefault: function () {} });
    await new Promise(function (r) { setTimeout(r, 0); });
    assert.deepStrictEqual(calls[0].body, { kakao_joined: "X" });
    assert.strictEqual(valueOf(dom.kakao), "X");
    assert.strictEqual(stampOf(dom.kakao), NEW);
    assert.strictEqual(dom.tr.getAttribute("data-f-joined"), "X");
    // 칩은 편집이 끝나면 치운다 — 값 상자만 비우게 되면서 저절로 사라지지
    // 않는다(예전에는 칸을 통째로 비우며 같이 사라졌다).
    assert.strictEqual(dom.kakao.querySelector(".cell-pop-choices"), null,
                       "고르고 나왔는데 칩이 칸에 남아 있습니다");
  }

  // 9) **응답에 날짜가 없어도 저장은 저장이다.** 옛 서버·깨진 본문에서
  //    값까지 되돌아가면 안 된다.
  {
    const dom = build();
    run(dom, null);
    await edit(dom.pitch, "새 소개").run();
    assert.strictEqual(valueOf(dom.pitch), "새 소개");
    assert.strictEqual(stampOf(dom.pitch), OLD, "못 받은 날짜를 지어냈습니다");
  }

  console.log("consulting_field_stamp_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
