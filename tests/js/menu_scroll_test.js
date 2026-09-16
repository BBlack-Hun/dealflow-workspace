// 눕힌 줄이 **지금 있는 자리**를 보여 주는가. (node tests/js/menu_scroll_test.js)
//
// 390px 에서 잰 것을 그대로 넣는다. 메뉴 줄은 1,015px 인데 보이는 폭은 390px
// 이고, 활성 항목은 화면마다 다른 자리에 있다:
//
//     주간 업무 84–177 · 딜 제안 관리 181–265 · 투자사 관리 현황 269–376
//     스타트업 380–447 · IR 기업 현황 451–535 · 딜 진행 관리 602–687
//     투자컨설턴트 779–868 · 업무 보고 872–942 · 팀 현황 946–1005
//
// 뒤의 여섯은 줄 밖이었다. 아래 검사는 **여섯이 안으로 들어오고, 앞의 셋은
// 가만히 있고, 넓은 화면(줄이 안 밀릴 때)에서는 아무 일도 안 하는지** 본다.
"use strict";
const assert = require("assert");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "menu_scroll.js");
// 브라우저가 아니므로 `window` 도 `document` 도 없다 — 그러면 이 파일은
// 스스로 돌지 않고 셈만 내어 준다.
const { pullIntoView, pullAll, EDGE, STRIPS } = require(SRC);

// ── 아주 작은 줄 ──────────────────────────────────────────────────────────
// 배치가 없다. 검사가 자리를 직접 말해 주고(`scrollWidth`·항목의 자리),
// 화면 코드가 그 자리를 어떻게 쓰는지만 본다.
function makeStrip(opts) {
  const clientWidth = opts.clientWidth;
  const strip = {
    scrollWidth: opts.scrollWidth,
    clientWidth,
    scrollLeft: opts.scrollLeft || 0,
    getBoundingClientRect() { return { left: 0, right: clientWidth }; },
    querySelector(sel) { return sel === opts.activeSelector ? strip._active : null; },
  };
  strip._active = opts.active === null ? null : {
    getBoundingClientRect() {
      // 줄 안에서의 자리 — 줄을 민 만큼 왼쪽으로 따라 움직인다.
      return { left: opts.active[0] - strip.scrollLeft,
               right: opts.active[1] - strip.scrollLeft };
    },
  };
  if (opts.active === null) strip._active = null;
  return strip;
}

function visible(strip) {
  const br = strip.getBoundingClientRect();
  const ar = strip._active.getBoundingClientRect();
  return ar.left >= br.left - 0.5 && ar.right <= br.right + 0.5;
}

// ── 1. 줄 밖이던 여섯이 들어온다 ──────────────────────────────────────────
const MENU = { scrollWidth: 1015, clientWidth: 390, activeSelector: ".menu-item.active" };
const 잰값 = [
  ["주간 업무", 84, 177, true],
  ["딜 제안 관리", 181, 265, true],
  ["투자사 관리 현황", 269, 376, true],
  ["스타트업", 380, 447, false],
  ["IR 기업 현황", 451, 535, false],
  ["딜 진행 관리", 602, 687, false],
  ["투자컨설턴트", 779, 868, false],
  ["업무 보고", 872, 942, false],
  ["팀 현황", 946, 1005, false],
];
for (const [이름, left, right, 처음에_보였나] of 잰값) {
  const strip = makeStrip(Object.assign({ active: [left, right] }, MENU));
  assert.strictEqual(visible(strip), 처음에_보였나,
    `${이름}: 잰 값이 바뀌었다 — 검사가 딛고 선 자리가 사라졌다`);
  const moved = pullIntoView(strip, MENU.activeSelector);
  assert.ok(visible(strip), `${이름} 이 끌어온 뒤에도 줄 밖이다`);
  assert.strictEqual(moved, !처음에_보였나,
    `${이름}: 이미 보이는데 줄을 밀었거나, 밖인데 안 밀었다`);
  // **끝에 딱 붙이지 않는다** — 옆에 더 있다는 것이 보여야 민다는 것을 안다.
  if (!처음에_보였나) {
    const ar = strip._active.getBoundingClientRect();
    assert.strictEqual(Math.round(strip.clientWidth - ar.right), EDGE,
      `${이름}: 줄 끝에 딱 붙었다 — 옆이 더 있는지 보이지 않는다`);
  }
}

// ── 2. 안 밀리는 줄은 건드리지 않는다 ─────────────────────────────────────
// 넓은 화면에서 메뉴는 세로라 `scrollWidth === clientWidth` 다(1440px 에서
// 200/200 으로 쟀다). 여기서 손대면 넓은 화면의 모양이 바뀐다.
{
  const strip = makeStrip({ scrollWidth: 200, clientWidth: 200, scrollLeft: 0,
                            active: [8, 192], activeSelector: ".menu-item.active" });
  assert.strictEqual(pullIntoView(strip, ".menu-item.active"), false,
    "안 밀리는 줄을 밀었다 — 넓은 화면에서도 도는 코드다");
  assert.strictEqual(strip.scrollLeft, 0, "넓은 화면에서 줄이 움직였다");
}

// ── 3. 왼쪽으로 나간 것도 끌어온다 ────────────────────────────────────────
// 줄을 손으로 밀어 둔 채 화면을 옮기면(브라우저가 자리를 되살리는 경우)
// 활성 항목이 왼쪽 밖에 있을 수 있다.
{
  const strip = makeStrip(Object.assign({ active: [84, 177], scrollLeft: 400 }, MENU));
  assert.ok(!visible(strip), "검사가 세운 자리가 틀렸다");
  assert.strictEqual(pullIntoView(strip, MENU.activeSelector), true);
  assert.ok(visible(strip), "왼쪽으로 나간 것을 안 끌어왔다");
  const ar = strip._active.getBoundingClientRect();
  assert.strictEqual(Math.round(ar.left), EDGE, "왼쪽 끝에 딱 붙었다");
}

// ── 4. 켜진 것이 없으면 아무 일도 안 한다 ─────────────────────────────────
{
  const strip = makeStrip(Object.assign({ active: null }, MENU));
  assert.strictEqual(pullIntoView(strip, MENU.activeSelector), false);
  assert.strictEqual(strip.scrollLeft, 0);
}

// ── 5. 명단 탭도 같은 자리다 ──────────────────────────────────────────────
// 투자컨설턴트의 세 번째 탭을 고르면 그 탭이 262–426 인데 줄은 362px 이다.
// 명단이 늘수록 더 뒤로 가므로, 메뉴만 고치면 반쪽이다.
{
  assert.deepStrictEqual(STRIPS.map((s) => s[0]), [".menu", ".sheet-tabs"],
    "눕는 줄 목록이 바뀌었다 — 아래 검사도 같이 고쳐야 한다");
  const strip = makeStrip({ scrollWidth: 478, clientWidth: 362, scrollLeft: 0,
                            active: [262, 426], activeSelector: ".sheet-tab.active" });
  assert.ok(!visible(strip), "잰 값이 바뀌었다");
  assert.strictEqual(pullIntoView(strip, ".sheet-tab.active"), true);
  assert.ok(visible(strip), "고른 탭이 줄 밖 그대로다");
}

// ── 6. 훑기가 두 줄을 다 본다 ─────────────────────────────────────────────
{
  const menu = makeStrip(Object.assign({ active: [946, 1005] }, MENU));
  const tabs = makeStrip({ scrollWidth: 478, clientWidth: 362, scrollLeft: 0,
                           active: [262, 426], activeSelector: ".sheet-tab.active" });
  const doc = {
    querySelectorAll(sel) {
      if (sel === ".menu") return [menu];
      if (sel === ".sheet-tabs") return [tabs];
      return [];
    },
  };
  assert.strictEqual(pullAll(doc), 2, "두 줄 중 하나만 끌어왔다");
  assert.ok(visible(menu) && visible(tabs));
}

console.log("menu_scroll_test 통과");
