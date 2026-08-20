// 투자사 풀 → 내 명단 할당.
//
// 풀은 확보해 둔 전체 명단이고, 거기서 골라 자기 명단을 만든다.
// 풀에서 빼지 않는다 — 뽑아 쓰는 것이지 옮기는 것이 아니다.
(function () {
  var bar = document.getElementById("assign-bar");
  if (!bar) return;

  var table = document.getElementById("contacts-table");
  var pickAll = document.getElementById("pick-all-pool");
  var countBox = document.getElementById("pick-count");
  var target = document.getElementById("assign-target");
  var button = document.getElementById("assign-btn");

  function boxes() {
    return Array.prototype.slice.call(table.querySelectorAll(".pool-cb"));
  }

  // 검색·필터로 숨긴 행까지 함께 골라지면, 화면에 없는 사람이 내 명단에 들어온다.
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
    button.disabled = n === 0;
  }

  table.addEventListener("change", function (e) {
    if (e.target.classList.contains("pool-cb")) refresh();
  });

  pickAll.addEventListener("change", function () {
    visibleBoxes().forEach(function (cb) { cb.checked = pickAll.checked; });
    refresh();
  });

  button.addEventListener("click", function () {
    var ids = picked().map(function (cb) { return parseInt(cb.value, 10); });
    var label = target.value;
    if (!ids.length) return;
    if (!confirm(ids.length + "명을 '" + label + "' 명단으로 할당합니다.\n" +
                 "풀에서 빠지지 않고 내 명단에 더해집니다.")) return;
    button.disabled = true;
    fetch("/api/contacts/assign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact_ids: ids, label: label })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "할당 실패"); button.disabled = false; return; }
        window.location.href = "/contacts?sheet=" + encodeURIComponent(label);
      })
      .catch(function () { alert("할당 요청 오류"); button.disabled = false; });
  });

  refresh();
})();
