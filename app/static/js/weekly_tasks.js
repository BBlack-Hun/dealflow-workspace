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
    // 저장에 실패하면 되돌아갈 값. 서버가 그려 준 상태에서 시작해서
    // 저장이 될 때마다 따라 온다.
    var before = select.getAttribute("data-prev");
    var after = select.value;
    fetch("/api/todo/tasks/" + select.getAttribute("data-id"), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: after })
    })
      .then(function (r) {
        if (!r.ok) throw new Error();
        select.setAttribute("data-prev", after);
        row.classList.toggle("task-done", after === "done");
        if (after === "done") row.classList.remove("overdue-row");
      })
      .catch(function () {
        // **고른 대로 되돌린다.** 그러지 않으면 칸에는 `완료` 가 떠 있고
        // 서버에는 `예정` 이 남는다 — 새로고침해야 알 수 있고, 그때까지
        // 다 한 줄로 보인다. 칸 수정(inline_edit.js)은 이미 이렇게 한다.
        if (before !== null) select.value = before;
        alert("상태를 저장하지 못했습니다.");
      });
  });
})();

// 요일 옆 오전/오후 — 반복 업무는 인라인 편집 대상이 아니라 버튼으로 고른다
// (값이 셋뿐이라 뜨는 편집창보다 눌러서 바로 켜는 편이 빠르다).
(function () {
  var table = document.getElementById("routine-table");
  if (!table) return;

  table.addEventListener("click", function (e) {
    var btn = e.target.closest(".tod-pick");
    if (!btn) return;
    var id = btn.getAttribute("data-routine");
    var value = btn.getAttribute("data-value");
    var now = btn.classList.contains("on");
    var next = now ? "" : value;   // 다시 누르면 '상관없음'으로

    fetch("/api/todo/routines/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ time_of_day: next })
    }).then(function (r) {
      if (!r.ok) throw new Error();
      table.querySelectorAll('.tod-pick[data-routine="' + id + '"]')
        .forEach(function (b) { b.classList.remove("on"); });
      if (next) btn.classList.add("on");
    }).catch(function () { alert("저장하지 못했습니다."); });
  });
})();
