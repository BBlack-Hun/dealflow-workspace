// 딜소개 메모 → 활동 이력 (#52) — 투자사 관리 현황 탭 툴바의 단추.
//
// 그룹웨어로 안 보내고 탭의 `N월 1차 딜소개` 칸에 메모로 적는 탭이 있다. 그
// 메모의 회차를 손으로 보낸 기록으로 옮긴다(`services/memo_intro.py`).
//   ① 세어 본다 — `confirm` 없이 불러 새로 적을 회차 · 이미 있음 · 건너뜀 ·
//      거둘 줄을 받아 온다. 이때 서버는 아무 것도 안 쓴다.
//   ② 묻고 반영한다 — [확인] 을 누르면 그때 `confirm: true` 로 보낸다.
(function () {
  var button = document.getElementById("memo-intro-btn");
  if (!button) return;                  // 딜소개 칸이 없는 탭 · 남의 탭

  var sheet = button.getAttribute("data-sheet") || "";
  var url = "/api/contacts/memo-intro";

  function ask(confirmed) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sheet: sheet, confirm: confirmed })
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  // 목록이 길면 확인창이 화면을 넘는다 — 앞의 몇 줄만 보이고 나머지는 수로 말한다.
  function list(items, line) {
    var out = items.slice(0, 6).map(function (i) { return "    " + line(i); });
    if (items.length > 6) out.push("    … 그 밖 " + (items.length - 6) + "줄");
    return out;
  }

  function where(i) {
    return (i.name || "(이름 없음)") + " · " + i.column + " · " +
      String(i.raw || "").split("\n")[0];
  }

  function planText(p) {
    var lines = ["딜소개 메모를 활동 이력에 반영합니다 (" +
                 String(p.start || "").slice(0, 7) + " 이후 회차만, 리마인드는 안 잡힘).", ""];
    lines.push("· 새로 적을 회차 " + p.add.length + "줄");
    lines = lines.concat(list(p.rounds || [], function (r) {
      return r.column + " " + r.day + " — " + r.people + "명";
    }));
    lines.push("· 이미 있음 " + p.already.length + "줄");
    if (p.undone.length) lines.push("· 되돌린 줄이라 다시 안 적음 " + p.undone.length + "줄");
    lines.push("· 건너뜀 — 날짜 없음 " + p.no_date.length + " · 기업 없음 " +
               p.no_company.length + " · 시작 달 이전 " + p.before_start.length +
               " · 앞날 " + p.future.length);
    if (p.no_date.length) lines = lines.concat(["  날짜 없음:"], list(p.no_date, where));
    if (p.no_company.length) lines = lines.concat(["  기업 없음:"], list(p.no_company, where));
    lines.push("· 거둘 줄(메모에서 지워진 회차) " + p.retract.length + "줄");
    lines = lines.concat(list(p.retract, function (r) {
      return (r.name || "(이름 없음)") + " · " + r.day + " · " +
        ((r.companies || []).join(", ") || (r.count + "개사"));
    }));
    return lines.join("\n");
  }

  function reset() { button.disabled = false; }

  button.addEventListener("click", function () {
    button.disabled = true;
    ask(false).then(function (res) {
      if (!res.ok) {
        alert((res.d && res.d.detail) || "메모를 확인하지 못했습니다");
        reset();
        return;
      }
      var p = res.d.plan;
      if (!p.add.length && !p.retract.length) {
        alert(planText(p) + "\n\n반영할 것이 없습니다.");
        reset();
        return;
      }
      if (!confirm(planText(p) + "\n\n반영할까요?")) { reset(); return; }
      ask(true).then(function (out) {
        if (!out.ok) {
          alert((out.d && out.d.detail) || "반영 실패");
          reset();
          return;
        }
        window.location.href = window.location.pathname + "?sheet=" +
          encodeURIComponent(sheet) + "&msg=" +
          encodeURIComponent("딜소개 메모 반영: " + out.d.note);
      }).catch(function () { alert("반영 요청 오류"); reset(); });
    }).catch(function () { alert("반영 요청 오류"); reset(); });
  });
})();
