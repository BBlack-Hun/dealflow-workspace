var MAX_COMPANIES = 10;  // 서버 MAX_COMPANIES_PER_SEND 와 동일하게 유지
// 딜소개 보내기 — selection, preview, send-list creation (FEATURE_SPEC §5).
(function () {
  var companyCbs = function () { return Array.prototype.slice.call(document.querySelectorAll(".company-cb")); };
  var contactCbs = function () { return Array.prototype.slice.call(document.querySelectorAll(".contact-cb")); };
  var companyCount = document.getElementById("company-count");
  var contactCount = document.getElementById("contact-count");
  var previewTabs = document.getElementById("preview-tabs");
  var previewArea = document.getElementById("preview-area");
  var warnBox = document.getElementById("send-warnings");
  var sendBtn = document.getElementById("send-btn");
  var lastPreviews = [];

  function selectedCompanyIds() {
    return companyCbs().filter(function (c) { return c.checked; }).map(function (c) { return parseInt(c.value, 10); });
  }
  function selectedContactIds() {
    return contactCbs().filter(function (c) { return c.checked; }).map(function (c) { return parseInt(c.value, 10); });
  }

  function updateCounts() {
    var nc = selectedCompanyIds().length;
    var nt = selectedContactIds().length;
    companyCount.textContent = "선택: " + nc + " / 3";
    contactCount.textContent = "선택: " + nt + "명";
    // Enforce max company cap
    if (nc >= MAX_COMPANIES) {
      companyCbs().forEach(function (c) { if (!c.checked) c.disabled = true; });
    } else {
      companyCbs().forEach(function (c) { c.disabled = false; });
    }
    sendBtn.disabled = !(nc >= 1 && nc <= MAX_COMPANIES && nt >= 1);
  }

  function renderPreview(idx) {
    var p = lastPreviews[idx];
    if (!p) { previewArea.innerHTML = '<p class="muted">미리보기 없음</p>'; return; }
    Array.prototype.slice.call(previewTabs.children).forEach(function (t, i) {
      t.classList.toggle("active", i === idx);
    });
    var over = p.too_long ? " over" : "";
    var roomLine = p.room_name ? ("💬 " + p.room_name) : ("⚠ " + (p.room_warning || "방 미등록"));
    previewArea.innerHTML =
      '<div class="bubble-meta">' + escapeHtml(p.name) + " " + escapeHtml(p.title || "") +
      " · " + escapeHtml(roomLine) + (p.has_history ? " · 재연락" : " · 첫연락") + "</div>" +
      '<div class="bubble">' + escapeHtml(p.message) + "</div>" +
      '<div class="charcount' + over + '">' + p.char_count + "자</div>";
  }

  function refreshPreview() {
    var cids = selectedCompanyIds();
    var tids = selectedContactIds();
    if (cids.length < 1 || tids.length < 1) {
      previewArea.innerHTML = '<p class="muted">기업과 담당자를 선택한 뒤 [미리보기 갱신]을 누르세요.</p>';
      previewTabs.innerHTML = "";
      return;
    }
    fetch("/api/deals/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_ids: cids, contact_ids: tids })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { previewArea.innerHTML = '<p class="muted">' + escapeHtml(res.d.detail || "미리보기 실패") + "</p>"; return; }
        lastPreviews = res.d.previews || [];
        previewTabs.innerHTML = "";
        lastPreviews.forEach(function (p, i) {
          var b = document.createElement("button");
          b.className = "preview-tab";
          b.textContent = p.name;
          b.onclick = function () { renderPreview(i); };
          previewTabs.appendChild(b);
        });
        if (lastPreviews.length) renderPreview(0);
        var warns = [];
        lastPreviews.forEach(function (p) {
          (p.warnings || []).forEach(function (w) { warns.push(p.name + ": " + w); });
        });
        if (warns.length) { warnBox.hidden = false; warnBox.innerHTML = warns.map(escapeHtml).join("<br>"); }
        else { warnBox.hidden = true; }
      })
      .catch(function () { previewArea.innerHTML = '<p class="muted">미리보기 요청 오류</p>'; });
  }

  function send() {
    var cids = selectedCompanyIds();
    var tids = selectedContactIds();
    var title = (document.getElementById("batch-title").value || "딜소개 회차").trim();
    if (!confirm("대상 " + tids.length + "명에게 발송 목록을 생성합니다.\n방 이름을 최종 확인하셨나요?")) return;
    sendBtn.disabled = true;
    fetch("/api/deals/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_ids: cids, contact_ids: tids, title: title })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert("발송 목록 생성 실패: " + (res.d.detail || "")); sendBtn.disabled = false; return; }
        window.location.href = "/jobs/" + res.d.job_id;
      })
      .catch(function () { alert("발송 요청 오류"); sendBtn.disabled = false; });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  document.addEventListener("change", function (e) {
    if (e.target.classList.contains("company-cb") || e.target.classList.contains("contact-cb")) updateCounts();
  });
  document.getElementById("refresh-preview").addEventListener("click", refreshPreview);
  document.getElementById("send-btn").addEventListener("click", send);
  var selAll = document.getElementById("select-all-contacts");
  if (selAll) selAll.addEventListener("click", function () {
    var boxes = contactCbs();
    var allOn = boxes.every(function (c) { return c.checked; });
    boxes.forEach(function (c) { c.checked = !allOn; });
    updateCounts();
  });
  updateCounts();
})();
