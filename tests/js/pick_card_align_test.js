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

assert.strictEqual(prop(CARD, "align-items"), "flex-start",
  "`.pick-card` 에 `align-items: flex-start` 가 없다 — 기본값(stretch)이면 " +
  "체크박스가 카드 키만큼 늘어나 카드마다 다른 자리에 선다");

for (const side of ["width", "height"]) {
  assert.ok(prop(BOX, side), `체크박스에 \`${side}\` 가 없다 — 키를 안 주면 늘어난다`);
}

// ── 2. 자리는 **계산된 값**이다 (손으로 민 값 금지) ─────────────────────────
//
// `margin-top: 3px` 이 있던 자리다. 그 값은 그때의 브라우저 기본 체크박스
// (13px)에 눈으로 맞춘 것이라, 체크박스가 20px 로 커지는 폰에서는 이미 틀렸다.

const boxMargin = prop(BOX, "margin") || prop(BOX, "margin-top");
assert.ok(/var\(--pick-line\)/.test(boxMargin) && /var\(--pick-box\)/.test(boxMargin),
  "체크박스 자리가 줄 키·상자 크기에서 나오지 않는다(손으로 민 값이면 폰에서 어긋난다): "
  + boxMargin);

const badgeMargin = prop(BADGE, "margin-top");
assert.ok(/var\(--pick-line\)/.test(badgeMargin) && /var\(--pick-badge\)/.test(badgeMargin),
  "번호 배지 자리가 줄 키·배지 크기에서 나오지 않는다: " + badgeMargin);

// ── 3. 몇 px 어긋나는가 ─────────────────────────────────────────────────────
//
// 카드 안쪽 위(padding 아래)를 0 으로 놓고 세운다. 세 조각 모두 같은 자리에서
// 시작하므로 카드 키·꼬리표 수·고름 여부와 상관이 없다 — 첫 줄만 보면 된다.

const TOLERANCE = 0.5;   // 픽셀 반 칸. 이보다 벌어지면 눈에 걸린다.
const lineCenter = LINE / 2;

/** `margin` 축약형의 **첫 값**(위쪽). 괄호 안의 빈칸에 속지 않게 짝을 센다. */
function topOf(shorthand) {
  let depth = 0, out = "";
  for (const ch of String(shorthand).trim()) {
    if (ch === "(") depth++;
    else if (ch === ")") depth--;
    else if (/\s/.test(ch) && depth === 0) break;
    out += ch;
  }
  return out;
}

function checkboxCenter(boxSize) {
  const top = px(topOf(boxMargin),
                 { "--pick-line": LINE, "--pick-box": boxSize });
  const size = px(prop(BOX, "height"), { "--pick-box": boxSize });
  return top + size / 2;
}

function badgeCenter() {
  const top = px(badgeMargin, { "--pick-line": LINE, "--pick-badge": BADGE_SIZE });
  const size = px(prop(BADGE, "height"), { "--pick-badge": BADGE_SIZE });
  return top + size / 2;
}

for (const [where, boxSize] of [["PC(>720px)", DESKTOP_BOX], ["폰(≤720px)", PHONE_BOX]]) {
  const off = checkboxCenter(boxSize) - lineCenter;
  assert.ok(Math.abs(off) <= TOLERANCE,
    `${where}: 체크박스가 이름 첫 줄에서 ${off.toFixed(1)}px 어긋난다 ` +
    `(줄 ${LINE}px · 상자 ${boxSize}px)`);
}

const badgeOff = badgeCenter() - lineCenter;
assert.ok(Math.abs(badgeOff) <= TOLERANCE,
  `고른 차례 번호가 이름 첫 줄에서 ${badgeOff.toFixed(1)}px 어긋난다`);

const badgeVsBox = badgeCenter() - checkboxCenter(DESKTOP_BOX);
assert.ok(Math.abs(badgeVsBox) <= TOLERANCE,
  `번호와 체크박스가 ${badgeVsBox.toFixed(1)}px 어긋나 서로 다른 줄에 선다 — ` +
  `번호는 문구에 나가는 차례 그 값이라(data-pick-order) 자리가 흔들리면 안 된다`);

// ── 4. 폰에서 누를 자리를 줄이지 않았는가 ───────────────────────────────────
//
// 폰 규칙은 체크박스를 20px 로 키워 둔다(#195). `.pick-card` 의 체크박스는
// 위 2번의 `width: var(--pick-box)` 가 그 규칙을 이기므로(선택자가 더 좁다),
// **변수도 같이 올라가 있어야** 손끝에 걸리는 크기가 그대로다.

const phoneGlobal = px(prop(PHONE_CB, "width"), {});
assert.strictEqual(PHONE_BOX, phoneGlobal,
  `폰에서 카드 체크박스가 ${PHONE_BOX}px 인데 다른 체크박스는 ${phoneGlobal}px 이다 — ` +
  `#195 에서 키워 둔 크기가 이 카드에서만 작아졌다`);
assert.ok(PHONE_BOX >= DESKTOP_BOX,
  "폰 체크박스가 PC 보다 작다 — 손가락으로 누르는 자리는 줄이지 않는다");

// 라벨 전체가 누를 자리다. 카드 안쪽 여백을 줄이면 그만큼 좁아진다.
assert.strictEqual(prop(CARD, "cursor"), "pointer", "카드가 누를 자리가 아니게 됐다");
assert.strictEqual(prop(CARD, "padding"), "10px", "카드 안쪽 여백이 줄었다 — 누를 자리가 좁아진다");

console.log(`ok — 줄 ${LINE}px · 체크박스 PC ${DESKTOP_BOX}px / 폰 ${PHONE_BOX}px · ` +
            `번호 ${BADGE_SIZE}px, 어긋남 0.0px`);
