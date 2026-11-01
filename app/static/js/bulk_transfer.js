// 투자사 관리 현황 — 고른 줄 여러 개를 한 담당자에게 한 번에 이관.
//
// 수정창의 [이관](`contacts.js` 의 `transfer`)을 여러 줄에 한다. 서버도 줄
// 하나 넘기기와 같은 판정을 줄마다 되풀이한다(`routers/contacts.py` 의
// `bulk_transfer_contacts`). 모양은 풀 할당(`pool_assign.js`) · 감춘 줄 지우기
// (`hidden_delete.js`)를 따르고, 머리글 [전체 선택]은 딜 소싱 표의 것처럼
// **지금 보이는 줄만** 고른다 — 켤 때 검색 · 필터에 가린 줄의 체크는 끈다.
(function () {
  var bar = document.getElementById("transfer-bar");
  if (!bar) return;                     // 넘길 수 없는 자리 — 아무 일도 안 한다

  var table = document.getElementById("contacts-table");
  if (!table) return;

  var pickAll = document.getElementById("transfer-pick-all");
  var countBox = document.getElementById("transfer-count");
  var target = document.getElementById("bulk-transfer-target");
  var button = document.getElementById("transfer-bulk-btn");

  function boxes() {
    return Array.prototype.slice.call(table.querySelectorAll(".transfer-cb"));
  }

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
    countBox.textContent = n + "명 선택";
    button.textContent = "선택한 " + n + "명 이관";
    button.disabled = n === 0;
    // 하나라도 고르면 그때 막대가 선다.
    bar.hidden = n === 0;
    if (pickAll) {
      var vis = visibleBoxes();
      var on = vis.filter(function (cb) { return cb.checked; }).length;
      pickAll.checked = vis.length > 0 && on === vis.length && on === n;
      pickAll.indeterminate = !pickAll.checked && n > 0;
    }
  }

  table.addEventListener("change", function (e) {
    if (e.target.classList && e.target.classList.contains("transfer-cb")) refresh();
  });

  if (pickAll) pickAll.addEventListener("change", function () {
    var on = !!pickAll.checked;
    var vis = visibleBoxes();
    boxes().forEach(function (cb) { cb.checked = on && vis.indexOf(cb) !== -1; });
    refresh();
  });

  // 확인창에 **누구를** 넘기는지 적는다. 수만 적으면 검색으로 걸러 놓고
  // [전체 선택]을 누른 뒤 무엇이 걸렸는지 확인할 길이 없다.
  function names(list) {
    var all = list.map(function (cb) { return cb.getAttribute("data-name") || ""; });
    var shown = all.slice(0, 10).join(", ");
    return all.length > 10 ? shown + " 외 " + (all.length - 10) + "명" : shown;
  }

  function resultText(d) {
    var lines = ["성공 " + d.moved.length + "명 · 건너뜀 " + d.skipped.length + "명"];
    d.skipped.slice(0, 10).forEach(function (s) {
      lines.push("· " + (s.name || "(이름 없음)") + " — " + s.why);
    });
    if (d.skipped.length > 10) lines.push("· … 그 밖 " + (d.skipped.length - 10) + "명");
    return lines.join("\n");
  }

  button.addEventListener("click", function () {
    var chosen = picked();
    if (!chosen.length) return;
    var label = target.value;
    if (!label) { alert("받을 담당자를 고르세요."); return; }
    var opt = target.options[target.selectedIndex];
    var owner = (opt && opt.getAttribute("data-owner")) || "";
    // 줄 하나 넘기기와 같은 말을 함께 적는다 — 월별 기록 이야기를 빼면
    // 넘긴 뒤 기록이 날아간 줄 알고 다시 적는다(`contacts.js` 의 `transfer`).
    if (!confirm(chosen.length + "명을 " + owner + " 님에게 이관합니다 (명단 '" + label + "').\n" +
                 names(chosen) + "\n\n" +
                 "· 지금 명단에서 빠지고 " + owner + " 님의 대시보드와 딜 소개 발송 대상으로 옮겨 갑니다.\n" +
                 "· 월별 기록은 명단마다 칸이 따로라 새 명단의 수정창에 보이지 않습니다. " +
                 "지워지지는 않고, 도로 넘기면 다시 보입니다.")) return;

    button.disabled = true;
    fetch("/api/contacts/bulk-transfer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contact_ids: chosen.map(function (cb) { return parseInt(cb.value, 10); }),
        label: label
      })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert((res.d && res.d.detail) || "이관 실패"); refresh(); return; }
        alert(resultText(res.d));
        // 명단별 인원(탭) · 전체 수 · 표의 줄은 모두 서버가 그린다.
        window.location.reload();
      })
      .catch(function () { alert("이관 요청 오류"); refresh(); });
  });

  refresh();
})();
