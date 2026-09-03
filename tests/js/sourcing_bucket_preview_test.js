// 갈래를 누르면 **그 갈래 문구**가 미리보기에 뜨는가.
// (node tests/js/sourcing_bucket_preview_test.js)
//
// 딜 소싱은 갈래마다 문구가 다르다 — 호칭('대표님'/'심사역님')도, 청하는
// 개수도, 찾는 범위도 갈래가 정한다(`services/sourcing_msg.py`). 그런데 갈래
// 칩은 **목록만 걸렀다.** 미리보기는 늘 첫 갈래의 문구였고, M&A 를 골라 놓고
// 시리즈 A 문구를 보며 발송을 누르게 된다.
//
// 여기서 못 박는 것은 둘이다.
//   ① 갈래를 누르면 미리보기를 **다시 부른다**
//   ② 그때 **누른 갈래**가 서버로 함께 나간다 — 안 나가면 서버는 어느 갈래를
//      보여 줄지 알 수 없어 첫 갈래로 되돌아간다
//
// 어느 갈래에 어떤 문구가 붙는지는 서버가 정한다(파이썬 쪽
// `tests/test_sourcing_buckets.py`). 여기는 **화면이 갈래를 말하는가**만 본다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");
const run = deals_.run;
const fakeFetch = deals_.fakeFetch;
const pickBucket = deals_.pickBucket;
const SOURCING = deals_.SOURCING;

const SERIES_A = SOURCING[0][2];
const MNA = SOURCING[1][2];

// 미리보기는 손이 멈춘 뒤 한 번 부른다. 검사에서는 기다릴 것이 없으니 바로 돌린다.
function now(fn) { fn(); return 0; }

function setup() {
  const fetch = fakeFetch([]);
  const dom = run(null, { fetch: fetch, setTimeout: now });
  // 딜 소싱 제안 탭으로. 여기서부터 갈래 칩이 뜬다.
  dom.document.querySelector('.mode-tab[data-mode="sourcing"]').fire("click");
  return { dom: dom, fetch: fetch };
}

function previewCalls(fetch) {
  return fetch.calls.filter(function (c) { return c.url === "/api/deals/preview"; });
}

// --- ① 갈래를 누르면 미리보기를 다시 부른다 ---------------------------------

const a = setup();
const before = previewCalls(a.fetch).length;
pickBucket(a.dom, MNA);
assert.ok(previewCalls(a.fetch).length > before,
          "갈래를 눌렀는데 미리보기를 다시 부르지 않았다");

// --- ② 누른 갈래가 서버로 나간다 --------------------------------------------

const b = setup();
pickBucket(b.dom, MNA);
let last = previewCalls(b.fetch).pop();
assert.strictEqual(last.body.bucket, MNA,
                   "누른 갈래가 안 나갔다: " + JSON.stringify(last.body.bucket));
assert.strictEqual(last.body.mode, "sourcing");

pickBucket(b.dom, SERIES_A);
last = previewCalls(b.fetch).pop();
assert.strictEqual(last.body.bucket, SERIES_A, "갈래를 바꿨는데 옛 갈래가 나갔다");

// '전체' 로 되돌리면 갈래가 빈다 — 서버는 그때만 첫 갈래로 돌아간다.
pickBucket(b.dom, "");
last = previewCalls(b.fetch).pop();
assert.strictEqual(last.body.bucket, "", "'전체' 인데 갈래가 실려 나갔다");

// --- 목록 거르기는 그대로다 --------------------------------------------------
//
// 미리보기를 따라오게 하면서 원래 하던 일(목록 거르기)이 빠지면 안 된다.

const c = setup();
pickBucket(c.dom, MNA);
const shown = c.dom.sourcingCards.filter(function (card) { return !card.hidden; })
  .map(function (card) { return card.getAttribute("data-bucket"); });
assert.deepStrictEqual(shown, [MNA], "갈래를 눌렀는데 목록이 안 걸러졌다");

console.log("ok - 갈래를 누르면 그 갈래로 미리보기가 따라온다");
