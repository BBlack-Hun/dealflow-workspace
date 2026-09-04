// IR 진행 관리의 [자료 보내기] — **그 자리에서 끝난다.**
// (node tests/js/ir_send_test.js)
//
// 예전에는 이 단추가 딜 제안 관리(`/deals`)로 화면을 통째로 옮겼다. 옮겨 간
// 화면에서 할 일은 이미 정해져 있었는데도(이 담당자 · 이 기업들 · 지금 보낸다)
// 넓은 발송 화면을 다시 읽어야 했고, 돌아올 길도 스스로 찾아야 했다.
//
// 이 검사가 지키는 것은 넷이다.
//   ① 화면이 **안 넘어간다** — 폼의 기본 동작이 막히고 그 자리에서 창이 열린다.
//   ② 번호·파일명·문구가 **서버가 준 그대로**다 — 화면이 세거나 짓지 않는다.
//      (그래서 딜 제안 관리의 목록과 갈릴 수가 없다 — 같은 응답, 같은 한 벌.)
//   ③ 발송은 **이미 있는 길**로 간다(`POST /api/deals/send`).
//   ④ 막히면 **막힌 이유가 뜬다** — 조용히 삼켜지지 않는다.
"use strict";
const assert = require("assert");

const ir_ = require("./_ir_dom.js");

const A = "가나애그";
const B = "다라헬스";

// 서버 미리보기 한 통. **번호는 서버 것**이다 — 고른 차례(1, 2)가 아니라
// 지난 딜 소개에서 붙은 번호(1, 3)이고, 문구도 그 번호로 짚는다.
function preview(over) {
  return Object.assign({
    contact_id: ir_.CONTACT_ID, name: ir_.NAME, title: "팀장", firm: "가나벤처스",
    room_name: "가담당 팀장님", room_from: "", room_verified: "verified",
    room_warning: null, has_history: true, sample: false, parts: [],
    char_count: 120, too_long: false, warnings: [],
    message: "가담당 팀장 안녕하세요.\n1번 기업 " + A + ", 3번 기업 " + B
      + " IR deck 먼저 전달드리겠습니다.",
    attachments: [
      { company_id: 11, name: A, file: A + "_IR.pdf", no: 1 },
      { company_id: 12, name: B, file: B + "_IR.pdf", no: 3 }
    ]
  }, over || {});
}

function previewReply(over) {
  return { ok: true, d: { previews: [preview(over)], auto_attach: false } };
}

const SENT = { ok: true, d: { job_id: 42, batch_id: 9, total: 1,
                              status: "queued", channel: "kakao" } };

// 문구에 적힌 번호 — `{기업명: 번호}`. 화면에 뜬 번호와 맞대 보려는 것이다.
function numbersInMessage(text) {
  const out = {};
  const re = /(\d+)번 기업 ([^\s,]+)/g;
  let m;
  while ((m = re.exec(text)) !== null) out[m[2]] = parseInt(m[1], 10);
  return out;
}

function opened(replies, opts) {
  const fetch = ir_.fakeFetch(replies);
  const dom = ir_.run(Object.assign({ fetch: fetch }, opts || {}));
  const prevented = ir_.pressDeliver(dom);
  return { dom: dom, fetch: fetch, prevented: prevented };
}

// ── ① 화면이 안 넘어간다 ────────────────────────────────────────────────────

(function theScreenStaysPut() {
  const s = opened([previewReply()]);

  assert.strictEqual(s.prevented, 1,
    "폼의 기본 동작을 안 막았다 — 브라우저가 그대로 /ir/deliver-guide 로 보낸다");
  assert.strictEqual(s.dom.window.location.href, "",
    "어디로도 옮기면 안 된다 — 그 자리에서 끝내는 것이 이 일의 전부다");
  assert.strictEqual(s.dom.modal.hidden, false, "창이 안 열렸다");
  // 뒷막은 띄울 때 만들고 닫을 때 지운다 — 숨겨 두면 `:has()` 가 계속 맞아
  // 창이 닫혀 있는데도 좌측 메뉴가 어두운 채로 남는다.
  assert.strictEqual(s.dom.root.querySelectorAll(".guard-backdrop").length, 1,
    "뒷막이 없다 — 뒤 화면이 그대로 눌린다");
  s.dom.document.getElementById("ir-send-close").fire("click");
  assert.strictEqual(s.dom.modal.hidden, true, "닫히지 않았다");
  assert.strictEqual(s.dom.root.querySelectorAll(".guard-backdrop").length, 0,
    "닫았는데 뒷막이 남았다 — 좌측 메뉴가 계속 어둡다");
}());

(function itAsksTheServerForThisContactAndTheseCompanies() {
  const s = opened([previewReply()]);
  const call = s.fetch.calls[0];

  assert.strictEqual(call.url, "/api/deals/preview",
    "미리보기를 서버에 안 물었다 — 화면이 문구를 지으면 두 벌이 된다");
  assert.deepStrictEqual(call.body, {
    mode: "ir", contact_ids: [ir_.CONTACT_ID], company_ids: ir_.COMPANY_IDS
  }, "화면이 실어 둔 담당자·기업 그대로 물어야 한다");
}());

// ── ② 번호·파일명·문구는 서버가 준 그대로 ────────────────────────────────────

(function theListShowsTheServersNumbersAndFiles() {
  const s = opened([previewReply()]);
  const rows = ir_.attachRows(s.dom);

  assert.strictEqual(rows.length, 2, "보낼 자료가 두 줄이어야 한다");
  assert.ok(rows[0].indexOf("1번") >= 0 && rows[0].indexOf(A) >= 0, rows[0]);
  assert.ok(rows[0].indexOf(A + "_IR.pdf") >= 0,
    "파일 이름이 없으면 어느 파일을 붙일지 알 수 없다: " + rows[0]);
  // 링크가 아니다(0056) — 파일은 각자 PC 에 있어서 브라우저가 열 자리가 없다.
  assert.ok(rows.join("").indexOf("<a ") < 0,
    "눌러도 아무 일이 없는 링크를 만들면 안 된다");
}());

(function theListNumbersMatchTheMessageNumbers() {
  // **여기가 이 일을 한 뜻이다.** 화면이 제 손으로 세면 목록은 `1, 2`, 문구는
  // `1번, 3번` 이 되어 어느 쪽이 맞는지 알 수 없다. 딜 제안 관리의 같은 검사
  // (`deals_ir_number_test.js`)와 **같은 것을 본다** — 두 화면이 한 벌을 쓰므로.
  const s = opened([previewReply()]);
  const shown = ir_.attachNumbers(s.dom, [A, B]);
  const said = numbersInMessage(
    s.dom.document.getElementById("ir-send-message").value);

  assert.deepStrictEqual(shown, said,
    "화면에 뜬 번호와 문구의 번호가 다르다: " + JSON.stringify(shown)
    + " vs " + JSON.stringify(said));
  assert.deepStrictEqual(shown, { [A]: 1, [B]: 3 });
}());

(function theMessageIsTheOneTheServerComposed() {
  const s = opened([previewReply()]);
  assert.strictEqual(s.dom.document.getElementById("ir-send-message").value,
                     preview().message,
                     "나갈 문구는 서버가 만든 그것이어야 한다");
}());

(function aCompanyWithoutANumberIsSaidSo() {
  // 지난 회차에 없던 기업은 번호가 없다. **지어내지 않는다** — 자리를 비우면
  // 화면이 덜 그려진 것으로 읽힌다.
  const s = opened([previewReply({
    attachments: [{ company_id: 11, name: A, file: A + "_IR.pdf", no: null }]
  })]);
  const rows = ir_.attachRows(s.dom);

  assert.ok(rows[0].indexOf("번호 없음") >= 0, rows[0]);
  // 번호가 왜 그런지 말하던 줄은 이 창에서 뺐다(설명 글귀 정리) — 그 자리를
  // 안 줘도 목록은 그대로 그려져야 한다.
  assert.strictEqual(s.dom.document.getElementById("ir-no-note"), null);
}());

(function theListKeepsTheOrderTheServerSent() {
  // **차례를 화면이 다시 세우지 않는다.** 번호순으로 세우는 것은 서버 일이고
  // (`deal_numbers.numbered_companies`), 문구도 같은 함수에서 나온다.
  // 화면이 여기서 또 정렬하면 서버가 어떤 차례로 보내든 화면만 달라져,
  // 문구와 갈리는 자리가 하나 더 생긴다.
  const s = opened([previewReply({
    // 서버가 이미 번호순으로 보낸다: 1번 → 3번 → 번호 없음.
    attachments: [
      { company_id: 11, name: A, file: A + "_IR.pdf", no: 1 },
      { company_id: 12, name: B, file: B + "_IR.pdf", no: 3 },
      { company_id: 13, name: "마바로보", file: "마바로보_IR.pdf", no: null }
    ]
  })]);
  const rows = ir_.attachRows(s.dom);

  assert.deepStrictEqual(
    rows.map(function (r) { const m = /(\d+)번/.exec(r); return m ? m[1] : null; }),
    ["1", "3", null], "받은 차례를 그대로 그려야 한다: " + JSON.stringify(rows));
}());

(function aCompanyWithoutAFileIsSaidSo() {
  const s = opened([previewReply({
    attachments: [{ company_id: 11, name: A, file: "", no: 1 }],
    warnings: ["첨부할 IR 자료가 없는 기업: " + A + " — IR 기업 현황에 자료 파일명을 등록하세요"]
  })]);

  assert.ok(ir_.attachRows(s.dom)[0].indexOf("첨부할 자료가 없습니다") >= 0);
  // 서버가 미리 잡아 준 걱정거리는 **삼키지 않는다.**
  const warn = s.dom.document.getElementById("ir-send-warnings");
  assert.strictEqual(warn.hidden, false);
  assert.ok(warn.textContent.indexOf("첨부할 IR 자료가 없는 기업") >= 0, warn.textContent);
}());

// ── ③ 발송은 이미 있는 길로 ─────────────────────────────────────────────────

(function sendingGoesThroughTheExistingEndpoint() {
  const s = opened([previewReply(), SENT], { confirm: function () { return true; } });
  s.dom.document.getElementById("ir-send-go").fire("click");

  const call = s.fetch.calls[1];
  assert.ok(call, "발송을 아예 안 불렀다");
  assert.strictEqual(call.url, "/api/deals/send",
    "발송 길을 새로 파면 안 된다 — 방 확인·검토중단 막이가 전부 그 함수 안에 있다");
  assert.deepStrictEqual(call.body, {
    mode: "ir", contact_ids: [ir_.CONTACT_ID], company_ids: ir_.COMPANY_IDS
  });
  // 보내고 나서도 화면은 그대로다.
  assert.strictEqual(s.dom.window.location.href, "",
    "보내고 나서 딴 화면으로 옮기면 그 자리에서 끝낸 것이 아니다");
}());

(function theRowChangesAfterSending() {
  // 눌렀는데 아무 일도 안 일어난 것처럼 보이면 한 번 더 누른다.
  const s = opened([previewReply(), SENT], { confirm: function () { return true; } });
  s.dom.document.getElementById("ir-send-go").fire("click");

  assert.strictEqual(s.dom.form.hidden, true, "보낸 뒤에도 [자료 보내기] 가 그대로다");
  const badge = s.dom.head.querySelector(".ir-sent-badge");
  assert.ok(badge, "그 줄에 아무 표시도 안 남았다");
  const state = s.dom.document.getElementById("ir-send-state");
  assert.strictEqual(state.hidden, false);
  assert.ok(state.textContent.indexOf("발송 목록") >= 0, state.textContent);
  // 어디까지 갔는지 볼 길.
  const job = s.dom.document.getElementById("ir-send-job");
  assert.strictEqual(job.hidden, false);
  assert.strictEqual(job.getAttribute("href"), "/jobs/42");
}());

(function cancellingTheConfirmSendsNothing() {
  // 확인창을 띄워 놓고 이미 보내 버리면 확인창은 장식일 뿐이다.
  const s = opened([previewReply()], { confirm: function () { return false; } });
  s.dom.document.getElementById("ir-send-go").fire("click");

  assert.strictEqual(s.fetch.calls.length, 1, "취소했는데 발송이 나갔다");
  assert.strictEqual(s.dom.form.hidden, false);
}());

(function thePathToTheSendScreenIsKept() {
  // 문구를 손보거나 담당자를 더하려면 그 화면이 필요하다 — 없애지 않는다.
  const s = opened([previewReply()]);
  const href = s.dom.document.getElementById("ir-send-open-deals").getAttribute("href");

  assert.ok(href.indexOf("/deals?") === 0, href);
  assert.ok(href.indexOf("mode=ir") >= 0, href);
  assert.ok(href.indexOf("contacts=" + ir_.CONTACT_ID) >= 0, href);
  assert.ok(href.indexOf("companies=" + ir_.COMPANY_IDS.join(",")) >= 0, href);
}());

// ── ④ 막히면 막힌 이유가 뜬다 ───────────────────────────────────────────────

(function theServersRefusalIsShownWordForWord() {
  const s = opened([previewReply(),
                    { ok: false, d: { detail: "'가담당' 카톡방 이름 미등록 — 발송 대상에서 제외하세요" } }],
                   { confirm: function () { return true; } });
  s.dom.document.getElementById("ir-send-go").fire("click");

  const warn = s.dom.document.getElementById("ir-send-warnings");
  assert.strictEqual(warn.hidden, false, "왜 안 나갔는지 아무 말도 없다");
  assert.ok(warn.textContent.indexOf("카톡방 이름 미등록") >= 0, warn.textContent);
  // 실패했으면 그 줄은 **안 바뀐다** — 안 보낸 것을 보냈다고 적으면 안 된다.
  assert.strictEqual(s.dom.form.hidden, false, "실패했는데 보낸 것처럼 보인다");
  assert.strictEqual(s.dom.document.getElementById("ir-send-go").disabled, false,
    "다시 시도할 수 없다");
}());

(function noRoomMeansNoSendButtonButStillACopy() {
  const s = opened([previewReply({ room_name: "", room_warning: "카톡방 이름 미등록" })]);

  assert.strictEqual(s.dom.document.getElementById("ir-send-go").disabled, true,
    "어차피 서버가 거절한다 — 눌러 보고 알기 전에 왜 못 누르는지 적혀 있어야 한다");
  assert.ok(s.dom.document.getElementById("ir-send-warnings")
    .textContent.indexOf("카톡방 이름 미등록") >= 0);
  // 손으로 붙여 넣는 길은 방 이름과 무관하다.
  assert.strictEqual(s.dom.document.getElementById("ir-send-copy").disabled, false,
    "복사까지 막으면 손으로 보낼 길이 없다");
}());

(function aBrokenPreviewBlocksTheSend() {
  // 무엇이 나갈지 못 본 채로 누르는 자리가 되면 안 된다.
  const s = opened([{ ok: false, d: { detail: "기업은 1~10개 선택하세요" } }]);

  assert.strictEqual(s.dom.document.getElementById("ir-send-go").disabled, true);
  const warn = s.dom.document.getElementById("ir-send-warnings");
  assert.ok(warn.textContent.indexOf("미리보기를 불러오지 못했습니다") >= 0, warn.textContent);
  assert.ok(warn.textContent.indexOf("기업은 1~10개") >= 0,
    "서버가 말해 준 사유가 사라졌다: " + warn.textContent);
}());

(function copyingTakesTheMessageAsItIs() {
  // 머리말·안내가 섞이면 그것까지 카톡방에 붙는다.
  let copied = null;
  const s = opened([previewReply()], {
    navigator: { clipboard: { writeText: function (t) {
      copied = t;
      return { then: function (ok) { ok(); return this; } };
    } } }
  });
  s.dom.document.getElementById("ir-send-copy").fire("click");

  assert.strictEqual(copied, preview().message);
}());

// ── ⑤ 설명 글귀는 한 줄만 ───────────────────────────────────────────────────

(function onlyOneExplanationIsLeft() {
  // 사용자가 창의 설명 글귀를 **한 줄만** 두고 지워 달라고 했다. 지운 것이
  // 되살아나지 않게 못박는다 — 다만 **일하는 부분과 알림은 그대로**다.
  const s = opened([previewReply()]);
  const d = s.dom.document;

  // 남은 한 줄.
  assert.ok(s.dom.modal.querySelector(".ir-attach"), "[보낼 자료] 칸이 없다");
  // 지운 설명들.
  assert.strictEqual(d.getElementById("ir-send-who"), null, "누구에게 보낸다는 줄이 남았다");
  assert.strictEqual(d.getElementById("ir-no-note"), null, "번호 설명 줄이 남았다");
  assert.strictEqual(s.dom.modal.querySelector(".send-modal-label"), null,
    "문구 칸 설명 줄이 남았다");
  // **일하는 부분**은 그대로여야 한다 — 지우면 그 자리에서 보낼 수가 없다.
  ["ir-links", "ir-send-message", "ir-send-copy", "ir-send-go", "ir-send-close",
   "ir-send-open-deals"].forEach(function (id) {
    assert.ok(d.getElementById(id), "일하는 자리가 사라졌다: " + id);
  });
  // **알림**도 그대로 — 지우면 어디로 가는지 모르고 누른다.
  assert.ok(d.getElementById("ir-send-state"), "어디로 나가는지 말하는 자리가 없다");
  assert.ok(d.getElementById("ir-send-warnings"), "막힌 사유를 말하는 자리가 없다");
}());

console.log("ok — [자료 보내기] 가 화면을 옮기지 않고 그 자리에서 끝낸다");
