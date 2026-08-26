// 미리보기에서 고친 문구가 살아남는가.
//
// 담당자를 하나 더 체크하면 미리보기가 새로 그려진다. 그때마다 앞서 고쳐 둔
// 것이 **말없이 사라졌다** — 열 명을 고치고 한 명 더 넣으면 열 명분이 날아간다.
//
// deals.js 는 DOM 에 매여 있어 통째로 못 부른다. 되살리는 규칙만 같은 모양으로
// 옮겨 두고, 그 규칙이 파일에 실제로 있는지도 함께 본다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

// --- 규칙 (deals.js 의 refreshPreview 안과 같은 모양) ---------------------
function restore(previews, savedEdits) {
  previews.forEach(function (p) {
    p.original = p.message;
    const kept = savedEdits[p.contact_id];
    if (kept !== undefined && kept !== p.message) {
      p.message = kept;
      p.edited = true;
    } else {
      p.edited = false;
    }
  });
  return previews;
}

function remember(savedEdits, p, value) {
  if (value.trim() && value !== p.original) savedEdits[p.contact_id] = value;
  else delete savedEdits[p.contact_id];
  return savedEdits;
}

// --- 고친 것이 다시 그려도 남는가 -----------------------------------------
{
  const edits = {};
  const first = restore([{ contact_id: 7, message: "기본 문구" }], edits);
  remember(edits, first[0], "내가 고친 문구");

  // 담당자를 한 명 더 체크 → 서버가 기본 문구로 다시 내려준다
  const again = restore(
    [{ contact_id: 7, message: "기본 문구" }, { contact_id: 8, message: "기본 문구" }],
    edits);

  assert.strictEqual(again[0].message, "내가 고친 문구", "고친 문구가 사라졌다");
  assert.strictEqual(again[0].edited, true);
  assert.strictEqual(again[1].message, "기본 문구", "안 고친 사람까지 바뀌었다");
  assert.strictEqual(again[1].edited, false);
}

// --- 되돌리면 남지 않는다 --------------------------------------------------
{
  const edits = {};
  const p = restore([{ contact_id: 7, message: "기본 문구" }], edits)[0];
  remember(edits, p, "고침");
  remember(edits, p, "기본 문구");        // 원래대로 되돌림
  assert.deepStrictEqual(edits, {}, "되돌렸는데 수정본이 남아 있다");
}

// --- 빈 문구는 남기지 않는다 ------------------------------------------------
{
  const edits = {};
  const p = restore([{ contact_id: 7, message: "기본 문구" }], edits)[0];
  remember(edits, p, "   ");
  assert.deepStrictEqual(edits, {}, "빈 문구가 수정본으로 남았다");
}

// --- 실제 파일에 그 규칙이 있는가 -------------------------------------------
{
  const src = fs.readFileSync(
    path.join(__dirname, "..", "..", "app", "static", "js", "deals.js"), "utf8");
  assert.ok(/var savedEdits = \{\}/.test(src), "고친 문구를 담아 둘 곳이 없다");
  assert.ok(/savedEdits\[p\.contact_id\] = ta\.value/.test(src),
            "고치는 즉시 남기지 않는다 — 체크 한 번에 사라진다");
  assert.ok(/kept !== undefined/.test(src), "다시 그릴 때 되살리지 않는다");
  // 방식을 바꾸면 버려야 한다 — 딜소개용 수정본이 IR 자료 전달에 얹히면 안 된다
  assert.ok(/savedEdits = \{\};/.test(src), "방식을 바꿔도 수정본이 남는다");
}

// --- 늦게 온 옛 응답이 새 것을 덮지 않는가 ---------------------------------
//
// 39명을 고른 요청은 느리고 전부 해제한 요청은 빠르다. 순서를 안 지키면
// 전체선택을 두 번 눌러 다 껐는데 미리보기에 투자사가 그대로 남는다.
{
  let previewSeq = 0;
  let shown = null;

  function request(label, previews, arriveAfter) {
    const seq = ++previewSeq;
    return { label, previews, arriveAfter, apply() {
      if (seq !== previewSeq) return false;   // 그 사이 새 요청이 나갔다
      shown = previews;
      return true;
    } };
  }

  const slow = request("전체선택 39명", ["투자사A", "투자사B"], 300);
  const fast = request("전부 해제", ["기본 문구"], 10);

  // 빠른 쪽이 먼저 도착
  assert.strictEqual(fast.apply(), true);
  // 느린 쪽이 뒤늦게 도착 — 덮으면 안 된다
  assert.strictEqual(slow.apply(), false, "늦게 온 옛 응답이 새 것을 덮었다");
  assert.deepStrictEqual(shown, ["기본 문구"]);
}

// --- 실제 파일에 순서 보장이 있는가 ------------------------------------------
{
  const src = fs.readFileSync(
    path.join(__dirname, "..", "..", "app", "static", "js", "deals.js"), "utf8");
  assert.ok(/var seq = \+\+previewSeq/.test(src), "요청에 번호를 붙이지 않는다");
  assert.ok((src.match(/seq !== previewSeq/g) || []).length >= 2,
            "응답과 오류 양쪽에서 번호를 확인해야 한다");
}

console.log("preview_edit_test: 통과");
