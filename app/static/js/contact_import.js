// 투자사 관리 현황 업로드 — 미리보기로 확인한 뒤에만 반영한다.
//
// 담당자 명단은 곧 발송 대상이다. 잘못 덮으면 그대로 오발송이 되므로
// 같은 파일을 두 번 보낸다: 먼저 dry_run 으로 결과만 받아 보여주고,
// 사람이 확인한 뒤에 dry_run=false 로 다시 보내 반영한다.
// (서버에 파일을 임시로 쌓아 두지 않아도 되고, 무엇을 반영하는지도 분명해진다)
(function () {
  var panel = document.getElementById("import-panel");
  if (!panel) return;

  var fileInput = document.getElementById("import-file");
  var sheetSel = document.getElementById("import-sheet");
  var yearInput = document.getElementById("import-year");
  var previewBtn = document.getElementById("import-preview");
  var applyBtn = document.getElementById("import-apply");
  var result = document.getElementById("import-result");
  var previewed = false;   // 미리보기를 통과한 적이 있어야 반영할 수 있다

  document.getElementById("import-btn").addEventListener("click", function () {
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  document.getElementById("import-close").addEventListener("click", function () {
    panel.hidden = true;
  });

  // 파일을 고르면 시트 목록을 먼저 받아 고를 수 있게 한다.
  // (구글 시트를 엑셀로 내려받으면 시트가 여러 장 들어 있다)
  fileInput.addEventListener("change", function () {
    resetPreview();
    sheetSel.innerHTML = '<option value="">첫 번째 시트</option>';
    var f = fileInput.files[0];
    if (!f) return;
    var fd = new FormData();
    fd.append("file", f);
    fetch("/api/import/contacts/sheets", { method: "POST", body: fd })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        (d.sheets || []).forEach(function (name) {
          var o = document.createElement("option");
          o.value = name;
          o.textContent = name;
          sheetSel.appendChild(o);
        });
      })
      .catch(function () { /* CSV 등 시트 개념이 없으면 그냥 첫 시트로 간다 */ });
  });

  [sheetSel, yearInput].forEach(function (el) {
    el.addEventListener("change", resetPreview);
  });

  function resetPreview() {
    previewed = false;
    applyBtn.disabled = true;
    result.innerHTML = "";
  }

  function send(dryRun) {
    var f = fileInput.files[0];
    if (!f) { result.innerHTML = '<p class="err">파일을 먼저 고르세요.</p>'; return; }

    var fd = new FormData();
    fd.append("file", f);
    fd.append("sheet", sheetSel.value || "");
    fd.append("year", yearInput.value || "0");
    fd.append("dry_run", dryRun ? "true" : "false");

    previewBtn.disabled = true;
    applyBtn.disabled = true;
    result.innerHTML = '<p class="muted">' + (dryRun ? "읽는 중…" : "반영 중…") + "</p>";

    fetch("/api/import/contacts", { method: "POST", body: fd })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        previewBtn.disabled = false;
        if (!res.ok) {
          result.innerHTML = '<p class="err">' + esc(res.d.detail || "업로드 실패") + "</p>";
          return;
        }
        render(res.d, dryRun);
        if (dryRun) {
          previewed = true;
          applyBtn.disabled = false;
        } else {
          window.location.reload();   // 표를 새로 그려야 반영 결과가 보인다
        }
      })
      .catch(function () {
        previewBtn.disabled = false;
        result.innerHTML = '<p class="err">업로드 요청 오류</p>';
      });
  }

  function render(d, dryRun) {
    var head = dryRun
      ? "미리보기 — 아직 반영되지 않았습니다"
      : "반영 완료";
    var html = '<div class="import-summary"><b>' + esc(head) + "</b>" +
      '<ul class="import-stats">' +
      li("읽은 시트", d.sheet_used || "(첫 시트)") +
      li("머리행", d.header_row === null ? "-" : "엑셀 " + (d.header_row + 1) + "행") +
      li("읽은 담당자", d.parsed_contacts + "명") +
      li("새로 생김", d.created + "명") +
      li("갱신", d.updated + "명") +
      li("활동 이력", d.activities_created + "건 추가 (중복 " + d.activities_existing + "건 건너뜀)") +
      li("시트와 다른 칸", (d.diffs_total || 0) + "칸 (안 덮었습니다)") +
      li("건너뛴 행", d.skipped_total + "행") +
      "</ul></div>";

    if ((d.notes || []).length) {
      html += '<ul class="import-notes">' +
        d.notes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>";
    }
    // 시트 값과 앱 값이 **다른 칸**. 이 업로드가 안 덮고 지나간 자리다 —
    // 고객이 "드린 내용이 왜 반영이 안 되나" 를 묻던 그 칸이라, 접힌 채로도
    // 몇 칸인지는 여는 줄에 적힌다.
    //
    // **지금 값과 시트 값을 나란히 둔다.** 둘 중 하나만 보이면 사람이
    // 판단할 수가 없다. 메모처럼 사람이 쥐는 칸은 서버가 값을 안 싣고
    // 길이만 보내므로(`import_diff.as_rows`) 여기서도 길이만 그린다.
    if ((d.diffs || []).length) {
      html += '<details class="import-skipped" open><summary>시트와 다른 칸 ' +
        (d.diffs_total || 0) + "개 보기 — 이 업로드는 <b>안 덮었습니다</b></summary>" +
        "<table class=\"mini-table\"><tr><th>줄</th><th>칸</th>" +
        "<th>지금 값</th><th>시트 값</th></tr>" +
        d.diffs.map(function (x) {
          var now = x.before === undefined ? x.before_len + "자" : x.before;
          var sheet = x.after === undefined ? x.after_len + "자" : x.after;
          return "<tr><td>" + esc(x.token) + "</td><td>" + esc(x.label) +
            (x.can_overwrite ? "" : " <i>(안 덮음)</i>") +
            "</td><td>" + esc(now) + "</td><td>" + esc(sheet) + "</td></tr>";
        }).join("") + "</table>" +
        "<p class=\"hint\">덮어야 한다면 되돌릴 파일을 먼저 뜨는 " +
        "<code>scripts/import_investor_list.py --overwrite</code> 를 씁니다. " +
        "<b>줄</b> 칸의 말(<code>418:note:c31</code>)을 그대로 베껴 고른 칸만 덮을 수 있습니다." +
        "</p></details>";
    }
    if (d.activities_stale) {
      html += '<p class="import-notes">시트에서 없어진 활동 줄 ' +
        d.activities_stale + "건 — <b>지우지 않습니다.</b> 이 표에는 손으로 적은 줄과 " +
        "발송이 만든 줄이 함께 삽니다.</p>";
    }
    if ((d.skipped || []).length) {
      html += '<details class="import-skipped"><summary>건너뛴 행 ' +
        d.skipped_total + "개 보기</summary><table class=\"mini-table\"><tr><th>행</th><th>사유</th><th>내용</th></tr>" +
        d.skipped.map(function (s) {
          return "<tr><td>" + s.row + "</td><td>" + esc(s.reason) + "</td><td>" + esc(s.preview) + "</td></tr>";
        }).join("") + "</table></details>";
    }
    result.innerHTML = html;
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
    if (!previewed) return;
    if (!confirm("미리보기 결과대로 반영합니다.\n같은 이름+투자사인 담당자는 덮어씁니다. 계속할까요?")) return;
    send(false);
  });
})();
