// 참고 자료 표 — 머리글과 칸을 눌러 바로 고친다.
//
// 보기만 되던 자료다. 스크립트·성격 정리는 쓰면서 다듬는 것이라, 고치려고
// 구글 시트를 따로 열어야 하면 화면 안으로 들여온 뜻이 없다.
//
// **머리글도 칸과 같은 길을 지난다** — 같은 `.ref-cell`, 같은 손잡이, 같은
// 입력칸, 같은 되돌리기. 표를 화면에서 세울 수 있게 되면서 머리글이
// `칸 1 · 칸 2 …` 로 서는데, 한 표 안에서 머리글과 칸을 고치는 법이 다르면
// 쓰는 사람이 헷갈리고 나중에 한쪽만 고쳐진다. 다른 것은 **어디에 저장하는가
// 하나뿐**이다(아래 `saveTo`).
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

  // 어디에 저장하는가. 머리글은 `columns[col]`, 칸은 `rows[row][col]` —
  // 자료에서 서로 다른 자리라 주소도 따로다(routers/contacts.py 참고:
  // 빈 값 규칙이 서로 반대여서 한 손잡이로 묶지 않았다).
  function saveTo(cell) {
    var col = parseInt(cell.getAttribute("data-col"), 10);
    if (cell.classList.contains("ref-head")) {
      return { url: "/api/ref-sheets/" + id + "/column", body: { col: col } };
    }
    return {
      url: "/api/ref-sheets/" + id + "/cell",
      body: { row: parseInt(cell.getAttribute("data-row"), 10), col: col }
    };
  }

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
      var to = saveTo(cell);
      to.body.value = after;
      fetch(to.url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(to.body)
      }).then(function (r) {
        if (r.ok) return;
        // **왜 안 됐는지 그대로 옮긴다.** '저장하지 못했습니다' 만 뜨면 빈
        // 머리글을 물린 것인지 연결이 끊긴 것인지 알 수 없어 같은 것을 또 누른다.
        return r.json().then(function (d) { return d && d.detail; },
                             function () { return ""; }).then(failed);
      }).catch(function () { failed(); });
    }

    // 저장이 **조용히 삼켜지지 않게** 한다 — 화면에는 고친 글자가, 서버에는
    // 옛 글자가 남으면 새로고침 전까지 아무도 모른다.
    function failed(why) {
      cell.textContent = before;
      alert(why ? "저장하지 못했습니다 — " + why : "저장하지 못했습니다.");
    }
  }
})();
