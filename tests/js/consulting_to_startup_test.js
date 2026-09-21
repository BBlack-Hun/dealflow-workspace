// 여러 줄을 골라 스타트업 명단으로 보내는 막대.
// (node tests/js/consulting_to_startup_test.js)
//
// 가장 위험한 자리는 [전체 선택]이다. 이 표는 검색·필터로 줄을 감추는데
// (`consulting.js` 의 `tr.hidden`), 감춘 줄까지 켜지면 **화면에 없는 기업이
// 남의 명단에 선다** — 누른 사람은 자기가 무엇을 보냈는지 모른다. 투자사
// 풀의 [내 명단으로 할당](`pool_assign.js`)이 같은 함정을 이미 겪었다.
//
// 그다음이 `이미 있는 줄`이다. 서버가 건너뛰기는 하지만 체크 칸이 서 있으면
// 골라 놓고 아무 일도 안 일어나는 줄이 된다 — 화면은 그런 줄에 체크 칸 자체를
// 안 세운다(서버가 그리는 그 모양을 여기서도 그대로 세운다).
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 실제로
// 돌린다**(consulting_kpi_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js",
                      "consulting_to_startup.js");
const src = fs.readFileSync(SRC, "utf8");

const TARGET = "스타트업 · 가담당";

// --- 서버가 그리는 것과 같은 모양의 줄 ---------------------------------------
//
// `inStartup` 인 줄에는 체크 칸이 없다 — 대신 `✓` 가 선다(consulting.html).
function row(id, name, opts) {
  opts = opts || {};
  const pick = D.el("td", { class: "pick-cell" });
  if (opts.inStartup) {
    pick.appendChild(D.el("span", { class: "muted" }));
  } else {
    // `data-firm` 은 **보내면 설 이름**이다 — 서버가 `기업명` 칸에서 꺼내
    // 실어 준다(`startup_handoff.company_name_of`).
    pick.appendChild(D.el("input", {
      type: "checkbox", class: "cs-pick", value: String(id),
      "data-firm": opts.firm || name }));
  }
  const nameCell = D.el("td", { class: "cell strong",
                                "data-field": "company_name" });
  nameCell.textContent = name;
  const tr = D.el("tr", { "data-id": String(id) },
                  [pick, D.el("td", { class: "num muted" }), nameCell]);
  tr.hidden = !!opts.hidden;
  return tr;
}

function build(rows) {
  D.resetHandlers();

  const all = D.el("input", { type: "checkbox", id: "cs-pick-all" });
  const count = D.el("span", { id: "cs-pick-count" });
  const target = D.el("select", { id: "cs-startup-target" });
  target.value = TARGET;
  const send = D.el("button", { id: "cs-startup-send" });
  const bar = D.el("div", { id: "cs-startup-bar", "data-page-label": "스타트업" },
                   [all, count, target, send]);
  const table = D.el("table", { id: "cs-table" }, [D.el("tbody", {}, rows)]);
  const root = D.el("div", {}, [bar, table]);

  const sent = [];
  const alerts = [];
  const asks = [];
  const sandbox = {
    document: D.makeDocument(root),
    window: { location: { href: "/consulting", pathname: "/consulting",
                          reload: function () {} } },
    setTimeout: setTimeout,
    confirm: function (text) { asks.push(text); return true; },
    alert: function (text) { alerts.push(text); },
    fetch: function (url, opts) {
      sent.push({ url: url, body: JSON.parse(opts.body) });
      // 서버가 돌려주는 모양 그대로.
      const answer = {
        ok: true, label: TARGET, owner: "가담당",
        added: ["샘플가"], skipped: [], blank: [],
        href: "/startup?sheet=x"
      };
      return Promise.resolve({
        ok: true, json: function () { return Promise.resolve(answer); }
      });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return { root: root, sent: sent, alerts: alerts, asks: asks,
           all: all, count: count, send: send, table: table };
}

function boxes(t) { return D.queryAll(t.table, ".cs-pick"); }
function picked(t) {
  return boxes(t).filter(function (cb) { return cb.checked; })
                 .map(function (cb) { return cb.value; });
}
function check(cb, on) { cb.checked = on; cb.fire("change"); }
function pickAll(t, on) { t.all.checked = on; t.all.fire("change"); }

// ── 1) 처음에는 아무것도 안 골라져 있고 단추가 꺼져 있다 ────────────────────
{
  const t = build([row(1, "샘플가"), row(2, "샘플나")]);
  assert.strictEqual(t.count.textContent, "0개 선택");
  assert.strictEqual(t.send.disabled, true,
    "아무것도 안 골랐는데 단추가 켜져 있다");
}

// ── 2) 고르면 수가 따라오고 단추가 켜진다 ───────────────────────────────────
{
  const t = build([row(1, "샘플가"), row(2, "샘플나")]);
  check(boxes(t)[0], true);
  assert.strictEqual(t.count.textContent, "1개 선택");
  assert.strictEqual(t.send.disabled, false);
  check(boxes(t)[0], false);
  assert.strictEqual(t.count.textContent, "0개 선택");
  assert.strictEqual(t.send.disabled, true, "다 풀었는데 단추가 켜져 있다");
}

// ── 3) ★ [전체 선택]은 **보이는 줄에만** 걸린다 ─────────────────────────────
//
// 검색으로 걸러 놓고 [전체 선택]을 누르는 순간 걸러진 줄까지 켜지면, 화면에
// 없는 기업이 남의 명단에 선다.
{
  const t = build([row(1, "샘플가"), row(2, "샘플나", { hidden: true }),
                   row(3, "샘플다")]);
  pickAll(t, true);
  assert.deepStrictEqual(picked(t), ["1", "3"],
    "검색으로 숨긴 줄까지 골라졌다 — 화면에 없는 기업이 명단에 선다");
  assert.strictEqual(t.count.textContent, "2개 선택");

  pickAll(t, false);
  assert.deepStrictEqual(picked(t), [], "[전체 선택]을 풀어도 남아 있다");
}

// ── 4) 이미 그 명단에 있는 줄은 **고를 수가 없다** ──────────────────────────
{
  const t = build([row(1, "샘플가"), row(2, "샘플나", { inStartup: true })]);
  pickAll(t, true);
  assert.deepStrictEqual(picked(t), ["1"],
    "이미 있는 줄에 체크 칸이 서 있다 — 골라 놓고 아무 일도 안 일어난다");
}

// ── 5) 보내는 것은 **고른 번호뿐**이고, 고른 명단이 함께 간다 ───────────────
{
  const t = build([row(1, "샘플가"), row(2, "샘플나"), row(3, "샘플다")]);
  check(boxes(t)[0], true);
  check(boxes(t)[2], true);
  t.send.fire("click");
  assert.strictEqual(t.sent.length, 1, "요청이 한 번만 나가야 한다");
  assert.strictEqual(t.sent[0].url, "/api/contacts/from-consulting");
  assert.deepStrictEqual(t.sent[0].body.company_ids, [1, 3]);
  assert.strictEqual(t.sent[0].body.label, TARGET);
}

// ── 6) 확인창은 **보내면 설 이름**을 적는다 ─────────────────────────────────
//
// `기업명` 칸에는 계약일·보수율이 함께 적혀 있다. 칸 글자를 그대로 물으면
// `라마바이오 / 무료 / 3%` 라고 물어 놓고 실제로는 `라마바이오` 가 선다.
{
  const t = build([row(1, "라마바이오 / 무료 / 3%", { firm: "라마바이오" })]);
  check(boxes(t)[0], true);
  t.send.fire("click");
  assert.ok(t.asks[0].indexOf("라마바이오") >= 0, "확인창에 기업 이름이 없다");
  assert.ok(t.asks[0].indexOf("무료") < 0,
    "확인창이 `기업명` 칸 글자를 그대로 적었다 — 물어본 이름과 실제로 서는 " +
    "이름이 다르다");
  assert.ok(t.asks[0].indexOf("빠지지 않습니다") >= 0,
    "원본이 남는다는 말이 확인창에 없다 — 누른 사람이 이관으로 읽는다");
}

// ── 7) 고른 것이 없으면 요청이 안 나간다 ────────────────────────────────────
{
  const t = build([row(1, "샘플가")]);
  t.send.fire("click");
  assert.strictEqual(t.sent.length, 0, "아무것도 안 골랐는데 요청이 나갔다");
}

console.log("ok");
