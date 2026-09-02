// `계약서 수신여부` 칸을 눌러 O/X 를 고르면 **정말 저장되고 필터에도 걸리는가.**
// (node tests/js/consulting_contract_received_test.js)
//
// 이 저장소는 칸을 고쳐도 조용히 저장이 안 되는 사고를 여러 번 겪었다 —
// pydantic 스키마에 이름을 안 적어 그냥 버려지거나(라우터의 `CompanyIn`),
// `data-filter-key` 가 없어 채워 넣어도 필터 목록은 옛것 그대로거나.
// 둘 다 화면은 멀쩡해 보인다. 그래서 규칙을 옮겨 적지 않고 **consulting.js 를
// 그대로 돌려서** 눌러 보고, 나간 요청과 행에 적힌 값을 확인한다.
//
// 여기서 막는 것은 셋이다.
//   1. 골라 넣을 수 있는가 — `O`·`o`·`ㅇ`·`○` 로 갈리면 두 가지뿐인 칸에서
//      필터가 못 쓰게 된다.
//   2. 무엇이 나가는가 — **칸 이름(`contract_received`)으로** 나가야 한다.
//   3. 고친 값이 행에 적히는가 — 안 적히면 머리글 필터가 옛 목록을 보여 준다.
//   4. **빈칸(아직 안 정함)으로 되돌아올 수 있는가** — `O`/`X` 둘뿐이면 잘못
//      누른 것을 되돌릴 길이 없다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 서버가 계약 탭에 그리는 것과 같은 모양의 줄 -----------------------------
function row(id, received) {
  const mgmt = D.el("td", {
    class: "cell", "data-field": "management", "data-filter-key": "mgmt"
  });
  mgmt.textContent = "유료";
  const cell = D.el("td", {
    class: "cell", "data-field": "contract_received",
    "data-filter-key": "received", "data-choices": "O,X"
  });
  cell.textContent = received;

  return D.el("tr", {
    "data-id": String(id),
    "data-search": "",
    "data-f-region": "",
    "data-f-received": received,
    "data-f-mgmt": "유료",
    "data-contacted": "0",
    "data-contacted-folded": "0",
    "data-contacted-prev": "0"
  }, [mgmt, cell]);
}

function build() {
  // 계약 탭이다 — `계약여부` 는 `무료`/`유료` 라 추리지 않고 그대로 건다.
  const rows = [row(1, ""), row(2, "O")];
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "1" }, [
    D.el("tbody", {}, rows)
  ]);
  const root = D.el("div", {}, [
    D.el("span", { class: "kpi-value", "data-kpi": "total" }),
    D.el("button", { "data-cs-filter": "" }),
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "월간 계약 업무현황표" }),
    D.el("button", { id: "cs-import-btn" }),
    D.el("section", { id: "cs-import" }),
    D.el("button", { id: "cs-import-close" })
  ]);
  return { root: root, rows: rows };
}

// --- consulting.js 를 그대로 돌린다 -----------------------------------------
const sent = [];

function run(dom) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const made = document.createElement;
  document.createElement = function (tag) {
    const el = made.call(document, tag);
    el.focus = function () {};
    el.setSelectionRange = function () {};
    // 브라우저에서 `input.blur()` 는 blur 이벤트를 낸다. 단추를 눌러 고르는
    // 길이 그 한 줄에 걸려 있어서(mousedown → 값 넣기 → blur → 저장) 여기서도
    // 같이 흉내 낸다. 없으면 이 검사만 다른 길로 도는 셈이 된다.
    el.blur = function () { el.fire("blur", { target: el }); };
    return el;
  };
  const sandbox = {
    document: document,
    window: { location: { reload: function () {} } },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function () { return true; },
    prompt: function () { return null; },
    fetch: function (url, opts) {
      sent.push({ url: url, method: opts.method, body: JSON.parse(opts.body) });
      return Promise.resolve({
        ok: true, json: function () { return Promise.resolve({}); }
      });
    }
  };
  sandbox.window.DealflowFilters = undefined;   // 칸 고치기만 떼어 본다
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "consulting.js" });
}

// 칸을 누르면 입력칸과 **고를 단추들**이 함께 선다.
//
// 이 검사용 DOM 은 `textContent = ""` 이 자식을 지우지 않아서(글자를 한 칸에
// 담는 아주 작은 DOM 이다) 같은 칸을 두 번 고치면 옛 것이 남는다 —
// 늘 **마지막** 것을 꺼낸다(consulting_chips_test.js 가 같은 이유로 그렇게 한다).
function open(tr) {
  const cell = tr.querySelector('[data-field="contract_received"]');
  cell.fire("click", { target: cell });
  const inputs = cell.children.filter(function (c) { return c.tag === "input"; });
  const boxes = cell.children.filter(function (c) {
    return c.classList.contains("cell-pop-choices");
  });
  const box = boxes[boxes.length - 1];
  return {
    cell: cell,
    input: inputs[inputs.length - 1],
    chips: box ? box.children : []
  };
}

function settle() { return new Promise(function (r) { setTimeout(r, 0); }); }

// 단추를 눌러 고른다. mousedown 이라야 input 의 blur 보다 먼저 잡힌다 —
// click 으로 달려 있으면 이미 편집이 끝난 뒤라 아무 일도 안 일어난다.
async function choose(tr, label) {
  const ui = open(tr);
  const chip = ui.chips.filter(function (c) { return c.textContent === label; })[0];
  assert.ok(chip, "`" + label + "` 단추가 없습니다 — 있는 것: "
    + ui.chips.map(function (c) { return c.textContent; }).join(", "));
  chip.fire("mousedown", { target: chip });
  await settle();
  return ui;
}

(async function () {
  const dom = build();
  run(dom);

  // --- 1. 골라 넣을 수 있는가 ------------------------------------------------
  const ui = open(dom.rows[0]);
  assert.deepStrictEqual(
    ui.chips.map(function (c) { return c.textContent; }), ["O", "X", "비움"],
    "`O`/`X` 를 골라 넣을 수 없습니다 — 손으로 적게 두면 `o`·`ㅇ`·`○` 로 갈립니다");

  // 지금 값이 무엇인지 보여야 한다. 2번 줄은 이미 `O` 다.
  const on = open(dom.rows[1]).chips.filter(function (c) {
    return c.classList.contains("on");
  });
  assert.deepStrictEqual(on.map(function (c) { return c.textContent; }), ["O"],
    "지금 골라 둔 값에 표시가 없습니다");

  // 빈칸인 줄에서는 `비움` 이 지금 값이다 — 빈칸도 값 하나로 서야
  // "아직 안 정했다" 가 화면에서 읽힌다.
  const blank = open(dom.rows[0]).chips.filter(function (c) {
    return c.classList.contains("on");
  });
  assert.deepStrictEqual(blank.map(function (c) { return c.textContent; }), ["비움"],
    "빈칸(아직 안 정함)이 지금 값으로 안 보입니다");

  // --- 2. 무엇이 나가는가 ---------------------------------------------------
  sent.length = 0;
  const picked = await choose(dom.rows[0], "X");
  assert.deepStrictEqual(sent, [{
    url: "/api/consulting/1", method: "PATCH", body: { contract_received: "X" }
  }], "칸 이름(`contract_received`)으로 저장되지 않습니다");
  assert.strictEqual(picked.cell.textContent, "X", "고른 값이 칸에 안 남습니다");

  // --- 3. 고친 값이 행에 적히는가 -------------------------------------------
  assert.strictEqual(
    dom.rows[0].getAttribute("data-f-received"), "X",
    "행에 다시 안 적혔습니다 — 채워 넣어도 머리글 필터는 옛 목록 그대로입니다");
  // 검색도 같이 따라와야 한다(서버가 그리는 `data-search` 와 같은 재료다).
  assert.ok(dom.rows[0].getAttribute("data-search").indexOf("x") >= 0,
    "검색이 새 값을 못 봅니다");

  // --- 4. 빈칸으로 되돌아올 수 있는가 ---------------------------------------
  sent.length = 0;
  const cleared = await choose(dom.rows[0], "비움");
  assert.deepStrictEqual(sent, [{
    url: "/api/consulting/1", method: "PATCH", body: { contract_received: "" }
  }], "빈칸(아직 안 정함)으로 되돌릴 수가 없습니다");
  assert.strictEqual(cleared.cell.textContent, "", "칸이 안 비었습니다");
  assert.strictEqual(dom.rows[0].getAttribute("data-f-received"), "",
    "행에는 옛 값이 남았습니다 — 필터에서 `(비어 있음)` 으로 안 걸립니다");

  // --- 5. 다른 탭에는 이 칸이 없다 ------------------------------------------
  //
  // 계약 탭에만 있는 칸이라, 없는 표에서 `data-f-received` 를 새로 만들면
  // 아무 머리글도 안 보는 죽은 값이 생긴다.
  const other = build();
  other.rows.forEach(function (tr) {
    tr.removeAttribute("data-f-received");
    const cell = tr.querySelector('[data-field="contract_received"]');
    cell.removeAttribute("data-field");
  });
  run(other);
  const mgmt = other.rows[0].querySelector('[data-field="management"]');
  mgmt.fire("click", { target: mgmt });
  const inputs = mgmt.children.filter(function (c) { return c.tag === "input"; });
  const input = inputs[inputs.length - 1];
  input.value = "무료";
  input.fire("blur", { target: input });
  await settle();
  assert.ok(!other.rows[0].hasAttribute("data-f-received"),
    "그 칸이 없는 표에 `data-f-received` 를 새로 만들었습니다");

  console.log("consulting_contract_received_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
