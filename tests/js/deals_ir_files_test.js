// [보낼 자료] 목록은 **번호와 파일 이름**을 함께 보여 준다.
// (node tests/js/deals_ir_files_test.js)
//
// 번호는 #112 가 붙였다 — 자료가 나가는 차례다. 이 파일이 지키는 것은 그 옆의
// **자료가 무엇으로 적히는가**이다.
//
// 그 칸은 원래 구글 드라이브 링크라 `[자료 열기]` 로 열 수 있었다. 이제 담기는
// 값이 파일명이고(0056) 파일은 각자 PC 의 자료 폴더에 있다 — 브라우저가 열 수
// 있는 자리가 아니다. `href` 를 억지로 만들면 깨진 링크나 (브라우저가 조용히
// 막는) `file://` 이 되어 **눌러도 아무 일이 없는 자리**가 된다.
//
// 그래서 이름을 그대로 보여 준다. 자동 첨부를 켠 사람은 그 이름이 폴더에 있는지
// 눈으로 맞춰 보고, 켜지 않은 사람은 그 이름으로 파일을 찾아 PC 카톡에 붙인다.
//
// **번호와 파일명은 둘 다 살아야 한다.** 한쪽만 있으면 무엇을 몇 번째로 붙일지
// 알 수 없다. 그래서 아래 검사들은 늘 둘을 함께 본다.
//
// 값은 **서버가 문구와 같은 응답에 실어 준다**(`attachments[].no` · `.file`).
// 화면이 고른 칸에서 따로 읽으면 번호는 서버 것, 이름은 화면 것이 되어 한쪽만
// 낡는다 — 그래서 여기서도 가짜 응답으로 몰아 준다.
"use strict";

const assert = require("assert");
const deals_ = require("./_deals_dom.js");

const A = "가나애그";
const B = "다라헬스";

// 서버가 돌려주는 한 통. `rows` 는 `[[기업명, 번호|null, 파일명], …]` 이고
// **고른 차례**다 — 문구도 이 차례로 짚는다.
function person(name, rows) {
  return {
    contact_id: name.length,
    name: name,
    title: "심사역",
    room_name: name + " 심사역님",
    message: rows.map(function (r) {
      return r[1] ? r[1] + "번 기업 " + r[0] : r[0];
    }).join(", ") + " IR deck 먼저 전달드리겠습니다.",
    parts: [],
    warnings: [],
    attachments: rows.map(function (r) {
      return { name: r[0], no: r[1], file: r[2] };
    })
  };
}

// 목록에 실제로 그려진 줄들.
function rows(dom) {
  return Array.prototype.slice
    .call(dom.document.getElementById("ir-links").children)
    .map(function (li) { return li.innerHTML; });
}

function show(dom, previews) {
  const fetch = deals_.fakeFetch([deals_.previewReply(previews)]);
  const dom_ = dom || deals_.run(null, { fetch: fetch });
  deals_.pickMode(dom_, "ir");
  deals_.toggleCompany(dom_, A);
  deals_.toggleCompany(dom_, B);
  dom_.document.getElementById("refresh-preview").fire("click");
  return dom_;
}

// ── 1) ★ 번호와 파일 이름이 **함께** 보인다 ────────────────────────────────
{
  const dom = show(null, [person("가담당", [[A, 3, A + "_IR.pdf"],
                                            [B, 1, B + "_IR.pdf"]])]);
  const shown = rows(dom);
  assert.strictEqual(shown.length, 2, "고른 기업이 목록에 없다: " + shown.join(" | "));

  assert.ok(shown[0].indexOf("3번") >= 0, "번호가 사라졌다: " + shown[0]);
  assert.ok(shown[0].indexOf(A + "_IR.pdf") >= 0, "파일 이름이 없다: " + shown[0]);
  assert.ok(shown[1].indexOf("1번") >= 0 && shown[1].indexOf(B + "_IR.pdf") >= 0,
            "두 번째 줄에 번호나 파일 이름이 빠졌다: " + shown[1]);

  // 링크가 아니다 — 눌러도 열리지 않는 자리를 만들지 않는다.
  shown.forEach(function (row) {
    assert.ok(row.indexOf("<a ") < 0, "파일명을 링크로 걸었다: " + row);
    assert.ok(row.indexOf("자료 열기") < 0, "링크 시절의 말이 남아 있다: " + row);
  });
}

// ── 2) 파일 이름이 없으면 **없다고 말한다** (번호는 그대로) ────────────────
//
// 조용히 비워 두면 자료가 안 나가는 줄 모르고 [발송] 을 누른다. 그리고 자료가
// 없는 것과 번호가 없는 것은 **다른 이야기**라, 번호는 그대로 있어야 한다.
{
  const dom = show(null, [person("가담당", [[A, 2, ""], [B, 5, B + "_IR.pdf"]])]);
  const shown = rows(dom);

  assert.ok(shown[0].indexOf("첨부할 자료가 없습니다") >= 0,
            "자료가 없는데 아무 말도 안 한다: " + shown[0]);
  assert.ok(shown[0].indexOf("2번") >= 0,
            "자료가 없다고 번호까지 지웠다: " + shown[0]);
}

// ── 3) 번호가 없어도 **파일 이름은 적는다** ───────────────────────────────
//
// 지난 딜 소개에 없던 기업이다. 번호는 지어내지 않지만, 붙일 파일은 있다.
{
  const dom = show(null, [person("가담당", [[A, null, A + "_IR.pdf"]])]);
  const shown = rows(dom);

  assert.ok(shown[0].indexOf("번호 없음") >= 0, "번호 없음 알약이 없다: " + shown[0]);
  assert.ok(shown[0].indexOf(A + "_IR.pdf") >= 0,
            "번호가 없다고 파일 이름까지 지웠다: " + shown[0]);
}

// ── 4) 탭을 바꾸면 **번호도 파일 이름도** 그 담당자 것으로 ─────────────────
//
// 번호는 담당자마다 다르고 파일명은 같다. 둘이 서로 다른 담당자를 가리키면
// 엉뚱한 자료가 그 번호 자리에 붙는다.
{
  const dom = show(null, [
    person("가담당", [[A, 3, A + "_IR.pdf"], [B, 1, B + "_IR.pdf"]]),
    person("나담당", [[A, 7, A + "_IR.pdf"], [B, 9, B + "_IR.pdf"]])
  ]);
  assert.ok(rows(dom)[0].indexOf("3번") >= 0, "첫 탭의 번호가 아니다");

  deals_.pickPreviewTab(dom, 1);
  const shown = rows(dom);
  assert.ok(shown[0].indexOf("7번") >= 0, "탭을 바꿨는데 번호가 안 따라왔다: " + shown[0]);
  assert.ok(shown[0].indexOf(A + "_IR.pdf") >= 0,
            "탭을 바꾸니 파일 이름이 사라졌다: " + shown[0]);
}

// ── 5) 이름은 **그대로** 실린다 — 화면 코드가 깎아 내지 않는다 ────────────
//
// 발송기는 이 이름으로 파일을 찾는다. 화면이 한 글자라도 다르게 보여 주면,
// 사람은 폴더에 있는 파일과 견주다 멀쩡한 이름을 고치게 된다.
{
  const odd = "샘플 & 애그 <2026> IR.pdf";
  const dom = show(null, [person("가담당", [[A, 1, odd]])]);
  const html = rows(dom)[0];

  // 이름은 사람이 친 글자라 **태그로 읽히면 안 된다** — 글자 그대로 실린다.
  assert.ok(html.indexOf("샘플 &amp; 애그 &lt;2026&gt; IR.pdf") >= 0,
            "이름이 화면에서 달라졌다: " + html);
  assert.ok(html.indexOf("<2026>") < 0, "이름을 태그로 그렸다: " + html);
}

console.log("ok — [보낼 자료] 목록은 번호와 파일 이름을 함께 보여 준다");
