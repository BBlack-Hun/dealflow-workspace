"use strict";
/* IR 요청 투자사 — 줄 지우기의 **확인창**. (node tests/js/closed_delete_confirm_test.js)
 *
 * 서버 쪽(그 줄만 지워지나 · 남의 줄이 막히나 · 로그에 남나)은 파이썬 검사가
 * 본다(`tests/test_closed_followup_delete.py`). 브라우저에서만 잴 수 있는
 * 것은 확인창 하나다.
 *
 *   · [취소] 를 누르면 **정말 안 나가는가** — `onsubmit` 이 거짓을 돌려주지
 *     않으면 확인창은 장식이고, 사람은 취소했다고 믿은 채 줄을 잃는다.
 *   · [확인] 을 누르면 나가는가.
 *   · 문구가 **되살아난다는 것을 말하는가** — 지운 뒤 [지난 발송에서 리마인드
 *     걸기] 를 누르면 같은 줄이 다시 선다. 그 말이 없으면 사람은 고장으로
 *     읽고, 고장이라고 믿으면 다시 지우려 든다.
 *   · 문구가 **무엇이 남는지** 말하는가 — 지우는 것은 이 표의 줄 하나지
 *     투자사가 아니다.
 *
 * 규칙을 옮겨 적지 않는다 — **화면에 실제로 실리는 그 속성**을 파일에서 뽑아
 * 그대로 돌린다. 베껴 두면 화면만 죽어 있는 상태가 된다.
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const PANEL = fs.readFileSync(
  path.join(ROOT, "app", "templates", "_closed_followups.html"), "utf8");

// ── 지우기 단추가 달린 폼을 찾는다 ──────────────────────────────────────────
const form = PANEL.match(
  /<form[^>]*action="\/followups\/\{\{ r\.id \}\}\/delete"([\s\S]*?)<\/form>/);
assert.ok(form, "줄 지우기 폼(`/followups/{id}/delete`)이 화면에 없다");

const onsubmit = form[1].match(/onsubmit="([\s\S]*?)"\s*>/);
assert.ok(onsubmit, "지우기 폼에 onsubmit 이 없다 — 확인 없이 지워진다");
const HOOK = onsubmit[1];

assert.ok(/\bconfirm\s*\(/.test(HOOK),
  "이 저장소의 다른 위험 조작과 달리 브라우저 confirm() 을 안 쓴다");

// ── [취소] 를 누르면 폼이 안 나간다 ─────────────────────────────────────────
function submit(answer) {
  const asked = [];
  const sandbox = { confirm(m) { asked.push(String(m)); return answer; } };
  vm.createContext(sandbox);
  // 브라우저가 `onsubmit` 속성을 다루는 방식 그대로 — 함수 몸통으로 감싼다.
  const went = vm.runInContext("(function () { " + HOOK + " })()", sandbox,
                               { filename: "_closed_followups.html#onsubmit" });
  return { went: went, asked: asked };
}

{
  const no = submit(false);
  assert.strictEqual(no.asked.length, 1, "확인창을 한 번 띄워야 한다");
  assert.strictEqual(no.went, false,
    "[취소] 를 눌렀는데 폼이 나간다 — 확인창이 장식이다");

  const yes = submit(true);
  assert.strictEqual(yes.went, true, "[확인] 을 눌렀는데 폼이 안 나간다");
}

// ── 문구가 말해야 하는 것 ───────────────────────────────────────────────────
{
  const text = submit(false).asked[0];

  assert.ok(/지울까요\?/.test(text), "무엇을 하려는지 안 묻는다: " + text);
  assert.ok(text.indexOf("IR 요청 투자사") >= 0,
    "어느 표에서 없애는 것인지 안 말한다: " + text);
  assert.ok(text.indexOf("지난 발송에서 리마인드 걸기") >= 0,
    "**되살아난다는 것**을 안 말한다 — 지웠는데 다시 생기면 고장으로 읽는다: " + text);
  assert.ok(/명단/.test(text) && /발송 기록/.test(text),
    "무엇이 남는지 안 말한다 — 투자사를 지우는 줄 안다: " + text);

  // 줄바꿈이 실제로 줄바꿈이어야 한다. `\n` 이 글자 그대로 보이면 한 줄이 된다.
  assert.ok(text.indexOf("\n") > 0, "확인 문구가 한 줄로 붙어 있다: " + text);
  assert.ok(text.indexOf("\\n") < 0, "`\\n` 이 글자 그대로 보인다: " + text);
}

// ── 표 머리의 [지난 발송에서 리마인드 걸기] 와 다른 문구여야 한다 ───────────
//
// 두 조작이 같은 말을 하면 어느 쪽을 누른 것인지 확인창을 보고도 모른다.
{
  const backfill = PANEL.match(
    /action="\/followups\/backfill"[\s\S]*?onsubmit="([\s\S]*?)"\s*>/);
  assert.ok(backfill, "[지난 발송에서 리마인드 걸기] 의 확인창을 못 찾았다");
  assert.notStrictEqual(backfill[1], HOOK, "두 조작의 확인 문구가 똑같다");
}

console.log("ok closed_delete_confirm_test");
