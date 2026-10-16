// `Series A 이상 딜 소싱` 탭의 [딜소개 문구 올리기] — 관리자만, 미리보기로 확인한 뒤에만 반영한다.
//
// 투자사 관리 현황 업로드(`contact_import.js`)와 같은 짜임이다. 같은 파일을 두 번
// 보낸다: 먼저 `dry_run` 으로 무엇이 바뀌는지 받아 보여 주고, 사람이 확인한 뒤
// `dry_run=false` 로 다시 보내 반영한다(서버에 파일을 쌓아 두지 않는다 — 반영도
// 파일에서 처음부터 다시 센다, `routers/series_a.upload_pitch`).
//
// 어느 줄에 맞는지 · 무엇이 바뀌는지는 **서버가 센다**(`services/series_a_pitch_upload.py`).
// 이 파일은 보내고 그리기만 한다 — 맞추는 규칙을 여기 또 적으면 두 벌이 된다.
// 표의 다른 일(검색 · 필터 · 고치기)은 `series_a.js` 가 한다 — 따로 둔 파일이다.
(function () {
  var panel = document.getElementById("sa-pitch-panel");
  if (!panel) return;

  var fileInput = document.getElementById("sa-pitch-file");
  // 탭 고르개 — 워크북에서 이 시트로 보이는 탭을 서버가 하나로 못 고를 때만 뜬다.
  var sheetBox = document.getElementById("sa-pitch-sheet-box");
  var sheetSel = document.getElementById("sa-pitch-sheet");
  var overwrite = document.getElementById("sa-pitch-overwrite");
  var previewBtn = document.getElementById("sa-pitch-preview");
  var applyBtn = document.getElementById("sa-pitch-apply");
  var result = document.getElementById("sa-pitch-result");
  var last = null;   // 지금 보이는 미리보기 — 있어야 반영할 수 있다

  var HOW = { fill: "채움", overwrite: "덮어씀" };

  document.getElementById("sa-pitch-btn").addEventListener("click", function () {
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  document.getElementById("sa-pitch-close").addEventListener("click", function () {
    panel.hidden = true;
  });

  // 파일 · 탭 · 덮어쓰기를 바꾸면 보던 미리보기는 낡았다 — 다시 봐야 반영할 수 있다.
  fileInput.addEventListener("change", function () {
    resetPreview();
    fillSheets([]);
  });
  sheetSel.addEventListener("change", resetPreview);
  overwrite.addEventListener("change", resetPreview);

  function resetPreview() {
    last = null;
    applyBtn.disabled = true;
    result.innerHTML = "";
  }

  // 서버가 알려 준 파일의 탭들로 고르개를 세운다. 고른 탭은 남긴다.
  function fillSheets(names) {
    var keep = sheetSel.value || "";
    while (sheetSel.children.length) sheetSel.removeChild(sheetSel.children[0]);
    var auto = document.createElement("option");
    auto.value = "";
    auto.textContent = "알아서 고르기";
    sheetSel.appendChild(auto);
    (names || []).forEach(function (name) {
      var o = document.createElement("option");
      o.value = name;
      o.textContent = name;
      sheetSel.appendChild(o);
    });
    sheetSel.value = (names || []).indexOf(keep) >= 0 ? keep : "";
    sheetBox.hidden = (names || []).length < 2;
  }

  function send(dryRun) {
    var f = fileInput.files && fileInput.files[0];
    if (!f) { result.innerHTML = '<p class="err">파일을 먼저 고르세요.</p>'; return; }

    var fd = new FormData();
    fd.append("file", f);
    fd.append("sheet", sheetSel.value || "");
    fd.append("overwrite", overwrite.checked ? "true" : "false");
    fd.append("dry_run", dryRun ? "true" : "false");

    previewBtn.disabled = true;
    applyBtn.disabled = true;
    result.innerHTML = '<p class="muted">' + (dryRun ? "읽는 중…" : "반영 중…") + "</p>";

    return fetch("/api/import/series-a-pitch", { method: "POST", body: fd })
      .then(function (r) {
        return r.json().catch(function () { return {}; })
          .then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (res) {
        previewBtn.disabled = false;
        if (res.d && res.d.sheets && res.d.sheets.length) fillSheets(res.d.sheets);
        if (!res.ok) {
          last = null;
          result.innerHTML = '<p class="err">' + esc(res.d.detail || "올리지 못했습니다") + "</p>";
          return;
        }
        if (dryRun) {
          last = res.d;
          render(res.d);
          // 바뀔 것이 없으면 [반영] 할 것도 없다.
          applyBtn.disabled = !res.d.changed;
        } else {
          done(res.d);
        }
      })
      .catch(function () {
        previewBtn.disabled = false;
        result.innerHTML = '<p class="err">올리기 요청 오류</p>';
      });
  }

  // 반영 뒤 — 표를 새로 그려야 바뀐 문구가 보인다. **보던 자리(탭 · 필터)는
  // 그대로** 두고 한 줄 알림(`msg`)만 얹는다(`hidden_delete.js` 와 같은 방식).
  function done(d) {
    var keep = String(window.location.search || "").replace(/^\?/, "").split("&")
      .filter(function (pair) { return pair && pair.indexOf("msg=") !== 0; });
    keep.push("msg=" + encodeURIComponent(d.summary || "반영했습니다."));
    window.location.href = window.location.pathname + "?" + keep.join("&");
  }

  function render(d) {
    var html = '<div class="import-summary"><b>미리보기 — 아직 반영되지 않았습니다</b>' +
      '<ul class="import-stats">' +
      ((d.sheets || []).length ? li("읽은 탭", d.sheet_used) : "") +
      li("파일의 줄", d.file_rows + "줄" +
         (d.no_name ? " (기업명이 빈 줄 " + d.no_name + "줄 건너뜀)" : "")) +
      li("맞은 줄", d.matched + "줄") +
      li("못 맞춘 줄", d.unmatched + "줄" +
         (d.unmatched_with_pitch ? " (문구 있는 줄 " + d.unmatched_with_pitch + ")" : "")) +
      li("애매해서 건너뛴 줄", d.ambiguous + "줄") +
      li("시트 안 중복", d.duplicates + "줄") +
      li("바뀔 줄", d.changed + "줄 (채움 " + d.filled + " · 덮어씀 " + d.overwritten + ")") +
      li("그대로 둘 줄", (d.same + d.kept + d.blank) + "줄") +
      "</ul></div>";

    var notes = [];
    if (d.kept) {
      notes.push("이미 다른 문구가 적힌 줄 " + d.kept + "줄은 그대로 둡니다 — " +
                 "덮으려면 [이미 적힌 문구도 덮어쓰기]를 켜고 다시 미리보세요.");
    }
    if (d.same) notes.push("문구가 이미 같은 줄 " + d.same + "줄은 그대로입니다.");
    if (d.blank) notes.push("파일의 딜소개 문구가 빈 줄 " + d.blank + "줄은 아무것도 지우지 않습니다.");
    if (d.unmatched) {
      notes.push("못 맞춘 줄은 이 탭에 없는 딜입니다 — 줄을 새로 만들지 않습니다.");
    }
    if (d.ambiguous) {
      notes.push("애매한 줄은 이 탭에 같은 기업명 · 수신 일자의 줄이 둘 이상이거나, " +
                 "그 줄을 바라는 파일 줄이 둘 이상입니다 — 표에서 겹친 줄을 정리한 뒤 다시 올리세요.");
    }
    if (d.duplicates) notes.push("파일 안에서 같은 딜이 겹친 줄은 앞 줄만 씁니다.");
    if (!d.changed) notes.push("바꿀 줄이 없습니다.");
    if (notes.length) {
      html += '<ul class="import-notes">' +
        notes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>";
    }

    // 바뀔 줄 — 지금 문구와 새 문구를 **나란히** 둔다. 둘 중 하나만 보이면 덮어도
    // 되는지 사람이 판단할 수 없다. 문구는 서버가 줄여 보낸다.
    if ((d.changes || []).length) {
      html += '<details class="import-skipped" open><summary>바뀔 줄 ' + d.changed + "줄" +
        more(d.changes.length, d.changed) + "</summary>" +
        '<table class="mini-table"><tr>' + heads() +
        "<th>지금 문구</th><th>새 문구</th></tr>" +
        d.changes.map(function (c) {
          var tag = c.how === "overwrite" ? "tag warn" : "tag soft";
          return "<tr>" + idCells(c) + "<td>" + esc(c.before) + "</td><td>" +
            '<span class="' + tag + '">' + esc(HOW[c.how] || c.how) + "</span> " +
            esc(c.after) + "</td></tr>";
        }).join("") + "</table></details>";
    }
    html += list("못 맞춘 줄", d.unmatched, d.unmatched_rows);
    html += list("애매해서 건너뛴 줄", d.ambiguous, d.ambiguous_rows);
    result.innerHTML = html;
  }

  function list(title, total, rows) {
    if (!(rows || []).length) return "";
    return '<details class="import-skipped"><summary>' + esc(title) + " " + total + "줄 보기" +
      more(rows.length, total) + "</summary>" +
      '<table class="mini-table"><tr>' + heads() + "<th>딜소개 문구</th></tr>" +
      rows.map(function (r) {
        return "<tr>" + idCells(r) + "<td>" + (r.has_pitch ? "있음" : "—") + "</td></tr>";
      }).join("") + "</table></details>";
  }

  function heads() {
    return "<th>기업명</th><th>수신 일자</th><th>공유 심사역</th><th>회사</th>";
  }

  function idCells(r) {
    return "<td>" + esc(r.name) + "</td><td>" + esc(r.received_at) + "</td><td>" +
      esc(r.shared_by) + "</td><td>" + esc(r.source_firm) + "</td>";
  }

  // 목록은 서버가 앞 몇 줄만 싣는다(`data_io.DIFF_ROWS`) — 잘렸으면 그렇다고 적는다.
  function more(shown, total) {
    return shown < total ? " — 앞 " + shown + "줄만 보입니다" : "";
  }

  function li(label, value) {
    return "<li><span>" + esc(label) + "</span><b>" + esc(value) + "</b></li>";
  }

  function esc(s) {
    return String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  previewBtn.addEventListener("click", function () { send(true); });
  applyBtn.addEventListener("click", function () {
    if (!last || !last.changed) return;
    var how = last.overwrite
      ? "이미 적힌 문구도 덮어씁니다(덮어씀 " + last.overwritten + "줄)."
      : "빈 칸만 채웁니다.";
    if (!window.confirm("미리보기대로 딜소개 문구 " + last.changed + "줄을 반영합니다.\n" + how +
                        "\n줄을 새로 만들거나 다른 칸을 고치지 않습니다. 계속할까요?")) return;
    send(false);
  });
})();
