// 날짜 칸을 **눌렀다 나가기만 해도** 값이 지워지지 않는가.
// (node tests/js/inline_edit_date_test.js)
//
// ── 무엇이 고장이었나 ────────────────────────────────────────────────────
//
// 날짜 칸(`data-type="date"`)은 `<input type="date">` 로 열린다. 그런데 브라우저의
// 날짜 입력은 **날짜가 아닌 글자를 담지 못한다** — `날짜 미정` 을 넣으면 값이 빈
// 글자가 된다(HTML 의 value sanitization). 그 칸을 눌렀다가 아무것도 안 하고
// 나가면 `빈 값 ≠ 날짜 미정` 이라 **빈 값이 저장됐다.** 사람이 적은 사실이 칸을
// 스치기만 해도 사라진다 — `Series A 이상 기업` 탭의 `수신 일자`, 스타트업DB 의
// `수신일` 이 이 길을 탄다.
//
// ── 여기서 잠그는 것 ──────────────────────────────────────────────────────
//
// ① `날짜 미정` → 눌러 열고 → 나가면: **아무것도 안 보내고**, 칸은 그대로다.
//    열린 입력칸은 그 글자를 **담고 있어야** 한다(날짜 입력이 아니라 글자 입력).
// ② 그 글자 칸에서 날짜를 적어 넣으면 저장된다(고칠 길은 남아 있다).
// ③ 제대로 된 날짜(`2026-08-25`)는 여전히 날짜 입력으로 열리고, 안 고치면 안 보낸다.
// ④ 날짜 입력에서 날짜를 바꾸면 저장되고, **일부러 비우면** 빈 값이 저장된다.
// ⑤ 날짜 입력이 사람 손 없이 비어 버려도(덜 적은 날짜 등) 저장하지 않는다 —
//    사람이 바꾼 것이 아니면 저장할 것이 없다.
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

// 브라우저의 `<input type="date">` 가 하는 일 — 날짜가 아닌 값은 **빈 글자로**
// 바꿔 담는다(HTML 표준의 value sanitization). 이 DOM 의 입력칸은 아무 글자나
// 담아서, 흉내 내지 않으면 고장이 여기서만 안 보인다.
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function realDay(text) {
  if (!ISO_DAY.test(text)) return false;
  const [y, m, d] = text.split("-").map(Number);
  const at = new Date(Date.UTC(y, m - 1, d));
  return at.getUTCFullYear() === y && at.getUTCMonth() === m - 1 && at.getUTCDate() === d;
}

function likeBrowserInput(node) {
  let value = "";
  Object.defineProperty(node, "value", {
    configurable: true,
    get() { return value; },
    set(v) {
      const text = v === null || v === undefined ? "" : String(v);
      value = node.type === "date" && !realDay(text) ? "" : text;
    }
  });
  return node;
}

function build(day) {
  const cell = D.el("td", { class: "cell", "data-field": "received_at", "data-type": "date" });
  cell.textContent = day;
  const tr = D.el("tr", { "data-id": "7" }, [cell]);
  const table = D.el("table", { id: "t", "data-inline-url": "/api/series-a-companies" },
    [D.el("tbody", {}, [tr])]);
  return { root: D.el("div", {}, [table]), table: table, cell: cell };
}

function run(dom) {
  D.resetHandlers();
  const sent = [];
  const document = D.makeDocument(dom.root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const node = made(tag);
    return tag === "input" ? likeBrowserInput(node) : node;
  };
  const win = {
    innerWidth: 1400, innerHeight: 900,
    addEventListener: function () {}, removeEventListener: function () {}
  };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    alert: function () {},
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse((opts && opts.body) || "{}") });
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
  };
  sandbox.window = win;
  win.document = document;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "inline_edit.js" });
  return {
    sent: sent,
    open: function () {
      dom.cell.fire("click");
      const input = dom.cell.querySelector(".cell-input");
      assert.ok(input, "칸을 눌렀는데 입력칸이 안 열렸다");
      return input;
    }
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function main() {
  // ── ① `날짜 미정` → 눌러 열고 → 그냥 나간다 ────────────────────────────
  {
    const dom = build("날짜 미정");
    const t = run(dom);
    const input = t.open();
    const shown = { value: input.value, type: input.type };
    input.blur();
    await flush();
    assert.deepStrictEqual(t.sent, [],
      "아무것도 안 고쳤는데 저장이 나갔다 ★ `날짜 미정` 이 빈 값으로 지워진다: "
      + JSON.stringify(t.sent));
    assert.strictEqual(dom.cell.textContent, "날짜 미정", "칸의 글자가 사라졌다");
    assert.strictEqual(shown.value, "날짜 미정",
      "열린 입력칸이 원래 글자를 못 담았다 ★ 고치려고 연 사람에게 빈 칸으로 보인다");
    assert.notStrictEqual(shown.type, "date",
      "날짜가 아닌 글자를 날짜 입력으로 열었다 — 담지 못해 빈 칸으로 보인다");
  }

  // ── ② 그 글자 칸에서 날짜를 적으면 저장된다 ─────────────────────────────
  {
    const dom = build("날짜 미정");
    const t = run(dom);
    const input = t.open();
    input.value = "2026-09-03";
    input.fire("input");
    input.blur();
    await flush();
    assert.strictEqual(t.sent.length, 1, "날짜를 적었는데 저장이 안 나갔다");
    assert.deepStrictEqual(t.sent[0],
      { url: "/api/series-a-companies/7", body: { received_at: "2026-09-03" } });
  }

  // ── ③ 제대로 된 날짜는 날짜 입력으로 열리고, 안 고치면 안 보낸다 ─────────
  {
    const dom = build("2026-08-25");
    const t = run(dom);
    const input = t.open();
    assert.strictEqual(input.type, "date", "날짜가 적힌 칸은 날짜 입력으로 열려야 한다");
    assert.strictEqual(input.value, "2026-08-25");
    input.blur();
    await flush();
    assert.deepStrictEqual(t.sent, [], "안 고쳤는데 저장이 나갔다");
    assert.strictEqual(dom.cell.textContent, "2026-08-25");
  }

  // 날짜처럼 보여도 **없는 날**(2월 30일)은 날짜 입력이 못 담는다 — 글자로 연다.
  {
    const dom = build("2026-02-30");
    const t = run(dom);
    const input = t.open();
    assert.strictEqual(input.value, "2026-02-30", "없는 날을 빈 값으로 바꿨다");
    input.blur();
    await flush();
    assert.deepStrictEqual(t.sent, [], "안 고쳤는데 `2026-02-30` 이 지워졌다");
  }

  // 빈 칸은 날짜 입력으로 열리고, 안 고치면 안 보낸다.
  {
    const dom = build("");
    const t = run(dom);
    const input = t.open();
    assert.strictEqual(input.type, "date");
    input.blur();
    await flush();
    assert.deepStrictEqual(t.sent, [], "빈 칸을 스쳤는데 저장이 나갔다");
  }

  // ── ④ 날짜를 바꾸면 저장 · 일부러 비우면 빈 값 저장 ─────────────────────
  {
    const dom = build("2026-08-25");
    const t = run(dom);
    const input = t.open();
    input.value = "2026-09-01";
    input.fire("change");
    input.blur();
    await flush();
    assert.strictEqual(t.sent.length, 1, "날짜를 바꿨는데 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].body.received_at, "2026-09-01");
  }
  {
    const dom = build("2026-08-25");
    const t = run(dom);
    const input = t.open();
    input.value = "";
    input.fire("input");
    input.blur();
    await flush();
    assert.strictEqual(t.sent.length, 1, "일부러 비웠는데 저장이 안 나갔다");
    assert.strictEqual(t.sent[0].body.received_at, "");
  }

  // ── ⑤ 사람 손 없이 비어 버린 날짜 입력은 저장하지 않는다 ─────────────────
  //
  // 브라우저가 덜 적힌 날짜(`2026-08-__`)를 빈 값으로 돌려줄 때가 그렇다 —
  // 사람이 지운 것이 아니다.
  {
    const dom = build("2026-08-25");
    const t = run(dom);
    const input = t.open();
    input.value = "";                    // 아무 입력 알림 없이 비었다
    input.blur();
    await flush();
    assert.deepStrictEqual(t.sent, [],
      "사람이 고치지 않았는데 빈 값이 저장됐다 ★ 날짜가 조용히 지워진다");
    assert.strictEqual(dom.cell.textContent, "2026-08-25", "칸이 원래 날짜로 돌아오지 않았다");
  }

  console.log("inline_edit_date_test: 모두 통과");
}

main().catch(function (err) {
  console.error(err);
  process.exit(1);
});
