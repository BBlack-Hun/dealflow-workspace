// [보낼 자료] 목록은 **파일 이름**을 보여 준다 — 링크가 아니다.
//
// 이 칸은 원래 구글 드라이브 링크라 `[자료 열기]` 로 열 수 있었다. 이제 담기는
// 값이 파일명이고(0056) 파일은 각자 PC 의 자료 폴더에 있다 — 브라우저가 열 수
// 있는 자리가 아니다. `href` 를 억지로 만들면 깨진 링크나 (브라우저가 조용히
// 막는) `file://` 이 되어 **눌러도 아무 일이 없는 자리**가 된다.
//
// 그래서 이름을 그대로 보여 준다. 자동 첨부를 켠 사람은 그 이름이 폴더에 있는지
// 눈으로 맞춰 보고, 켜지 않은 사람은 그 이름으로 파일을 찾아 PC 카톡에 붙인다.
"use strict";

const assert = require("assert");
const deals_ = require("./_deals_dom.js");

const A = "가나애그";
const B = "다라헬스";

function items(dom) {
  return Array.prototype.slice
    .call(dom.document.getElementById("ir-links").children)
    .map(function (li) { return li.innerHTML; });
}

// ── 1) ★ 이름이 보이고, 링크는 없다 ─────────────────────────────────────────
{
  const dom = deals_.run(null, {});
  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, A);

  const shown = items(dom);
  assert.strictEqual(shown.length, 1, "고른 기업이 목록에 없다");
  assert.ok(shown[0].indexOf(A + "_IR.pdf") >= 0,
            "파일 이름이 안 보인다: " + shown[0]);
  assert.ok(shown[0].indexOf("<a ") < 0,
            "파일명을 링크로 걸었다 — 눌러도 열리지 않는다: " + shown[0]);
  assert.ok(shown[0].indexOf("자료 열기") < 0,
            "링크 시절의 말이 그대로 남아 있다: " + shown[0]);
}

// ── 2) 이름이 없으면 **없다고 말한다** ──────────────────────────────────────
//
// 조용히 비워 두면 자료가 안 나가는 줄 모르고 [발송] 을 누른다.
{
  const dom = deals_.run(null, {});
  const box = deals_.companyBox(dom, B);
  box.setAttribute("data-ir-file", "");

  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, B);

  assert.ok(items(dom)[0].indexOf("첨부할 자료가 없습니다") >= 0,
            "자료가 없는데 아무 말도 안 한다: " + items(dom)[0]);
}

// ── 3) 이름은 **그대로** 실린다 — 화면 코드가 깎아 내지 않는다 ──────────────
//
// 발송기는 이 이름으로 파일을 찾는다. 화면이 한 글자라도 다르게 보여 주면,
// 사람은 폴더에 있는 파일과 견주다 멀쩡한 이름을 고치게 된다.
{
  const dom = deals_.run(null, {});
  const odd = "샘플 & 애그 <2026> IR.pdf";
  const box = deals_.companyBox(dom, A);
  box.setAttribute("data-ir-file", odd);

  deals_.pickMode(dom, "ir");
  deals_.toggleCompany(dom, A);

  const html = items(dom)[0];
  // 이름은 사람이 친 글자라 **태그로 읽히면 안 된다** — 글자 그대로 실린다.
  assert.ok(html.indexOf("샘플 &amp; 애그 &lt;2026&gt; IR.pdf") >= 0,
            "이름이 화면에서 달라졌다: " + html);
  assert.ok(html.indexOf("<2026>") < 0, "이름을 태그로 그렸다: " + html);
}

console.log("ok — [보낼 자료] 목록은 파일 이름을 그대로 보여 준다");
