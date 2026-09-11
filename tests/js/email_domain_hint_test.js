// 메일 칸의 **도메인 후보** — 치는 대로 `친글자@도메인` 이 뜨는가.
// (node tests/js/email_domain_hint_test.js)
//
// ── 여기서 잠그는 것 ─────────────────────────────────────────────────────
//
// 이 기능은 **저장 흐름 위에 얹히는** 물건이라, 동작하느냐보다 **무엇을 안
// 깨뜨리느냐**가 잠글 것이다.
//
//   · 후보를 누르는 순간 `blur` 가 나서 **고르기도 전에 저장되고 창이 닫히는**
//     일이 없어야 한다(#152 가 `.cell-pop` 여백에서 고친 것과 같은 함정).
//   · `@` 앞은 한 글자도 안 바뀐다.
//   · 안 골라도 그만이다 — 목록에 없는 도메인을 쳐도 그대로 저장된다.
//   · `Esc` 는 목록만 닫는다. 한 번 더 눌러야 창이 닫힌다.
//   · 도메인 목록을 읽는 자리가 **한 곳**이다.
//   · 표에서 고치는 길과 수정창에서 고치는 길이 **같은 부품**을 쓴다.
//   · 메일이 하나도 없는 화면에서 안 깨진다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const HINT = fs.readFileSync(path.join(SRC, "email_hint.js"), "utf8");
const INLINE = fs.readFileSync(path.join(SRC, "inline_edit.js"), "utf8");

// 서버가 골라 준 차례 그대로(많이 쓰인 것부터). 열 가지 — 한 번에 세우는
// 여덟을 넘겨야 "잘랐다" 는 말이 나오는지 볼 수 있다.
const DOMAINS = ["example.com", "example.net", "example.org", "samp.example",
                 "sample.example", "demo.example", "test.example",
                 "mail.example", "ex.example", "exam.example"];

function build(domains) {
  const carrier = D.el("div", {
    id: "opts-email-domain", hidden: "",
    "data-domains": JSON.stringify(domains === undefined ? DOMAINS : domains)
  });

  // ① 표에서 눌러 고치는 길
  const cell = D.el("td", {
    class: "cell ellipsis", "data-field": "contact_email", "data-type": "email"
  });
  cell.textContent = "before@samp.example";
  const plain = D.el("td", { class: "who" });          // 아무것도 아닌 자리(= 바깥)
  const tr = D.el("tr", { "data-id": "7" }, [cell, plain]);
  const table = D.el("table",
    { id: "co-table", "data-inline-url": "/api/companies" },
    [D.el("tbody", {}, [tr])]);

  // ② 수정창에서 고치는 길
  const field = D.el("input", { type: "text", id: "f-contact_email",
                                "data-email-hint": "" });
  const label = D.el("label", { class: "field" }, [field]);

  const root = D.el("div", {}, [carrier, table, label]);
  return { root, table, cell, plain, field, carrier };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const win = {
    innerWidth: 1400, innerHeight: 900,
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
  // 화면이 싣는 차례 그대로 — 후보 부품이 먼저다.
  vm.runInContext(HINT, sandbox, { filename: "email_hint.js" });
  vm.runInContext(INLINE, sandbox, { filename: "inline_edit.js" });
  return {
    sent: sent,
    win: win,
    pop: function () { return dom.root.querySelector(".cell-pop"); },
    // 브라우저의 차례 그대로 — pointerdown 이 먼저, click 이 나중이다.
    press: function (node) { node.fire("pointerdown"); node.fire("click"); },
    // 고칠 칸의 입력. 표 칸은 편집창 안에, 수정창은 그 칸 자체다.
    cellInput: function () {
      const pop = dom.root.querySelector(".cell-pop");
      return pop && pop.querySelector(".cell-pop-input");
    },
    hintOf: function (input) {
      // 목록 상자는 **불러 준 자리 안쪽**에 선다. 표 칸이면 편집창 안,
      // 수정창이면 그 칸의 부모 안 — 어느 쪽이든 여기서 찾아진다.
      let node = input.parentNode;
      while (node) {
        const box = node.querySelector(".email-hint");
        if (box) return box;
        node = node.parentNode;
      }
      return null;
    },
    type: function (input, value) { input.value = value; input.fire("input"); },
    key: function (input, key) { input.fire("keydown", { key: key }); }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

function items(box) {
  return box.querySelectorAll(".email-hint-item").map((n) => n.textContent);
}

async function main() {
  // ── 1. `이름@` 까지 치면 후보가 뜬다 (표에서 고치는 길) ────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    assert.ok(input, "메일 칸을 눌렀는데 편집창이 안 떴다");

    const box = t.hintOf(input);
    assert.ok(box, "도메인 후보 상자가 아예 안 만들어졌다");
    assert.strictEqual(box.hidden, true, "아무것도 안 쳤는데 후보가 떠 있다");

    t.type(input, "hong");
    assert.strictEqual(box.hidden, true,
      "`@` 를 안 쳤는데 후보가 떴다 ★ 이름을 치는 내내 목록이 앞을 가린다");

    t.type(input, "hong@");
    assert.strictEqual(box.hidden, false,
      "`이름@` 까지 쳤는데 도메인 후보가 안 뜬다 ★ 이 기능의 전부다");
    assert.strictEqual(items(box)[0], "example.com",
      "가장 많이 쓰인 도메인이 맨 앞에 안 선다 — `@` 만 치고 멈춘 손이 훑어야 한다");
  }

  // ── 2. 목록 상자는 **편집창 안쪽**이다 (닫힘 판정에 안 걸린다) ─────────
  //
  // 이것이 이 기능의 함정 자리다. 상자를 `document.body` 에 띄우면 보이는
  // 자리는 같은데, 누르는 순간 편집창의 "바깥을 눌렀나" 판정에 걸려
  // **고르기도 전에 저장되고 창이 닫힌다.**
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    const pop = t.pop();
    const box = t.hintOf(input);
    t.type(input, "hong@");

    assert.ok(pop.contains(box),
      "후보 목록이 편집창 밖에 섰다 ★ 누르는 순간 창이 저장되며 닫힌다");

    box.fire("pointerdown");
    assert.strictEqual(t.pop(), pop,
      "후보 목록을 눌렀는데 편집창이 닫혔다 ★ 고르기도 전에 사라진다");
    assert.deepStrictEqual(t.sent, [],
      "후보를 **고르기도 전에** 저장이 나갔다 ★ blur 함정");
  }

  // ── 3. 고르면 `이름@도메인` 이 되고 `@` 앞이 안 바뀐다 ────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    const pop = t.pop();
    const box = t.hintOf(input);
    t.type(input, "hong.gildong+vc@");

    box.querySelectorAll(".email-hint-item")[1].fire("mousedown");
    assert.strictEqual(input.value, "hong.gildong+vc@example.net",
      "고른 도메인이 안 붙거나 `@` 앞이 바뀌었다");
    assert.strictEqual(box.hidden, true, "골랐는데 목록이 그대로 떠 있다");

    // **고르는 것과 저장하는 것은 다른 걸음이다.** 고른 뒤에도 앞자리를 고칠
    // 수 있어야 하고, 수정창 쪽은 [저장]을 눌러야 저장되는 칸이라 두 길의
    // 동작이 같아야 한다.
    assert.strictEqual(t.pop(), pop, "골랐다고 편집창이 닫혔다");
    assert.deepStrictEqual(t.sent, [], "골랐다고 곧바로 저장까지 나갔다");

    // 그리고 바깥을 누르면 고른 그대로 저장된다.
    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent.length, 1, "바깥을 눌렀는데 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].body.contact_email, "hong.gildong+vc@example.net",
      "고른 값이 아닌 것이 저장됐다");
  }

  // ── 4. ↑↓ 로 짚고 Enter 로 고른다 ─────────────────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    const box = t.hintOf(input);
    t.type(input, "kim@");

    assert.strictEqual(box.querySelectorAll(".email-hint-item.on").length, 0,
      "아직 아무것도 안 짚었는데 짚힌 줄이 있다 ★ Enter 한 번에 남의 도메인이 붙는다");

    t.key(input, "ArrowDown");
    t.key(input, "ArrowDown");
    assert.deepStrictEqual(
      box.querySelectorAll(".email-hint-item.on").map((n) => n.textContent),
      ["example.net"], "↑↓ 로 짚은 줄이 표시되지 않는다");

    t.key(input, "ArrowUp");
    t.key(input, "Enter");
    assert.strictEqual(input.value, "kim@example.com",
      "Enter 로 짚어 둔 후보를 못 골랐다 ★ 마우스로만 되면 타이핑 중에 손이 뜬다");
    assert.deepStrictEqual(t.sent, [], "고르는 Enter 가 저장까지 해 버렸다");
  }

  // ── 5. **짚어 둔 것이 없으면** Enter 는 그냥 저장이다 ──────────────────
  //
  // 목록이 떠 있다는 이유로 첫 줄을 대신 골라 주면, 사람이 친 것과 저장된
  // 것이 달라진다 — 후보에 없는 도메인을 치는 길이 그 자리에서 막힌다.
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    t.type(input, "lee@ex");          // `ex.example`·`exam.example` 이 뜬다

    t.key(input, "Enter");
    await flush();
    assert.strictEqual(t.pop(), null, "Enter 로 편집창이 안 닫혔다");
    assert.strictEqual(t.sent.length, 1, "Enter 로 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].body.contact_email, "lee@ex",
      "짚어 둔 것이 없는데 후보가 대신 골라졌다 ★ 친 것과 저장된 것이 다르다");
  }

  // ── 6. 후보에 없는 도메인도 그대로 저장된다 ───────────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    const box = t.hintOf(input);
    t.type(input, "park@nowhere.example");
    assert.strictEqual(box.hidden, true,
      "맞는 후보가 없는데 빈 목록이 떠 있다 — 치는 앞을 가린다");

    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent[0].body.contact_email, "park@nowhere.example",
      "목록에 없는 도메인이 그대로 저장되지 않았다");
  }

  // ── 7. `Esc` 는 목록만 닫는다. 한 번 더 눌러야 창이 닫힌다 ────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    const pop = t.pop();
    const box = t.hintOf(input);
    t.type(input, "choi@");
    assert.strictEqual(box.hidden, false, "후보가 안 떴다");

    t.key(input, "Escape");
    assert.strictEqual(box.hidden, true, "Esc 로 목록이 안 닫혔다");
    assert.strictEqual(t.pop(), pop,
      "목록을 닫는 Esc 가 편집창까지 닫았다 ★ 적던 값이 통째로 사라진다");

    t.key(input, "Escape");
    await flush();
    assert.strictEqual(t.pop(), null, "두 번째 Esc 로 편집창이 안 닫혔다");
    assert.deepStrictEqual(t.sent, [], "Esc 는 버리고 닫는 길인데 저장이 나갔다");
  }

  // ── 8. 너무 많으면 자르고, **자른 것을 말해 준다** ────────────────────
  {
    const dom = build();
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    const box = t.hintOf(input);
    t.type(input, "yoon@");           // 열 가지가 다 걸린다

    const shown = items(box);
    assert.strictEqual(shown.length, 8,
      "후보를 안 잘랐다 — 백 줄이 서면 고르는 것보다 치는 것이 빠르다");
    const note = box.querySelector(".email-hint-note");
    assert.ok(note && /외 2개/.test(note.textContent),
      "자른 사실을 안 말해 준다 ★ 안 보이는 것이 없는 것으로 읽힌다");

    // 더 치면 좁혀지고, 그때는 자를 것이 없다.
    t.type(input, "yoon@exa");
    assert.deepStrictEqual(items(box), ["example.com", "example.net",
                                        "example.org", "exam.example"]);
    assert.ok(/두 번 이상 쓰인 도메인만/.test(
      box.querySelector(".email-hint-note").textContent),
      "왜 이것만 뜨는지 안 말해 준다 ★ 자기 도메인이 없는 사람이 목록을 뒤진다");
  }

  // ── 9. 수정창에서도 **똑같이** 된다 ───────────────────────────────────
  //
  // 두 길 중 한쪽만 되면, 사람이 어느 쪽으로 들어왔느냐에 따라 화면이 달라진다.
  {
    const dom = build();
    const t = run(dom);
    const input = dom.field;
    const box = t.hintOf(input);
    assert.ok(box, "수정창의 메일 칸에는 후보 상자가 안 붙었다 ★ 두 길이 갈렸다");

    t.type(input, "jung@");
    assert.strictEqual(box.hidden, false, "수정창에서 후보가 안 뜬다");

    box.querySelectorAll(".email-hint-item")[0].fire("mousedown");
    assert.strictEqual(input.value, "jung@example.com",
      "수정창에서 고른 도메인이 안 붙었다");

    // 수정창은 [저장]을 눌러야 저장되는 자리다 — 고르는 것만으로 아무것도
    // 나가면 안 된다.
    assert.deepStrictEqual(t.sent, [], "수정창에서 골랐을 뿐인데 요청이 나갔다");

    // ↑↓·Enter 도 같다.
    t.type(input, "jung@sam");
    t.key(input, "ArrowDown");
    t.key(input, "Enter");
    assert.strictEqual(input.value, "jung@samp.example",
      "수정창에서 키보드로 못 고른다");
  }

  // ── 10. 메일이 하나도 없는 화면에서 안 깨진다 ─────────────────────────
  {
    const dom = build([]);
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    assert.ok(input, "후보가 없다고 칸이 아예 안 열린다");
    const box = t.hintOf(input);
    t.type(input, "seo@");
    assert.ok(!box || box.hidden === true, "후보가 없는데 빈 목록이 떴다");

    input.value = "seo@example.com";
    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent[0].body.contact_email, "seo@example.com",
      "후보가 없을 때 그냥 치는 길까지 막혔다");
  }

  // ── 11. 후보를 싣는 칸이 없어도(구버전 화면) 안 깨진다 ────────────────
  {
    const dom = build();
    dom.root.removeChild(dom.carrier);
    const t = run(dom);
    t.press(dom.cell);
    const input = t.cellInput();
    assert.ok(input, "후보 칸이 없다고 편집창이 안 뜬다");
    input.value = "no@carrier.example";
    dom.plain.fire("pointerdown");
    await flush();
    assert.strictEqual(t.sent[0].body.contact_email, "no@carrier.example");
  }

  // ── 12. 도메인 목록을 읽는 자리가 **한 곳**이다 ───────────────────────
  //
  // 두 벌이 되는 날 두 화면이 서로 다른 후보를 띄운다 — 이 저장소가 반복해
  // 당한 부류다. 그래서 글자로 잠근다.
  {
    const readers = fs.readdirSync(SRC)
      .filter((f) => f.endsWith(".js"))
      .filter((f) => /opts-email-domain/.test(
        fs.readFileSync(path.join(SRC, f), "utf8")));
    assert.deepStrictEqual(readers, ["email_hint.js"],
      "도메인 목록을 읽는 자리가 둘 이상이다 ★ 두 화면의 후보가 갈린다");

    assert.ok(/global\.DealflowEmailHint/.test(INLINE),
      "표에서 고치는 길이 공통 부품을 안 쓴다 — 같은 판단이 두 벌이 된다");
    assert.ok(!/lastIndexOf\("@"\)/.test(INLINE),
      "`@` 를 가르는 규칙이 inline_edit.js 에도 적혀 있다 ★ 한쪽만 고쳐진다");
  }

  console.log("email_domain_hint_test OK");
}

main().catch((err) => { console.error(err); process.exit(1); });
