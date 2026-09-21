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

// 엔터로는 추가되지 않는다 — [추가] 를 눌러야 들어간다.
//
// 세부업무가 여러 줄 칸(textarea)이 되면서 **그 칸의** 엔터는 줄바꿈이 됐다.
// 그런데 같은 폼의 한 줄 칸(항목)에서 엔터를 치면 브라우저가 폼을 보낸다
// (implicit submission) — 요일도 안 고른 규칙이 적다 만 채로 들어간다.
// 사용자가 말한 것은 "엔터로는 추가가 안 되게" 이므로 **폼 전체**에서 막는다.
// 칸마다 막으면 칸이 하나 늘 때 빠뜨리고, 그 칸만 예전처럼 나간다.
//
// **막지 않는 둘**
//   textarea — 엔터가 줄바꿈이다. 막으면 여러 줄을 적을 수가 없다.
//   단추     — 엔터·스페이스로 누른다. 막으면 키보드만 쓰는 사람은 [추가] 에
//              닿아도 누를 수가 없다. `submit` 은 여기서 막는 게 아니라 이
//              단추로만 가게 하는 것이다.
// 체크상자(요일·주차)의 엔터는 막는다. 체크상자를 켜는 키는 **스페이스**이고
// (그건 그대로 돈다), 거기서의 엔터는 토글이 아니라 폼 보내기다 — 켜고 끄는
// 조작은 하나도 안 줄어든다.
(function () {
  var BUTTONISH = { submit: 1, button: 1, reset: 1, image: 1 };

  function keepsEnter(el) {
    if (!el || !el.tagName) return true;
    var tag = String(el.tagName).toUpperCase();
    if (tag === "TEXTAREA" || tag === "BUTTON") return true;
    return tag === "INPUT" && !!BUTTONISH[String(el.type || "").toLowerCase()];
  }

  var forms = document.querySelectorAll("form[data-no-enter-submit]");
  Array.prototype.forEach.call(forms, function (form) {
    form.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      // **한글을 조합하는 중에는 비켜선다.** 그 엔터는 만들던 글자를 굳히는
      // 것이라 폼을 보내는 뜻이 없고(입력기가 먹는다), 여기서 가로채면 조합이
      // 깨진다 — 적는 말이 죄다 한글이다(inline_edit.js 의 같은 자리).
      if (e.isComposing || e.keyCode === 229) return;
      if (keepsEnter(e.target)) return;
      e.preventDefault();
    });
  });
})();
