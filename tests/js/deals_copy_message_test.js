// 미리보기 문구를 **복사할 수 있는가.** (node tests/js/deals_copy_message_test.js)
//
// 자료 전달은 앱이 보내 주지 않는다 — 사람이 PC 카톡에 자료를 손으로 붙이고
// 문구도 손으로 보낸다. 그러면 화면에 그린 문구를 집어갈 수 있어야 한다.
//
// 지킬 것은 셋이다.
//
//  1. 담기는 것이 **실제로 나갈 문구 그대로**여야 한다. 화면의 머리말
//     ("가담당 심사역 · 💬 방이름 · 재연락")이나 "3통으로 나갑니다" 같은
//     안내가 섞이면 그것까지 카톡에 붙는다.
//  2. 담당자를 여럿 고르면 문구도 여럿이다 — **지금 열어 둔 탭**의 것이어야
//     한다. 옆의 [보낼 자료] 목록도 같은 탭을 따르므로, 둘이 다른 담당자를
//     가리키면 엉뚱한 자료가 붙는다.
//  3. 눌렀다는 것이 **보여야** 한다. 아무 일도 안 나면 복사된 줄 알고 빈 것을
//     붙여 넣는다 — `navigator.clipboard` 는 https·localhost 가 아니면 아예
//     없어서 실제로 그런 일이 난다.
//
// 화면은 `_deals_dom.js` 가 세우고, deals.js 는 그대로 돌린다.
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

const A = "가나애그";
const B = "다라헬스";

// 아주 작은 약속 — deals.js 가 `.then(성공, 실패)` 로 받는다.
function resolved(value) {
  return { then: function (ok) { if (ok) ok(value); return this; } };
}
function rejected() {
  return { then: function (ok, bad) { if (bad) bad(); return this; } };
}

// `navigator.clipboard` 가 있는 브라우저(https·localhost). 담은 글자를 모아 둔다.
function withClipboard(box, fail) {
  return {
    clipboard: {
      writeText: function (text) {
        if (fail) return rejected();
        box.push(text);
        return resolved();
      }
    }
  };
}

function person(name, pairs) {
  return {
    contact_id: name.length,
    name: name,
    title: "심사역",
    room_name: name + " 심사역님",
    has_history: true,
    message: pairs.map(function (pair) {
      return pair[1] ? pair[1] + "번 기업 " + pair[0] : pair[0];
    }).join(", ") + " IR deck 먼저 전달드리겠습니다.",
    parts: [],
    warnings: [],
    attachments: pairs.map(function (pair) {
      return { name: pair[0], file: pair[0] + "_IR.pdf", no: pair[1] };
    })
  };
}

// 기업 둘을 고르고 미리보기를 받아 온 상태로 만든다.
function opened(previews, opts) {
  const fetch = deals_.fakeFetch([deals_.previewReply(previews)]);
  const dom = deals_.run(null, Object.assign({ fetch: fetch }, opts || {}));
  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, B);
  deals_.toggleCompany(dom, A);
  dom.document.getElementById("refresh-preview").fire("click");
  return dom;
}

function copyBtn(dom) {
  const btn = dom.document.getElementById("copy-message");
  assert.ok(btn, "미리보기에 복사 단추가 없다 — 문구는 사람이 손으로 보낸다");
  return btn;
}

const GA = person("가담당", [[B, 3], [A, 2]]);
const NA = person("나담당", [[B, 1], [A, 5]]);

// ── 1) ★ 담기는 것은 **실제로 나갈 문구 그대로** ───────────────────────────
{
  const copied = [];
  const dom = opened([GA], { navigator: withClipboard(copied) });

  copyBtn(dom).fire("click");
  assert.deepStrictEqual(copied, [GA.message],
    "복사된 것이 나갈 문구와 다르다: " + JSON.stringify(copied));

  // 화면 장식이 섞이지 않았는지 못박는다 — 머리말·방 이름은 화면의 것이다.
  assert.ok(copied[0].indexOf("💬") < 0, "방 이름 머리말이 섞였다: " + copied[0]);
  assert.ok(copied[0].indexOf("심사역") < 0, "직함 머리말이 섞였다: " + copied[0]);
  assert.ok(copied[0].indexOf("재연락") < 0, "화면 표시가 섞였다: " + copied[0]);
}

// ── 2) ★ **지금 열어 둔 탭**의 문구를 담는다 ───────────────────────────────
//
// 담당자를 여럿 고르면 문구도 여럿이다. 옆의 [보낼 자료] 목록도 같은 탭을
// 따르므로, 여기서 다른 탭 것을 담으면 번호와 문구가 다른 담당자를 가리킨다.
{
  const copied = [];
  const dom = opened([GA, NA], { navigator: withClipboard(copied) });

  copyBtn(dom).fire("click");
  assert.strictEqual(copied[0], GA.message, "첫 탭의 문구가 아니다");

  deals_.pickPreviewTab(dom, 1);
  copyBtn(dom).fire("click");
  assert.strictEqual(copied[1], NA.message,
    "탭을 바꿨는데 앞 담당자의 문구를 담았다: " + copied[1]);

  // 그 탭의 [보낼 자료] 번호와 같은 담당자인지 함께 본다.
  const rows = Array.prototype.slice
    .call(dom.document.getElementById("ir-links").children)
    .map(function (li) { return li.innerHTML; });
  assert.ok(/1번/.test(rows[0]) && /5번/.test(rows[1]),
    "복사한 문구와 [보낼 자료] 목록이 다른 담당자를 가리킨다: " + rows.join(" | "));
}

// ── 3) ★ 고친 문구를 담는다 — **나가는 것이 그것**이다 ─────────────────────
{
  const copied = [];
  const dom = opened([GA], { navigator: withClipboard(copied) });
  const ta = dom.document.getElementById("bubble-edit");

  ta.value = GA.message + "\n말씀 주신 자료 함께 보내드립니다.";
  ta.fire("input");

  copyBtn(dom).fire("click");
  assert.strictEqual(copied[0], ta.value,
    "고치기 전 문구를 담았다 — 나가는 것은 고친 쪽이다: " + copied[0]);
}

// ── 4) ★ 눌렀다는 것이 보인다 ──────────────────────────────────────────────
{
  const copied = [];
  const dom = opened([GA], { navigator: withClipboard(copied) });
  const btn = copyBtn(dom);
  const before = btn.textContent;

  assert.ok(before && before.indexOf("복사") >= 0,
    "단추에 무엇을 하는 것인지 안 적혀 있다: " + before);
  btn.fire("click");
  assert.notStrictEqual(btn.textContent, before,
    "복사하고도 단추 글자가 그대로다 — 됐는지 알 수 없다");
  assert.ok(/복사했/.test(btn.textContent), "됐다는 말이 아니다: " + btn.textContent);
}

// ── 5) ★ `navigator.clipboard` 가 없어도 복사가 된다 ───────────────────────
//
// https 나 localhost 가 아니면 그 물건이 **아예 없다**(사내에서 http 로 여는
// 화면이 그렇다). 옛 방식으로 한 번 더 해 본다.
{
  const dom = opened([GA]);            // navigator 를 안 준다 = 클립보드 없음
  const ta = dom.document.getElementById("bubble-edit");
  let selected = false;
  let asked = null;
  ta.select = function () { selected = true; };
  dom.document.execCommand = function (cmd) { asked = cmd; return true; };

  copyBtn(dom).fire("click");
  assert.ok(selected, "글자를 고르지도 않았다 — 옛 방식은 고른 것을 담는다");
  assert.strictEqual(asked, "copy", "옛 방식으로 복사를 해 보지 않았다");
  assert.ok(/복사했/.test(copyBtn(dom).textContent),
    "복사됐는데 안 됐다고 말한다: " + copyBtn(dom).textContent);
}

// ── 6) ★ 그마저 안 되면 **사람이 알 수 있게** 한다 ─────────────────────────
//
// 조용히 실패하는 것이 제일 나쁘다 — 복사된 줄 알고 빈 것을 붙여 넣는다.
// 골라 두고 그렇게 말해 준다(llm_brief.js 와 같은 방식).
{
  const dom = opened([GA]);            // 클립보드 없음
  const ta = dom.document.getElementById("bubble-edit");
  let selected = false;
  ta.select = function () { selected = true; };
  dom.document.execCommand = function () { return false; };   // 옛 방식도 막힘

  copyBtn(dom).fire("click");
  assert.ok(selected, "복사가 다 막혔는데 글자를 골라 두지도 않았다");
  assert.ok(/Ctrl/.test(copyBtn(dom).textContent),
    "손으로 복사하라는 말이 없다: " + copyBtn(dom).textContent);
}

// ── 7) ★ 클립보드가 있어도 **거절당하면** 마찬가지다 ───────────────────────
//
// 권한을 안 준 브라우저는 물건은 있는데 약속이 깨진다. 여기서 조용히 넘어가면
// 5·6 번의 대비가 무용지물이다.
{
  const dom = opened([GA], { navigator: withClipboard([], true) });
  const ta = dom.document.getElementById("bubble-edit");
  let selected = false;
  ta.select = function () { selected = true; };

  copyBtn(dom).fire("click");
  assert.ok(selected, "클립보드가 거절했는데 아무 대비도 없다");
  assert.ok(/Ctrl/.test(copyBtn(dom).textContent),
    "거절당한 것을 사람에게 안 알린다: " + copyBtn(dom).textContent);
}

console.log("ok — 미리보기 문구를 지금 보고 있는 담당자 것으로 복사한다");
