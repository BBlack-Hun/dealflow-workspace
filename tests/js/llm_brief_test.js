// LLM 에 물어보기 패널을 실제로 돌려 본다. (node tests/js/llm_brief_test.js)
//
// 이 패널의 값어치는 두 가지에 달려 있다.
//
//   ① [화면에서 보기] 가 **내려받기 링크와 같은 주소**를 부르는가.
//      스크립트가 주소를 따로 적어 두면, 주소를 고쳤을 때 링크만 고쳐지고
//      화면은 옛 주소를 부른다 — 이 저장소가 반복해 당한 사고다.
//   ② 붙여 넣은 답에서 번호를 뽑아 **이름으로 그려 주는가**.
//      이 길이 없으면 번호로 내보내는 기능은 반쪽이다.
//
// 둘 다 브라우저 안에서 일어나는 일이라 `<script>` 태그가 그려지는지만 보는
// 검사로는 못 잡는다. 그래서 파일을 vm 으로 **그대로 실행**한다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "llm_brief.js");
const src = fs.readFileSync(SRC, "utf8");

// 가상의 자료다 — 저장소가 공개라 실제 이름·회사를 두지 않는다.
const BRIEF = {
  generated_at: "2026-09-01T09:00:00+09:00",
  scope: "본인 담당",
  amount_unit: "백만원",
  investors: [{ id: "V-31", sectors: "AI", room_open: true }],
  companies: [{ id: "C-7", name: "가상바이오", introducible: true }]
};

function build() {
  const nodes = {};
  const root = D.makeEl("div");
  function add(tag, id, attrs) {
    const node = D.el(tag, Object.assign({ id: id }, attrs || {}));
    root.appendChild(node);
    nodes[id] = node;
    return node;
  }
  add("button", "llm-toggle");
  add("div", "llm-body").hidden = true;
  add("a", "llm-download", { href: "/api/llm-brief.json" });
  add("button", "llm-show");
  add("button", "llm-copy").hidden = true;
  add("pre", "llm-out").hidden = true;
  add("span", "llm-state");
  add("textarea", "llm-answer");
  add("button", "llm-resolve");
  add("span", "llm-found-state");
  add("div", "llm-found");
  return { root: root, nodes: nodes };
}

// 파일을 돌리고, 오간 요청을 남긴다.
function run(setup, options) {
  D.resetHandlers();
  const dom = build();
  if (setup) setup(dom);
  options = options || {};

  const calls = [];
  function fetchStub(url, options) {
    calls.push({ url: url, options: options || {} });
    const body = url.indexOf("resolve") >= 0
      ? JSON.stringify(fetchStub.resolveAnswer)
      : JSON.stringify(BRIEF, null, 2);
    return Promise.resolve({
      ok: true,
      text: function () { return Promise.resolve(body); },
      json: function () { return Promise.resolve(JSON.parse(body)); }
    });
  }
  fetchStub.resolveAnswer = { investors: [], companies: [] };

  // 클립보드가 없을 때 대신 **골라 주는** 길까지 본다 — 눌렀는데 아무 일도
  // 안 나면 복사된 줄 알고 빈 것을 붙여 넣는다.
  const picked = [];
  const document = D.makeDocument(dom.root);
  document.createRange = function () {
    return { selectNodeContents: function (node) { picked.push(node); } };
  };

  const context = {
    document: document,
    fetch: fetchStub,
    navigator: options.navigator || {},
    console: console,
    JSON: JSON,
    Promise: Promise
  };
  context.window = context;
  context.getSelection = function () {
    return { removeAllRanges: function () {}, addRange: function () {} };
  };
  vm.createContext(context);
  vm.runInContext(src, context, { filename: "llm_brief.js" });

  return { dom: dom, nodes: dom.nodes, calls: calls, fetch: fetchStub,
           picked: picked };
}

// 프라미스 사슬이 끝날 때까지 기다린다.
function settle() {
  return new Promise(function (done) { setImmediate(done); });
}

async function main() {
  // ── 접었다 펴기 ──────────────────────────────────────────────────────────
  {
    const app = run();
    assert.strictEqual(app.nodes["llm-body"].hidden, true,
      "매주 한 번 쓰는 자리라 기본은 접혀 있어야 한다");
    app.nodes["llm-toggle"].fire("click");
    assert.strictEqual(app.nodes["llm-body"].hidden, false);
    assert.strictEqual(app.nodes["llm-toggle"].getAttribute("aria-expanded"), "true");
    app.nodes["llm-toggle"].fire("click");
    assert.strictEqual(app.nodes["llm-body"].hidden, true);
  }

  // ── ① 화면에서 보기 = 내려받기 링크와 같은 주소 ──────────────────────────
  {
    const app = run();
    app.nodes["llm-show"].fire("click");
    await settle();
    assert.deepStrictEqual(app.calls.map(function (c) { return c.url; }),
      ["/api/llm-brief.json"]);
    assert.strictEqual(app.nodes["llm-out"].hidden, false,
      "꺼낸 자료가 화면에 보여야 내보내기 전에 눈으로 훑을 수 있다");
    assert.ok(app.nodes["llm-out"].textContent.indexOf("V-31") >= 0);
    assert.strictEqual(app.nodes["llm-copy"].hidden, false);
    // 몇 건인지 먼저 말해 준다 — 빈 자료를 그대로 붙여 넣는 일이 없게.
    assert.ok(app.nodes["llm-state"].textContent.indexOf("투자사 1곳") >= 0,
      app.nodes["llm-state"].textContent);
    assert.ok(app.nodes["llm-state"].textContent.indexOf("본인 담당") >= 0);
  }
  {
    // 링크의 주소를 바꾸면 [화면에서 보기] 도 그리로 따라가야 한다.
    // 스크립트가 주소를 따로 들고 있으면 여기서 갈린다.
    const app = run(function (dom) {
      dom.nodes["llm-download"].setAttribute("href", "/api/llm-brief.json?scope=team");
    });
    app.nodes["llm-show"].fire("click");
    await settle();
    assert.deepStrictEqual(app.calls[0].url, "/api/llm-brief.json?scope=team",
      "스크립트가 주소를 따로 적어 두면 링크만 고쳐졌을 때 둘이 갈린다");
  }

  // ── ② 번호를 이름으로 ────────────────────────────────────────────────────
  {
    const app = run();
    app.fetch.resolveAnswer = {
      investors: [
        { id: "V-31", found: true, name: "홍길동", firm: "가나벤처스",
          href: "/contacts?contact=31" },
        { id: "V-99", found: false, name: "", firm: "", href: "" }
      ],
      companies: [{ id: "C-7", found: true, name: "가상바이오",
                    href: "/companies?q=%EA%B0%80%EC%83%81%EB%B0%94%EC%9D%B4%EC%98%A4" }]
    };
    app.nodes["llm-answer"].value = "V-31 님께 C-7 을. V-99 는 모르겠습니다.";
    app.nodes["llm-resolve"].fire("click");
    await settle();

    assert.strictEqual(app.calls.length, 1);
    assert.strictEqual(app.calls[0].url, "/api/llm-brief/resolve");
    assert.strictEqual(app.calls[0].options.method, "POST");
    // 답을 **통째로** 보낸다 — 번호만 골라 적게 하면 옮기다 틀린다.
    assert.deepStrictEqual(JSON.parse(app.calls[0].options.body),
      { text: "V-31 님께 C-7 을. V-99 는 모르겠습니다." });

    const rows = app.nodes["llm-found"].children;
    assert.strictEqual(rows.length, 3, "투자사 둘 + 기업 하나");
    assert.strictEqual(rows[0].children[0].textContent, "V-31");
    assert.strictEqual(rows[0].children[1].tag, "a");
    // 브라우저에서는 `a.href = …` 가 곧 주소다.
    assert.strictEqual(rows[0].children[1].href, "/contacts?contact=31");
    assert.strictEqual(rows[0].children[1].textContent, "홍길동 · 가나벤처스");
    // 못 찾은 번호도 **지우지 않고 남긴다** — 조용히 빠지면 다섯을 넣고
    // 셋만 뜬 것을 눈치채지 못한다.
    assert.ok(rows[1].classList.contains("missing"));
    assert.strictEqual(rows[1].children[0].textContent, "V-99");
    assert.strictEqual(rows[1].children[1].tag, "span");
    assert.ok(app.nodes["llm-found-state"].textContent.indexOf("1개는 내 담당에 없습니다") >= 0,
      app.nodes["llm-found-state"].textContent);
    assert.strictEqual(rows[2].children[1].textContent, "가상바이오");
    assert.ok(rows[2].children[1].href.indexOf("/companies?q=") === 0);
  }
  {
    // 번호가 하나도 없으면 **왜 없는지** 말해 준다. 맨숫자는 일부러 안 읽기
    // 때문에, 그것을 모르면 붙여 넣기가 잘못된 줄 안다.
    const app = run();
    app.nodes["llm-answer"].value = "3곳을 30억 규모로 추천합니다";
    app.nodes["llm-resolve"].fire("click");
    await settle();
    assert.ok(app.nodes["llm-found-state"].textContent.indexOf("V-31 · C-7") >= 0,
      app.nodes["llm-found-state"].textContent);
  }
  {
    // 빈 채로 누르면 부르지 않는다.
    const app = run();
    app.nodes["llm-resolve"].fire("click");
    await settle();
    assert.strictEqual(app.calls.length, 0);
    assert.ok(app.nodes["llm-found-state"].textContent.indexOf("붙여 넣어") >= 0);
  }

  // ── 복사 ─────────────────────────────────────────────────────────────────
  {
    const copied = [];
    const app = run(null, { navigator: { clipboard: { writeText: function (t) {
      copied.push(t);
      return Promise.resolve();
    } } } });
    app.nodes["llm-show"].fire("click");
    await settle();
    app.nodes["llm-copy"].fire("click");
    await settle();
    assert.strictEqual(copied.length, 1);
    assert.ok(copied[0].indexOf("V-31") >= 0, "화면에 보이는 그것을 복사해야 한다");
    assert.ok(app.nodes["llm-state"].textContent.indexOf("복사") >= 0);
  }
  {
    // `navigator.clipboard` 는 http 로 열었거나 권한이 없으면 아예 없다.
    // 그때 조용히 실패하면 복사된 줄 알고 빈 것을 붙여 넣는다 — 대신 골라 준다.
    const app = run();
    app.nodes["llm-show"].fire("click");
    await settle();
    app.nodes["llm-copy"].fire("click");
    await settle();
    assert.deepStrictEqual(app.picked, [app.nodes["llm-out"]]);
    assert.ok(app.nodes["llm-state"].textContent.indexOf("골라") >= 0,
      app.nodes["llm-state"].textContent);
  }

  console.log("llm_brief_test: 통과");
}

main().catch(function (err) {
  console.error(err && err.stack || err);
  process.exit(1);
});
