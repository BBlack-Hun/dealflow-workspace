// 투자사 조사 업로드(관리자 · #1) — `챗GPT 조사 소유펀드` · `펀드 종류` · `소분류`.
// 미리보기로 맞춘 회사 / 못 맞춘 이름 / 못 넣는 줄을 본 뒤, **확인을 받고** 회사마다
// 채운 칸만 바꾼다.
//
// 같은 파일을 두 번 보낸다(`contact_import.js` 와 같은 방식): 먼저 dry_run 으로
// 결과만 받아 보여 주고, 사람이 확인한 뒤 dry_run=false 로 다시 보낸다 — 서버에
// 파일을 쌓아 두지 않아도 되고, 무엇을 반영하는지가 분명하다.
(function () {
  "use strict";
  var panel = document.getElementById("funds-panel");
  if (!panel) return;

  var fileInput = document.getElementById("funds-file");
  var previewBtn = document.getElementById("funds-preview");
  var applyBtn = document.getElementById("funds-apply");
  var result = document.getElementById("funds-result");
  var pending = 0;   // 미리보기에서 바뀌는 회사 수 — 0 이면 반영할 것이 없다

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  document.getElementById("funds-btn").addEventListener("click", function () {
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  document.getElementById("funds-close").addEventListener("click", function () {
    panel.hidden = true;
  });
  fileInput.addEventListener("change", reset);

  function reset() {
    pending = 0;
    applyBtn.disabled = true;
    result.innerHTML = "";
  }

  function render(d) {
    var c = d.counts || {};
    var html = '<ul class="import-stats">' +
      "<li><span>맞춘 회사</span><b>" + (c.matched || 0) + "곳</b></li>" +
      "<li><span>값이 바뀌는 회사</span><b>" + (c.changes || 0) + "곳</b></li>" +
      "<li><span>못 맞춘 이름</span><b" + (c.unmatched ? ' class="warn"' : "") + ">" +
        (c.unmatched || 0) + "개</b></li>" +
      "<li><span>값이 다 빈 줄(건너뜀)</span><b>" + (c.blank || 0) + "줄</b></li>" +
      "<li><span>못 넣는 줄</span><b" + (c.errors ? ' class="warn"' : "") + ">" +
        (c.errors || 0) + "줄</b></li>" +
      "</ul>";
    var labels = d.labels || {};
    // 채운 칸만 `머리글: 값` 으로 한 줄씩(서버가 실은 `before` · `after` 의 칸).
    function values(m, side) {
      return Object.keys(m.after).map(function (f) {
        var v = side === "after" ? "<b>" + esc(m.after[f]) + "</b>" : esc(m.before[f] || "—");
        return esc(labels[f] || f) + ": " + v;
      }).join("<br>");
    }
    var changes = (d.matched || []).filter(function (m) { return m.changes; });
    if (changes.length) {
      html += '<table class="grid-table compact"><thead><tr>' +
        "<th>줄</th><th>올린 이름</th><th>맞춘 회사</th><th>지금 값</th><th>바뀔 값</th>" +
        "</tr></thead><tbody>" +
        changes.map(function (m) {
          return "<tr><td>" + esc(m.line) + "</td><td>" + esc(m.name) + "</td><td>" +
            esc(m.firm) + ' <span class="muted">(' + esc(m.rows) + "줄)</span></td><td>" +
            values(m, "before") + "</td><td>" + values(m, "after") + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    if ((d.unmatched || []).length) {
      html += '<p class="hint err">못 맞춘 이름 — 넣지 않습니다(투자사 관리 현황에 없는 회사): ' +
        d.unmatched.map(function (u) { return esc(u.name) + " (" + esc(u.line) + "줄)"; })
          .join(", ") + "</p>";
    }
    if ((d.errors || []).length) {
      html += '<p class="hint err">못 넣는 줄 — 넣지 않습니다: ' +
        d.errors.map(function (u) {
          return esc(u.name) + " (" + esc(u.line) + "줄 — " + esc(u.reason) + ")";
        }).join(", ") + "</p>";
    }
    if ((d.duplicates || []).length) {
      html += '<p class="hint">같은 회사가 두 번 — 아래 줄 값을 씁니다: ' +
        d.duplicates.map(function (u) {
          return esc(u.name) + " (" + esc(u.line) + "줄 → " + esc(u.kept_line) + "줄)";
        }).join(", ") + "</p>";
    }
    result.innerHTML = html;
  }

  function send(dryRun) {
    var f = fileInput.files[0];
    if (!f) { result.innerHTML = '<p class="err">파일을 먼저 고르세요.</p>'; return; }
    var fd = new FormData();
    fd.append("file", f);
    fd.append("dry_run", dryRun ? "true" : "false");
    previewBtn.disabled = true;
    applyBtn.disabled = true;
    result.innerHTML = '<p class="muted">' + (dryRun ? "읽는 중…" : "반영 중…") + "</p>";
    fetch("/api/import/owned-funds", { method: "POST", body: fd })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        previewBtn.disabled = false;
        if (!res.ok) {
          result.innerHTML = '<p class="err">' + esc(res.d.detail || "읽지 못했습니다") + "</p>";
          return;
        }
        if (dryRun) {
          render(res.d);
          pending = (res.d.counts || {}).changes || 0;
          applyBtn.disabled = !pending;
          return;
        }
        result.innerHTML = '<p class="hint ok">' + esc(res.d.changed) +
          "곳의 값을 바꿨습니다. 표를 다시 불러옵니다…</p>";
        setTimeout(function () { window.location.reload(); }, 700);
      })
      .catch(function () {
        previewBtn.disabled = false;
        result.innerHTML = '<p class="err">보내지 못했습니다.</p>';
      });
  }

  previewBtn.addEventListener("click", function () { send(true); });
  applyBtn.addEventListener("click", function () {
    if (!pending) return;
    // **확인을 받고** 바꾼다 — 회사마다 값을 통째로 갈아 끼우고, 그 회사의 모든
    // 사람 줄에 그대로 보인다.
    if (!window.confirm(pending + "곳의 값을 올린 값으로 바꿉니다(빈 칸은 그대로).\n" +
                        "같은 회사의 모든 줄에 그대로 보입니다. 진행할까요?")) return;
    send(false);
  });
})();
