// `카톡 연결 여부` 칸을 눌러 `O`/`X` 를 고르면 **정말 저장되고 필터에도
// 걸리는가.**
// (node tests/js/consulting_kakao_joined_test.js)
//
// 규칙을 여기 옮겨 적지 않고 **consulting.js 를 그대로 돌린다** —
// `consulting_contract_done_test.js` 와 같은 방식이다. 이 저장소는 칸을
// 고쳐도 조용히 저장이 안 되는 사고를 여러 번 겪었고(라우터의 `CompanyIn` 에
// 이름을 안 적으면 pydantic 이 그냥 버린다, `data-filter-key` 가 없으면
// 채워 넣어도 필터는 옛 목록 그대로다) 둘 다 화면은 멀쩡해 보인다.
//
// 여기서 막는 것은 넷이다.
//   1. 골라 넣을 수 있는가 — 손으로 적게 두면 `O`·`o`·`ㅇ`·`○` 로 갈려 두
//      가지뿐인 칸에서 머리글 필터가 못 쓰게 된다.
//   2. 무엇이 나가는가 — **칸 이름(`kakao_joined`)으로** 나가야 한다.
//   3. 고친 값이 행에 적히는가(`data-f-joined`), 그리고 **옆의 `O`/`X` 칸을
//      덮지 않는가** — `계약서 수신완료여부` 와 보기가 같아서 짝을 잘못 적으면
//      한 칸을 고쳤을 때 다른 칸의 필터 값이 같이 바뀐다.
//   4. 빈칸(아직 안 정함)으로 되돌아올 수 있는가.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "consulting.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 서버가 `관리 스타트업` 탭에 그리는 것과 같은 모양의 줄 -------------------
function row(id, joined, received) {
  const mgmt = D.el("td", {
    class: "cell multi", "data-field": "management", "data-filter-key": "mgmt"
  });
  mgmt.textContent = "관리 중";
  // 보기가 같은 `O`/`X` 칸을 나란히 세운다 — 둘이 서로를 덮지 않는지 보려는
  // 것이다. 칸 이름과 필터 키가 다른 것도 화면과 같다(`consulting.html`).
  const r = D.el("td", {
    class: "cell", "data-field": "contract_received",
    "data-filter-key": "received", "data-choices": "O,X"
  });
  r.textContent = received;
  const k = D.el("td", {
    class: "cell", "data-field": "kakao_joined",
    "data-filter-key": "joined", "data-choices": "O,X"
  });
  k.textContent = joined;

  return D.el("tr", {
    "data-id": String(id),
    "data-search": "",
    "data-f-region": "",
    "data-f-received": received,
    "data-f-joined": joined,
    "data-f-mgmt": "관리 중",
    "data-contacted": "0",
    "data-contacted-folded": "0",
    "data-contacted-prev": "0"
  }, [mgmt, r, k]);
}

function build() {
  const rows = [row(1, "", ""), row(2, "", "X")];
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
    // 단추를 눌러 고르는 길이 blur 한 줄에 걸려 있다
    // (mousedown → 값 넣기 → blur → 저장).
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

  // --- 1. 골라 넣을 수 있는가 -------------------------------------------------
  const ui = open(dom.rows[0], "kakao_joined");
  assert.deepStrictEqual(
    ui.chips.map(function (c) { return c.textContent; }), ["O", "X", "비움"],
    "보기를 골라 넣을 수 없습니다 — 손으로 적게 두면 같은 뜻이 "
    + "`O`·`o`·`ㅇ`·`○` 로 갈립니다");
  // 한 줄짜리 입력이어야 한다 — 긴 글 표시(`multi`)가 붙으면 두 글자만 서야
  // 할 자리에 줄바꿈이 들어간다.
  assert.strictEqual(ui.input.tag, "input",
    "고르는 칸이 여러 줄(textarea)로 열립니다");
  // 빈칸인 줄에서는 `비움` 이 지금 값이다.
  assert.deepStrictEqual(
    open(dom.rows[0], "kakao_joined").chips
      .filter(function (c) { return c.classList.contains("on"); })
      .map(function (c) { return c.textContent; }),
    ["비움"], "빈칸(아직 안 정함)이 지금 값으로 안 보입니다");

  // --- 2. 무엇이 나가는가 -----------------------------------------------------
  sent.length = 0;
  const picked = await choose(dom.rows[0], "kakao_joined", "O");
  assert.deepStrictEqual(sent, [{
    url: "/api/consulting/1", method: "PATCH", body: { kakao_joined: "O" }
  }], "칸 이름(`kakao_joined`)으로 저장되지 않습니다");
  assert.strictEqual(picked.cell.textContent, "O", "고른 값이 칸에 안 남습니다");

  // --- 3. 고친 값이 행에 적히는가 ---------------------------------------------
  assert.strictEqual(dom.rows[0].getAttribute("data-f-joined"), "O",
    "data-f-joined 가 다시 안 적혔습니다 — 채워 넣어도 머리글 필터는 옛 목록 "
    + "그대로입니다");
  // 검색에도 그 자리에서 따라붙는다(`refreshRowFlags` 가 `td.cell` 을 이어
  // 붙인다) — 서버가 그리는 `data-search` 와 같아야 새로고침 전후가 안 갈린다.
  assert.ok(dom.rows[0].getAttribute("data-search").indexOf("o") >= 0,
    "고친 값이 검색에 안 실립니다");

  // --- 3-b. 옆의 같은 `O`/`X` 칸을 덮지 않는가 --------------------------------
  await choose(dom.rows[1], "kakao_joined", "O");
  assert.strictEqual(dom.rows[1].getAttribute("data-f-joined"), "O");
  assert.strictEqual(dom.rows[1].getAttribute("data-f-received"), "X",
    "`계약서 수신완료여부` 값이 `카톡 연결 여부` 를 고치면서 바뀌었습니다");
  await choose(dom.rows[1], "contract_received", "O");
  assert.strictEqual(dom.rows[1].getAttribute("data-f-joined"), "O",
    "`카톡 연결 여부` 값이 `계약서 수신완료여부` 를 고치면서 바뀌었습니다");

  // --- 4. 빈칸으로 되돌아올 수 있는가 -----------------------------------------
  sent.length = 0;
  const cleared = await choose(dom.rows[0], "kakao_joined", "비움");
  assert.deepStrictEqual(sent, [{
    url: "/api/consulting/1", method: "PATCH", body: { kakao_joined: "" }
  }], "빈칸(아직 안 정함)으로 되돌릴 수가 없습니다");
  assert.strictEqual(cleared.cell.textContent, "", "칸이 안 비었습니다");
  assert.strictEqual(dom.rows[0].getAttribute("data-f-joined"), "",
    "행에는 옛 값이 남았습니다 — 필터에서 `(비어 있음)` 으로 안 걸립니다");

  // --- 5. 그 칸이 없는 표에는 값을 새로 만들지 않는다 --------------------------
  //
  // 이 칸은 `관리 스타트업` 탭에만 선다. 없는 탭에서 아무 칸이나 고칠 때
  // `data-f-joined` 를 새로 만들면 아무 머리글도 안 보는 죽은 값이 된다.
  const other = build();
  other.rows.forEach(function (tr) {
    tr.removeAttribute("data-f-joined");
    tr.querySelector('[data-field="kakao_joined"]').removeAttribute("data-field");
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
  assert.ok(!other.rows[0].hasAttribute("data-f-joined"),
    "그 칸이 없는 표에 `data-f-joined` 를 새로 만들었습니다");

  console.log("consulting_kakao_joined_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
