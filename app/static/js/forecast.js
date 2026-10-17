// 업무 보고 › `매출예상리스트`(#46) — 저장 뒤 다시 그리기 · 추가 · 지우기 · [이걸로].
//
// 칸을 눌러 고치는 일은 공통 부품(`inline_edit.js`)이 한다. 자동 칸은 서버만
// 알므로(`services/forecast.py`) 저장 응답의 `cells` 로 그 줄을 다시 그린다.
// 기업 · 투자사 · 심사역을 고치면 딱지(후보)도 바뀌어 화면을 다시 연다.
(function () {
  var table = document.getElementById("fc-table");
  if (!table) return;
  var RELOAD = ["firm", "company_name", "vc_name"];

  function send(method, url, body) {
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.detail || "저장하지 못했습니다");
        return d;
      });
    });
  }

  function reload() { window.location.reload(); }
  function fail(err) { alert(err.message); }

  table.addEventListener("inline-saved", function (e) {
    var cells = (e.detail.data || {}).cells || {};
    var field = e.detail.cell && e.detail.cell.getAttribute("data-field");
    if (RELOAD.indexOf(field) !== -1) { reload(); return; }
    Object.keys(cells).forEach(function (f) {
      var cell = e.detail.row.querySelector('.cell[data-field="' + f + '"]');
      if (!cell) return;
      cell.textContent = cells[f].text;
      cell.setAttribute("data-value", cells[f].value);
      cell.classList.toggle("fc-auto", !!cells[f].auto);
    });
  });

  document.getElementById("fc-add").addEventListener("submit", function (e) {
    e.preventDefault();
    var name = this.elements.company_name.value.trim();
    if (name) send("POST", "/api/forecast", { company_name: name }).then(reload, fail);
  });

  table.addEventListener("click", function (e) {
    var btn = e.target.closest("button");
    var tr = btn && btn.closest("tr[data-id]");
    if (!tr) return;
    var url = "/api/forecast/" + tr.getAttribute("data-id");
    if (btn.classList.contains("js-fc-company")) {
      send("POST", url + "/company",
           { company_id: parseInt(btn.getAttribute("data-company"), 10) }).then(reload, fail);
    } else if (btn.classList.contains("js-fc-vc")) {
      send("PATCH", url, { vc_name: btn.getAttribute("data-name") }).then(reload, fail);
    } else if (btn.classList.contains("js-fc-delete")) {
      var name = tr.querySelector('[data-field="company_name"]').textContent.trim();
      if (window.confirm("'" + name + "' 줄을 지웁니다. 되돌릴 수 없습니다.")) {
        send("DELETE", url).then(reload, fail);
      }
    }
  });
})();
