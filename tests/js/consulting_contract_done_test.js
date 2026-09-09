// `계약완료여부` · `계약서 수신완료여부` 칸을 눌러 보기를 고르면 **정말
// 저장되고 필터에도 걸리는가.** 그리고 `계약관리` 는 자유 글로 열리는가.
// (node tests/js/consulting_contract_done_test.js)
//
// 이 저장소는 칸을 고쳐도 조용히 저장이 안 되는 사고를 여러 번 겪었다 —
// pydantic 스키마에 이름을 안 적어 그냥 버려지거나(라우터의 `CompanyIn`),
// `data-filter-key` 가 없어 채워 넣어도 필터 목록은 옛것 그대로거나.
// 둘 다 화면은 멀쩡해 보인다. 그래서 규칙을 옮겨 적지 않고 **consulting.js 를
// 그대로 돌려서** 눌러 보고, 나간 요청과 행에 적힌 값을 확인한다.
// (`consulting_contract_received_test.js` 와 같은 방식이다.)
//
// 여기서 막는 것은 다섯이다.
//   1. 골라 넣을 수 있는가 — 손으로 적게 두면 `무료계약완료`·`무료 계약 완료`
//      로 갈려 두 가지뿐인 칸에서 필터가 못 쓰게 된다.
//   2. 무엇이 나가는가 — **칸 이름**(`contract_done`·`contract_received`)으로
//      나가야 한다.
//   3. 고친 값이 행에 적히는가 — 안 적히면 머리글 필터가 옛 목록을 보여 준다.
//      **두 칸이 서로의 값을 덮지 않는가**까지 본다.
//   4. 빈칸(아직 안 정함)으로 되돌아올 수 있는가.
//   5. `계약관리` 는 보기 없이 **여러 줄로** 열리는가 — 자유 글 칸이다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

// 서버가 화면에 그리는 보기 그대로다(`routers/consulting.py` 의
// `CONTRACT_DONE_CHOICES` → `data-choices`). 이 파일이 말을 지어내지 않게
// 파이썬 쪽에서도 같은 값을 확인한다(`tests/test_consulting_contract_done.py`).
const DONE = ["무료계약완료", "유료계약완료"];

// --- 서버가 `관리 스타트업` 탭에 그리는 것과 같은 모양의 줄 -------------------
function row(id, done, received) {
  const mgmt = D.el("td", {
    class: "cell multi", "data-field": "management", "data-filter-key": "mgmt"
  });
  mgmt.textContent = "관리 중";
  const c = D.el("td", { class: "cell multi", "data-field": "contract_management" });
  c.textContent = "";
  const d = D.el("td", {
    class: "cell", "data-field": "contract_done",
    "data-filter-key": "done", "data-choices": DONE.join(",")
  });
  d.textContent = done;
  const r = D.el("td", {
    class: "cell", "data-field": "contract_received",
    "data-filter-key": "received", "data-choices": "O,X"
  });
  r.textContent = received;

  return D.el("tr", {
    "data-id": String(id),
    "data-search": "",
    "data-f-region": "",
    "data-f-done": done,
    "data-f-received": received,
    "data-f-mgmt": "관리 중",
    "data-contacted": "0",
    "data-contacted-folded": "0",
    "data-contacted-prev": "0"
  }, [mgmt, c, d, r]);
}

function build() {
  // 스타트업 탭이다 — `기업 관리` 는 문장이라 추려서 건다(`data-contract-sheet=0`).
  const rows = [row(1, "", ""), row(2, "무료계약완료", "X")];
  const table = D.el("table", { id: "cs-table", "data-contract-sheet": "0" }, [
    D.el("tbody", {}, rows)
  ]);
  const root = D.el("div", {}, [
    D.el("span", { class: "kpi-value", "data-kpi": "total" }),
    D.el("button", { "data-cs-filter": "" }),
    table,
    D.el("input", { id: "cs-search" }),
    D.el("p", { id: "cs-note" }),
    D.el("button", { id: "cs-add", "data-sheet": "스타트업" }),
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
    // 같이 흉내 낸다.
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
// 이 검사용 DOM 은 `textContent = ""` 이 자식을 지우지 않아서 같은 칸을 두 번
// 고치면 옛 것이 남는다 — 늘 **마지막** 것을 꺼낸다.
function open(tr, field) {
  const cell = tr.querySelector('[data-field="' + field + '"]');
  cell.fire("click", { target: cell });
  const inputs = cell.children.filter(function (c) {
    return c.tag === "input" || c.tag === "textarea";
  });
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

async function choose(tr, field, label) {
  const ui = open(tr, field);
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

  const AXES = [
    { field: "contract_done", attr: "data-f-done",
      choices: DONE, pick: "유료계약완료" },
    { field: "contract_received", attr: "data-f-received",
      choices: ["O", "X"], pick: "X" }
  ];

  for (const axis of AXES) {
    // --- 1. 골라 넣을 수 있는가 ---------------------------------------------
    const ui = open(dom.rows[0], axis.field);
    assert.deepStrictEqual(
      ui.chips.map(function (c) { return c.textContent; }),
      axis.choices.concat(["비움"]),
      axis.field + ": 보기를 골라 넣을 수 없습니다 — 손으로 적게 두면 같은 뜻이 "
      + "여러 글자로 갈립니다");

    // 빈칸인 줄에서는 `비움` 이 지금 값이다 — 빈칸도 값 하나로 서야
    // "아직 안 정했다" 가 화면에서 읽힌다.
    const blank = open(dom.rows[0], axis.field).chips.filter(function (c) {
      return c.classList.contains("on");
    });
    assert.deepStrictEqual(blank.map(function (c) { return c.textContent; }),
      ["비움"], axis.field + ": 빈칸(아직 안 정함)이 지금 값으로 안 보입니다");

    // --- 2. 무엇이 나가는가 -------------------------------------------------
    sent.length = 0;
    const picked = await choose(dom.rows[0], axis.field, axis.pick);
    const body = {};
    body[axis.field] = axis.pick;
    assert.deepStrictEqual(sent, [{
      url: "/api/consulting/1", method: "PATCH", body: body
    }], "칸 이름(`" + axis.field + "`)으로 저장되지 않습니다");
    assert.strictEqual(picked.cell.textContent, axis.pick,
      "고른 값이 칸에 안 남습니다");

    // --- 3. 고친 값이 행에 적히는가 -----------------------------------------
    assert.strictEqual(dom.rows[0].getAttribute(axis.attr), axis.pick,
      axis.attr + " 가 다시 안 적혔습니다 — 채워 넣어도 머리글 필터는 옛 목록 "
      + "그대로입니다");

    // --- 4. 빈칸으로 되돌아올 수 있는가 -------------------------------------
    sent.length = 0;
    const cleared = await choose(dom.rows[0], axis.field, "비움");
    const empty = {};
    empty[axis.field] = "";
    assert.deepStrictEqual(sent, [{
      url: "/api/consulting/1", method: "PATCH", body: empty
    }], "빈칸(아직 안 정함)으로 되돌릴 수가 없습니다");
    assert.strictEqual(cleared.cell.textContent, "", "칸이 안 비었습니다");
    assert.strictEqual(dom.rows[0].getAttribute(axis.attr), "",
      "행에는 옛 값이 남았습니다 — 필터에서 `(비어 있음)` 으로 안 걸립니다");
  }

  // **두 칸이 서로를 덮지 않는가.** 규칙을 한 자리에서 돌리므로 짝을 잘못
  // 적으면 한 칸을 고쳤을 때 다른 축의 값이 같이 바뀐다 — 화면은 멀쩡한데
  // 필터만 거짓말을 한다.
  await choose(dom.rows[1], "contract_done", "유료계약완료");
  assert.strictEqual(dom.rows[1].getAttribute("data-f-done"), "유료계약완료");
  assert.strictEqual(dom.rows[1].getAttribute("data-f-received"), "X",
    "`계약서 수신완료여부` 값이 `계약완료여부` 를 고치면서 바뀌었습니다");
  await choose(dom.rows[1], "contract_received", "O");
  assert.strictEqual(dom.rows[1].getAttribute("data-f-done"), "유료계약완료",
    "`계약완료여부` 값이 `계약서 수신완료여부` 를 고치면서 바뀌었습니다");
  assert.strictEqual(dom.rows[1].getAttribute("data-f-received"), "O");

  // --- 5. `계약관리` 는 자유 글이다 ------------------------------------------
  //
  // 보기가 없어야 하고(무엇을 담을 칸인지 정한 적이 없다), 여러 줄로 열려야
  // 한다 — 한 줄짜리 입력이면 엔터가 저장이 되어 줄을 나눌 수가 없다.
  sent.length = 0;
  const free = open(dom.rows[0], "contract_management");
  assert.strictEqual(free.chips.length, 0,
    "자유 글 칸에 고를 단추가 섰습니다 — 사람이 적을 자리가 없어집니다");
  assert.strictEqual(free.input.tag, "textarea",
    "여러 줄로 안 열립니다 — 엔터가 저장이 되어 줄을 나눌 수가 없습니다");
  free.input.value = "무료로 시작.\n유료 전환 논의 중";
  free.input.fire("blur", { target: free.input });
  await settle();
  assert.deepStrictEqual(sent, [{
    url: "/api/consulting/1", method: "PATCH",
    body: { contract_management: "무료로 시작.\n유료 전환 논의 중" }
  }], "칸 이름(`contract_management`)으로 저장되지 않습니다");
  // 필터를 안 세운 칸이라 행에 값이 새로 생기면 안 된다 — 아무 머리글도 안
  // 보는 죽은 속성이 된다.
  assert.ok(!dom.rows[0].hasAttribute("data-f-contract_management"));
  assert.ok(!dom.rows[0].hasAttribute("data-f-contract"));
  // 검색은 따라와야 한다(서버가 그리는 `data-search` 와 같은 재료다).
  assert.ok(dom.rows[0].getAttribute("data-search").indexOf("유료 전환 논의 중") >= 0,
    "검색이 새 값을 못 봅니다");

  // --- 6. 그 칸이 없는 표에는 값을 새로 만들지 않는다 ------------------------
  //
  // `계약서 수신완료여부` 는 두 탭에 서지만 나머지 탭에는 없고,
  // `계약완료여부` 는 `관리 스타트업` 탭에만 있다.
  const other = build();
  other.rows.forEach(function (tr) {
    AXES.forEach(function (axis) {
      tr.removeAttribute(axis.attr);
      tr.querySelector('[data-field="' + axis.field + '"]')
        .removeAttribute("data-field");
    });
  });
  run(other);
  const mgmt = other.rows[0].querySelector('[data-field="management"]');
  mgmt.fire("click", { target: mgmt });
  const inputs = mgmt.children.filter(function (c) {
    return c.tag === "input" || c.tag === "textarea";
  });
  const input = inputs[inputs.length - 1];
  input.value = "드랍";
  input.fire("blur", { target: input });
  await settle();
  AXES.forEach(function (axis) {
    assert.ok(!other.rows[0].hasAttribute(axis.attr),
      "그 칸이 없는 표에 `" + axis.attr + "` 를 새로 만들었습니다");
  });

  console.log("consulting_contract_done_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
