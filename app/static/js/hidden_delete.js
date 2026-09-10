// 감춘 줄 골라 지우기 — 투자사 관리 현황의 [함께 보기] 안에서만.
//
// 감추기는 지우기가 아니다(`models.VcContact.is_hidden`). 현황 시트를 새로
// 올리면 새 시트에 없는 줄이 감기고, 되돌릴 수 있게 그대로 남는다. 이 파일은
// **그 다음 걸음**이다: 감긴 줄을 훑어보고 확인한 것만 골라 정말로 지운다.
//
// 되돌릴 수 없는 일이라 걸음이 셋이다.
//   ① 고른다 — 상자는 **감춘 줄에만** 서 있다(contacts.html).
//   ② 세어 본다 — 서버를 `confirm` 없이 한 번 불러 무엇이 함께 사라지는지,
//      못 지우는 줄이 있는지 받아 온다. 이때 서버는 아무 것도 지우지 않는다.
//   ③ 묻고 지운다 — 사람이 [확인] 을 누르면 그때 `confirm: true` 로 보낸다.
//
// 확인을 여기(브라우저)에만 두지 않는 이유는 서버 쪽에 적어 두었다
// (`routers/contacts.py` 의 `bulk_delete_contacts`).
(function () {
  var bar = document.getElementById("hidden-del-bar");
  if (!bar) return;                     // 평소 화면 — 아무 일도 하지 않는다

  var table = document.getElementById("contacts-table");
  if (!table) return;

  var pickAll = document.getElementById("pick-all-hidden");
  var countBox = document.getElementById("hidden-del-count");
  var button = document.getElementById("hidden-del-btn");

  function boxes() {
    return Array.prototype.slice.call(table.querySelectorAll(".hidden-del-cb"));
  }

  // 검색·필터로 숨긴 줄까지 [전체 선택]에 딸려 오면, 화면에 없는 줄이 사라진다.
  // 풀 할당 막대가 같은 이유로 같은 것을 본다(`pool_assign.js`).
  function visibleBoxes() {
    return boxes().filter(function (cb) {
      var tr = cb.closest("tr");
      return tr && !tr.hidden;
    });
  }

  function picked() {
    return boxes().filter(function (cb) { return cb.checked; });
  }

  function refresh() {
    var n = picked().length;
    countBox.textContent = n + "줄 선택";
    // 고른 수를 **단추에도** 적는다. 확인창을 보기 전에 몇 줄이 걸린 일인지
    // 알아야 한다 — 80줄과 8줄은 다른 일이다.
    button.textContent = n ? "선택 삭제 (" + n + "줄)" : "선택 삭제";
    button.disabled = n === 0;
  }

  table.addEventListener("change", function (e) {
    if (e.target.classList.contains("hidden-del-cb")) refresh();
  });

  pickAll.addEventListener("change", function () {
    visibleBoxes().forEach(function (cb) { cb.checked = pickAll.checked; });
    refresh();
  });

  function ask(url, ids, confirmed) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact_ids: ids, confirm: confirmed })
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  // 못 지우는 줄을 사람이 읽을 수 있게 편다. 이름을 다 늘어놓으면 확인창이
  // 화면을 넘으므로 앞의 몇 줄만 보이고 나머지는 수로 말한다.
  function blockedText(blocked) {
    var head = blocked.slice(0, 8).map(function (b) {
      return "· " + (b.name || "(이름 없음)") + " — " + b.why.join(", ");
    }).join("\n");
    if (blocked.length > 8) head += "\n· … 그 밖 " + (blocked.length - 8) + "줄";
    return head;
  }

  function planText(plan) {
    var lines = ["고른 " + plan.deletable + "줄을 정말 지웁니다. " +
                 "감추기가 아니라 삭제이고, 되돌릴 수 없습니다.", ""];
    if (plan.activities) {
      lines.push("· 딸린 활동 이력 " + plan.activities + "건이 함께 사라집니다.");
    } else {
      lines.push("· 딸린 자료는 없습니다.");
    }
    lines.push("");
    lines.push("지울까요?");
    return lines.join("\n");
  }

  function done(n) {
    // **보던 자리로 돌아간다.** 명단 탭과 [함께 보기] 를 잃으면, 지운 뒤에
    // 남은 감춘 줄을 다시 찾아 들어가야 한다.
    window.location.href = window.location.pathname +
      "?sheet=" + encodeURIComponent(bar.getAttribute("data-sheet") || "") +
      "&hidden=1&msg=" + encodeURIComponent(n + "줄을 지웠습니다.");
  }

  button.addEventListener("click", function () {
    var chosen = picked();
    var ids = chosen.map(function (cb) { return parseInt(cb.value, 10); });
    if (!ids.length) return;
    button.disabled = true;

    // ② 먼저 세어 본다 — 이 부름은 아무 것도 지우지 않는다.
    ask("/api/contacts/bulk-delete", ids, false).then(function (res) {
      if (!res.ok) {
        alert((res.d && res.d.detail) || "지울 줄을 확인하지 못했습니다");
        refresh();
        return;
      }
      var plan = res.d.plan || {};
      var blocked = plan.blocked || [];
      if (blocked.length) {
        // 걸린 줄은 **체크를 풀어 준다.** 무엇을 풀어야 하는지 사람이 목록에서
        // 찾아 헤매지 않도록. 지우는 것은 다시 눌러야 한다 — 푼 채로 그대로
        // 지워 버리면 고른 것과 사라진 것이 달라진다.
        var off = {};
        blocked.forEach(function (b) { off[b.id] = true; });
        chosen.forEach(function (cb) {
          if (off[parseInt(cb.value, 10)]) cb.checked = false;
        });
        refresh();
        alert("발송 기록 · IR 요청 · 미팅이 걸린 " + blocked.length +
              "줄은 지울 수 없습니다. 그 이력까지 사라지면 지난 보고의 수가 " +
              "바뀝니다.\n\n" + blockedText(blocked) +
              "\n\n체크를 풀었습니다 — 나머지를 지우려면 다시 눌러 주세요.");
        return;
      }
      if (!plan.deletable) { refresh(); return; }
      if (!confirm(planText(plan))) { refresh(); return; }

      // ③ 여기서만 참으로 지운다.
      ask("/api/contacts/bulk-delete", ids, true).then(function (out) {
        if (!out.ok) {
          alert((out.d && out.d.detail) || "삭제 실패");
          refresh();
          return;
        }
        done(out.d.deleted);
      }).catch(function () { alert("삭제 요청 오류"); refresh(); });
    }).catch(function () { alert("삭제 요청 오류"); refresh(); });
  });

  refresh();
})();
