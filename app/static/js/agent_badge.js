// Poll the agent connection badge (FEATURE_SPEC §0.2).
(function () {
  var badge = document.getElementById("agent-badge");
  var label = document.getElementById("agent-badge-label");
  if (!badge) return;
  function refresh() {
    fetch("/api/agent-status")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        badge.classList.toggle("on", !!d.online);
        badge.classList.toggle("off", !d.online);
        if (label) label.textContent = d.label;
      })
      .catch(function () {});
  }
  refresh();
  setInterval(refresh, 5000);
})();

// 내 투자사 선호 — 몇 명까지 볼지 새로고침 없이 바꾼다.
// 대시보드 전체를 다시 그리면 스크롤이 맨 위로 튀고, 이 목록 하나 보려고
// 나머지를 다 기다린다.
(function () {
  var list = document.getElementById("req-rank");
  if (!list) return;

  document.querySelectorAll(".js-top-n").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var n = btn.getAttribute("data-n");
      btn.disabled = true;
      fetch("/api/dashboard/top-requesters?top=" + n)
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) throw new Error();
          list.innerHTML = d.rows.map(rowHtml).join("");
          // 몇 명이 걸렸는지도 같이 고친다 — 개수만 바꾸고 숫자를 그대로 두면
          // 50명으로 놓았는데 12명이 나온 이유를 알 수 없다.
          var pill = document.getElementById("req-rank-count");
          if (pill) {
            pill.innerHTML = "<b>" + d.rows.length + "</b>명";
            pill.classList.toggle("on", d.rows.length > 0);
          }
          document.querySelectorAll(".js-top-n").forEach(function (b) {
            b.classList.toggle("active", b === btn);
          });
          // 주소도 맞춰 둔다 — 새로고침해도 같은 개수가 나온다
          if (history.replaceState) history.replaceState(null, "", "/?top=" + n);
        })
        .catch(function () { alert("불러오지 못했습니다."); })
        .finally(function () { btn.disabled = false; });
    });
  });

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  function rowHtml(r, i) {
    var chips = (r.companies || []).map(function (c) {
      return '<span class="tag soft">' + esc(c) + "</span>";
    }).join("");
    return '<li>' +
      '<a href="/contacts?contact=' + r.id + '" title="이 투자사 상세 보기 (선호 분야·라운드)">' +
        '<span class="req-no">' + (i + 1) + "</span>" +
        '<span class="req-who"><b>' + esc(r.name) + "</b> " +
          '<span class="muted">' + esc(r.title) + "</span>" +
          '<span class="cell-sub muted">' + esc(r.firm) + "</span></span>" +
        '<span class="req-count"><b>' + r.count + "</b>건</span>" +
      "</a>" +
      (chips ? '<div class="req-companies">' + chips + "</div>" : "") +
      "</li>";
  }
})();
