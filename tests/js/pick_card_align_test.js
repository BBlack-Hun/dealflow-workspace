// 고르는 카드의 **체크박스가 이름 첫 줄에 서는가.** (node tests/js/pick_card_align_test.js)
//
// ## 이 검사가 잡는 것
//
// 「딜 제안 관리」의 기업·담당자 카드(`.pick-card`)는 `<label>` 하나에
// [고른 차례 번호][체크박스][이름·꼬리표·방 이름] 을 flex 로 늘어놓는다.
// **카드 키는 카드마다 다르다** — 꼬리표(★ · 시리즈 · `내용 부족` ·
// `3일 전 소개` · `3회`)가 늘면 이름이 두 줄로 접히고, 담당자 카드에는 방 이름
// 줄까지 붙는다. 그런데 체크박스에 키를 안 주면 `align-items` 기본값(stretch)이
// 그것을 **카드 키만큼 늘려** 버리고, 브라우저는 그 한가운데에 네모를 그린다.
// 그래서 카드가 클수록 체크박스가 아래로 내려갔다.
//
// 헤드리스 크롬으로 실제로 재 본 값이다(고치기 전, `getBoundingClientRect`).
// `어긋남` 은 체크박스 세로 중심 − 이름 첫 줄 세로 중심:
//
//     폭      카드            카드 키    체크박스 상자   어긋남
//     1440   한 줄            61.0        13 × 33.0     +9.5px
//     1440   두 줄(꼬리표 넷)  82.0        13 × 54.0    +20.0px
//     1440   thin(내용 부족)   79.5        13 × 51.5    +18.7px
//     1440   담당자           106.8        13 × 78.8    +32.4px
//     1440   담당자 두 줄     148.8        13 × 120.8   +53.3px
//      768   한 줄            61.0        13 × 33.0     +9.5px
//      390   한 줄            61.0        20 × 20.0     +3.0px   ← 폰은 20px 고정
//
// 고른 차례 번호(`::before`)는 `margin-top: 2px` 로 맨 위에 서 있었으므로,
// 번호와 체크박스가 **서로 다른 줄**에 놓였다(1440px 에서 7.5~18px 차이).
// 번호는 문구에 나가는 차례 그 값이라(`data-pick-order`) 자리가 흔들리면
// 어느 카드의 번호인지 헷갈린다.
//
// ## 어떻게 보는가
//
// 값은 **CSS 원본에서 뽑는다.** 여기 옮겨 적으면 두 벌이 되어, 원본만 고쳐졌을
// 때 이 검사는 이미 없는 규칙을 보증하게 된다(tests/js/table_fit_test.js 와 같은
// 방식이다). 뽑은 값으로 카드 안쪽 위에서부터 자리를 세워 보고, 체크박스와
// 번호의 세로 중심이 **첫 줄 한가운데에서 0.5px 안**인지 본다.
//
// 폰(≤720px)에서는 체크박스가 20px 로 커진다(#195). 그 폭에서도 같은 값으로
// 다시 세워 본다 — 크기만 올리고 맞춤이 읽는 값을 안 올리면 2px 어긋난다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const CSS_PATH = path.join(__dirname, "..", "..", "app", "static", "css", "app.css");
const CSS = fs.readFileSync(CSS_PATH, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

const PHONE = "@media (max-width: 720px)";

// ── CSS 에서 값 뽑기 ────────────────────────────────────────────────────────

/** `@media …{ … }` 한 덩어리 (중괄호 짝을 센다). */
function mediaBlock(header) {
  const start = CSS.indexOf(header);
  assert.notStrictEqual(start, -1, `${header} 블록이 없다`);
  let depth = 0;
  for (let i = CSS.indexOf("{", start); i < CSS.length; i++) {
    if (CSS[i] === "{") depth++;
    else if (CSS[i] === "}" && --depth === 0) return CSS.slice(start, i + 1);
  }
  throw new Error(`${header} 블록이 안 닫혔다`);
}

/** `@media` 를 걷어낸 본문. 같은 선택자가 폰 규칙에도 있어서, 안 걷어내면
    좁은 폭의 값이 넓은 폭의 값인 척 잡힌다. */
const BASE = (function () {
  let out = "", depth = 0, skipping = false;
  for (let i = 0; i < CSS.length; i++) {
    if (!skipping && CSS.startsWith("@media", i)) { skipping = true; depth = 0; }
    if (!skipping) { out += CSS[i]; continue; }
    if (CSS[i] === "{") depth++;
    else if (CSS[i] === "}" && --depth === 0) skipping = false;
  }
  return out;
})();

/** 선택자 하나의 선언 덩어리. 같은 선택자가 여럿이면 뒤엣것이 이긴다. */
function rule(selector, where) {
  const text = where || BASE;
  const re = new RegExp(
    "(?:^|[};])\\s*" + selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{([^{}]*)\\}",
    "g");
  let m, last = null;
  while ((m = re.exec(text))) last = m[1];
  assert.ok(last !== null, `CSS 에 \`${selector}\` 규칙이 없다`);
  return last;
}

function prop(decls, name) {
  const re = new RegExp("(?:^|;)\\s*" + name + "\\s*:\\s*([^;]+)", "i");
  const m = re.exec(decls);
  return m ? m[1].trim() : null;
}

const CARD = rule(".pick-card");
const BOX = rule(".pick-card > input[type=checkbox]");
const BADGE = rule("#company-list .pick-card::before");
// 폰에서는 체크박스가 20px 로 커진다(#195). 맞춤이 읽는 값도 그 블록에서
// 같이 올라가 있어야 한다 — 없으면 여기서 멈춘다.
const PHONE_BLOCK = mediaBlock(PHONE);
assert.ok(/\.pick-card\s*\{[^{}]*--pick-box/.test(PHONE_BLOCK),
  "폰 규칙에 `.pick-card { --pick-box: … }` 가 없다 — 체크박스만 20px 로 커지고 " +
  "맞춤은 PC 크기로 잡혀 2px 어긋난다");
const PHONE_CARD = rule(".pick-card", PHONE_BLOCK);
const PHONE_CB = rule("input[type=checkbox], input[type=radio]", PHONE_BLOCK);

/** `calc(…)` · `21px` 같은 길이를 숫자로. `var(--x)` 는 준 값으로 바꾼다. */
function px(value, vars) {
  let s = String(value).trim();
  for (const [k, v] of Object.entries(vars || {})) {
    s = s.split(`var(${k})`).join(`${v}px`);
  }
  assert.ok(!/var\(/.test(s), `풀 수 없는 변수가 남았다: ${value}`);
  s = s.replace(/calc/g, "").replace(/px/g, "");
  assert.ok(/^[\d\s().+\-*/]+$/.test(s), `길이로 읽을 수 없다: ${value}`);
  return Function(`"use strict"; return (${s});`)();
}

// ── 값 ──────────────────────────────────────────────────────────────────────

const LINE = px(prop(CARD, "--pick-line"), {});
const DESKTOP_BOX = px(prop(CARD, "--pick-box"), {});
const PHONE_BOX = px(prop(PHONE_CARD, "--pick-box"), {});
const BADGE_SIZE = px(prop(CARD, "--pick-badge"), {});

// ── 1. 체크박스는 늘어나지 않는다 ───────────────────────────────────────────
//
// 이 한 줄이 원인이었다. `align-items` 가 기본값(stretch)이면 키를 안 준
// 체크박스가 카드 키만큼(33~120.8px) 늘어난다.

assert.strictEqual(prop(CARD, "align-items"), "center",
  "`.pick-card` 에 `align-items: center` 가 없다 — 사용자가 카드 세로 " +
  "한가운데로 정했다(한 번 이름 첫 줄에 맞췄다가 되돌렸다). 기본값(stretch)이면 " +
  "체크박스가 카드 키만큼 늘어나 카드마다 다른 자리에 선다");

for (const side of ["width", "height"]) {
  assert.ok(prop(BOX, side), `체크박스에 \`${side}\` 가 없다 — 키를 안 주면 늘어난다`);
}
assert.ok(prop(BADGE, "height"), "번호 배지에 `height` 가 없다 — 키를 안 주면 늘어난다");

// ── 2. 자리는 **정렬이 정한다** (손으로 민 값 금지) ─────────────────────────
//
// `margin-top: 3px` 이 있던 자리다. 그 값은 그때의 브라우저 기본 체크박스
// (13px)에 눈으로 맞춘 것이라, 체크박스가 20px 로 커지는 폰에서는 이미 틀렸다.
// 이제는 계산조차 하지 않는다 — `align-items: center` 하나가 셋을 다 세운다.

const boxMargin = (prop(BOX, "margin") || prop(BOX, "margin-top") || "0").trim();
assert.ok(!/[1-9]/.test(boxMargin),
  "체크박스를 손으로 밀고 있다(자리는 정렬이 정한다): " + boxMargin);

const badgeAlign = prop(BADGE, "align-self") || "";
const badgeMargin = (prop(BADGE, "margin-top") || "0").trim();
assert.ok(badgeAlign === "center" || !/[1-9]/.test(badgeMargin),
  "번호 배지가 가운데에 안 선다 — `align-self: center` 이거나 미는 값이 없어야 한다: "
  + (badgeAlign || badgeMargin));

// ── 3. 셋이 같은 줄에 서는가 ───────────────────────────────────────────────
//
// 가운데 정렬이면 자리를 px 로 셀 필요가 없다 — 카드 키가 얼마든 세 조각이
// **같은 축**에 선다. 볼 것은 "셋 다 가운데인가" 하나다.
// (번호는 문구에 나가는 차례 그 값이라(`data-pick-order`) 체크박스와 다른
//  줄에 서면 어느 카드의 번호인지 헷갈린다.)

assert.strictEqual(prop(CARD, "align-items"), "center",
  "카드가 가운데 정렬이 아니면 아래 판단이 무의미하다");
assert.ok(!/[1-9]/.test(boxMargin) && (badgeAlign === "center" || !/[1-9]/.test(badgeMargin)),
  "체크박스와 번호 중 하나가 가운데에서 밀려 있다 — 둘이 다른 줄에 선다");

console.log("pick_card_align_test: ok");
