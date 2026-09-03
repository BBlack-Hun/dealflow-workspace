// [수정] 창의 칸이 **실제로 저장 요청에 실리는가.**
// (node tests/js/company_edit_fields_test.js)
//
// 이 저장소가 겪은 사고를 못 박는 검사다. 창은 템플릿(`companies.html`)에
// 세우고 저장은 스크립트(`companies.js`)의 `FIELDS` 를 지나는데, **한쪽만
// 고치면 아무 표시 없이 저장이 안 된다** — 칸은 화면에 버젓이 있고, 고쳐
// 넣고, [저장]을 눌러도 200 이 온다. 그런데 새로고침하면 옛 값이다.
//
// 파이썬으로는 두 파일에 이름이 있는지까지만 볼 수 있다. 여기서는 **창을 열고
// [저장]을 누르는 흐름 그대로** 돌려서, 값이 정말 요청 몸통에 실리는지 본다.
//
// 특히 보는 것:
//   1. 템플릿의 `id="f-…"` 하나하나가 **되읽기(fill)→저장(collect)** 을 지나
//      글자 그대로 살아 나오는가.
//   2. 연도별 매출이 **적힌 그대로** 나가는가 — `1,224백만원` 이 숫자로
//      바뀌면 100배가 틀어진 채 딜소개 문구에 실려 나간다.
//   3. 서버가 그 칸을 **안 실어 보냈을 때**(응답에 키가 없을 때) 창이 그것을
//      빈 값으로 덮어 보내지 않는가 — 창은 표와 달리 모든 칸을 한 번에
//      보내므로, 이게 곧 "열어 본 것만으로 지워진다" 이다.
//
// 값은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");
const ROOT = path.join(__dirname, "..", "..");
const HTML = fs.readFileSync(
  path.join(ROOT, "app", "templates", "companies.html"), "utf8");
const src = fs.readFileSync(
  path.join(ROOT, "app", "static", "js", "companies.js"), "utf8");

// 창에 실제로 세워진 칸. **템플릿에서 읽는다** — 여기에 손으로 한 벌 더 적으면
// 칸이 늘 때 고칠 곳이 하나 더 생기고, 그 순간 이 검사가 막으려던 그 사고가
// 검사 안에서 난다.
const SHOWN = [];
HTML.replace(/id="f-([a-z_0-9]+)"/g, function (_all, f) {
  if (SHOWN.indexOf(f) < 0) SHOWN.push(f);
  return _all;
});

// 저장 요청에 실리면 **안 되는** 칸.
//   desc_backup   합치기 전 값(0051) — 읽기 전용이다. 실리면 되살리려고
//                 열어 본 것만으로 백업이 덮인다.
//   is_top_deal   체크박스라 `collect()` 가 따로 싣는다(불리언).
const NOT_SENT = ["desc_backup", "is_top_deal"];
const FIELDS = SHOWN.filter((f) => NOT_SENT.indexOf(f) < 0);

// 억으로 보여 주고 백만원으로 보내는 칸(companies.js 의 `EOK_FIELDS`).
// 이 넷만 글자가 아니라 숫자로 오간다.
const EOK = ["revenue_recent", "funding_total", "raise_target", "pre_value"];

// `<select>` 인 칸은 아무 글자나 못 고른다 — 화면에 있는 값으로만 잰다.
const CHOICES = {
  contract_status: "paid",
  contract_received: "O",
  summary_status: "done"
};

// 되읽기로 창에 채워 넣을 값. **칸마다 다른 글자**여야 한다 — 같은 글자면
// 이름이 뒤바뀌어 실려도 통과한다.
//
// 연도별 매출·설립년도·수신일에는 **실데이터에 실제로 있는 모양**을 넣는다.
// 숫자 칸이나 날짜 칸으로 바꿔 둔 순간 브라우저가 못 읽어 빈 값이 되는데,
// 그 고장이 바로 여기서 걸린다.
const SAMPLE = {
  revenue_2022: "8.2억",
  revenue_2023: "1,224백만원",
  revenue_2024: "150억 ~ 200억",
  revenue_2025: "4월 기준 3억",
  founded_year: "2015년",
  received_at: "날짜 미정",
  contact_phone: "010-0000-5678",
  contact_email: "sample@example.com"
};

function valueFor(field) {
  if (CHOICES[field]) return CHOICES[field];
  if (SAMPLE[field]) return SAMPLE[field];
  return "샘플 " + field;
}

// --- 템플릿에 세워진 칸 그대로 DOM 을 만든다 ---------------------------------
function build() {
  const editBtn = D.el("button", { class: "linkbtn js-co-edit" });
  const row = D.el("tr", { "data-id": "1", "data-search": "" },
                   [D.el("td", { class: "rowno muted" }), D.el("td", {}, [editBtn])]);
  const table = D.el("table", { id: "co-table", "data-inline-url": "/api/companies" },
                     [D.el("tbody", {}, [row])]);

  const inputs = {};
  SHOWN.forEach(function (f) {
    const node = D.el("input", { id: "f-" + f });
    node.focus = function () {};          // 이 DOM 에는 초점이 없다
    inputs[f] = node;
  });

  const kids = [
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
    D.el("div", { id: "f-desc_backup-box" }, [D.el("div", { id: "f-desc_backup" })]),
    D.el("div", { id: "f-one_liner-note" }, [
      D.el("span", { id: "one-liner-state" }),
      D.el("button", { id: "one-liner-auto" })
    ])
  ].concat(SHOWN.map(function (f) { return inputs[f]; }));

  return { root: D.el("div", {}, kids), row: row, inputs: inputs };
}

let sent = null;

function run(dom, payload) {
  D.resetHandlers();
  sent = null;
  const sandbox = {
    document: D.makeDocument(dom.root),
    window: { location: { reload: function () {} }, DealflowFilters: undefined },
    setTimeout: setTimeout,
    alert: function (m) { throw new Error("alert: " + m); },
    confirm: function () { return true; },
    fetch: function (url, opts) {
      if (opts && opts.body) sent = JSON.parse(opts.body);
      const body = opts ? {} : payload;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "companies.js" });
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function openAndSave(payload) {
  const dom = build();
  run(dom, payload);
  dom.row.querySelector("button.js-co-edit").fire("click");
  await flush();
  dom.root.querySelector("#co-save").fire("click");
  await flush();
  return dom;
}

async function main() {
  // ── 0. 창과 스크립트가 **한 벌**인가 ──────────────────────────────────
  //
  // 여기서 갈리면 아래 검사들이 무엇을 재고 있는지도 알 수 없다.
  const listed = /var FIELDS = \[(.*?)\];/s.exec(src);
  assert.ok(listed, "companies.js 에서 FIELDS 를 못 찾았습니다");
  const inScript = listed[1].match(/"([a-z_0-9]+)"/g).map((s) => s.slice(1, -1));
  assert.deepStrictEqual(
    FIELDS.slice().sort(), inScript.slice().sort(),
    "창에 세운 칸과 companies.js 의 FIELDS 가 갈렸습니다 ★ 갈린 칸은 조용히 저장이 안 됩니다");

  // ── 1. 되읽은 값이 하나도 빠짐없이 저장 요청에 실린다 ──────────────────
  {
    const payload = { id: 1, name: "샘플가나헬스", introducible: true };
    FIELDS.forEach(function (f) {
      payload[f] = EOK.indexOf(f) >= 0 ? 1830 : valueFor(f);
    });
    const dom = await openAndSave(payload);

    assert.ok(sent, "저장 요청이 안 나갔습니다");
    const missing = FIELDS.filter((f) => !(f in sent));
    assert.deepStrictEqual(missing, [],
      "창에 있는 칸이 저장 요청에 안 실렸습니다 ★ 고쳐도 조용히 저장이 안 됩니다");

    FIELDS.forEach(function (f) {
      if (EOK.indexOf(f) >= 0) {
        // 화면은 억, 저장은 백만원 — 되돌아와야 한다.
        assert.strictEqual(sent[f], 1830, f + ": 억↔백만원 되돌림이 어긋났습니다");
      } else {
        assert.strictEqual(sent[f], payload[f],
          f + ": 되읽은 값과 보내는 값이 다릅니다 (" +
          JSON.stringify(payload[f]) + " → " + JSON.stringify(sent[f]) + ")");
      }
      assert.strictEqual(dom.inputs[f].value, EOK.indexOf(f) >= 0 ? "18.3" : payload[f],
        f + ": 창에 되읽어진 값이 다릅니다");
    });
  }

  // ── 2. 연도별 매출은 **적힌 그대로**다 ────────────────────────────────
  //
  // 숫자 칸으로 바꿔 두면 `1,224백만원` 이 통째로 사라지거나 `1` 이 된다.
  // 그 값이 그대로 딜소개 문구의 `매출 …` 토막이 된다.
  {
    ["revenue_2022", "revenue_2023", "revenue_2024", "revenue_2025"].forEach(function (f) {
      assert.strictEqual(typeof sent[f], "string", f + ": 글자가 아닙니다");
      assert.strictEqual(sent[f], SAMPLE[f], f + ": 값이 다듬어졌습니다");
    });
  }

  // ── 3. 합치기 전 값은 저장 요청에 안 실린다 (읽기 전용) ────────────────
  {
    assert.ok(!("desc_backup" in sent),
      "합치기 전 값이 저장 요청에 실렸습니다 ★ 열어 본 것만으로 백업이 덮입니다");
  }

  // ── 4. 한줄 소개의 상태가 화면에 보인다 ────────────────────────────────
  //
  // 서버는 진작부터 `one_liner_auto` 를 실어 보내고 있었는데 화면이 안 읽어서,
  // 스타트업DB 를 채워도 소개가 왜 그대로인지 알 길이 없었다.
  {
    const base = { id: 1, name: "샘플나다물류", introducible: true };
    FIELDS.forEach(function (f) { base[f] = ""; });

    // (가) 사람이 쓴 값 — 단추가 뜨고, 누르면 조합 결과가 칸에 들어온다.
    let dom = build();
    run(dom, Object.assign({}, base, {
      one_liner: "사람이 다듬어 쓴 소개",
      one_liner_suggestion: "자동 조합 | 매출 3억",
      one_liner_auto: false
    }));
    dom.row.querySelector("button.js-co-edit").fire("click");
    await flush();
    let state = dom.root.querySelector("#one-liner-state").textContent;
    assert.ok(/직접 쓰신/.test(state), "손으로 쓴 값인 것이 안 보입니다: " + state);
    assert.strictEqual(dom.root.querySelector("#one-liner-auto").hidden, false,
      "되돌리는 길이 없습니다");

    dom.root.querySelector("#one-liner-auto").fire("click");
    assert.strictEqual(dom.inputs.one_liner.value, "자동 조합 | 매출 3억",
      "[자동 조합으로 바꾸기] 가 조합 결과를 안 넣었습니다");
    // **누르는 것만으로 저장되지는 않는다** — [취소] 를 눌러도 남아 있으면
    // 창의 다른 칸들과 규칙이 달라진다.
    assert.strictEqual(sent, null, "단추가 그 자리에서 저장해 버렸습니다");

    // (나) 자동으로 만든 값 — 조합과 같으니 단추가 없다.
    dom = build();
    run(dom, Object.assign({}, base, {
      one_liner: "자동 조합 | 매출 3억",
      one_liner_suggestion: "자동 조합 | 매출 3억",
      one_liner_auto: true
    }));
    dom.row.querySelector("button.js-co-edit").fire("click");
    await flush();
    state = dom.root.querySelector("#one-liner-state").textContent;
    assert.ok(/자동으로 만든/.test(state), "자동으로 만든 값인 것이 안 보입니다: " + state);
    assert.strictEqual(dom.root.querySelector("#one-liner-auto").hidden, true,
      "눌러도 아무 일이 안 일어나는 단추가 떠 있습니다");

    // (다) 빈 값 — 무엇을 채워야 하는지 말해 준다.
    dom = build();
    run(dom, Object.assign({}, base, {
      one_liner: "", one_liner_suggestion: "", one_liner_auto: false
    }));
    dom.row.querySelector("button.js-co-edit").fire("click");
    await flush();
    state = dom.root.querySelector("#one-liner-state").textContent;
    assert.ok(/비어 있습니다/.test(state), "빈 값인 것이 안 보입니다: " + state);
    assert.strictEqual(dom.root.querySelector("#one-liner-auto").hidden, true,
      "조합할 재료가 없는데 바꾸기 단추가 떠 있습니다");
  }

  console.log("company_edit_fields_test OK (" + FIELDS.length + "칸)");
}

main().catch(function (e) { console.error(e); process.exit(1); });
