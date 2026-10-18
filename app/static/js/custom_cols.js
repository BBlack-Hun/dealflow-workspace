// 관리자가 자리를 고른 **추가 칸**(`컬럼 관리` · 0110)을 그 기존 칸 뒤로 옮긴다.
//
// 서버는 추가 칸을 표 오른쪽 끝에 그린다(`_custom_cols.html`). 기존 칸은 템플릿마다
// 손으로 적혀 있어 서버가 그 사이에 끼울 자리를 모른다 — 그래서 머리글 이름
// (`data-after`)으로 앵커 칸을 찾아 머리글과 줄마다의 칸을 같은 차례로 옮긴다.
// 앵커가 없는 표(그 칸이 없는 탭)에서는 아무것도 안 옮긴다 — 맨 끝 그대로다.
//
// **필터 · 정렬 · 칸 고치기보다 먼저 돈다**(`base.html` 이 페이지 스크립트 앞에
// 싣는다). 셋 다 칸을 자리 번호가 아니라 `data-filters` · `data-sort` ·
// `data-field` 로 찾지만, `filters.js` 가 머리글 이름 글자를 단추로 바꾸므로
// 이름은 그 전에 읽어야 한다.
(function () {
  "use strict";

  // 서버의 `custom_columns.label_key` 와 같다 — 띄어쓰기를 하나로.
  function key(text) { return String(text || "").replace(/\s+/g, " ").trim(); }

  // 머리글 이름 — 칸 안의 글자 노드만(필터 자리 `<div>` 는 뺀다). `table_sort.js` 와 같다.
  function label(th) {
    var own = Array.prototype.map.call(th.childNodes, function (n) {
      return n.nodeType === 3 ? n.textContent : "";
    }).join("");
    return key(own) || key(th.textContent);
  }

  function arrange(head) {
    var cells = Array.prototype.slice.call(head.children);
    var anchors = {};
    cells.forEach(function (th) {
      var name = label(th);
      if (!th.classList.contains("custom-col") && name && !anchors[name]) anchors[name] = th;
    });
    // 같은 칸 뒤에 여럿이면 서버가 그린 차례(`position`) 그대로 잇는다.
    var last = {};
    var moved = false;
    cells.forEach(function (th) {
      var to = key(th.getAttribute("data-after"));
      if (!th.classList.contains("custom-col") || !anchors[to]) return;
      var prev = last[to] || anchors[to];
      if (prev.nextSibling !== th) head.insertBefore(th, prev.nextSibling);
      last[to] = th;
      moved = true;
    });
    if (!moved) return;
    // 줄마다 머리글과 같은 차례로. 칸 수가 머리글과 다른 줄(안내 줄 colspan)은 둔다.
    var order = Array.prototype.map.call(head.children, function (th) {
      return cells.indexOf(th);
    });
    var table = head.closest("table");
    Array.prototype.forEach.call(table.querySelectorAll("tbody tr"), function (tr) {
      var tds = Array.prototype.slice.call(tr.children);
      if (tr.closest("table") !== table || tds.length !== cells.length) return;
      order.forEach(function (i) { tr.appendChild(tds[i]); });
    });
  }

  var done = [];
  Array.prototype.forEach.call(document.querySelectorAll("th.custom-col[data-after]"),
    function (th) {
      var head = th.parentNode;
      if (done.indexOf(head) < 0) { done.push(head); arrange(head); }
    });
})();
