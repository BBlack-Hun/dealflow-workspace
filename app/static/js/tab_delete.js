// 탭 지우기 — 투자사 관리 현황 · 스타트업의 [⚙ 명단·칸 설정] 안(관리자만).
//
// **그 탭에만 있는 투자사도 함께 지운다.** 다른 탭에도 있는 사람은 남고 이 탭
// 표시만 빠진다. 되돌릴 수 없는 일이라 [선택 삭제] 와 같은 걸음을 밟는다
// (`hidden_delete.js`).
//   ① 세어 본다 — 서버를 `confirm` 없이 불러 몇 명이 지워지고 몇 명이 남는지,
//      막는 사람이 있는지 받아 온다. 이때 서버는 아무 것도 지우지 않는다.
//   ② 묻고 지운다 — 사람이 [확인] 을 누르면 그때 `confirm: true` 로 보낸다.
//
// 확인을 여기(브라우저)에만 두지 않는 이유는 서버 쪽에 적어 두었다
// (`routers/contacts.py` 의 `delete_list_sheet`).
(function () {
  var button = document.getElementById("tab-delete-btn");
  if (!button) return;                  // 관리자가 아니거나 탭을 안 고른 화면

  var label = button.getAttribute("data-label") || "";
  var url = "/api/contacts/sheets/delete";

  function ask(confirmed) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: label, confirm: confirmed })
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  // 막는 사람을 읽을 수 있게 편다. 다 늘어놓으면 확인창이 화면을 넘으므로
  // 앞의 몇 명만 보이고 나머지는 수로 말한다.
  function blockedText(blocked) {
    var head = blocked.slice(0, 8).map(function (b) {
      var who = b.name || "(이름 없음)";
      if (b.firm) who += " · " + b.firm;
      return "· " + who + " — " + b.why;
    }).join("\n");
    if (blocked.length > 8) head += "\n· … 그 밖 " + (blocked.length - 8) + "명";
    return head;
  }

  function planText(plan) {
    return [
      "'" + plan.label + "' 탭을 지웁니다. 되돌릴 수 없습니다.",
      "",
      "· 이 탭에만 있는 투자사 " + plan.only + "명 — 함께 지워집니다.",
      "· 다른 탭에도 있는 " + plan.shared + "명 — 남습니다(이 탭 표시만 빠집니다).",
      "· 활동 이력 " + (plan.activities || 0) + "건 — 함께 지워집니다.",
      "",
      "지울까요?"
    ].join("\n");
  }

  function reset() { button.disabled = false; }

  button.addEventListener("click", function () {
    button.disabled = true;

    // ① 먼저 세어 본다 — 이 부름은 아무 것도 지우지 않는다.
    ask(false).then(function (res) {
      if (!res.ok) {
        alert((res.d && res.d.detail) || "지울 탭을 확인하지 못했습니다");
        reset();
        return;
      }
      var plan = res.d.plan || {};
      var blocked = plan.blocked || [];
      if (blocked.length) {
        alert("이 탭에만 있는 투자사 중 " + blocked.length + "명에게 발송 기록 · " +
              "IR 요청 · 미팅이 걸려 있어 탭을 지울 수 없습니다. 그 이력까지 " +
              "사라지면 지난 보고의 수가 바뀝니다.\n\n" + blockedText(blocked) +
              "\n\n그 사람들을 [수정] 창의 [이관] 으로 다른 명단에 옮긴 뒤 다시 " +
              "눌러 주세요.");
        reset();
        return;
      }
      if (!confirm(planText(plan))) { reset(); return; }

      // ② 여기서만 참으로 지운다.
      ask(true).then(function (out) {
        if (!out.ok) {
          alert((out.d && out.d.detail) || "탭 삭제 실패");
          reset();
          return;
        }
        // 지운 탭은 다시 열 수 없으니 `?sheet=` 없이 그 화면만 연다
        // (참고 탭 지우기와 같다 — `delete_ref_sheet`).
        var d = out.d;
        window.location.href = (d.back || window.location.pathname) +
          "?msg=" + encodeURIComponent("'" + d.plan.label + "' 탭을 지웠습니다 — 투자사 " +
            d.deleted + "명 삭제 · " + d.kept + "명은 다른 탭에 남음.");
      }).catch(function () { alert("탭 삭제 요청 오류"); reset(); });
    }).catch(function () { alert("탭 삭제 요청 오류"); reset(); });
  });
})();
