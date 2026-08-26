// 칸을 고치면 그 값이 **필터 목록에도** 나오는가. (node tests/js/filter_loop_test.js)
//
// 한 바퀴는 네 고리다. 하나만 끊겨도 증상은 똑같다 —
// 값은 화면에 보이는데 필터에는 없다.
//
//   1. inline_edit.js  저장 뒤 행의 data-f-<키> 를 고쳐 적는다
//                      (data-filter-key 가 있으면 그 이름을 먼저 쓴다)
//   2. 템플릿          칸이 자기 필터 키를 알고 있다   ← tests/test_filter_columns.py
//   3. filters.js      inline-saved 를 듣고 행을 다시 읽는다
//   4. filters.js      다시 읽은 값이 목록·거르기에 반영된다
//
// 끊겼던 자리: 투자사 관리 현황은 (2) 가 없어 행이 안 바뀌었고, 딜 소싱은
// (3) 을 이어 줄 화면 코드가 없어 refresh 가 영영 안 불렸다.
//
// filters.js 의 DOM 연결부(init)는 브라우저에 매여 있어 통째로 못 부른다.
// 부를 수 있는 순수 함수는 **원본 그대로** 쓰고, 나머지는 파일에 그 고리가
// 실제로 있는지 본다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const F = require(path.join(SRC, "filters.js"));

function read(name) {
  return fs.readFileSync(path.join(SRC, name), "utf8");
}

// inline_edit.js 는 통째로 못 불러온다 — 불러오는 순간 document 를 찾는다.
// 그래서 **파일에 든 그 함수를 떼어 내** 돌린다. 베껴 두면 원본이 바뀌어도
// 테스트만 옛 규칙을 지키며 통과한다(두 벌이 되면 어긋나도 모른다).
function lift(src, name) {
  const at = src.indexOf("function " + name + "(");
  assert.ok(at >= 0, name + " 이(가) 파일에 없다");
  let depth = 0;
  let i = src.indexOf("{", at);
  for (; i < src.length; i++) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) break; }
  }
  return new Function("return (" + src.slice(at, i + 1) + ");")();
}

const INLINE = read("inline_edit.js");
const forFilter = lift(INLINE, "forFilter");

function node(attrs) {
  const data = Object.assign({}, attrs);
  return {
    getAttribute: function (k) { return k in data ? data[k] : null; },
    setAttribute: function (k, v) { data[k] = v; },
    hasAttribute: function (k) { return k in data; }
  };
}

// 고리 1 — inline_edit.js 의 save() 안과 같은 모양.
function saveCell(row, cell, value) {
  const fkey = cell.getAttribute("data-filter-key") || cell.getAttribute("data-field");
  if (row && row.hasAttribute("data-f-" + fkey)) {
    row.setAttribute("data-f-" + fkey, forFilter(cell, value));
  }
}

// 고리 3 — filters.js 의 refresh() 안과 같은 모양.
function reread(rows, rowData, keys) {
  rows.forEach(function (tr, i) {
    keys.forEach(function (k) {
      rowData[i][k] = F.splitValues(tr.getAttribute("data-f-" + k));
    });
  });
  return rowData;
}

function values(rowData, key, state) {
  return F.facets(rowData, key, state || {}).map(function (f) { return f.value; });
}

// ── 칸 이름과 필터 키가 다른 표에서도 행이 바뀐다 ───────────────────────────
//
// 투자사 관리 현황은 하나도 안 겹친다(round_size ↔ data-f-round). 칸 이름으로만
// 적으면 아무도 안 보는 data-f-round_size 에 적히고, 행은 옛 값 그대로다.
{
  const keys = ["round"];
  const rows = [node({ "data-f-round": "" }), node({ "data-f-round": "10~30억" })];
  const rowData = reread(rows, [{}, {}], keys);
  assert.deepStrictEqual(values(rowData, "round"), ["10~30억", F.EMPTY],
                         "처음 읽은 목록부터 어긋난다");

  const cell = node({ "data-field": "round_size", "data-filter-key": "round" });
  saveCell(rows[0], cell, "50억 이상");

  assert.strictEqual(rows[0].getAttribute("data-f-round"), "50억 이상",
                     "필터 키가 아니라 칸 이름에 적었다 — 아무도 그 이름을 안 본다");
  assert.strictEqual(rows[0].getAttribute("data-f-round_size"), null);

  assert.ok(values(rowData, "round").indexOf("50억 이상") < 0,
            "다시 읽기 전인데 벌써 반영됐다 — 이 검사가 무의미해졌다");

  reread(rows, rowData, keys);
  const after = values(rowData, "round");
  assert.ok(after.indexOf("50억 이상") >= 0, "칸을 고쳤는데 필터 목록에 그 값이 없다");
  assert.ok(after.indexOf(F.EMPTY) < 0, "빈 칸을 다 채웠는데 '(비어 있음)' 이 남아 있다");
  assert.strictEqual(F.matchRow(rowData[0], { round: ["50억 이상"] }), true,
                     "목록에는 떴는데 그 값으로 걸러지지 않는다 — 골라 놓고 0명을 본다");
}

// ── 한 칸에 값이 여럿인 칸은 필터 구분자로 바꿔 적는다 ──────────────────────
//
// 선호 투자분야는 사람에게 `AI, 헬스케어` 로 보여 주고 필터는 `|` 로 나눠
// 태그 단위로 거른다. 보이는 그대로 적으면 통째로 값 하나가 되어, 고친 그
// 사람만 목록에서 따로 떨어져 나온다(`AI` 를 골라도 안 걸린다).
{
  const cell = node({ "data-field": "sectors", "data-filter-key": "sector",
                      "data-filter-sep": "," });
  const stored = forFilter(cell, "AI, 헬스케어");
  assert.strictEqual(stored, "AI|헬스케어");
  assert.deepStrictEqual(F.splitValues(stored), ["AI", "헬스케어"]);

  assert.strictEqual(F.matchRow({ sector: F.splitValues("AI, 헬스케어") },
                                { sector: ["AI"] }), false,
                     "보이는 그대로 적어도 걸리면 이 검사가 무의미해졌다");
  assert.strictEqual(F.matchRow({ sector: F.splitValues(stored) },
                                { sector: ["AI"] }), true,
                     "태그 단위로 안 걸린다");

  // 구분자를 안 준 칸은 적힌 그대로가 값 하나다 — 라운드 사이즈에는 쉼표가
  // 섞여 있는데(`10, 20억`) 쪼개면 없는 값 두 개가 생긴다.
  const plain = node({ "data-field": "round_size", "data-filter-key": "round" });
  assert.strictEqual(forFilter(plain, "10, 20억"), "10, 20억");
}

// ── 필터가 보지 않는 칸은 행에 붙이지 않는다 ────────────────────────────────
{
  const row = node({ "data-f-round": "10~30억" });
  saveCell(row, node({ "data-field": "memo" }), "10월 통화 예정");
  assert.strictEqual(row.getAttribute("data-f-memo"), null,
                     "필터가 보지 않는 값까지 행에 붙는다");
  assert.strictEqual(row.getAttribute("data-f-round"), "10~30억",
                     "엉뚱한 칸을 고쳤는데 필터 값이 바뀌었다");
}

// ── 고리가 파일에 실제로 있는가 ─────────────────────────────────────────────

// 1. 저장 뒤 행에 적는다
{
  assert.ok(/getAttribute\("data-filter-key"\)\s*\|\|\s*cell\.getAttribute\("data-field"\)/
            .test(INLINE),
            "data-filter-key 를 먼저 보고 없으면 칸 이름으로 떨어져야 한다");
  assert.ok(/setAttribute\("data-f-" \+ fkey, forFilter\(cell, value\)\)/.test(INLINE),
            "행에 적을 때 구분자 규칙을 거치지 않는다 — 여러 값 칸이 통째로 값 하나가 된다");
  assert.ok(/dispatchEvent\(new CustomEvent\("inline-saved"/.test(INLINE),
            "저장했다고 알리지 않으면 필터가 알아챌 방법이 없다");
}

// 3. 필터가 **스스로** 그 알림을 듣는다
//
// 화면마다 이어 주게 두었더니 딜 소싱만 빠져 있었고, 빠진 화면은 값이 바뀌어도
// 필터 목록이 옛날 그대로였다. 표를 읽는 쪽이 스스로 듣는 편이 빠뜨릴 자리가 없다.
{
  const src = read("filters.js");
  const init = src.slice(src.indexOf("function init("));
  const at = init.indexOf('addEventListener("inline-saved"');
  assert.ok(at > 0,
            "filters.js 가 저장 알림을 직접 듣지 않는다 — 화면 하나만 빠뜨려도 " +
            "그 화면 필터는 영영 옛 값이다");
  assert.ok(/refresh/.test(init.slice(at, at + 260)),
            "알림을 듣고도 다시 읽지 않는다");
  assert.ok(/setTimeout\(refresh, 0\)/.test(init.slice(at, at + 260)),
            "저장 직후에 바로 읽는다 — 같은 알림으로 행을 다듬는 화면이 있어 " +
            "그 정리보다 먼저 읽으면 같은 값이 목록에 두 벌로 생긴다");
}

// 4. 다시 읽기가 행의 data-f-* 를 실제로 다시 읽는다
{
  const src = read("filters.js");
  const at = src.indexOf("function refresh");
  assert.ok(at > 0, "filters.js 에 refresh 가 없다");
  const body = src.slice(at, at + 500);
  assert.ok(/getAttribute\("data-f-" \+ k\)/.test(body),
            "refresh 가 행을 다시 읽지 않는다 — 처음 읽은 값 그대로다");
  assert.ok(/apply\(\)/.test(body), "다시 읽고 나서 적용하지 않는다 — 화면은 그대로다");
}

// ── IR 기업현황의 뒤처리: 행에 적히는 값이 나머지 296행과 같은 모양이어야 한다 ─
//
// 기업구분은 표에 **짧은 이름**만 보인다(`Seed`). 고를 때는 설명이 붙은 원문을
// 고르므로, 그대로 적으면 같은 단계가 목록에 두 벌로 갈린다.
// 핵심/TOP Deal 은 비우면 `일반` 이다 — 빈 값으로 두면 `(비어 있음)` 이 따로 생긴다.
{
  const src = read("companies.js");
  assert.ok(/setAttribute\("data-f-series", short\)/.test(src),
            "짧은 이름으로 되돌려 그리면서 행에는 원문을 남긴다 — 목록이 두 벌이 된다");
  assert.ok(/setAttribute\("data-f-top", "일반"\)/.test(src),
            "핵심/TOP Deal 을 비우면 '일반' 과 '(비어 있음)' 이 같은 목록에 함께 뜬다");
}

console.log("filter_loop_test: 통과");
