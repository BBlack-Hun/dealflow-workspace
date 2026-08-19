// 공통 필터 컴포넌트의 순수 로직 테스트 (node 로 실행: node tests/js/filters_test.js)
// DOM 연결부(init)는 브라우저에서 확인하고, 여기서는 규칙(AND/OR·쿼리·건수)만 검증한다.
const assert = require("assert");
const path = require("path");

const F = require(path.join(__dirname, "..", "..", "app", "static", "js", "filters.js"));

const tests = {};
function test(name, fn) { tests[name] = fn; }

// ── 다중 값 셀 ────────────────────────────────────────────────────────────
test("다중 값 셀은 '|' 로 태그 단위 분해", () => {
  assert.deepStrictEqual(F.splitValues("AI|헬스케어"), ["AI", "헬스케어"]);
});

test("빈 값은 '(비어 있음)' 으로 필터 가능", () => {
  assert.deepStrictEqual(F.splitValues(""), [F.EMPTY]);
  assert.deepStrictEqual(F.splitValues(null), [F.EMPTY]);
});

// ── URL 쿼리 왕복 ─────────────────────────────────────────────────────────
test("쿼리스트링 파싱", () => {
  assert.deepStrictEqual(
    F.parseQuery("?stage=Seed,SeriesA&status=active", ["stage", "status"]),
    { stage: ["Seed", "SeriesA"], status: ["active"] }
  );
});

test("필터와 무관한 쿼리는 무시한다", () => {
  assert.deepStrictEqual(F.parseQuery("?page=2&stage=Seed", ["stage"]), { stage: ["Seed"] });
});

test("쿼리 왕복(값에 쉼표·공백이 있어도 보존)", () => {
  const state = { sector: ["AI, 로보틱스"], status: ["활발"] };
  const qs = F.buildQuery(state);
  assert.ok(qs.indexOf("%2C") > 0, "쉼표는 인코딩되어야 구분자와 섞이지 않는다");
  assert.deepStrictEqual(F.parseQuery(qs, ["sector", "status"]), state);
});

test("선택이 없으면 빈 쿼리", () => {
  assert.strictEqual(F.buildQuery({}), "");
  assert.strictEqual(F.buildQuery({ stage: [] }), "");
});

// ── 결합 규칙: 컬럼 간 AND, 컬럼 내 OR ────────────────────────────────────
const rows = [
  { stage: ["Seed"], sector: ["AI"], status: ["활발"] },
  { stage: ["SeriesA", "SeriesB"], sector: ["헬스케어"], status: ["활발"] },
  { stage: ["Seed"], sector: ["AI", "핀테크"], status: ["반응없음"] },
  { stage: [F.EMPTY], sector: [F.EMPTY], status: ["활발"] }
];

test("같은 컬럼 다중 선택은 OR", () => {
  const hits = rows.filter((r) => F.matchRow(r, { stage: ["Seed", "SeriesA"] }));
  assert.strictEqual(hits.length, 3);
});

test("다른 컬럼끼리는 AND", () => {
  const hits = rows.filter((r) => F.matchRow(r, { stage: ["Seed"], status: ["활발"] }));
  assert.strictEqual(hits.length, 1);
});

test("다중 값 셀은 하나라도 일치하면 통과", () => {
  assert.ok(F.matchRow(rows[2], { sector: ["핀테크"] }));
});

test("'(비어 있음)' 으로도 걸러진다", () => {
  const hits = rows.filter((r) => F.matchRow(r, { sector: [F.EMPTY] }));
  assert.strictEqual(hits.length, 1);
});

test("선택이 없으면 전부 통과", () => {
  assert.strictEqual(rows.filter((r) => F.matchRow(r, {})).length, rows.length);
});

// ── 고유값 + 건수 ─────────────────────────────────────────────────────────
test("고유값과 건수를 센다", () => {
  assert.deepStrictEqual(F.facets(rows, "stage", {}), [
    { value: "Seed", count: 2 },
    { value: "SeriesA", count: 1 },
    { value: "SeriesB", count: 1 },
    { value: F.EMPTY, count: 1 }
  ]);
});

test("건수는 다른 컬럼 필터를 반영한다(고르면 몇 건 남는지 보이게)", () => {
  const facets = F.facets(rows, "stage", { status: ["활발"] });
  const seed = facets.find((f) => f.value === "Seed");
  assert.strictEqual(seed.count, 1);
});

test("자기 컬럼 선택은 자기 건수에 영향을 주지 않는다", () => {
  const a = F.facets(rows, "stage", {});
  const b = F.facets(rows, "stage", { stage: ["Seed"] });
  assert.deepStrictEqual(a, b);
});

test("'(비어 있음)' 은 목록 맨 끝", () => {
  const values = F.facets(rows, "sector", {}).map((f) => f.value);
  assert.strictEqual(values[values.length - 1], F.EMPTY);
});

// ── 실행 ──────────────────────────────────────────────────────────────────
let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try {
    fn();
    console.log("ok   - " + name);
  } catch (err) {
    failed += 1;
    console.error("FAIL - " + name + "\n       " + err.message);
  }
}
console.log(`\n${Object.keys(tests).length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
