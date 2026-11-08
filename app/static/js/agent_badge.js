// Poll the agent connection badge (FEATURE_SPEC §0.2).
(function () {
  var badge = document.getElementById("agent-badge");
  var label = document.getElementById("agent-badge-label");
  if (!badge) return;
  function refresh() {
    fetch("/api/agent-status")
      // 로그인이 끊겼거나 막힌 화면(초기 비밀번호 변경 전)이면 배지를 그대로 둔다.
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
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

  // 고를 값이 여섯(10~300)으로 늘면서 칩 여섯 줄이 390px 을 넘겼다.
  // 이제 **드롭다운 한 칸**이라 누르는 것이 아니라 고르는 것이다(`change`).
  document.querySelectorAll("select.js-top-n").forEach(function (pick) {
    pick.addEventListener("change", function () {
      var n = pick.value;
      pick.disabled = true;
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
          // 고른 수보다 적게 나왔으면 그 까닭도 같이 말한다 — 운영에서는
          // 요청한 곳이 10곳뿐이라 100·200·300 이 전부 같은 목록을 준다.
          // 이 줄이 없으면 사용자는 자기 명단이 아니라 화면을 의심한다.
          var all = document.getElementById("req-rank-all");
          if (all) {
            var short = d.rows.length > 0 && d.rows.length < Number(n);
            all.hidden = !short;
            var b = all.querySelector("b");
            if (b) b.textContent = d.rows.length;
          }
          // 주소도 맞춰 둔다 — 새로고침해도 같은 개수가 나온다
          if (history.replaceState) history.replaceState(null, "", "/?top=" + n);
        })
        .catch(function () { alert("불러오지 못했습니다."); })
        .finally(function () { pick.disabled = false; });
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

// 옛 발송기 알림(`_agent_update.html`) — [오늘 하루 보지 않기] 를 고르고 닫으면
// 오늘은 다시 안 띄운다. 쿠키에 적는 날짜는 서버가 창에 실어 준 한국 날짜
// (`data-today`)이고, 띄울지는 서버가 그 쿠키를 오늘과 견주어 정한다
// (`services/agent_update.HIDE_COOKIE`) — 자정이 지나면 날짜가 어긋나 다시 뜬다.
// 닫기는 브라우저가 한다(`method="dialog"`). 여기는 적기만 한다.
(function () {
  var box = document.querySelector("dialog.agent-update");
  if (!box) return;
  box.addEventListener("close", function () {
    var skip = document.getElementById("agent-update-skip");
    var day = box.getAttribute("data-today");
    if (!skip || !skip.checked || !day) return;
    document.cookie = "agent_update_hide=" + day + "; path=/; max-age=86400; SameSite=Lax";
  });
})();

// 자동 발송 알림(`_auto_alert.html`) — [확인] 으로 닫으면 그 알림의 열쇠(`data-key`)를
// 쿠키에 `|` 로 이어 적는다. 같은 열쇠의 창은 서버가 다시 안 띄우고
// (`automation_runner.ALERT_COOKIE`), 다음 단계(당일 · 끝난 뒤)는 열쇠가 달라 뜬다.
// [자세히 보기] 로 넘어가도 본 것으로 적는다 — 넘어간 화면에서 같은 창이 또 뜨지 않게.
// 닫기는 브라우저가 한다(`method="dialog"`). 여기는 적기만 한다.
(function () {
  var box = document.querySelector("dialog.auto-alert");
  if (!box) return;
  function seen() {
    var key = box.getAttribute("data-key");
    if (!key) return;
    var found = document.cookie.match(/(?:^|; )auto_alert_seen=([^;]*)/);
    var keys = (found ? found[1].split("|") : []).filter(function (k) { return k && k !== key; });
    keys.push(key);
    document.cookie = "auto_alert_seen=" + keys.slice(-6).join("|") +
      "; path=/; max-age=" + 7 * 86400 + "; SameSite=Lax";
  }
  box.addEventListener("close", seen);
  var go = box.querySelector("a.guard-go");
  if (go) go.addEventListener("click", seen);
})();
