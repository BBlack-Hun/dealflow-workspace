// 넓은 표의 **가로 스크롤바가 화면 안에 남아 있는가.** (node tests/js/table_fit_test.js)
//
// ## 이 검사가 잡는 것
//
// 표 위쪽 머리 영역(머리말·툴바·요약 패널)이 자라면, 표는 그만큼 아래에서
// 시작한다. 표 키를 `100vh - 상수` 로 자르면 머리가 그 상수를 넘는 순간
// 표의 아래쪽 끝 — **가로 스크롤바가 붙어 있는 자리** — 가 화면 밖으로
// 나간다. 옆으로 밀려면 끝까지 내려갔다가 다시 올라와야 한다.
//
// 실제로 그렇게 났다. 상수는 320px 이었는데 브라우저에서 잰 머리 높이는:
//
//     딜 소싱 291 · IR 기업 현황 301 · 투자사 관리 현황 443 · 스타트업DB 478px
//
// 투자사 관리 현황·스타트업DB 는 스크롤바가 화면 아래 123·158px 밖에 있었다.
// 머리는 칸·패널이 붙을 때마다 또 자란다 — **다음에 또 나면 여기가 빨개진다.**
//
// ## 어떻게 보는가
//
// `table_fit.js` 를 그대로 돌려 `--head` 를 받아 내고, CSS 규칙
// (`max-height: calc(100vh - var(--head))` · `min-height`)을 그대로 적용해
// 감싸개의 키를 낸 다음, 아래쪽 끝이 화면 안인지 본다. 규칙을 옮겨 적은
// 곳은 `applyCss` 한 군데뿐이고, 그 모양이 CSS 와 어긋나지 않는지는
// tests/test_table_scroll_fit.py 가 따로 지킨다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "table_fit.js");
const CSS = path.join(__dirname, "..", "..", "app", "static", "css", "app.css");

// 숫자는 **원본에서 뽑아 쓴다.** 여기에 옮겨 적으면 두 벌이 되어, 원본만
// 고쳐졌을 때 이 검사는 이미 없는 규칙을 보증하게 된다.
const FLOOR = (function () {
  const m = /min-height:\s*min\((\d+)px,\s*calc\(100vh - var\(--head\)\)\)/
    .exec(fs.readFileSync(CSS, "utf8"));
  assert.ok(m, "app.css 의 `.table-wrap.wide` 최소 키 규칙 모양이 바뀌었다 — " +
               "아래 applyCss 도 같이 고쳐야 한다");
  return parseInt(m[1], 10);
})();

// ── 아주 작은 화면 ────────────────────────────────────────────────────────
// 이 DOM 에는 배치가 없다. 검사가 **자리를 직접 말해 주고**(`top`), 화면
// 코드가 그 자리를 어떻게 쓰는지만 본다.
function makeWrap(opts) {
  const style = {};
  return {
    top: opts.top,                       // 문서 맨 위에서 감싸개까지
    natural: opts.natural,               // 안 자르면 표가 가질 키
    fit: opts.fit || "under",            // CSS 가 정하는 맞춤 방식
    style: {
      setProperty(k, v) { style[k] = v; },
      getPropertyValue(k) { return style[k] === undefined ? "" : style[k]; },
    },
    getBoundingClientRect() { return { top: this.top }; },   // 스크롤 0 에서 잰다
  };
}

let GAP = null;          // table_fit.js 가 감싸개 아래 남기는 틈 (원본에서 받는다)

function run(wraps, innerH) {
  const ctx = {
    console: console,
    module: { exports: {} },
    document: {
      querySelectorAll(sel) {
        assert.strictEqual(sel, ".table-wrap.wide", "잴 대상이 바뀌었다");
        return wraps;
      },
    },
    window: { innerHeight: innerH, pageYOffset: 0, addEventListener() {} },
    getComputedStyle(el) {
      return { getPropertyValue(k) { return k === "--fit" ? el.fit : ""; } };
    },
    requestAnimationFrame(fn) { fn(); },
  };
  ctx.window.document = ctx.document;
  vm.runInNewContext(fs.readFileSync(SRC, "utf8"), ctx, { filename: "table_fit.js" });
  GAP = ctx.module.exports.GAP;
  assert.strictEqual(typeof GAP, "number", "table_fit.js 가 GAP 을 안 내보낸다");
}

// CSS 규칙을 그대로 적용해 감싸개의 최종 키를 낸다.
//   max-height: calc(100vh - var(--head))
//   min-height: min(320px, calc(100vh - var(--head)))   ← min-height 가 이긴다
function applyCss(wrap, innerH) {
  const head = parseFloat(wrap.style.getPropertyValue("--head"));
  assert.ok(!Number.isNaN(head), "--head 를 안 채웠다");
  const room = innerH - head;
  const maxH = Math.max(0, room);
  const minH = Math.max(0, Math.min(FLOOR, room));
  return Math.max(minH, Math.min(wrap.natural, maxH));
}

// 브라우저에서 실제로 잰 자리들. 앞의 넷은 데스크톱(1512×1080),
// 폰은 사이드바가 표 위로 쌓여 머리가 훨씬 깊다.
const REAL = [
  { name: "딜 소싱",          top: 291,  natural: 1025 },
  { name: "IR 기업 현황",     top: 301,  natural: 16235 },
  { name: "투자사 관리 현황", top: 443,  natural: 6236 },
  { name: "스타트업DB",       top: 478,  natural: 799 },
];
const HEIGHTS = [1080, 900, 768];

// ── 1) ★ 쉬는 자리에서 가로 스크롤바가 화면 안에 있다 ──────────────────────
//
// 여기가 이 기능의 전부다. 머리가 얼마나 깊든, 감싸개의 아래쪽 끝은 화면
// 안이어야 한다 — 그래야 표를 보면서 그대로 옆으로 밀 수 있다.
for (const h of HEIGHTS) {
  for (const spec of REAL) {
    const wrap = makeWrap(spec);
    run([wrap], h);
    const height = applyCss(wrap, h);
    assert.ok(
      spec.top + height <= h,
      `${spec.name} (창 ${h}px, 머리 ${spec.top}px): 감싸개 아래쪽 끝이 ` +
      `${spec.top + height}px — 화면(${h}px) 밖이다. 가로 스크롤바가 안 보인다.`
    );
  }
}

// ── 2) 감싸개는 화면 한 장보다 크지 않다 ───────────────────────────────────
//
// 폰은 머리(650~1,030px)가 화면(844px)보다 깊어서 1) 이 애초에 불가능하다.
// 대신 감싸개가 화면보다 작아야 **한 번 밀면** 표와 가로 스크롤바를 함께
// 볼 수 있다. 크면 끝까지 내렸다 올라오는 그 고생이 그대로 돌아온다.
for (const top of [650, 811, 1032]) {
  const wrap = makeWrap({ top: top, natural: 19645, fit: "screen" });
  run([wrap], 844);
  const height = applyCss(wrap, 844);
  assert.ok(height <= 844 - GAP,
    `폰(머리 ${top}px): 감싸개 키 ${height}px 는 화면(844px)보다 크다`);
  assert.ok(height > FLOOR, `폰(머리 ${top}px): 표가 ${height}px 로 너무 얇다`);
}

// ── 3) 첫 화면 밖에서 시작하는 표는 통째로 사라지지 않는다 ────────────────
//
// IR 발송처럼 표가 페이지 중간의 한 토막이면 감싸개가 화면 밖(1,208px)에서
// 시작한다. 그 자리에 `머리 밑에 맞추기`를 그대로 쓰면 남는 자리가 0 이하라
// 표가 0px 로 접힌다 — 화면에서 표가 없어진다.
{
  const wrap = makeWrap({ top: 1208, natural: 504 });      // fit 은 under 그대로
  run([wrap], 768);
  const height = applyCss(wrap, 768);
  assert.ok(height > 0, "첫 화면 밖에서 시작하는 표가 0px 로 접혔다");
  assert.ok(height <= 768 - GAP, `감싸개 키 ${height}px 가 화면보다 크다`);
}

// ── 4) 상수로 되돌리면 빨개진다 ────────────────────────────────────────────
//
// 이 검사가 **정말 무엇을 보는지** 못 박는다. `--head` 를 예전처럼 320px
// 상수로 두면 1) 이 깨져야 한다 — 안 깨지면 위 검사들은 아무것도 안 지킨다.
{
  const wrap = makeWrap({ top: 478, natural: 799 });
  wrap.style.setProperty("--head", "320px");               // 예전 방식 흉내
  const height = applyCss(wrap, 1080);
  assert.ok(478 + height > 1080,
    "상수 320px 로 두어도 스크롤바가 화면 안이라면, 1) 은 아무것도 안 지킨다");
}

// ── 5) 같은 값을 다시 쓰지 않는다 ─────────────────────────────────────────
//
// ResizeObserver 가 이 파일을 다시 부르는데, 매번 style 을 건드리면 배치가
// 또 바뀌어 서로를 깨우는 고리가 된다.
{
  const wrap = makeWrap({ top: 301, natural: 16235 });
  let writes = 0;
  const real = wrap.style.setProperty.bind(wrap.style);
  wrap.style.setProperty = function (k, v) { writes += 1; real(k, v); };
  run([wrap], 1080);
  const first = writes;
  run([wrap], 1080);                                        // 같은 자리에서 다시
  assert.strictEqual(writes, first, "값이 그대로인데 style 을 다시 썼다");
}

console.log("table_fit_test.js ok");
