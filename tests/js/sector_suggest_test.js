// 빈 `사업분야` 칸을 열었을 때, 서버가 골라 준 후보가 **맨 앞에 서는가.**
// (node tests/js/sector_suggest_test.js)
//
// 후보는 `data-suggest` 로 칸에 실려 온다. 화면이 해야 할 일은 딱 둘이다.
//
//   1. 그 값들을 고를 보기 **맨 앞**으로 옮기고 표시를 남긴다.
//   2. 나머지 보기는 하나도 없애지 않는다 — 후보가 다 틀렸을 때 사람이
//      아래에서 원래 값을 골라야 한다.
//
// **보기를 새로 만들면 안 된다.** 후보는 이미 그 칸에 쓰이고 있는 값 중에서
// 온 것이라(services/sector_hint.py) 목록에 원래 들어 있다. 목록에 없는 값을
// 후보라고 끼워 넣으면, 사람이 그걸 누르는 순간 **쓰이지 않던 갈래가 다시
// 생긴다** — 없애려던 오염을 제안 기능이 도로 만드는 셈이다.
//
// inline_edit.js 는 통째로 못 불러온다(불러오는 순간 document 를 찾는다).
// filter_loop_test.js 와 같은 방식으로 **파일에 든 그 함수를 떼어 내** 돌린다 —
// 베껴 두면 원본이 바뀌어도 테스트만 옛 규칙을 지키며 통과한다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const INLINE = fs.readFileSync(path.join(SRC, "inline_edit.js"), "utf8");

function lift(src, name) {
  const at = src.indexOf("function " + name + "(");
  assert.ok(at >= 0, name + " 이(가) inline_edit.js 에 없다");
  let depth = 0;
  let i = src.indexOf("{", at);
  for (; i < src.length; i++) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) break; }
  }
  return new Function("return (" + src.slice(at, i + 1) + ");")();
}

const suggestedFirst = lift(INLINE, "suggestedFirst");

// 표에 실제로 쓰이고 있는 갈래들(= 고를 보기). 가상값이다.
const USED = ["AI·SaaS·데이터", "ESG·푸드·애그테크", "딥테크·제조",
              "커머스·라이프스타일", "헬스케어·바이오"];

// 1 — 후보가 맨 앞으로, 적어 준 차례 그대로.
{
  const got = suggestedFirst(USED, "딥테크·제조|헬스케어·바이오");
  assert.deepStrictEqual(got.suggested, ["딥테크·제조", "헬스케어·바이오"]);
  assert.deepStrictEqual(got.order.slice(0, 2), ["딥테크·제조", "헬스케어·바이오"],
    "후보가 맨 앞에 서지 않으면 다섯 줄을 훑어 찾아야 한다");
}

// 2 — 보기가 하나도 줄지 않는다.
{
  const got = suggestedFirst(USED, "딥테크·제조");
  assert.strictEqual(got.order.length, USED.length,
    "후보를 앞으로 옮기면서 고를 보기가 줄었다 — 후보가 다 틀리면 고를 것이 없어진다");
  USED.forEach(function (v) {
    assert.ok(got.order.indexOf(v) !== -1, v + " 이(가) 목록에서 사라졌다");
  });
}

// 3 — 후보가 없으면 차례도 그대로다.
{
  ["", null, undefined, "   ", "|"].forEach(function (raw) {
    const got = suggestedFirst(USED, raw);
    assert.deepStrictEqual(got.suggested, [], "후보가 없는데 있다고 했다");
    assert.deepStrictEqual(got.order, USED,
      "후보가 없으면 원래 차례 그대로여야 한다");
  });
}

// 4 — **목록에 없는 후보는 버린다.** 이 검사가 오염을 막는 자리다.
{
  const got = suggestedFirst(USED, "핀테크·블록체인|딥테크·제조");
  assert.deepStrictEqual(got.suggested, ["딥테크·제조"],
    "표에 없는 갈래를 후보로 세웠다 — 누르는 순간 쓰이지 않던 값이 다시 생긴다");
  assert.strictEqual(got.order.indexOf("핀테크·블록체인"), -1,
    "표에 없는 갈래가 고를 보기에 끼어들었다");
  assert.strictEqual(got.order.length, USED.length);
}

// 5 — 같은 후보가 두 번 와도 한 번만 선다.
{
  const got = suggestedFirst(USED, "딥테크·제조|딥테크·제조");
  assert.deepStrictEqual(got.suggested, ["딥테크·제조"]);
  assert.strictEqual(got.order.length, USED.length,
    "같은 값이 목록에 두 번 실렸다");
}

// 6 — 앞뒤 공백은 다듬어 견준다(서버가 `|` 로 이어 보낸다).
{
  const got = suggestedFirst(USED, " 딥테크·제조 | 헬스케어·바이오 ");
  assert.deepStrictEqual(got.suggested, ["딥테크·제조", "헬스케어·바이오"]);
}

// 7 — 화면이 그 함수를 실제로 부르고, 후보에 표시를 남기는가.
//     (규칙은 위에서 돌려 봤고, 여기서는 **연결**만 본다)
{
  assert.ok(/var picked = suggestedFirst\(used, cell\.getAttribute\("data-suggest"\)\)/
    .test(INLINE), "고를 보기를 만들 때 suggestedFirst 를 부르지 않는다");
  assert.ok(/suggested\.indexOf\(value\) !== -1 \? " suggested" : ""/.test(INLINE),
    "후보 딱지에 표시(`suggested`)를 남기지 않는다 — 어느 것이 추천인지 알 수 없다");
  assert.ok(/한줄 소개를 보고 고른 후보/.test(INLINE),
    "이 값이 어디서 왔는지 알려 주는 말이 없다");
}

// 8 — 칸 옆 안내 딱지를 눌러도 그 칸이 열려야 한다(빈 칸은 누를 자리가 없다).
{
  assert.ok(/closest\("\.cell-hint"\)/.test(INLINE),
    "`.cell-hint` 를 눌러도 칸이 열리지 않는다 — 빈 칸은 누를 자리가 한 줄뿐이다");
}

console.log("sector_suggest_test OK");
