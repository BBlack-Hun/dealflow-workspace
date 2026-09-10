// 필터가 주소를 고쳐 쓸 때 **남의 쿼리를 지우지 않는가**.
// (node 로 실행: node tests/js/filters_url_test.js)
//
// 필터 상태는 주소에 남는다 — 새로고침해도 공유해도 유지되게 하려는 것이다.
// 그런데 고쳐 쓸 때 `location.pathname + 내_쿼리` 로 통째로 갈아 끼우고 있었다.
// 읽을 때는 모르는 키를 얌전히 건너뛰면서(`parseQuery`) 쓸 때만 다 버린 셈이다.
//
// 증상은 조용하다. `/sourcing?tab=M&A 찾는 투자사` 를 열면 아무것도 안 골랐는데도
// 화면을 그리자마자 주소가 `/sourcing` 이 되고, 그 상태로 새로고침하면 **다른
// 갈래**가 열린다. 투자컨설턴트 현황은 `?sheet=` 가 곧 명단이라 더 나쁘다 —
// 검색어를 한 글자 치면 남의 시트로 넘어간다.
//
// `syncUrl` 은 화면 상태를 닫아 쥔 init 안에 있어 밖에서 부를 수가 없다.
// 규칙만 같은 모양으로 옮겨 두고, 그 규칙이 파일에 실제로 있는지도 함께 본다
// (filters_refresh_test.js 와 같은 방식).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const F = require(path.join(SRC, "filters.js"));

// filters.js 의 keptQuery + syncUrl 과 같은 모양
function synced(pathname, search, keys, state, hash) {
  const q = String(search || "").replace(/^\?/, "");
  const parts = q.split("&").filter(function (pair) {
    if (!pair) return false;
    const i = pair.indexOf("=");
    return keys.indexOf(decodeURIComponent(i < 0 ? pair : pair.slice(0, i))) < 0;
  });
  const mine = F.buildQuery(state).replace(/^\?/, "");
  if (mine) parts.push(mine);
  return pathname + (parts.length ? "?" + parts.join("&") : "") + (hash || "");
}

const KEYS = ["region", "mgmt"];

// --- 아무것도 안 골랐을 때 남의 쿼리를 지우지 않는다 -------------------------
{
  assert.strictEqual(
    synced("/consulting", "?sheet=%EC%A4%91%EC%9A%94&ref=3", KEYS, {}),
    "/consulting?sheet=%EC%A4%91%EC%9A%94&ref=3",
    "화면을 열자마자 시트 탭이 주소에서 사라진다");
}

// --- 골랐을 때는 남의 쿼리 **뒤에** 붙는다 ----------------------------------
{
  assert.strictEqual(
    synced("/consulting", "?sheet=a", KEYS, { region: ["서울"] }),
    "/consulting?sheet=a&region=%EC%84%9C%EC%9A%B8");
}

// --- 내 키는 두 번 적히지 않는다 --------------------------------------------
//
// 주소에는 이미 앞선 선택이 적혀 있다. 그대로 두고 새 값을 또 붙이면
// `?region=대구&region=서울` 이 되어, 다시 읽을 때 어느 쪽이 이길지 모른다.
{
  assert.strictEqual(
    synced("/consulting", "?sheet=a&region=%EB%8C%80%EA%B5%AC", KEYS,
           { region: ["서울"] }),
    "/consulting?sheet=a&region=%EC%84%9C%EC%9A%B8");
}

// --- 해제하면 내 키만 빠진다 ------------------------------------------------
{
  assert.strictEqual(
    synced("/consulting", "?sheet=a&region=%EB%8C%80%EA%B5%AC", KEYS, {}),
    "/consulting?sheet=a");
}

// --- 원래 쿼리가 없으면 물음표도 안 붙는다 ----------------------------------
{
  assert.strictEqual(synced("/sourcing", "", ["assignee_name"], {}), "/sourcing");
}

// --- `#구역` 도 안 지운다 ----------------------------------------------------
//
// 딜 진행 관리는 한 페이지에 구역이 넷이고 `/followups` 는 `/ir#remind` 로
// 넘긴다. 화면을 그리자마자 주소가 `/ir` 이 되면, 그 주소를 새로고침하거나
// 복사해 갔을 때 리마인드가 아니라 **맨 위**가 열린다.
{
  assert.strictEqual(
    synced("/ir", "", ["region"], {}, "#remind"),
    "/ir#remind",
    "화면을 열자마자 `#remind` 가 주소에서 사라진다");
}

// 쿼리와 해시가 함께 있을 때 차례도 지킨다(`?…` 다음에 `#…`).
{
  assert.strictEqual(
    synced("/ir", "?contact=7", KEYS, { region: ["서울"] }, "#remind"),
    "/ir?contact=7&region=%EC%84%9C%EC%9A%B8#remind");
}

// --- filters.js 가 실제로 그렇게 하는가 -------------------------------------
{
  const src = fs.readFileSync(path.join(SRC, "filters.js"), "utf8");
  const at = src.indexOf("function syncUrl");
  assert.ok(at > 0, "filters.js 에 syncUrl 이 없다");
  const body = src.slice(at, at + 600);
  assert.ok(!/pathname\s*\+\s*qs\b/.test(body),
            "pathname 에 자기 쿼리만 이어 붙이고 있다 — 남의 쿼리가 통째로 날아간다");
  assert.ok(/keptQuery\(\)/.test(body),
            "남길 쿼리를 추리지 않는다 — 시트 탭·갈래 탭이 주소에서 사라진다");
  assert.ok(/location\.hash/.test(body),
            "해시를 안 이어 붙인다 — `/ir#remind` 가 `/ir` 이 된다");
}

console.log("filters_url_test: 통과");
