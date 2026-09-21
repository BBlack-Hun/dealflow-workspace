// `스타트업 명단으로 보내기` 막대를 접어 두어도 **쓸 수 있는가.**
// (node tests/js/consulting_startup_fold_test.js)
//
// 사용자 요청은 "이관메뉴는 닫음 처리해주고 열어서 기능 사용할 수 있게" 였다.
// 기본을 닫힘으로 두면 함정이 하나 생긴다 — **체크 칸은 표 안에 있어 접어도
// 그대로 보인다.** 줄을 골라 놓고도 개수도 [보내기] 단추도 안 보이는 상태가
// 된다. 그래서 두 가지를 단다: 고른 개수를 여는 줄에 적고, 처음 하나를 고르면
// 저절로 펴진다.
//
// 저절로 펴지는 것에도 반대쪽 함정이 있다 — 사람이 일부러 접었는데 줄을 고를
// 때마다 도로 펴지면 화면이 말을 안 듣는 것이다. 그래서 **손으로 접은 뒤에는
// 안 건드린다.**
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 실제로
// 돌린다**(consulting_to_startup_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js",
                      "consulting_to_startup.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 화면 모양 그대로 ---------------------------------------------------------
function build() {
  function pickRow(id, firm) {
    const cb = D.el("input", { type: "checkbox", class: "cs-pick", value: String(id),
                               "data-firm": firm });
    return { cb: cb, tr: D.el("tr", { "data-id": String(id) },
                              [D.el("td", { class: "pick-cell" }, [cb])]) };
  }
  const a = pickRow(1, "샘플가");
  const b = pickRow(2, "샘플나");
  const table = D.el("table", { id: "cs-table" }, [D.el("tbody", {}, [a.tr, b.tr])]);

  const count = D.el("span", { class: "muted", id: "cs-pick-count" });
  count.textContent = "0개 선택";
  const pickAll = D.el("input", { type: "checkbox", id: "cs-pick-all" });
  const target = D.el("select", { id: "cs-startup-target" });
  target.value = "샘플 명단";
  const button = D.el("button", { id: "cs-startup-send" });
  button.disabled = true;

  const bar = D.el("div", { id: "cs-startup-bar", "data-page-label": "스타트업" },
                   [pickAll, target, button]);
  // **여는 줄에 개수가 적힌다** — 접힌 채로도 몇 개 골랐는지 보여야 한다.
  const summary = D.el("summary", {}, [count]);
  const fold = D.el("details", { class: "sheet-fold", id: "cs-startup-fold" },
                    [summary, D.el("div", { class: "sheet-fold-body" }, [bar])]);
  // `<details>` 는 기본이 닫힘이다(화면이 `open` 을 안 적는다).
  fold.open = false;

  const root = D.el("div", {}, [fold, table]);
  return { root, fold, count, button, pickAll, a, b };
}

function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const calls = [];
  const sandbox = {
    document: document,
    window: { location: { href: "", reload: function () {} } },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    fetch: function (url, opt) {
      calls.push({ url: url, body: JSON.parse(opt.body || "{}") });
      return Promise.resolve({
        ok: true,
        json: function () {
          return Promise.resolve({ added: ["샘플가"], skipped: [], blank: [],
                                   label: "샘플 명단", href: "/startup" });
        }
      });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "consulting_to_startup.js" });
  return calls;
}

// `<details>` 의 여닫이를 흉내 낸다 — 브라우저는 `open` 이 바뀌면 `toggle` 을 쏜다.
function setOpen(fold, open) {
  fold.open = open;
  fold.fire("toggle", { target: fold });
}

function pick(dom, which) {
  which.cb.checked = true;
  which.cb.fire("change", { target: which.cb });
}

(function () {
  // 1) **처음 하나를 고르면 저절로 펴진다.** 접힌 채로는 [보내기] 단추가
  //    안 보여, 줄을 골라 놓고 아무 일도 못 하게 된다.
  {
    const dom = build();
    run(dom);
    assert.strictEqual(dom.fold.open, false, "기본이 닫힘이 아닙니다");
    pick(dom, dom.a);
    assert.strictEqual(dom.fold.open, true,
                       "줄을 골랐는데 막대가 접힌 채로 남았습니다 — " +
                       "[보내기] 단추에 닿을 길이 없습니다");
    assert.strictEqual(dom.button.disabled, false);
  }

  // 2) **접힌 채로도 개수가 보인다.** 개수를 적는 자리는 여는 줄 하나다.
  {
    const dom = build();
    run(dom);
    pick(dom, dom.a);
    pick(dom, dom.b);
    assert.strictEqual(dom.count.textContent, "2개 선택");
    // 그 자리가 정말 여는 줄 안인가 — 몸통 안에 있으면 접었을 때 안 보인다.
    assert.strictEqual(dom.count.parent.tag, "summary",
                       "개수가 여는 줄 밖에 적혀 있습니다 — 접으면 안 보입니다");
  }

  // 3) **손으로 접으면 그 뒤로는 안 건드린다.** 접어 둔 것을 줄을 고를 때마다
  //    도로 펴면 화면이 말을 안 듣는 것이다.
  {
    const dom = build();
    run(dom);
    pick(dom, dom.a);
    setOpen(dom.fold, false);          // 사람이 일부러 접는다
    pick(dom, dom.b);
    assert.strictEqual(dom.fold.open, false,
                       "사람이 접어 둔 막대가 줄을 고르자 도로 펴졌습니다");
    // 그래도 개수는 따라간다 — 접힌 채로 보이는 값이라 이쪽은 계속 맞아야 한다.
    assert.strictEqual(dom.count.textContent, "2개 선택");
  }

  // 4) **여닫이가 없는 화면에서도 죽지 않는다.** 여닫이는 화면 쪽 일이라
  //    이 파일이 그것에 기대면 안 된다(다른 탭·옛 화면).
  {
    const dom = build();
    dom.fold.removeAttribute("id");     // `#cs-startup-fold` 를 못 찾게 한다
    run(dom);
    pick(dom, dom.a);
    assert.strictEqual(dom.count.textContent, "1개 선택");
    assert.strictEqual(dom.button.disabled, false);
  }

  // 5) **보내는 일 자체는 그대로 된다.** 접는 상자를 하나 끼운 것뿐이다.
  {
    const dom = build();
    const calls = run(dom);
    pick(dom, dom.a);
    dom.button.fire("click", { target: dom.button });
    assert.strictEqual(calls.length, 1, "보내기 요청이 안 나갔습니다");
    assert.deepStrictEqual(calls[0].body,
                           { company_ids: [1], label: "샘플 명단" });
  }

  console.log("consulting_startup_fold_test OK");
})();
