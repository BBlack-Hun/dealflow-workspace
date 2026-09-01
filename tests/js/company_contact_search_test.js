// IR 기업 현황 · 스타트업DB 의 검색칸 — 기업명 말고 **대표자·연락처·이메일**로도
// 찾아지는가. (node tests/js/company_contact_search_test.js)
//
// 규칙을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모른다. 그래서 **실제로 나가는
// 코드 두 개를 그대로 돌린다** —
//
//   app/static/js/filters.js      공용 컬럼 필터(검색은 여기에 AND 로 얹힌다)
//   app/static/js/companies.js    이 화면이 검색칸을 거는 자리
//
// 특히 보는 것:
//   1. 전화번호를 **어떤 모양으로 쳐도** 걸리는가 — 원본에 `010-0000-5678` ·
//      `01000001234` · `010 0000 4321` 이 섞여 있고, 사람은 자기 버릇대로 친다.
//      뒷자리 네 개(`5678`)로 찾는 것이 실제로는 가장 흔하다.
//   2. 검색과 컬럼 필터가 서로를 지우지 않는가 — 이 저장소는 둘이 번갈아
//      `tr.hidden` 을 덮어써 서로를 지운 적이 있다.
//
// 이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const { el } = dom_;

const ROOT = path.join(__dirname, "..", "..");
const SRC = path.join(ROOT, "app", "static", "js");
const FILTERS = fs.readFileSync(path.join(SRC, "filters.js"), "utf8");
const COMPANIES = fs.readFileSync(path.join(SRC, "companies.js"), "utf8");

// 서버가 줄에 실어 주는 것과 **같은 규칙**으로 만든다
// (app/routers/companies.py 의 `search_text`). 번호는 적은 그대로와 숫자만
// 남긴 꼴을 함께 싣는다 — 아래 `test_company_search.py` 가 파이썬 쪽이 정말
// 그렇게 싣는지 본다.
function searchText(r) {
  const phone = (r.phone || "").trim();
  const digits = phone.replace(/[^0-9]/g, "");
  return [r.name, r.contact, r.email, phone,
          digits === phone ? "" : digits, r.oneLiner]
    .filter(Boolean).join(" ").toLowerCase();
}

const ROWS = [
  { name: "가나테크", contact: "김가나", email: "ganatech@example.com",
    phone: "010-0000-5678", oneLiner: "농산물 선도거래 b2b", contract: "계약" },
  { name: "다라바이오", contact: "이다라", email: "dara@example.com",
    phone: "01000001234", oneLiner: "뇌영상 분석 ai", contract: "미계약" },
  { name: "마바에너지", contact: "박마바", email: "maba@example.com",
    phone: "010 0000 4321", oneLiner: "에너지 저장장치", contract: "계약" }
];

function buildDom() {
  dom_.resetHandlers();
  const root = dom_.makeEl("html");

  const trs = ROWS.map(function (r, i) {
    return el("tr", {
      "data-id": String(i + 1),
      "data-search": searchText(r),
      "data-f-contract": r.contract
    }, [el("td", { class: "rowno" })]);
  });
  // 화면과 같은 모양의 머리글 — 필터 단추는 `.th-filters` 안에 선다.
  const th = el("th", { "data-filters": "contract:계약여부" },
    [el("div", { class: "th-filters" })]);
  const table = el("table", { id: "co-table" }, [
    el("thead", {}, [el("tr", {}, [th])]),
    el("tbody", {}, trs)
  ]);

  root.appendChild(el("input", { id: "co-search", type: "search" }));
  root.appendChild(el("div", { class: "chip-row", "data-filter-chips": "" }));
  root.appendChild(el("p", { id: "co-note", class: "hint" }));
  root.appendChild(table);
  // 상세 패널 쪽 요소들 — companies.js 가 불러올 때 바로 잡는 것들만 세운다.
  ["co-add", "co-close", "co-cancel", "co-save"].forEach(function (id) {
    root.appendChild(el("button", { id: id, type: "button" }));
  });
  root.appendChild(el("div", { id: "co-backdrop" }));
  root.appendChild(el("aside", { id: "co-panel" }));
  root.appendChild(el("p", { id: "co-status" }));
  root.appendChild(el("h2", { id: "co-title" }));

  return { root: root, document: dom_.makeDocument(root), trs: trs };
}

// `query` 는 주소에 남아 있는 컬럼 필터 상태다 — 필터를 걸어 둔 채 새로고침한
// 화면이 그 모습이다(filters.js 가 `location.search` 에서 상태를 읽는다).
function run(query) {
  const dom = buildDom();
  const win = { location: { search: query || "", pathname: "/companies" },
                history: {} };
  const ctx = { document: dom.document, console: console,
                setTimeout: function (fn) { return fn && fn(); } };
  ctx.window = win;
  win.document = dom.document;
  vm.runInNewContext(FILTERS, ctx, { filename: "filters.js" });
  assert.ok(ctx.window.DealflowFilters, "공용 필터 모듈이 안 실렸다");
  vm.runInNewContext(COMPANIES, ctx, { filename: "companies.js" });
  return dom;
}

function shown(dom) {
  return dom.trs
    .map(function (tr, i) { return tr.hidden ? null : ROWS[i].name; })
    .filter(Boolean);
}

function type(dom, text) {
  const box = dom.document.getElementById("co-search");
  box.value = text;
  box.fire("input");
}

function check(query, want, why) {
  const dom = run();
  type(dom, query);
  assert.deepStrictEqual(shown(dom), want, why + ` (친 글자: "${query}")`);
}

// ── 아무 것도 안 쳤으면 전부 보인다 ─────────────────────────────────────────
{
  const dom = run();
  assert.deepStrictEqual(shown(dom), ["가나테크", "다라바이오", "마바에너지"]);
}

// ── 기업명 (예전부터 되던 것 — 새 규칙이 이걸 깨면 안 된다) ─────────────────
check("가나테크", ["가나테크"], "기업명으로 안 걸린다");
check("에너지", ["마바에너지"], "기업명 일부로 안 걸린다");

// ── 대표자 이름 ─────────────────────────────────────────────────────────────
// 표에 이름이 보이는데 그 이름을 쳐도 안 걸리면 "검색이 고장났다" 로 보인다.
check("이다라", ["다라바이오"], "대표자 이름으로 안 걸린다");

// ── 이메일 ──────────────────────────────────────────────────────────────────
check("maba@example.com", ["마바에너지"], "이메일 전체로 안 걸린다");
check("ganatech@", ["가나테크"], "이메일 앞부분으로 안 걸린다");

// ── 전화번호: 어떤 모양으로 쳐도 걸린다 ─────────────────────────────────────
// 저장된 모양과 친 모양이 다른 조합을 전부 본다. 한 방향만 되면 사람은
// "가끔 되고 가끔 안 된다" 고 느끼는데, 그게 제일 못 믿는 상태다.
check("010-0000-5678", ["가나테크"], "적은 그대로 쳤는데 안 걸린다");
check("01000005678", ["가나테크"], "하이픈이 든 줄을 숫자만 쳐서 못 찾는다");
check("010 0000 5678", ["가나테크"], "띄어쓰기로 쳤는데 안 걸린다");

check("01000001234", ["다라바이오"], "숫자만 저장된 줄을 숫자만 쳐서 못 찾는다");
check("010-0000-1234", ["다라바이오"], "숫자만 저장된 줄을 하이픈으로 쳐서 못 찾는다");

check("010 0000 4321", ["마바에너지"], "띄어쓰기로 저장된 줄이 안 걸린다");
check("01000004321", ["마바에너지"], "띄어쓰기로 저장된 줄을 숫자만 쳐서 못 찾는다");
check("010-0000-4321", ["마바에너지"], "띄어쓰기로 저장된 줄을 하이픈으로 쳐서 못 찾는다");

// 뒷자리 네 개 — 실제로 번호는 이렇게 찾는다.
check("5678", ["가나테크"], "뒷자리로 안 걸린다");
check("1234", ["다라바이오"], "뒷자리로 안 걸린다");
check("4321", ["마바에너지"], "뒷자리로 안 걸린다");
check("0000-4321", ["마바에너지"], "중간부터 하이픈으로 쳤는데 안 걸린다");

// 앞자리는 다 같으니 셋 다 나온다 — 안 그러면 숫자만 남기는 길이 안 도는 것이다.
check("010", ["가나테크", "다라바이오", "마바에너지"], "앞자리로 전부 안 걸린다");

// ── 글자가 섞이면 숫자만 남기지 않는다 ──────────────────────────────────────
// 아무 글자에서나 숫자를 뽑아내면 `b2b` 가 `2` 가 되어 번호에 걸린다.
check("b2b", ["가나테크"], "한줄 소개로 안 걸린다");
check("가나4321", [], "글자가 섞인 말에서 숫자를 뽑아내 엉뚱한 줄이 걸렸다");

// ── 없는 번호는 아무 줄도 안 나온다 ─────────────────────────────────────────
check("01000009999", [], "없는 번호인데 뭔가 걸린다");

// ── 지웠다 다시 치면 돌아온다 ───────────────────────────────────────────────
// 검색이 `tr.hidden` 을 자기 마음대로 만지면 한 번 감춘 줄이 안 돌아온다.
{
  const dom = run();
  type(dom, "5678");
  assert.deepStrictEqual(shown(dom), ["가나테크"]);
  type(dom, "");
  assert.deepStrictEqual(shown(dom), ["가나테크", "다라바이오", "마바에너지"],
    "검색어를 지웠는데 줄이 안 돌아온다");
}

// ── 몇 개 보이는지 알려 준다 ────────────────────────────────────────────────
{
  const dom = run();
  type(dom, "5678");
  const note = dom.document.getElementById("co-note");
  assert.strictEqual(note.hidden, false, "걸러 놓고 몇 개인지 말을 안 한다");
  assert.strictEqual(note.textContent, "1 / 3개 표시 중");
}

// ── ★ 계약여부 필터를 걸어 둔 채로 검색해도 맞는가 ──────────────────────────
//
// 검색과 필터는 **AND** 다. 둘이 각자 `tr.hidden` 을 만지면 나중에 도는 쪽이
// 앞의 것을 지운다 — 필터를 걸어 둔 것을 잊고 "검색이 이상하다" 고 하게 된다.
{
  const dom = run("?contract=계약");
  assert.deepStrictEqual(shown(dom), ["가나테크", "마바에너지"],
    "필터를 걸어 둔 채 열었는데 필터가 안 걸려 있다");

  // 필터에 걸린 줄을 번호로 찾는다 — 둘 다 만족하니 보여야 한다.
  type(dom, "5678");
  assert.deepStrictEqual(shown(dom), ["가나테크"], "필터 + 번호 검색이 안 맞는다");

  // 필터에서 빠진 줄(미계약)을 번호로 찾는다 — 검색에는 맞지만 필터에 걸려
  // 있으니 안 나와야 한다. 여기서 나오면 검색이 필터를 지운 것이다.
  type(dom, "01000001234");
  assert.deepStrictEqual(shown(dom), [],
    "검색이 컬럼 필터를 지웠다 — 필터에서 빠진 줄이 검색으로 되살아났다");

  // 검색어를 지우면 **필터만** 남는다. 여기서 셋 다 나오면 검색이 필터를 지운다.
  type(dom, "");
  assert.deepStrictEqual(shown(dom), ["가나테크", "마바에너지"],
    "검색어를 지웠더니 컬럼 필터까지 같이 풀렸다");
}

console.log("company_contact_search_test: 통과");
