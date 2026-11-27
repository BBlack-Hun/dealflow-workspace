// 딜 제안 관리 › IR 자료 전달을 **이메일로** 고르면 화면의 말이 따라온다 (0.11.17).
// (node tests/js/deals_ir_mail_note_test.js)
//
// 메일에도 자료 파일이 붙는다 — 발송 PC 가 올린 파일을 서버가 붙여 보낸다
// (`app/services/mail_attach.py`). 요약줄이 "PC 카톡에서 직접 첨부" 를 그대로 달고
// 있으면 사람은 메일에 자료가 안 붙는 줄 안다. 붙일 수 있는 계정인지는 서버가
// 가른다(미리보기 경고 · 발송 목록 만들기 — 파이썬 쪽 `tests/test_ir_attach_job.py`).
"use strict";
const assert = require("assert");

const deals_ = require("./_deals_dom.js");

function now(fn) { fn(); return 0; }

const fetch = deals_.fakeFetch([]);
const dom = deals_.run(null, { fetch: fetch, setTimeout: now });
const note = dom.document.getElementById("ss-note");
const channel = dom.document.querySelector('input[name="channel"]');

deals_.pickMode(dom, "ir");
assert.ok(/PC 카톡에서 직접 첨부/.test(note.textContent),
          "카톡 · 자동 첨부 꺼짐 — 지금까지의 말이 아니다: " + note.textContent);

// 이메일을 고른다(검사용 화면은 채널 칸이 하나라 값을 바꿔 끼운다).
channel.value = "email";
channel.fire("change");
assert.strictEqual(note.textContent, "자료 파일은 메일에 첨부해 보냅니다");
const previews = fetch.calls.filter(function (c) { return c.url === "/api/deals/preview"; });
assert.strictEqual(previews[previews.length - 1].body.channel, "email",
                   "미리보기가 채널을 안 실었다 — 서버가 메일 경고를 못 낸다");

channel.value = "kakao";
channel.fire("change");
assert.ok(/PC 카톡에서 직접 첨부/.test(note.textContent), "카톡으로 돌아왔는데 메일 말이 남았다");

console.log("deals_ir_mail_note_test: ok");
