// 딜 소싱 — 카톡방 [방 후보 찾기] · [이 방으로 확정]을 **새로고침 없이** 보낸다.
// (node tests/js/sourcing_rooms_async_test.js)
//
// 사용자: "딜 소싱에서 방 후보 누를때 비동기로 해줘… 계속 새로고침이 되서… 연속해서
// 클릭을 못함". 예전에는 폼이 보내지고 되돌아오며 화면 전체를 다시 그려 스크롤 ·
// 검색 · 필터 · 체크가 풀렸다.
//
// **폼은 그대로 둔다** — 스크립트가 없으면 예전처럼 보내고 되돌아온다. 여기서는 그
// 폼의 제출을 가로채 같은 주소로 `Accept: application/json` 을 달아 보내고(서버가
// JSON 으로 답한다 — `routers/sourcing._answer`), 그 줄만 고친다. 무엇을 찾을지 ·
// 무엇을 확정할 수 있는지는 예전처럼 서버가 정한다.
//
// 다른 손이 먼저 막은 제출(툴바 [방 후보 찾기]의 확인창 취소 · 아무도 안 고름 —
// `sourcing.html`, 팀원 화면으로 보는 중 — `view_as.js`)은 건드리지 않는다.
(function () {
  function note(form, text, bad) {
    var box = form.querySelector(".js-room-note");
    if (!box) {
      box = document.createElement("span");
      box.style.marginLeft = "6px";
      form.appendChild(box);
    }
    box.className = "js-room-note " + (bad ? "warn-text" : "muted");
    box.textContent = text;
  }

  // 찾기는 잡만 세운다 — 찾는 것은 누른 사람 PC 의 발송기다. 실린 줄마다 적어 둔다.
  function searched(form, d) {
    var text = "찾기 요청됨(회차 #" + d.job_id + ") — 끝나면 새로고침해 후보를 고르세요";
    (d.ids || []).forEach(function (id) {
      var tr = document.querySelector('#sourcing-table tr[data-id="' + id + '"]');
      var rowForm = tr && tr.querySelector(".js-room-search");
      if (rowForm) note(rowForm, text);
    });
    if (!form.closest("tr")) note(form, d.msg || text);
  }

  // 확정 — 서버가 그리는 확정된 줄과 같게: 방 이름 칸에 제목, `방 없음` · 후보 · 이어받은
  // 방 표시는 걷는다(`sourcing.html` 의 카톡방 칸).
  function confirmed(form, d) {
    var td = form.closest("td");
    var tr = form.closest("tr");
    if (!td || !tr) return;
    var cell = td.querySelector('.cell[data-field="kakao_room_name"]');
    if (cell) cell.textContent = d.room || "";
    td.setAttribute("title", d.room || "");
    Array.prototype.slice.call(td.querySelectorAll(".cell-sub")).forEach(function (n) {
      if (n.parentNode) n.parentNode.removeChild(n);
    });
    var done = document.createElement("div");
    done.className = "cell-sub muted js-room-note";
    done.textContent = "✓ 이 방으로 확정했습니다";
    td.appendChild(done);
    tr.removeAttribute("data-no-room");
    // 툴바 [방 후보 찾기 (선택 N명)]이 이 줄을 다시 세게 — 그 셈은 체크 칸이 바뀔 때 돈다.
    var cb = tr.querySelector(".js-sourcing-pick");
    if (cb) cb.dispatchEvent(new Event("change", { bubbles: true }));
  }

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || !form.classList) return;
    var search = form.classList.contains("js-room-search");
    if (!search && !form.classList.contains("js-room-confirm")) return;
    if (e.defaultPrevented) return;
    e.preventDefault();
    // 한 줄의 후보 단추들은 함께 잠근다 — 둘을 잇달아 누르면 화면과 저장이 갈린다.
    var scope = (!search && form.closest(".sourcing-room")) || form;
    if (scope.getAttribute("data-busy")) return;
    // 서버가 잠가 둔 단추(같은 제목이 여럿)는 끝나도 잠긴 채로 둔다.
    var btns = Array.prototype.slice.call(scope.querySelectorAll("button"))
      .filter(function (b) { return !b.disabled; });
    function release() {
      scope.removeAttribute("data-busy");
      btns.forEach(function (b) { b.disabled = false; });
    }
    scope.setAttribute("data-busy", "1");
    btns.forEach(function (b) { b.disabled = true; });
    note(form, search ? "찾기 요청 중…" : "확정 중…");
    fetch(form.getAttribute("action"), {
      method: "POST",
      headers: { "Accept": "application/json" },
      body: new FormData(form)
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (d) { return { ok: r.ok && !!d.ok, d: d }; });
    }).then(function (res) {
      release();
      if (!res.ok) {
        var why = typeof res.d.detail === "string" && res.d.detail;
        note(form, why || "처리하지 못했습니다 — 화면을 새로 열어 다시 눌러 보세요", true);
        return;
      }
      if (search) searched(form, res.d);
      else confirmed(form, res.d);
    }).catch(function () {
      release();
      note(form, "요청 오류 — 다시 눌러 보세요", true);
    });
  });
})();
