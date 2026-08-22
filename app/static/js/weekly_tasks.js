// 주간 업무 — 상태 바꾸기. 칸 수정은 inline_edit.js 가 맡는다.
(function () {
  var table = document.getElementById("task-table");
  if (!table) return;

  // 상태는 고르는 순간 저장한다. 체크리스트에서 가장 자주 누르는 곳이라
  // 저장 버튼을 한 번 더 누르게 하면 안 쓴다.
  table.addEventListener("change", function (e) {
    var select = e.target;
    if (!select.classList.contains("task-status")) return;
    var row = select.closest("tr");
    fetch("/api/todo/tasks/" + select.getAttribute("data-id"), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: select.value })
    })
      .then(function (r) {
        if (!r.ok) throw new Error();
        row.classList.toggle("task-done", select.value === "done");
        if (select.value === "done") row.classList.remove("overdue-row");
      })
      .catch(function () { alert("상태를 저장하지 못했습니다."); });
  });
})();
