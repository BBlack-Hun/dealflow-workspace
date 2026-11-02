// 메모 칸에 새로 다는 줄 앞에 **오늘 날짜**(`2026/07/25`)를 붙인다(i139).
//
// 칸을 열 때 맨 끝 새 줄에 `오늘 날짜 + 빈칸` 을 미리 채워 두고(`open`), 닫을 때
// 그 뒤에 아무것도 안 적었으면 그 줄을 뗀다(`close`). 서버에서 붙이지 않는 것은
// **사람이 화면에서 단 메모에만** 붙어야 해서다 — 엑셀 가져오기 · 스크립트 ·
// 동기화는 이 편집기를 지나지 않는다. 적는 사람이 붙은 날짜를 보고 고칠 수도 있다.
//
// 어느 칸이 메모인지는 템플릿이 정한다(`data-memo-date`). 선호 칸 · 소개 문구처럼
// 밖으로 나가거나 짧은 값인 칸에는 안 붙인다. 쓰는 곳은 `inline_edit.js` 의
// `startLong` 과 `consulting.js` 의 `startEdit`(추가 메모 칸) 둘이다.
//
// **옛 글은 한 글자도 안 바꾼다.** 덧붙인 꼬리만 본다.
(function (global) {
  "use strict";

  var KST = 9 * 60 * 60 * 1000;   // 한국은 서머타임이 없다 — 시차가 늘 9시간이다
  // 사람이 날짜를 따로 적었는가(`10/31` · `2026.10.31` · `2026-10-31`). `3/4분기` 는 아니다.
  var OWN_DATE = /^(\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}\/\d{1,2})(?=$|[\s:,.)\]])/;

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  // 서울의 오늘. 밤새 열어 둔 화면도 맞게 — 서버가 그려 준 날짜가 아니라 지금 시계로 잰다.
  function today(now) {
    var d = new Date((now === undefined ? Date.now() : now) + KST);
    return d.getUTCFullYear() + "/" + pad(d.getUTCMonth() + 1) + "/" + pad(d.getUTCDate());
  }

  function open(before, now) {
    return (before ? before + "\n" : "") + today(now) + " ";
  }

  function close(value, before, now) {
    var stamp = today(now);
    var old = String(before || "");
    var text = String(value).replace(/\s+$/, "");
    var lines = text.split("\n");
    // 날짜만 남은 끝줄은 뗀다 — 옛 글이 원래 그 줄로 끝났으면 그건 옛 글이라 둔다.
    if (lines[lines.length - 1].trim() === stamp && old.split("\n").pop().trim() !== stamp) {
      lines.pop();
      return lines.join("\n").replace(/\s+$/, "");
    }
    // 붙인 날짜 뒤에 사람이 날짜를 또 적었으면 붙인 쪽을 뗀다 — 날짜가 둘 서지 않게.
    var head = old ? old + "\n" : "";
    var rest = text.slice(head.length + stamp.length + 1).replace(/^\s+/, "");
    if (text.slice(0, head.length) === head
        && text.slice(head.length, head.length + stamp.length + 1) === stamp + " "
        && OWN_DATE.test(rest)) {
      return head + rest;
    }
    return text;
  }

  global.DealflowMemoDate = { today: today, open: open, close: close };
})(window);
