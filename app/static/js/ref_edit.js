// 참고 자료 표 — 칸을 눌러 바로 고친다.
//
// 보기만 되던 자료다. 스크립트·성격 정리는 쓰면서 다듬는 것이라, 고치려고
// 구글 시트를 따로 열어야 하면 화면 안으로 들여온 뜻이 없다.
//
// 투자사 표의 inline_edit 와 저장 모양이 다르다(칸을 줄·열 번호로 가리킨다)
// 그래서 여기만 따로 둔다.
(function () {
  "use strict";

  var table = document.getElementById("ref-table");
  if (!table) return;
  var id = table.getAttribute("data-ref-id");
  var editing = null;

  table.addEventListener("click", function (e) {
    var cell = e.target.closest(".ref-cell");
    if (!cell || cell === editing) return;
    start(cell);
  });

  function start(cell) {
    if (editing) return;
    editing = cell;
    var before = cell.textContent.trim();

    var input = document.createElement("textarea");
    input.className = "cell-input";
    input.rows = 1;
    input.value = before;

    // 빠져나갈 길을 먼저 만든다 — focus 가 던지면 blur 가 안 붙어 칸에 갇힌다.
    input.addEventListener("blur", finish);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = before; input.blur(); }
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); input.blur(); }
    });

    cell.textContent = "";
    cell.appendChild(input);
    try { input.focus(); } catch (err) { /* 포커스 실패해도 갇히지 않는다 */ }

    function finish() {
      var after = input.value.trim();
      cell.textContent = after;
      editing = null;
      if (after === before) return;
      fetch("/api/ref-sheets/" + id + "/cell", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          row: parseInt(cell.getAttribute("data-row"), 10),
          col: parseInt(cell.getAttribute("data-col"), 10),
          value: after
        })
      }).then(function (r) {
        if (!r.ok) { cell.textContent = before; alert("저장하지 못했습니다."); }
      }).catch(function () {
        cell.textContent = before;
        alert("저장하지 못했습니다.");
      });
    }
  }
})();
