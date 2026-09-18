// 「요청받은 기업」 칸의 **기업명 후보** — 치는 줄에만 뜨는가.
// (node tests/js/ir_company_hint_test.js)
//
// ── 여기서 잠그는 것 ─────────────────────────────────────────────────────
//
// 이 칸은 **번호로도 적는 칸**이다(`2, 4`). 후보를 얹다가 그 길이 깨지면,
// 지난 회차 번호로 적던 사람이 갑자기 이름을 골라야 한다.
//
//   · 이름을 치면 후보가 뜬다 — **가운데 글자로도**(`<datalist>` 로는 안 되는 자리).
//   · **숫자만 친 조각에는 안 뜬다** — 그 줄은 번호로 읽는 줄이다.
//   · 여러 줄 중 **지금 치는 줄만** 갈아 끼운다.
//   · `2, 샘` 의 `2, ` 는 한 글자도 안 바뀐다.
//   · ↑↓·Enter 로 고른다. **짚어 둔 것이 없는 Enter 는 줄바꿈** — 이 칸은
//     여러 줄을 적는 칸이라 Enter 를 뺏으면 안 된다.
//   · `Esc` 는 목록만 닫는다.
//   · 후보를 누를 때 **초점이 칸을 안 떠난다**(`mousedown` 에서 막는다).
//   · 후보가 없으면 **조용히** 아무 일도 안 한다.
//   · 후보 목록을 읽는 자리가 **한 곳**이다.
//
// 기업 이름은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const HINT = fs.readFileSync(path.join(SRC, "ir_company_hint.js"), "utf8");

// 서버가 실어 주는 후보(`routers/ir.py` 의 `_company_names`). 열한 곳 —
// 한 번에 세우는 여덟을 넘겨야 "잘랐다" 는 말이 나오는지 볼 수 있다.
const NAMES = ["샘플애그", "샘플바이오", "샘플에너지", "샘플헬스",
               "가나테크", "다라소프트", "마바로보틱스", "사아모빌리티",
               "자차데이터", "카타핀테크", "파하클라우드"];

function build(names) {
  D.resetHandlers();
  const carrier = D.el("div", {
    id: "opts-ir-company", hidden: "",
    "data-names": JSON.stringify(names === undefined ? NAMES : names)
  });
  const textarea = D.el("textarea", {
    id: "request-companies", name: "company_name", "data-company-hint": ""
  });
  const label = D.el("label", { class: "field inline-field" }, [textarea]);
  const form = D.el("form", { method: "post", action: "/ir/requests" }, [label]);
  const root = D.el("div", { class: "member-form", id: "new-request" },
                    [form, carrier]);
  return { root: root, textarea: textarea, label: label, carrier: carrier };
}

function run(dom) {
  const document = D.makeDocument(dom.root);
  const win = { innerWidth: 1440, innerHeight: 900,
                addEventListener: function () {}, removeEventListener: function () {} };
  const sandbox = { document: document, console: console, setTimeout: setTimeout };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(HINT, sandbox, { filename: "ir_company_hint.js" });
  return { win: win, sandbox: sandbox };
}

// 목록 상자는 **불러 준 자리 안쪽**에 선다(칸의 부모).
function boxOf(dom) { return dom.label.querySelector(".name-hint"); }

function items(dom) {
  const box = boxOf(dom);
  return box ? box.querySelectorAll(".name-hint-item").map((n) => n.textContent) : [];
}

function note(dom) {
  const one = boxOf(dom).querySelector(".name-hint-note");
  return one ? one.textContent : "";
}

// 친다. 커서는 **친 자리 끝**에 둔다 — 브라우저와 같다.
function type(dom, value, caret) {
  dom.textarea.value = value;
  dom.textarea.selectionStart = caret === undefined ? value.length : caret;
  dom.textarea.fire("input");
}

function key(dom, name) {
  let prevented = 0;
  dom.textarea.fire("keydown", {
    key: name, preventDefault: function () { prevented += 1; },
    stopPropagation: function () {}
  });
  return prevented;
}

function main() {
  // ── 1. 이름을 치면 후보가 뜬다 — **가운데 글자로도** ──────────────────
  {
    const dom = build();
    run(dom);
    type(dom, "샘플");
    assert.ok(items(dom).length >= 4, "앞 글자로 후보가 안 뜬다");
    type(dom, "바이오");
    assert.deepStrictEqual(items(dom), ["샘플바이오"],
      "이름 가운데 글자로 못 찾는다 ★ `<datalist>` 로는 안 되던 그 자리다");
  }

  // ── 2. **숫자만 친 조각에는 안 뜬다** ────────────────────────────────
  //
  // 투자사는 "4번, 6번 주세요" 라고 답하고, 그 줄은 지난 회차 번호로 읽힌다
  // (`pipeline.resolve_request_names`). 거기서 이름을 권하면 뜻이 바뀐다.
  {
    const dom = build();
    run(dom);
    type(dom, "2");
    assert.strictEqual(boxOf(dom).hidden, true,
      "번호를 치는데 이름 후보가 떴다 ★ 번호로 적는 길이 흔들린다");
    type(dom, "2, 4");
    assert.strictEqual(boxOf(dom).hidden, true, "`2, 4` 에도 후보가 떴다");
  }

  // ── 3. `2, 샘` — **번호 조각은 한 글자도 안 바뀐다** ─────────────────
  {
    const dom = build();
    run(dom);
    type(dom, "2, 샘플애");
    assert.deepStrictEqual(items(dom), ["샘플애그"], "쉼표 뒤 조각을 못 읽는다");
    boxOf(dom).querySelectorAll(".name-hint-item")[0]
      .fire("mousedown", { preventDefault: function () {} });
    assert.strictEqual(dom.textarea.value, "2, 샘플애그",
      "앞의 번호가 함께 갈렸다 ★ 번호로 적은 것이 사라진다");
  }

  // ── 4. **여러 줄 중 지금 치는 줄만** 갈아 끼운다 ─────────────────────
  {
    const dom = build();
    run(dom);
    const text = "샘플바이오\n가나테";
    type(dom, text);
    assert.deepStrictEqual(items(dom), ["가나테크"], "둘째 줄을 못 읽는다");
    boxOf(dom).querySelectorAll(".name-hint-item")[0]
      .fire("mousedown", { preventDefault: function () {} });
    assert.strictEqual(dom.textarea.value, "샘플바이오\n가나테크",
      "앞 줄이 함께 갈렸다 ★ 적어 둔 기업이 사라진다");
  }

  // ── 5. 커서가 **가운데 줄**에 있어도 그 줄만 본다 ────────────────────
  {
    const dom = build();
    run(dom);
    const text = "샘플애그\n다라소\n카타핀테크";
    type(dom, text, "샘플애그\n다라소".length);
    assert.deepStrictEqual(items(dom), ["다라소프트"],
      "커서가 있는 줄이 아니라 다른 줄을 읽었다");
    boxOf(dom).querySelectorAll(".name-hint-item")[0]
      .fire("mousedown", { preventDefault: function () {} });
    assert.strictEqual(dom.textarea.value, "샘플애그\n다라소프트\n카타핀테크",
      "가운데 줄만 갈리지 않았다");
  }

  // ── 6. ↑↓·Enter 로 고른다 ───────────────────────────────────────────
  //
  // 마우스만 되면 빨리 적는 사람에게 오히려 방해다.
  {
    const dom = build();
    run(dom);
    type(dom, "샘플");
    const shown = items(dom);
    assert.ok(shown.length >= 2, "후보가 둘은 떠야 ↑↓ 를 볼 수 있다");
    assert.strictEqual(key(dom, "ArrowDown"), 1, "↓ 가 아무 일도 안 한다");
    assert.strictEqual(key(dom, "ArrowDown"), 1, "↓ 두 번째가 안 먹는다");
    assert.strictEqual(key(dom, "Enter"), 1, "Enter 가 짚어 둔 것을 안 고른다");
    assert.strictEqual(dom.textarea.value, shown[1],
      "↓↓ 로 짚은 둘째 후보가 아니라 다른 것이 들어갔다");
  }

  // ── 7. **짚어 둔 것이 없는 Enter 는 줄바꿈이다** ─────────────────────
  //
  // 이 칸은 여러 개를 줄바꿈으로 적는 칸이다. 목록이 떠 있다는 이유로 첫
  // 후보를 대신 골라 주면, 둘째 기업을 적으려던 Enter 가 첫 줄을 갈아 버린다.
  {
    const dom = build();
    run(dom);
    type(dom, "샘플");
    assert.strictEqual(key(dom, "Enter"), 0,
      "짚어 둔 것이 없는데 Enter 를 가로챘다 ★ 줄을 바꿀 수가 없다");
    assert.strictEqual(dom.textarea.value, "샘플",
      "Enter 가 대신 골라 줬다 ★ 친 것과 적히는 것이 달라진다");
  }

  // ── 8. `Esc` 는 목록만 닫는다 ────────────────────────────────────────
  {
    const dom = build();
    run(dom);
    type(dom, "샘플");
    assert.strictEqual(boxOf(dom).hidden, false, "후보가 안 떴다");
    assert.strictEqual(key(dom, "Escape"), 1, "Esc 가 아무 일도 안 한다");
    assert.strictEqual(boxOf(dom).hidden, true, "Esc 로 목록이 안 닫힌다");
    assert.strictEqual(dom.textarea.value, "샘플", "Esc 가 친 글자를 지웠다");
  }

  // ── 9. 후보를 누를 때 **초점이 칸을 안 떠난다** ──────────────────────
  //
  // `mousedown` 에서 막지 않으면 고르기도 전에 칸을 벗어난다 —
  // `email_hint.js` 가 겪은 그 함정이다.
  {
    const dom = build();
    run(dom);
    type(dom, "샘플애");
    let blocked = 0;
    boxOf(dom).querySelectorAll(".name-hint-item")[0]
      .fire("mousedown", { preventDefault: function () { blocked += 1; } });
    assert.strictEqual(blocked, 1,
      "후보를 누를 때 기본 동작을 안 막는다 ★ 초점이 칸을 떠난다");
  }

  // ── 10. 후보가 없으면 **조용히** 아무 일도 안 한다 ───────────────────
  {
    const dom = build();
    run(dom);
    type(dom, "없는기업이름");
    assert.strictEqual(boxOf(dom).hidden, true, "안 맞는데 목록이 떠 있다");
    assert.deepStrictEqual(items(dom), [], "빈 목록이 그려져 있다");
  }

  // ── 11. 실어 준 후보가 **하나도 없어도** 칸은 그대로 산다 ────────────
  {
    const dom = build([]);
    run(dom);
    assert.strictEqual(boxOf(dom), null, "후보가 없는데 목록 상자를 세웠다");
    dom.textarea.value = "샘플애그";
    dom.textarea.fire("input");              // 아무 일도 안 나야 한다
    assert.strictEqual(dom.textarea.value, "샘플애그", "친 글자가 바뀌었다");
  }

  // ── 12. 여덟을 넘으면 **잘랐다고 말한다** ────────────────────────────
  //
  // 안 보이는 것이 없는 것으로 읽히면 사람이 목록을 뒤진다.
  {
    const dom = build();
    run(dom);
    type(dom, "샘");                          // `샘플…` 넷 — 안 잘린다
    assert.ok(!/외 /.test(note(dom)), "안 잘랐는데 잘랐다고 말한다: " + note(dom));
    type(dom, "ㅏ");                          // 아무 데도 안 걸리는 글자
    assert.strictEqual(boxOf(dom).hidden, true, "안 걸리는데 목록이 떴다");

    const many = build(NAMES.concat(["샘플가", "샘플나", "샘플다", "샘플라",
                                     "샘플마", "샘플바"]));
    run(many);
    type(many, "샘플");
    assert.strictEqual(items(many).length, 8, "여덟보다 많이 세웠다");
    assert.ok(/외 \d+곳/.test(
      boxOf(many).querySelector(".name-hint-note").textContent),
      "자른 것을 말해 주지 않는다");
  }

  // ── 13. 후보 목록을 읽는 자리가 **한 곳**이다 ────────────────────────
  {
    const readers = fs.readdirSync(SRC)
      .filter((f) => f.endsWith(".js"))
      .filter((f) => /opts-ir-company/.test(
        fs.readFileSync(path.join(SRC, f), "utf8")));
    assert.deepStrictEqual(readers, ["ir_company_hint.js"],
      "기업 후보를 읽는 자리가 둘 이상이다 ★ 두 자리의 후보가 갈린다");
  }

  console.log("ir_company_hint_test OK");
}

main();
