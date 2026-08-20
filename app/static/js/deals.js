var MAX_COMPANIES = 10;   // 서버 MAX_COMPANIES_PER_SEND 와 동일하게 유지
var WARN_CHARS = 3000;    // 서버 MESSAGE_WARN_CHARS 와 동일하게 유지
// 딜소개 보내기 — selection, preview, send-list creation (FEATURE_SPEC §5).
(function () {
  var companyCbs = function () { return Array.prototype.slice.call(document.querySelectorAll(".company-cb")); };
  var contactCbs = function () { return Array.prototype.slice.call(document.querySelectorAll(".contact-cb")); };
  var companyPill = document.getElementById("company-pill");
  var contactPill = document.getElementById("contact-pill");
  var contactSummary = document.getElementById("contact-summary");
  var ssCompanies = document.getElementById("ss-companies");
  var ssContacts = document.getElementById("ss-contacts");
  var ssNote = document.getElementById("ss-note");
  var companyPanel = document.querySelector("#company-list").closest(".panel");
  var mode = "deal";   // deal = 기업 목록까지 · ask = 문구만
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


  // ── 기업 검색 ─────────────────────────────────────────────
  // 소개 가능한 기업이 100개를 넘어가면 목록을 훑어서 고르기 어렵다.
  // 검색으로 좁히되, **선택한 항목은 검색어와 무관하게 항상 보이게** 한다
  // (검색어를 바꾸다 이미 고른 기업이 사라지면 몇 개 골랐는지 알 수 없다).
  function applyCompanyFilter() {
    var box = document.getElementById("company-search");
    var onlyPicked = document.getElementById("only-picked");
    var note = document.getElementById("company-filter-note");
    if (!box) return;

    var q = (box.value || "").trim().toLowerCase();
    var pickedOnly = onlyPicked && onlyPicked.checked;
    var shown = 0, total = 0;

    document.querySelectorAll("#company-list .pick-card").forEach(function (card) {
      var cb = card.querySelector(".company-cb");
      var picked = cb && cb.checked;
      var hay = card.getAttribute("data-search") || "";
      var hit = !q || hay.indexOf(q) !== -1;
      total += 1;
      // 선택한 항목은 언제나 보인다.
      var visible = picked || (hit && !pickedOnly);
      card.hidden = !visible;
      if (visible) shown += 1;
    });

    if (note) {
      if (q || pickedOnly) {
        note.hidden = false;
        note.textContent = shown + " / " + total + "개 표시 중" + (q ? " (검색: " + box.value.trim() + ")" : "");
      } else {
        note.hidden = true;
      }
    }
  }


  // ── 문구(템플릿) 선택 ─────────────────────────────────────
  // 상황마다 인사말·안내문이 달라진다(첫 연락/재연락, 연말 인사 …).
  // /templates 에서 만들어 둔 문구를 회차마다 골라 쓴다. 고르지 않으면 기본 동작.
  var templateCache = null;

  function loadTemplates(force) {
    if (templateCache && !force) { renderTemplates(); return; }
    fetch("/api/templates").then(function (r) { return r.json(); }).then(function (d) {
      templateCache = d.templates || [];
      renderTemplates();
    }).catch(function () { /* 문구 목록 실패해도 기본 문구로 발송 가능 */ });
  }

  function renderTemplates() {
    var byKind = {};
    (templateCache || []).forEach(function (t) {
      (byKind[t.kind] = byKind[t.kind] || []).push(t);
    });
    fill("tpl-opening", (byKind["opening_first"] || []).concat(byKind["opening_re"] || []));
    // 문구만 보낼 때는 안내문이 아니라 '선호 분야 묻기' 문구를 고른다.
    fill("tpl-closing", mode === "ask"
      ? (byKind["ask_preference"] || [])
      : (byKind["closing_day1"] || []));
  }

  function fill(selectId, list) {
    var sel = document.getElementById(selectId);
    if (!sel) return;
    sel.innerHTML = '<option value="">기본</option>';
    list.forEach(function (t) {
      var o = document.createElement("option");
      o.value = t.id;
      o.textContent = t.name + " — " + t.body.replace(/\n/g, " ").slice(0, 30);
      sel.appendChild(o);
    });
    if (!sel.dataset.bound) {
      sel.addEventListener("change", refreshPreview);
      sel.dataset.bound = "1";
    }
  }

  function selectedTemplateIds() {
    var o = document.getElementById("tpl-opening");
    var c = document.getElementById("tpl-closing");
    return {
      opening_template_id: o && o.value ? parseInt(o.value, 10) : null,
      closing_template_id: c && c.value ? parseInt(c.value, 10) : null,
      mode: mode
    };
  }

  // 몇 개/몇 명 골랐는지는 발송 직전에 가장 궁금한 값이라
  // 패널 제목 옆(알약)과 발송 요약 두 곳에 크게 띄운다.
  function updateCounts() {
    var nc = selectedCompanyIds().length;
    var nt = selectedContactIds().length;
    var askMode = mode === "ask";

    companyPill.innerHTML = "<b>" + nc + "</b> / " + MAX_COMPANIES;
    companyPill.classList.toggle("on", nc > 0);
    contactPill.innerHTML = "<b>" + nt + "</b>명";
    contactPill.classList.toggle("on", nt > 0);

    ssCompanies.innerHTML = "<b>" + nc + "</b>개 기업";
    ssCompanies.hidden = askMode;                 // 문구만 보낼 때는 기업 수가 의미 없다
    document.querySelector(".ss-arrow").hidden = askMode;
    ssContacts.textContent = nt;
    ssNote.textContent = askMode
      ? "기업 목록 없이 문구만 나갑니다"
      : (nc > MAX_COMPANIES ? "기업은 최대 " + MAX_COMPANIES + "개까지" : "");

    // 고른 사람 이름을 보여준다 — 숫자만으로는 누구를 넣었는지 알 수 없다.
    var names = contactCbs().filter(function (c) { return c.checked; })
      .map(function (c) { return c.getAttribute("data-name"); });
    if (names.length) {
      contactSummary.hidden = false;
      contactSummary.textContent = names.length <= 6
        ? names.join(", ")
        : names.slice(0, 6).join(", ") + " 외 " + (names.length - 6) + "명";
    } else {
      contactSummary.hidden = true;
    }

    // 상한을 넘기면 더 못 고르게 막는다
    if (nc >= MAX_COMPANIES) {
      companyCbs().forEach(function (c) { if (!c.checked) c.disabled = true; });
    } else {
      companyCbs().forEach(function (c) { c.disabled = false; });
    }
    sendBtn.disabled = askMode
      ? nt < 1
      : !(nc >= 1 && nc <= MAX_COMPANIES && nt >= 1);
    applyCompanyFilter();   // 선택 항목은 검색 중에도 계속 보이게
  }

  // ── 보내는 방식 전환 ───────────────────────────────────────
  function setMode(next) {
    mode = next;
    var askMode = mode === "ask";
    document.querySelectorAll(".mode-tab").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    companyPanel.classList.toggle("dimmed", askMode);
    document.getElementById("mode-help").textContent = askMode
      ? "반응이 없는 담당자에게 기업 목록 없이 문구만 보냅니다 (기업 선택 불필요)"
      : "기업 1~10개 선택 → 대상 담당자 체크 → 담당자별 미리보기 → 발송";
    var closingWrap = document.getElementById("tpl-closing-wrap");
    if (closingWrap) closingWrap.querySelector("span").textContent = askMode ? "문구" : "안내문";
    lastPreviews = [];
    previewTabs.innerHTML = "";
    previewArea.innerHTML = '<p class="muted">[미리보기 갱신]을 누르세요.</p>';
    warnBox.hidden = true;
    loadTemplates(true);
    updateCounts();
  }

  ["company-search", "only-picked"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", applyCompanyFilter);
    if (el) el.addEventListener("change", applyCompanyFilter);
  });

  // 미리보기는 **그대로 고쳐서 보낼 수 있다**.
  // 자동 조합이 늘 완벽할 수는 없어서, 담당자별로 한 줄 덧붙이거나 표현을 바꾸는 일이 잦다.
  // 고친 내용은 lastPreviews[i].message 에 남고 발송 시 그 문장이 그대로 나간다.
  function renderPreview(idx) {
    var p = lastPreviews[idx];
    if (!p) { previewArea.innerHTML = '<p class="muted">미리보기 없음</p>'; return; }
    Array.prototype.slice.call(previewTabs.children).forEach(function (t, i) {
      t.classList.toggle("active", i === idx);
    });
    var roomLine = p.room_name ? ("💬 " + p.room_name) : ("⚠ " + (p.room_warning || "방 미등록"));
    previewArea.innerHTML =
      '<div class="bubble-meta">' + escapeHtml(p.name) + " " + escapeHtml(p.title || "") +
      " · " + escapeHtml(roomLine) + (p.has_history ? " · 재연락" : " · 첫연락") +
      ' <span class="edited-flag" id="edited-flag" hidden>· 수정함</span></div>' +
      '<textarea class="bubble-edit" id="bubble-edit" spellcheck="false"></textarea>' +
      '<div class="charcount" id="charcount"></div>';

    var ta = document.getElementById("bubble-edit");
    ta.value = p.message;               // innerHTML 이 아니라 value 로 넣어야 안전하다
    var flag = document.getElementById("edited-flag");
    flag.hidden = !p.edited;
    updateCharCount(ta.value);

    ta.addEventListener("input", function () {
      p.message = ta.value;
      p.edited = ta.value !== p.original;
      flag.hidden = !p.edited;
      updateCharCount(ta.value);
      markTabEdited(idx, p.edited);
    });
  }

  function updateCharCount(text) {
    var el = document.getElementById("charcount");
    if (!el) return;
    var n = text.length;
    el.textContent = n + "자";
    el.className = "charcount" + (n > WARN_CHARS ? " over" : "");
  }

  function markTabEdited(idx, edited) {
    var tab = previewTabs.children[idx];
    if (tab) tab.classList.toggle("edited", !!edited);
  }

  // 고친 문구만 서버로 보낸다. 안 고친 담당자는 서버가 다시 조합한다.
  function editedOverrides() {
    return lastPreviews
      .filter(function (p) { return p.edited && (p.message || "").trim(); })
      .map(function (p) { return { contact_id: p.contact_id, message: p.message }; });
  }

  function refreshPreview() {
    var cids = selectedCompanyIds();
    var tids = selectedContactIds();
    if ((mode !== "ask" && cids.length < 1) || tids.length < 1) {
      previewArea.innerHTML = '<p class="muted">' +
        (mode === "ask" ? "담당자를 선택한 뒤" : "기업과 담당자를 선택한 뒤") +
        " [미리보기 갱신]을 누르세요.</p>";
      previewTabs.innerHTML = "";
      return;
    }
    fetch("/api/deals/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ company_ids: cids, contact_ids: tids }, selectedTemplateIds()))
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { previewArea.innerHTML = '<p class="muted">' + escapeHtml(res.d.detail || "미리보기 실패") + "</p>"; return; }
        lastPreviews = res.d.previews || [];
        lastPreviews.forEach(function (p) { p.original = p.message; p.edited = false; });
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
    var edits = editedOverrides();
    var editNote = edits.length ? "\n직접 수정한 문구 " + edits.length + "건이 그대로 발송됩니다." : "";
    var what = mode === "ask"
      ? "선호 분야를 묻는 문구(기업 목록 없음)"
      : cids.length + "개 기업 딜소개";
    if (!confirm(what + "\n대상 " + tids.length + "명에게 발송합니다." + editNote +
                 "\n방 이름을 최종 확인하셨나요?")) return;
    sendBtn.disabled = true;
    fetch("/api/deals/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ company_ids: cids, contact_ids: tids, title: title,
                                          overrides: editedOverrides() }, selectedTemplateIds()))
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
  document.querySelectorAll(".mode-tab").forEach(function (b) {
    b.addEventListener("click", function () { setMode(b.getAttribute("data-mode")); });
  });

  var noreactBtn = document.getElementById("select-noreact");
  if (noreactBtn) noreactBtn.addEventListener("click", function () {
    var targets = contactCbs().filter(function (c) {
      return c.getAttribute("data-noreact") === "1";
    });
    if (!targets.length) { alert("반응이 없는 담당자가 없습니다."); return; }
    var allOn = targets.every(function (c) { return c.checked; });
    contactCbs().forEach(function (c) { c.checked = false; });
    if (!allOn) targets.forEach(function (c) { c.checked = true; });
    updateCounts();
  });

  updateCounts();
  loadTemplates();
})();
