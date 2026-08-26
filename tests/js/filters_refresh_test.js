// 칸을 고치면 그 값이 필터에도 나오는가. (node 로 실행: node tests/js/filters_refresh_test.js)
//
// 필터는 표를 **처음 한 번만** 읽어 목록을 만든다. 그래서 칸을 고쳐도 다시
// 읽어 주지 않으면 값은 있는데 필터에는 없는 상태가 된다 — 관심도를 채워
// 넣었는데 필터 목록이 비어 있었다. 있는 줄 알고 골랐다가 아무것도 안 나온다.
//
// 세 곳이 다 이어져야 한 바퀴가 돈다:
//   inline_edit.js  저장 뒤 행의 data-f-<필드> 를 고쳐 적는다
//                   (data-filter-key 가 있으면 그 이름을 먼저 쓴다)
//   contacts.js     inline-saved 를 받아 filters.refresh() 를 부른다
//   filters.js      refresh() 가 행의 data-f-* 를 다시 읽는다
//
// filters.js 의 DOM 연결부(init)는 브라우저에 매여 있어 통째로 못 부른다.
// 되살리는 규칙만 같은 모양으로 옮겨 두고, 그 규칙이 파일에 실제로 있는지도
// 함께 본다(preview_edit_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const F = require(path.join(SRC, "filters.js"));

function read(name) {
  return fs.readFileSync(path.join(SRC, name), "utf8");
}

// --- 가짜 행/칸 (getAttribute 만 있으면 규칙을 돌릴 수 있다) -----------------
function row(attrs) {
  const data = Object.assign({}, attrs);
  return {
    getAttribute: function (k) { return k in data ? data[k] : null; },
    setAttribute: function (k, v) { data[k] = v; },
    hasAttribute: function (k) { return k in data; }
  };
}

function cell(attrs) {
  return { getAttribute: function (k) { return k in attrs ? attrs[k] : null; } };
}

// --- 규칙 1: 저장 뒤 행에 값을 적는다 (inline_edit.js 의 save 안과 같은 모양)
function markRow(tr, td, value) {
  const fkey = td.getAttribute("data-filter-key") || td.getAttribute("data-field");
  if (tr && tr.hasAttribute("data-f-" + fkey)) tr.setAttribute("data-f-" + fkey, value);
}

// --- 규칙 2: 필터가 행을 다시 읽는다 (filters.js 의 refresh 안과 같은 모양)
function refresh(rows, rowData, keys) {
  rows.forEach(function (tr, i) {
    keys.forEach(function (k) {
      rowData[i][k] = F.splitValues(tr.getAttribute("data-f-" + k));
    });
  });
  return rowData;
}

// --- 칸을 채우면 필터 목록에 그 값이 생긴다 ---------------------------------
{
  const keys = ["interest"];
  const rows = [row({ "data-f-interest": "" }), row({ "data-f-interest": "높음" })];
  const rowData = refresh(rows, [{}, {}], keys);

  assert.deepStrictEqual(
    F.facets(rowData, "interest", {}).map(function (f) { return f.value; }),
    ["높음", F.EMPTY], "처음 읽은 목록부터 어긋난다");

  // 빈 칸에 '중간' 을 적어 저장했다
  markRow(rows[0], cell({ "data-field": "interest" }), "중간");

  const stale = F.facets(rowData, "interest", {}).map(function (f) { return f.value; });
  assert.ok(stale.indexOf("중간") < 0,
            "다시 읽기 전인데 벌써 반영됐다 — 이 검사가 무의미해졌다");

  refresh(rows, rowData, keys);
  const fresh = F.facets(rowData, "interest", {}).map(function (f) { return f.value; });
  assert.ok(fresh.indexOf("중간") >= 0, "칸을 고쳤는데 필터 목록에 그 값이 없다");
  assert.ok(fresh.indexOf(F.EMPTY) < 0,
            "빈 칸을 다 채웠는데 '(비어 있음)' 이 목록에 남아 있다");
}

// --- 고친 값으로 실제로 걸러진다 --------------------------------------------
//
// 목록에 뜨기만 하고 걸러지지 않으면, 골라 놓고 "0명" 을 보게 된다.
{
  const keys = ["interest"];
  const rows = [row({ "data-f-interest": "낮음" })];
  const rowData = refresh(rows, [{}], keys);
  assert.strictEqual(F.matchRow(rowData[0], { interest: ["높음"] }), false);

  markRow(rows[0], cell({ "data-field": "interest" }), "높음");
  refresh(rows, rowData, keys);
  assert.strictEqual(F.matchRow(rowData[0], { interest: ["높음"] }), true,
                     "고친 값으로 걸러지지 않는다");
  assert.strictEqual(F.matchRow(rowData[0], { interest: ["낮음"] }), false,
                     "옛 값으로도 여전히 걸러진다");
}

// --- 필터 이름이 칸 이름과 다르면 data-filter-key 를 따른다 -----------------
//
// 표의 필터 이름은 짧고(interest) 칸 이름은 DB 컬럼(interest_level)인 표가 있다.
// 칸 이름으로만 적으면 아무도 안 보는 data-f-interest_level 에 적힌다.
{
  const tr = row({ "data-f-interest": "낮음" });
  markRow(tr, cell({ "data-filter-key": "interest",
                     "data-field": "interest_level" }), "높음");

  assert.strictEqual(tr.getAttribute("data-f-interest"), "높음",
                     "data-filter-key 를 무시하고 엉뚱한 이름에 적었다");
  assert.strictEqual(tr.getAttribute("data-f-interest_level"), null,
                     "아무도 안 보는 이름에 적혔다");
}

// --- 필터가 보지 않는 칸은 행에 붙이지 않는다 -------------------------------
{
  const tr = row({ "data-f-interest": "높음" });
  markRow(tr, cell({ "data-field": "memo" }), "10월 통화 예정");
  assert.strictEqual(tr.getAttribute("data-f-memo"), null,
                     "필터가 보지 않는 값까지 행에 붙는다");
  assert.strictEqual(tr.getAttribute("data-f-interest"), "높음",
                     "엉뚱한 칸을 고쳤는데 필터 값이 바뀌었다");
}

// --- filters.js 에 실제로 refresh 가 있는가 ---------------------------------
{
  const src = read("filters.js");
  assert.ok(/function refresh\s*\(/.test(src), "filters.js 에 refresh 가 없다");
  assert.ok(/refresh:\s*refresh/.test(src),
            "refresh 를 내주지 않으면 화면에서 부를 수가 없다");

  const body = src.slice(src.indexOf("function refresh"), src.indexOf("function refresh") + 500);
  assert.ok(/getAttribute\("data-f-" \+ k\)/.test(body),
            "refresh 가 행의 data-f-* 를 다시 읽지 않는다 — 처음 읽은 값 그대로다");
  assert.ok(/apply\(\)/.test(body), "다시 읽고 나서 적용하지 않는다 — 화면은 그대로다");
}

// --- inline_edit.js 가 저장 뒤 행에 적는가 ----------------------------------
{
  const src = read("inline_edit.js");
  assert.ok(
    /getAttribute\("data-filter-key"\)\s*\|\|\s*cell\.getAttribute\("data-field"\)/.test(src),
    "data-filter-key 를 먼저 보고 없으면 칸 이름으로 떨어져야 한다");
  // 적는 값은 그대로일 수도, 구분자 규칙(`forFilter`)을 거칠 수도 있다 —
  // 한 칸에 값이 여럿인 칸은 화면의 쉼표를 필터의 `|` 로 바꿔 적는다.
  // 여기서 볼 것은 **행에 적는다**는 사실 하나다.
  assert.ok(/setAttribute\("data-f-" \+ fkey, /.test(src),
            "저장 뒤 행에 값을 적지 않는다 — 다시 읽어도 옛 값뿐이다");
  assert.ok(/dispatchEvent\(new CustomEvent\("inline-saved"/.test(src),
            "저장했다고 알리지 않으면 화면이 알아챌 방법이 없다");
}

// --- contacts.js 가 저장 뒤 필터를 다시 읽는가 ------------------------------
{
  const src = read("contacts.js");
  const at = src.indexOf('addEventListener("inline-saved"');
  assert.ok(at > 0, "저장을 알아채지 못하면 필터는 영영 옛 값이다");
  assert.ok(/filters\.refresh\(\)/.test(src.slice(at, at + 300)),
            "저장 뒤 filters.refresh() 를 부르지 않는다");
}

console.log("filters_refresh_test: 통과");
