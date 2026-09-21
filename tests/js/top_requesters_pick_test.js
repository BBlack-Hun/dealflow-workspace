// 「내 투자사 선호」를 몇 명까지 볼지 고르는 칸. (node tests/js/top_requesters_pick_test.js)
//
// 고를 값이 넷(10·30·50·100)에서 **여섯**(200·300 을 더했다)으로 늘면서 칩
// 단추가 드롭다운으로 바뀌었다. 칩 여섯은 390px 에서 343px 로 패널(328px)을
// 넘기고 1440px 에서 두 줄로 접혔다.
//
// 그 바뀜이 이 파일에 두 가지를 걸었다:
//
//   1) 누르는 것(`click`)이 아니라 **고르는 것**(`change`)이다. `click` 에
//      매달린 채 두면 드롭다운을 골라도 목록이 안 바뀐다. `data-n` 이 아니라
//      `select.value` 를 읽는 것도 같은 자리다.
//   2) 300 을 골라도 목록이 안 늘어나는 일이 흔해졌다 — 운영에서 IR 자료를
//      달라고 한 곳이 10곳뿐이라 100·200·300 이 전부 같은 목록을 준다. 그때
//      사용자가 의심하는 것은 자기 명단이 아니라 **이 화면**이라, "요청한
//      곳이 이게 전부" 라고 적어 줘야 한다(`#req-rank-all`).
//      다 찼을 때는 숨긴다 — 더 있을지 모르는데 "이게 전부" 라고 하면 거짓말이다.
//
// 규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **파일을 그대로
// 돌린다** (weekly_status_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "agent_badge.js");
const src = fs.readFileSync(SRC, "utf8");

// --- 서버가 그리는 것과 같은 모양 --------------------------------------------
function build(chosen) {
  const pick = D.el("select", { class: "chip-select js-top-n", id: "top-n" });
  pick.value = String(chosen);

  const countPill = D.el("span", { class: "count-pill on", id: "req-rank-count" });
  countPill.innerHTML = "<b>21</b>명";

  const hint = D.el("p", { class: "hint req-rank-all", id: "req-rank-all" },
                    [D.el("b", {})]);
  hint.hidden = false;

  const list = D.el("ol", { class: "req-rank", id: "req-rank" });

  return {
    root: D.el("div", {}, [
      D.el("h2", { class: "panel-title" },
           [countPill, D.el("span", { class: "top-pick" }, [pick])]),
      hint, list
    ]),
    pick: pick, hint: hint, list: list, countPill: countPill
  };
}

// 서버가 돌려주는 줄. `top` 을 얼마로 부르든 **요청한 곳의 수만큼만** 나온다.
function rows(n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push({ id: i + 1, name: "담당자" + i, title: "심사역", firm: "가나벤처스",
               count: 3, companies: [] });
  }
  return out;
}

// --- agent_badge.js 를 그대로 돌린다 -----------------------------------------
//
// `available` = 실제로 IR 자료를 달라고 한 곳의 수. 서버는 `top` 과 이 수 중
// **작은 쪽**만큼 돌려준다 — 그게 "300 을 눌러도 안 늘어난다" 의 정체다.
function run(dom, available) {
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const alerts = [];
  const asked = [];
  const sandbox = {
    document: document,
    history: { replaceState: function () {} },
    setInterval: function () {},
    setTimeout: setTimeout,
    alert: function (m) { alerts.push(m); },
    fetch: function (url) {
      asked.push(url);
      const top = Number(String(url).split("top=")[1]);
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ rows: rows(Math.min(top, available)) })
      });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "agent_badge.js" });
  return { alerts: alerts, asked: asked };
}

// 이 작은 DOM 은 `innerHTML` 글자에서 아이디가 붙은 태그만 요소로 세운다
// (`_dom.js`). 줄에는 아이디가 없으므로 **글자를 센다.**
function listed(dom) {
  return (String(dom.list.innerHTML).match(/<li>/g) || []).length;
}

function choose(dom, value) {
  dom.pick.value = String(value);
  dom.pick.fire("change", { target: dom.pick });
  return new Promise(function (r) { setTimeout(r, 0); });
}

(async function () {
  // 1) 고르면(누르는 것이 아니다) 그 수로 불러온다.
  {
    const dom = build(50);
    const out = run(dom, 21);
    await choose(dom, 300);
    assert.deepStrictEqual(
      out.asked, ["/api/dashboard/top-requesters?top=300"],
      "드롭다운을 골랐는데 불러오지 않았습니다 — `click` 에 매달려 있습니다");
    assert.strictEqual(listed(dom), 21);
    assert.strictEqual(dom.countPill.innerHTML, "<b>21</b>명",
      "몇 명이 걸렸는지를 안 고치면 300 으로 놓고 21명이 나온 이유를 알 수 없습니다");
  }

  // 2) 고른 수보다 적게 나왔으면 **그 까닭을 적는다.**
  //    이게 없으면 100·200·300 이 전부 같은 목록을 주는 것이 버그로 읽힌다.
  {
    const dom = build(50);
    run(dom, 10);
    await choose(dom, 300);
    assert.strictEqual(dom.hint.hidden, false,
      "300 을 골랐는데 10곳만 나왔습니다 — 왜 안 늘어나는지 화면이 말해야 합니다");
    assert.strictEqual(String(dom.hint.children[0].textContent), "10",
      "안내에 적힌 수가 실제로 걸린 수와 달라졌습니다");
  }

  // 3) 다 찼으면 숨긴다 — 더 있을지 모르는데 "이게 전부" 라고 하면 거짓말이다.
  {
    const dom = build(50);
    run(dom, 30);
    await choose(dom, 10);
    assert.strictEqual(listed(dom), 10);
    assert.strictEqual(dom.hint.hidden, true,
      "열 곳을 달라고 해서 열 곳이 나왔습니다 — 이게 전부라고 하면 거짓말입니다");
  }

  // 4) 아무 곳도 요청하지 않았으면 안내를 띄우지 않는다.
  //    그때는 목록 자리가 "아직 IR 자료 요청이 없습니다" 를 이미 말한다.
  {
    const dom = build(50);
    run(dom, 0);
    await choose(dom, 300);
    assert.strictEqual(dom.hint.hidden, true,
      "한 곳도 없는데 `0곳뿐입니다` 를 또 띄우면 같은 말이 두 번 섭니다");
  }

  console.log("top_requesters_pick_test OK");
})().catch(function (e) { console.error(e); process.exit(1); });
