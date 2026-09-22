// 기업 **강제 삭제** — 잘못 누르기 어려운가. (node tests/js/company_force_delete_test.js)
//
// 자료가 정말로 없어지는 길이다. 파이썬으로는 잴 수 없는 자리가 넷이다.
//
//   1. **딸린 것이 없으면 강제 상자가 아예 안 뜬다.** 평범한 [삭제] 로
//      지워지는 기업까지 이름을 적게 하면, 사람은 곧 그 칸을 기계적으로
//      채우게 되고 그 순간 확인이 확인이 아니게 된다.
//   2. **무엇이 같이 지워지는지 숫자로 보여 준다.** 갈래 이름만 늘어놓으면
//      손댈 수 없는 이력 뭉치인지 한 건짜리인지 판단이 안 선다.
//   3. **이름을 글자 그대로 적기 전에는 단추가 안 열린다.**
//   4. **다른 기업으로 넘어가면 상자가 접힌다.** 안 접히면 앞 기업을 보고 연
//      상자가 뒤 기업 이름을 받는다 — 지우려던 것과 지워지는 것이 갈린다.
//
// 규칙을 옮겨 적지 않고 companies.js 를 그대로 돌린다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const src = fs.readFileSync(path.join(SRC, "companies.js"), "utf8");
const MODAL = fs.readFileSync(path.join(SRC, "panel_modal.js"), "utf8");

// 서버가 실제로 주는 모양 그대로(`routers/companies.py` 의 `delete_plan`).
const LABELS = {
  sends: "발송 이력", ir_requests: "IR 요청", meetings: "미팅",
  batches: "발송 회차에 실린 줄", queued: "예약에 실린 줄",
  backups: "한 줄 소개 되돌리기 버퍼"
};
const 마바 = { id: 1, name: "샘플마바에너지", one_liner: "", introducible: true };
const 다라 = { id: 2, name: "샘플다라소재", one_liner: "", introducible: true };

const 걸린판 = {
  id: 1, name: "샘플마바에너지", labels: LABELS,
  counts: { sends: 4, ir_requests: 2, meetings: 1, batches: 3, queued: 1, backups: 0 },
  detached: 7, removed: 4, live_queue: 1, by_name: 5,
  blocks: ["발송 이력 4건", "IR 요청 2건", "미팅 1건", "발송 회차에 실린 줄 3건"]
};
const 빈판 = {
  id: 2, name: "샘플다라소재", labels: LABELS,
  counts: { sends: 0, ir_requests: 0, meetings: 0, batches: 0, queued: 0, backups: 0 },
  detached: 0, removed: 0, live_queue: 0, by_name: 0, blocks: []
};

// --- 템플릿의 [수정] 패널 + 강제 삭제 상자와 같은 뼈대만 세운다 --------------
function build() {
  function editBtn(id) {
    const b = D.el("button", { class: "linkbtn js-co-edit" });
    return D.el("tr", { "data-id": String(id), "data-search": "" },
                [D.el("td", { class: "rowno muted" }), D.el("td", {}, [b])]);
  }
  const rows = [editBtn(1), editBtn(2)];
  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
                     [D.el("tbody", {}, rows)]);

  const plan = D.el("ul", { id: "co-force-plan" });
  const force = D.el("div", { id: "co-force", class: "force-del" }, [plan]);
  force.hidden = true;
  const typed = D.el("input", { id: "co-force-name" });
  const go = D.el("button", { id: "co-force-go" });
  go.disabled = true;

  const root = D.el("div", {}, [
    table,
    D.el("input", { id: "co-search" }),
    D.el("p", { id: "co-note" }),
    D.el("p", { id: "co-status" }),
    D.el("aside", { id: "co-panel" }),
    D.el("div", { id: "co-backdrop" }),
    D.el("h2", { id: "co-title" }),
    D.el("button", { id: "co-add" }),
    D.el("button", { id: "co-close" }),
    D.el("button", { id: "co-cancel" }),
    D.el("button", { id: "co-save" }),
    D.el("button", { id: "co-delete" }),
    D.el("input", { id: "f-name" }),
    D.el("textarea", { id: "f-one_liner" }),
    D.el("input", { id: "f-is_top_deal" }),
    force, plan, typed, go,
    D.el("button", { id: "co-force-cancel" })
  ]);
  return { root: root, rows: rows, force: force, plan: plan, typed: typed, go: go };
}

// --- companies.js 를 그대로 돌린다 -------------------------------------------
let calls = [];
let asked = null;          // confirm() 에 뜬 글자

function run(dom, plans) {
  D.resetHandlers();
  calls = [];
  asked = null;
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: { location: { reload: function () {} }, DealflowFilters: undefined },
    setTimeout: setTimeout,
    alert: function () {},
    confirm: function (text) { asked = text; return true; },
    fetch: function (url, opts) {
      const method = (opts && opts.method) || "GET";
      calls.push({ url: url, method: method, body: opts && opts.body });
      let body = {};
      let m = /\/api\/companies\/(\d+)\/delete-plan$/.exec(url);
      if (m) body = plans[m[1]];
      else if (/\/force-delete$/.test(url)) body = { deleted: 1 };
      else if ((m = /\/api\/companies\/(\d+)$/.exec(url)) && method === "GET") {
        body = m[1] === "1" ? 마바 : 다라;
      }
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve(body); } });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(MODAL, sandbox, { filename: "panel_modal.js" });
  vm.runInContext(src, sandbox, { filename: "companies.js" });
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });

async function openRow(dom, at) {
  dom.rows[at].querySelector("button.js-co-edit").fire("click");
  await flush();
}

async function main() {
  const plans = { 1: 걸린판, 2: 빈판 };

  // ── 1. 딸린 것이 없으면 강제 상자가 안 뜬다 — 평범한 확인창으로 지운다 ──
  {
    const dom = build();
    run(dom, plans);
    await openRow(dom, 1);                       // 샘플다라소재(빈판)
    dom.root.querySelector("#co-delete").fire("click");
    await flush();

    assert.strictEqual(dom.force.hidden, true,
      "딸린 것이 없는데 강제 삭제 상자가 떴습니다 ★ 확인이 기계적인 절차가 됩니다");
    assert.ok(asked && asked.indexOf("샘플다라소재") >= 0,
      "확인창이 무엇을 지우는지 이름을 대지 않습니다");
    const del = calls.filter(function (c) { return c.method === "DELETE"; });
    assert.strictEqual(del.length, 1, "평범한 삭제가 안 나갔습니다");
    assert.strictEqual(del[0].url, "/api/companies/2");
  }

  // ── 2. 걸린 것이 있으면 상자가 열리고 **숫자로** 말한다 ─────────────────
  {
    const dom = build();
    run(dom, plans);
    await openRow(dom, 0);                       // 샘플마바에너지(걸린판)
    dom.root.querySelector("#co-delete").fire("click");
    await flush();

    assert.strictEqual(dom.force.hidden, false, "걸린 것이 있는데 상자가 안 열렸습니다");
    assert.strictEqual(
      calls.filter(function (c) { return c.method === "DELETE"; }).length, 0,
      "막힐 것을 알면서 삭제 요청을 던졌습니다");

    const text = dom.plan.innerHTML;
    // 연결만 끊는 것 / 줄째 지우는 것을 **갈라서** 적는다.
    assert.ok(/발송 이력 4건/.test(text) && /IR 요청 2건/.test(text) && /미팅 1건/.test(text),
      "연결만 끊기는 것이 몇 건인지 안 적혀 있습니다: " + text);
    assert.ok(/연결만 끊깁니다/.test(text), "남는 것인지 사라지는 것인지 안 말합니다");
    assert.ok(/발송 회차에 실린 줄 3건/.test(text) && /줄째 함께 지워집니다/.test(text),
      "줄째 지워지는 것이 몇 건인지 안 적혀 있습니다: " + text);
    // 아직 안 나간 예약 — 세 곳짜리 회차가 말없이 두 곳이 되어 나간다.
    assert.ok(/예약/.test(text), "대기 중인 예약에 들어 있다는 말이 없습니다");
    // 이름으로만 붙는 시트 이력.
    assert.ok(/5건/.test(text), "이름으로 붙은 시트 이력 수가 없습니다");
  }

  // ── 3. 이름을 글자 그대로 적기 전에는 단추가 안 열린다 ──────────────────
  {
    const dom = build();
    run(dom, plans);
    await openRow(dom, 0);
    dom.root.querySelector("#co-delete").fire("click");
    await flush();

    assert.strictEqual(dom.go.disabled, true, "열자마자 단추가 눌립니다");

    dom.typed.value = "샘플마바";                 // 앞부분만
    dom.typed.fire("input");
    assert.strictEqual(dom.go.disabled, true, "이름이 다른데 단추가 열렸습니다");

    dom.typed.value = "샘플마바에너지주식회사";     // 더 긴 이름
    dom.typed.fire("input");
    assert.strictEqual(dom.go.disabled, true, "이름이 다른데 단추가 열렸습니다");

    dom.typed.value = "  샘플마바에너지 ";          // 긁어 붙이면 공백이 딸려 온다
    dom.typed.fire("input");
    assert.strictEqual(dom.go.disabled, false, "이름이 맞는데 단추가 안 열립니다");

    dom.go.fire("click");
    await flush();
    const post = calls.filter(function (c) { return c.method === "POST"; });
    assert.strictEqual(post.length, 1, "강제 삭제 요청이 안 나갔습니다");
    assert.strictEqual(post[0].url, "/api/companies/1/force-delete");
    assert.deepStrictEqual(JSON.parse(post[0].body), { confirm_name: "샘플마바에너지" });
  }

  // ── 4. 다른 기업으로 넘어가면 상자가 접힌다 ────────────────────────────
  //
  // 안 접히면 앞 기업을 보고 연 상자가 **뒤 기업 이름**을 받는다.
  {
    const dom = build();
    run(dom, plans);
    await openRow(dom, 0);
    dom.root.querySelector("#co-delete").fire("click");
    await flush();
    dom.typed.value = "샘플마바에너지";
    dom.typed.fire("input");
    assert.strictEqual(dom.go.disabled, false);

    await openRow(dom, 1);                       // 다른 기업을 연다
    assert.strictEqual(dom.force.hidden, true, "상자가 그대로 열려 있습니다");
    assert.strictEqual(dom.typed.value, "", "앞 기업 이름이 칸에 남아 있습니다");
    assert.strictEqual(dom.go.disabled, true, "단추가 열린 채로 넘어갔습니다");
  }

  // ── 5. [그만두기] 로 접으면 적던 것도 지워진다 ──────────────────────────
  {
    const dom = build();
    run(dom, plans);
    await openRow(dom, 0);
    dom.root.querySelector("#co-delete").fire("click");
    await flush();
    dom.typed.value = "샘플마바에너지";
    dom.typed.fire("input");
    dom.root.querySelector("#co-force-cancel").fire("click");

    assert.strictEqual(dom.force.hidden, true, "상자가 안 접혔습니다");
    assert.strictEqual(dom.typed.value, "");
    assert.strictEqual(dom.go.disabled, true);
  }

  console.log("company_force_delete_test OK");
}

main().catch(function (e) { console.error(e); process.exit(1); });
