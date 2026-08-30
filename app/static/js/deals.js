var MAX_COMPANIES = 10;   // 서버 MAX_COMPANIES_PER_SEND 와 동일하게 유지
var WARN_CHARS = 3000;    // 서버 MESSAGE_WARN_CHARS 와 동일하게 유지
// 딜소개 보내기 — selection, preview, send-list creation (FEATURE_SPEC §5).
(function () {
  var companyCbs = function () { return Array.prototype.slice.call(document.querySelectorAll(".company-cb")); };
  // 대상 목록이 두 개다(투자사 담당자 / 딜 소싱 명단). **지금 보이는 쪽만**
  // 센다 — 숨은 목록에 체크가 남아 있는데 그것까지 보내면, 화면에 없는
  // 사람에게 나간다.
  var activeList = function () {
    return document.getElementById(mode === "sourcing" ? "sourcing-list" : "contact-list");
  };
  var contactCbs = function () {
    var box = activeList();
    return box ? Array.prototype.slice.call(box.querySelectorAll(".contact-cb")) : [];
  };
  var companyPill = document.getElementById("company-pill");
  var contactPill = document.getElementById("contact-pill");
  var contactSummary = document.getElementById("contact-summary");
  var ssCompanies = document.getElementById("ss-companies");
  var ssContacts = document.getElementById("ss-contacts");
  var ssNote = document.getElementById("ss-note");
  var companyPanel = document.querySelector("#company-list").closest(".panel");
  var mode = "deal";
  // 딜소개 말고는 전부 기업 목록 없이 문구만 나간다.
  // 이미 목록을 받은 사람에게 같은 목록을 다시 밀어 넣는 것은 후속이 아니라 재발송이다.
  var FOLLOW_UP = { ask: "선호 분야 묻기", remind: "리마인드", meeting: "미팅 요청",
                    review: "미팅 후기", ir: "IR 자료 전달",
                    sourcing: "딜 소싱 제안" };
  // IR 자료 전달은 기업을 고른다(무엇을 보내는지 알아야 한다).
  // 나머지 후속 문구는 기업과 무관하다.
  var NEEDS_COMPANIES = { deal: true, ir: true };
  function isFollowUp() { return !!FOLLOW_UP[mode]; }
  function needsCompanies() { return !!NEEDS_COMPANIES[mode]; }
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

    var hideRecent = document.getElementById("hide-recent");
    var q = (box.value || "").trim().toLowerCase();
    var pickedOnly = onlyPicked && onlyPicked.checked;
    var skipRecent = hideRecent && hideRecent.checked;
    var shown = 0, total = 0;

    document.querySelectorAll("#company-list .pick-card").forEach(function (card) {
      var cb = card.querySelector(".company-cb");
      var picked = cb && cb.checked;
      var hay = card.getAttribute("data-search") || "";
      var hit = !q || hay.indexOf(q) !== -1;
      var recent = card.getAttribute("data-recent") === "1";
      total += 1;
      // 선택한 항목은 언제나 보인다.
      var visible = picked || (hit && !pickedOnly && !(skipRecent && recent));
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


  // ── 담당자 검색 ───────────────────────────────────────────
  // 116명 중에서 몇 명을 골라야 한다. 기업 검색과 같은 규칙을 쓴다:
  // **선택한 담당자는 검색어와 무관하게 항상 보인다** — 검색어를 바꾸다
  // 이미 고른 사람이 사라지면 몇 명 골랐는지 알 수 없다.
  function applyContactFilter() {
    var box = document.getElementById("contact-search");
    var onlyPicked = document.getElementById("only-picked-contacts");
    var note = document.getElementById("contact-filter-note");
    if (!box) return;

    var q = (box.value || "").trim().toLowerCase();
    var pickedOnly = onlyPicked && onlyPicked.checked;
    var shown = 0, total = 0, outside = 0;

    var list = activeList();
    (list ? list.querySelectorAll(".pick-card") : []).forEach(function (card) {
      var cb = card.querySelector(".contact-cb");
      var picked = cb && cb.checked;
      var hit = !q || (card.getAttribute("data-search") || "").indexOf(q) !== -1;
      // 갈래 필터는 소싱 목록에만 있다. 고른 사람은 갈래를 바꿔도 계속 보인다 —
      // 사라지면 몇 명 골랐는지 알 수 없다(검색과 같은 규칙).
      var inBucket = !bucketFilter || card.getAttribute("data-bucket") === bucketFilter;
      var inAssignee = !assigneeFilter ||
        card.getAttribute("data-assignee") === assigneeFilter;
      var inGroup = matchesGroup(card);
      total += 1;
      // **조건에 맞는가(match)와 화면에 보이는가(visible)는 다르다.**
      // 고른 사람은 조건에서 벗어나도 계속 보인다(몇 명 골랐는지 알아야 한다).
      // 그래서 `보이는 것 = 조건에 맞는 것` 이라고 읽으면, 그룹으로 추려 놓고
      // [전체선택]을 눌렀을 때 **아까 고른 다른 그룹 사람까지 함께 켜진다** —
      // 실제 투자사에게 문구가 나가는 자리라 그 차이를 여기서 갈라 적어 둔다.
      var matched = hit && inBucket && inAssignee && inGroup;
      var visible = picked || (matched && !pickedOnly);
      card.setAttribute("data-match", matched ? "1" : "0");
      card.hidden = !visible;
      if (visible) shown += 1;
      if (picked && !matched) outside += 1;
    });

    if (note) {
      if (q || pickedOnly || bucketFilter || assigneeFilter || groupFilter) {
        note.hidden = false;
        note.textContent = shown + " / " + total + "명 표시 중" +
          (q ? " (검색: " + box.value.trim() + ")" : "") +
          (groupFilter ? " (그룹: " + groupFilter + ")" : "") +
          (bucketFilter ? " (갈래: " + bucketFilter + ")" : "") +
          (assigneeFilter ? " (담당: " + assigneeFilter + ")" : "") +
          // 조건 밖인데 이미 고른 사람은 그대로 발송에 들어간다 — 숫자만
          // 줄어든 줄 알고 보내면 안 되므로 몇 명인지 말해 준다.
          (outside ? " · 조건 밖에서 고른 " + outside + "명이 함께 있습니다" : "");
      } else {
        note.hidden = true;
      }
    }
  }

  // ── 소싱 필터(갈래 · 담당) ────────────────────────────────
  // 갈래는 곧 문구이고, 담당은 누구를 챙길 차례인가다. 둘 다 이름을 검색창에
  // 쳐서 찾게 하면 무엇이 몇 개인지도 모른 채 골라야 한다.
  var bucketFilter = "";
  var assigneeFilter = "";
  var filterBox = document.getElementById("sourcing-filters");

  // ── 그룹 필터(투자사 담당자) ──────────────────────────────
  // 투자사 관리 현황의 `그룹` 칸(`data-f-group`)이 거르는 그 값이다. 표 필터
  // (`filters.js`)는 `th[data-filters]` 와 `tbody tr` 을 걸어 다녀서 카드 묶음인
  // 이 목록에는 붙지 않는다 — 그래서 바로 위 갈래·담당과 **같은 칩 방식**을 쓴다.
  //
  // `(비어 있음)` 이라는 말은 서버가 실어 보낸다(`data-empty`). 여기 한글을
  // 박아 두면 표 쪽 말이 바뀌는 날 한쪽만 고쳐져, 같은 조건인데 두 화면이
  // 서로 다른 사람을 고르게 된다.
  var groupFilter = "";
  var groupBox = document.getElementById("contact-filters");
  var groupBar = document.getElementById("group-filter");
  var EMPTY_GROUP = (groupBar && groupBar.getAttribute("data-empty")) || "";

  function matchesGroup(card) {
    if (!groupFilter) return true;
    // 소싱 명단에는 그룹이라는 것이 없다 — 그쪽 카드까지 걸러 버리면
    // 목록이 통째로 빈다.
    if (mode === "sourcing") return true;
    var value = (card.getAttribute("data-group") || "").trim();
    return groupFilter === EMPTY_GROUP ? value === "" : value === groupFilter;
  }

  function bindFilter(id, set) {
    var bar = document.getElementById(id);
    if (!bar) return null;
    bar.addEventListener("click", function (e) {
      var chip = e.target.closest(".chip");
      if (!chip) return;
      set(chip.getAttribute("data-value") || "");
      bar.querySelectorAll(".chip").forEach(function (c) {
        c.classList.toggle("active", c === chip);
      });
      applyContactFilter();
    });
    return bar;
  }
  var bucketBar = bindFilter("bucket-filter", function (v) { bucketFilter = v; });
  var assigneeBar = bindFilter("assignee-filter", function (v) { assigneeFilter = v; });
  bindFilter("group-filter", function (v) { groupFilter = v; });

  function resetGroupFilter() {
    groupFilter = "";
    if (!groupBar) return;
    groupBar.querySelectorAll(".chip").forEach(function (c, i) {
      c.classList.toggle("active", i === 0);
    });
  }

  function resetSourcingFilters() {
    bucketFilter = "";
    assigneeFilter = "";
    [bucketBar, assigneeBar].forEach(function (bar) {
      if (!bar) return;
      bar.querySelectorAll(".chip").forEach(function (c, i) {
        c.classList.toggle("active", i === 0);
      });
    });
  }

  function syncBucketMixNote() {
    var note = document.getElementById("bucket-mix-note");
    if (!note) return;
    if (mode !== "sourcing") { note.hidden = true; return; }
    var picked = {};
    contactCbs().forEach(function (c) {
      if (!c.checked) return;
      var card = c.closest(".pick-card");
      if (card) picked[card.getAttribute("data-bucket") || ""] = true;
    });
    var names = Object.keys(picked);
    // 갈래를 섞어도 사람마다 제 갈래의 문구가 나간다 — 사고는 아니지만
    // 모르고 섞으면 미리보기에서 다른 문구를 보고 놀란다.
    note.hidden = names.length < 2;
    if (!note.hidden) {
      note.textContent = "갈래 " + names.length + "개가 섞여 있습니다 — " +
        "갈래마다 다른 문구가 나갑니다 (" + names.join(" · ") + ")";
    }
  }

  ["contact-search", "only-picked-contacts"].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", applyContactFilter);
    el.addEventListener("change", applyContactFilter);
  });

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

  // 같은 이름('팀 기본')이 둘 이상 뜨면 어느 것을 고르는지 알 수 없다.
  // 종류를 함께 보여준다.
  var KIND_NOTE = {
    opening_first: "첫 연락", opening_re: "재연락",
    closing_day1: "딜소개", closing_remind: "리마인드",
    closing_meeting: "미팅 요청", ask_preference: "선호 분야",
    meeting_review: "미팅 후기", ir_delivery: "IR 자료 전달"
  };
  // 고르지 않았을 때 쓰는 문구의 이름. '기본' 만으로는 무엇의 기본인지 모른다.
  var CLOSING_DEFAULT = {
    deal: "기본 안내문", remind: "기본 안내문", meeting: "기본 안내문",
    review: "기본 문구", ask: "기본 문구", ir: "기본 문구",
    sourcing: "갈래별 기본 문구"
  };

  function renderTemplates() {
    var byKind = {};
    (templateCache || []).forEach(function (t) {
      (byKind[t.kind] = byKind[t.kind] || []).push(t);
    });
    // 팀 기본은 첫 연락·재연락 두 개지만 시스템이 알아서 고른다.
    // 목록에 둘 다 올리면 같은 이름이 두 번 뜨고, 골라도 자동 선택이 막힌다.
    var openings = (byKind["opening_first"] || []).concat(byKind["opening_re"] || [])
      .filter(function (t) { return t.mine; });
    fill("tpl-opening", openings, "기본 인삿말 (첫 연락 / 재연락 자동)");
    // 문구만 보낼 때는 안내문이 아니라 그 방식의 문구를 고른다.
    var kindByMode = { ask: "ask_preference", remind: "closing_remind",
                       meeting: "closing_meeting", review: "meeting_review",
                       deal: "closing_day1", ir: "ir_delivery",
                       sourcing: "sourcing_intro" };
    fill("tpl-closing", byKind[kindByMode[mode]] || [],
         CLOSING_DEFAULT[mode] || "기본 안내문");
  }

  function fill(selectId, list, defaultLabel) {
    var sel = document.getElementById(selectId);
    if (!sel) return;
    var keep = sel.value;
    sel.innerHTML = "";
    var base = document.createElement("option");
    base.value = "";
    base.textContent = defaultLabel;
    sel.appendChild(base);

    list.forEach(function (t) {
      var o = document.createElement("option");
      o.value = t.id;
      var note = KIND_NOTE[t.kind];
      o.textContent = t.name + (note ? " · " + note : "") +
        " — " + t.body.replace(/\n/g, " ").slice(0, 26);
      sel.appendChild(o);
    });
    // 방식을 바꿔도 고르던 문구가 그 목록에 있으면 유지한다.
    if (keep && sel.querySelector('option[value="' + keep + '"]')) sel.value = keep;

    if (!sel.dataset.bound) {
      sel.addEventListener("change", refreshPreview);
      sel.dataset.bound = "1";
    }
  }

  function currentChannel() {
    var picked = document.querySelector('input[name="channel"]:checked');
    return picked ? picked.value : "kakao";
  }

  // 메일과 카톡은 나가는 길이 다르다 — 고른 채널에 맞춰 화면도 바뀐다.
  function syncChannel() {
    var email = currentChannel() === "email";
    var box = document.getElementById("mail-fields");
    if (box) box.hidden = !email;
    updateCounts();
  }

  document.querySelectorAll('input[name="channel"]').forEach(function (radio) {
    radio.addEventListener("change", syncChannel);
  });

  function selectedTemplateIds() {
    var o = document.getElementById("tpl-opening");
    var c = document.getElementById("tpl-closing");
    var greet = document.getElementById("include-opening");
    return {
      opening_template_id: o && o.value ? parseInt(o.value, 10) : null,
      closing_template_id: c && c.value ? parseInt(c.value, 10) : null,
      mode: mode,
      include_opening: greet ? greet.checked : true
    };
  }

  // 인사말을 끄면 인사말 문구를 고르는 칸은 의미가 없다.
  function syncOpeningToggle() {
    var greet = document.getElementById("include-opening");
    var wrap = document.getElementById("tpl-opening-wrap");
    if (wrap) wrap.hidden = !greet.checked;
  }

  // 몇 개/몇 명 골랐는지는 발송 직전에 가장 궁금한 값이라
  // 패널 제목 옆(알약)과 발송 요약 두 곳에 크게 띄운다.
  // 고르는 대로 미리보기가 따라온다. 갱신 버튼을 누르게 두면 안 누른 채로
  // 발송을 눌러, 화면에 보이는 것과 실제로 나가는 것이 달라진다.
  //
  // 다만 체크할 때마다 서버를 부르면 7개 고르는 동안 7번 나간다 — 손이
  // 멈춘 뒤 한 번만 부른다.
  var previewTimer = null;
  function schedulePreview() {
    var state = document.getElementById("preview-state");
    if (state) state.textContent = "고르는 중…";
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(function () {
      previewTimer = null;
      if (state) state.textContent = "고르는 대로 바로 나옵니다";
      refreshPreview();
    }, 400);
  }

  function updateCounts() {
    var nc = selectedCompanyIds().length;
    var nt = selectedContactIds().length;
    var askMode = !needsCompanies();

    companyPill.innerHTML = "<b>" + nc + "</b> / " + MAX_COMPANIES;
    companyPill.classList.toggle("on", nc > 0);
    contactPill.innerHTML = "<b>" + nt + "</b>명";
    contactPill.classList.toggle("on", nt > 0);

    ssCompanies.innerHTML = "<b>" + nc + "</b>개 기업";
    ssCompanies.hidden = askMode;                 // 문구만 보낼 때는 기업 수가 의미 없다
    document.querySelector(".ss-arrow").hidden = askMode;
    ssContacts.textContent = nt;
    schedulePreview();
    ssNote.textContent = askMode
      ? FOLLOW_UP[mode] + " — 기업 목록 없이 문구만 나갑니다"
      : (mode === "ir" ? "자료를 먼저 보내고 문구를 뒤에 보냅니다"
                       : (nc > MAX_COMPANIES ? "기업은 최대 " + MAX_COMPANIES + "개까지" : ""));
    if (mode === "ir") renderIrLinks();

    syncBucketMixNote();
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
    applyContactFilter();
  }

  // 고른 기업의 IR 자료 링크를 띄운다 — 무엇을 보내야 하는지 그 자리에서 보여야 한다.
  function renderIrLinks() {
    var box = document.getElementById("ir-attach");
    if (!box) return;
    box.hidden = mode !== "ir";
    if (mode !== "ir") return;
    var list = document.getElementById("ir-links");
    list.innerHTML = "";
    companyCbs().filter(function (c) { return c.checked; }).forEach(function (c) {
      var li = document.createElement("li");
      var name = c.getAttribute("data-name");
      var url = c.getAttribute("data-ir-url");
      if (url) {
        li.innerHTML = escapeHtml(name) + " — " +
          '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">자료 열기</a>';
      } else {
        li.innerHTML = escapeHtml(name) +
          ' <span class="warn-text">— 자료 링크가 없습니다</span>';
      }
      list.appendChild(li);
    });
    if (!list.children.length) {
      list.innerHTML = '<li class="muted">보낼 기업을 고르세요.</li>';
    }
  }

  // ── 보내는 방식 전환 ───────────────────────────────────────
  function setMode(next) {
    mode = next;
    var askMode = !needsCompanies();
    document.querySelectorAll(".mode-tab").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    companyPanel.classList.toggle("dimmed", askMode);
    // 대상 목록 자체를 바꾼다 — 소싱은 받는 사람이 다른 명단에 있다.
    var sourcingMode = mode === "sourcing";
    var contactBox = document.getElementById("contact-list");
    var sourcingBox = document.getElementById("sourcing-list");
    if (contactBox) contactBox.hidden = sourcingMode;
    if (sourcingBox) sourcingBox.hidden = !sourcingMode;
    var contactHead = document.getElementById("contact-head");
    if (contactHead) contactHead.textContent = sourcingMode ? "② 딜 소싱 대상" : "② 대상 담당자";
    var noReactBtn = document.getElementById("select-noreact");
    // 소싱 명단에는 '반응' 이라는 개념이 없다 — 아직 보낸 적이 없다.
    if (noReactBtn) noReactBtn.hidden = sourcingMode;
    if (filterBox) {
      filterBox.hidden = !sourcingMode;
      // 필터를 켜 둔 채 다른 탭으로 갔다 오면, 왜 사람이 적은지 모른다.
      resetSourcingFilters();
    }
    // 그룹은 투자사 담당자 목록에만 있다. **필터 줄을 감출 때는 조건도 함께
    // 푼다** — 켜져 있는데 보이지 않는 필터가 제일 나쁘다(왜 사람이 적은지
    // 알 길이 없고, [전체선택]이 무엇에 걸리는지도 알 수 없다).
    if (groupBox) {
      groupBox.hidden = sourcingMode;
      if (sourcingMode) resetGroupFilter();
    }
    applyContactFilter();
    // 설명 줄은 화면에서 뺐다. 없어도 터지지 않아야 한다.
    var help = document.getElementById("mode-help");
    if (help) help.textContent =
      mode === "ir"
        ? "요청받은 기업을 고르면, 자료를 먼저 보내고 안내 문구를 뒤에 보냅니다"
        : (sourcingMode
            ? "딜 소싱 명단에서 대상을 고르면, 갈래(시리즈 A 이상 · 투자사 대표 · 개인 참여 …)에 맞는 문구가 나갑니다"
            : (askMode ? FOLLOW_UP[mode] + " — 기업 목록 없이 문구만 보냅니다 (기업 선택 불필요)"
                       : "기업 1~10개 선택 → 대상 담당자 체크 → 담당자별 미리보기 → 발송"));
    var companyHint = document.getElementById("company-hint");
    if (companyHint) companyHint.hidden = mode === "ir";
    renderIrLinks();
    var closingWrap = document.getElementById("tpl-closing-wrap");
    if (closingWrap) closingWrap.querySelector("span").textContent = askMode ? "문구" : "안내문";
    // 인사말은 **기본으로 붙인다.** 빼는 것은 선호 분야를 되물을 때뿐이다 —
    // 그건 이미 대화가 오간 방에 한 줄만 덧붙이는 것이라 다시 인사하면 어색하다.
    // (자료 전달 문구는 그 자체가 "○○ 님 안녕하세요" 로 시작하므로 서버가
    //  중복을 걸러낸다 — deals.py 의 FOLLOW_UP_MODES 참고.)
    // 켜고 끄는 것은 그대로 사람이 정한다.
    var greet = document.getElementById("include-opening");
    if (greet) { greet.checked = (mode !== "ask"); syncOpeningToggle(); }
    lastPreviews = [];
    // 방식을 바꾸면 고친 것도 버린다 — 딜소개용으로 고친 문구가 IR 자료
    // 전달에 얹히면 엉뚱한 말이 나간다.
    savedEdits = {};
    previewTabs.innerHTML = "";
    previewArea.innerHTML = '<p class="muted">불러오는 중…</p>';
    warnBox.hidden = true;
    loadTemplates(true);
    updateCounts();   // 여기서 미리보기가 따라온다
  }

  ["company-search", "only-picked", "hide-recent"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", applyCompanyFilter);
    if (el) el.addEventListener("change", applyCompanyFilter);
  });

  // 미리보기는 **그대로 고쳐서 보낼 수 있다**.
  // 자동 조합이 늘 완벽할 수는 없어서, 담당자별로 한 줄 덧붙이거나 표현을 바꾸는 일이 잦다.
  // 고친 내용은 lastPreviews[i].message 에 남고 발송 시 그 문장이 그대로 나간다.
  // 자료 전달은 한 통이 아니라 여러 통으로 나간다 — 링크를 먼저 한 통씩 던지고
  // 설명이 마지막이다. 그게 보이지 않으면 무엇이 어떤 순서로 나가는지 확인할 수 없다.
  // 여기서 고치면 **한 통으로** 나간다(어디서 끊을지는 고친 사람만 안다).
  function splitNotice(p) {
    var parts = p.parts || [];
    if (parts.length < 2) return "";
    var heads = parts.map(function (t, i) {
      return '<li><b>' + (i + 1) + '통</b> ' +
        escapeHtml(t.split("\n")[0].slice(0, 40)) + '</li>';
    }).join("");
    return '<div class="split-notice">' +
      '<b>' + parts.length + '통으로 나갑니다</b> — 링크가 먼저, 설명이 마지막' +
      '<ol>' + heads + '</ol>' +
      '<span class="muted">여기서 고치면 한 통으로 나갑니다</span></div>';
  }

  function renderPreview(idx) {
    var p = lastPreviews[idx];
    if (!p) { previewArea.innerHTML = '<p class="muted">미리보기 없음</p>'; return; }
    Array.prototype.slice.call(previewTabs.children).forEach(function (t, i) {
      t.classList.toggle("active", i === idx);
    });
    var roomLine = p.room_name
      ? ("💬 " + p.room_name + (p.room_from ? " (" + p.room_from + ")" : ""))
      : ("⚠ " + (p.room_warning || "방 미등록"));
    // 기본 문구는 아직 아무에게도 가지 않는다 — 진짜 사람에게 갈 문구로
    // 읽히면 확인만 하려다 그대로 보내게 된다.
    var meta = p.sample
      ? '<div class="bubble-meta sample">기본 문구 — 아직 대상을 고르지 않았습니다. ' +
        '담당자를 고르면 그 사람 이름으로 바뀝니다.' +
        ' <span class="edited-flag" id="edited-flag" hidden>· 수정함</span></div>'
      : '<div class="bubble-meta">' + escapeHtml(p.name) + " " + escapeHtml(p.title || "") +
        " · " + escapeHtml(roomLine) + (p.has_history ? " · 재연락" : " · 첫연락") +
        ' <span class="edited-flag" id="edited-flag" hidden>· 수정함</span></div>';
    previewArea.innerHTML =
      meta +
      splitNotice(p) +
      '<textarea class="bubble-edit" id="bubble-edit" spellcheck="false"></textarea>' +
      '<div class="charcount" id="charcount"></div>' +
      '<button type="button" class="linkbtn" id="revert-edit"' +
      (p.edited ? '' : ' hidden') + '>고친 것 되돌리기</button>';

    var ta = document.getElementById("bubble-edit");
    ta.value = p.message;               // innerHTML 이 아니라 value 로 넣어야 안전하다
    var flag = document.getElementById("edited-flag");
    flag.hidden = !p.edited;
    updateCharCount(ta.value);

    ta.addEventListener("input", function () {
      p.message = ta.value;
      // 고치는 즉시 남겨 둔다. 저장 단추가 따로 없으니, 여기서 안 남기면
      // 담당자를 하나 더 체크하는 순간 사라진다.
      if (ta.value.trim() && ta.value !== p.original) {
        savedEdits[p.contact_id] = ta.value;
      } else {
        delete savedEdits[p.contact_id];
      }
      p.edited = ta.value !== p.original;
      flag.hidden = !p.edited;
      updateCharCount(ta.value);
      markTabEdited(idx, p.edited);
      if (revert) revert.hidden = !p.edited;
    });

    // 되돌릴 수 없으면 고치기가 부담스럽다 — 손댄 뒤 원래 문구를 다시 못 본다.
    var revert = document.getElementById("revert-edit");
    if (revert) revert.addEventListener("click", function () {
      delete savedEdits[p.contact_id];
      p.message = p.original;
      p.edited = false;
      ta.value = p.original;
      flag.hidden = true;
      revert.hidden = true;
      updateCharCount(ta.value);
      markTabEdited(idx, false);
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
  // 고친 문구를 담당자별로 들고 있는다 — 미리보기를 다시 그려도 남아야 한다.
  var savedEdits = {};
  // 미리보기 요청 번호. 늦게 온 옛 응답이 새 것을 덮지 않게 한다.
  var previewSeq = 0;

  function editedOverrides() {
    return lastPreviews
      .filter(function (p) { return p.edited && (p.message || "").trim(); })
      .map(function (p) { return { contact_id: p.contact_id, message: p.message }; });
  }

  function refreshPreview() {
    var cids = selectedCompanyIds();
    var tids = selectedContactIds();
    // 아무도 안 골랐어도 **기본 문구**를 부른다. 문구를 확인하려고 아무나
    // 한 명 체크했다가 그대로 발송을 누르는 일이 있었다.
    // (딜 소개는 기업까지 골라야 목록이 채워지지만, 인사말·안내문 모양은
    //  기업 없이도 보인다)
    // 요청마다 번호를 붙인다. 39명을 고른 요청은 느리고 전부 해제한 요청은
    // 빠른데, 순서를 안 지키면 **늦게 도착한 옛 응답이 새 것을 덮는다** —
    // 전체선택을 두 번 눌러 다 껐는데 미리보기에 투자사가 그대로 남았다.
    var seq = ++previewSeq;
    fetch("/api/deals/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ company_ids: cids, contact_ids: tids }, selectedTemplateIds()))
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (seq !== previewSeq) return;      // 그 사이 새 요청이 나갔다
        if (!res.ok) { previewArea.innerHTML = '<p class="muted">' + escapeHtml(res.d.detail || "미리보기 실패") + "</p>"; return; }
        lastPreviews = res.d.previews || [];
        // 고친 문구를 되살린다. 담당자를 하나 더 체크하면 미리보기가 새로
        // 그려지는데, 그때마다 앞서 고쳐 둔 것이 **말없이 사라졌다** —
        // 열 명을 고치고 한 명 더 넣으면 열 명분이 날아간다.
        lastPreviews.forEach(function (p) {
          p.original = p.message;
          var kept = savedEdits[p.contact_id];
          if (kept !== undefined && kept !== p.message) {
            p.message = kept;
            p.edited = true;
          } else {
            p.edited = false;
          }
        });
        previewTabs.innerHTML = "";
        lastPreviews.forEach(function (p, i) {
          var b = document.createElement("button");
          b.className = "preview-tab";
          b.textContent = p.sample ? "기본 문구" : p.name;
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
      .catch(function () {
        if (seq !== previewSeq) return;
        previewArea.innerHTML = '<p class="muted">미리보기 요청 오류</p>';
      });
  }

  function send() {
    var cids = selectedCompanyIds();
    var tids = selectedContactIds();
    var title = (document.getElementById("batch-title").value || "딜소개 회차").trim();
    var edits = editedOverrides();
    var editNote = edits.length ? "\n직접 수정한 문구 " + edits.length + "건이 그대로 발송됩니다." : "";
    var via = currentChannel() === "email" ? "이메일로 " : "";
    var what = mode === "ir"
      ? cids.length + "개 기업 IR 자료 전달"
      : (isFollowUp() ? FOLLOW_UP[mode] + " 문구 (기업 목록 없음)"
                      : cids.length + "개 기업 딜소개");
    var lastCheck = currentChannel() === "email"
      ? "\n받는 주소를 최종 확인하셨나요?"
      : "\n방 이름을 최종 확인하셨나요?";
    if (!confirm(what + "\n" + via + "대상 " + tids.length + "명에게 발송합니다."
                 + editNote + lastCheck)) return;
    sendBtn.disabled = true;
    fetch("/api/deals/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign(
        { company_ids: cids, contact_ids: tids, title: title,
          overrides: editedOverrides(), channel: currentChannel(),
          subject: (document.getElementById("mail-subject") || {}).value || null },
        selectedTemplateIds()))
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
  // **지금 조건에 맞는 사람**만. `card.hidden` 만 보면 안 된다 — 이미 고른
  // 사람은 조건에서 벗어나도 계속 보이게 두기 때문에(몇 명 골랐는지 알아야
  // 한다), `안 숨겨졌다 = 조건에 맞다` 로 읽으면 그룹으로 추려 놓고 누른
  // [전체선택]에 **다른 그룹 사람까지 딸려 온다.** 실제 투자사에게 문구가
  // 나가는 자리다.
  function filteredBoxes() {
    return contactCbs().filter(function (c) {
      var card = c.closest(".pick-card");
      if (!card) return true;
      // 아직 한 번도 안 걸렀으면(속성 없음) 전부 조건에 맞는 것이다.
      return card.getAttribute("data-match") !== "0" && !card.hidden;
    });
  }

  var selAll = document.getElementById("select-all-contacts");
  if (selAll) selAll.addEventListener("click", function () {
    var boxes = filteredBoxes();
    if (!boxes.length) return;
    var allOn = boxes.every(function (c) { return c.checked; });
    boxes.forEach(function (c) { c.checked = !allOn; });
    updateCounts();
    applyContactFilter();   // 켠 사람은 검색어와 무관하게 계속 보인다
  });
  document.querySelectorAll(".mode-tab").forEach(function (b) {
    b.addEventListener("click", function () { setMode(b.getAttribute("data-mode")); });
  });

  var greetBox = document.getElementById("include-opening");
  if (greetBox) greetBox.addEventListener("change", function () {
    syncOpeningToggle();
    refreshPreview();
  });
  syncOpeningToggle();

  var noreactBtn = document.getElementById("select-noreact");
  if (noreactBtn) noreactBtn.addEventListener("click", function () {
    // [전체선택]과 같은 규칙이다 — 그룹으로 추려 놓았으면 그 안에서만 고른다.
    // 여기만 전체 목록을 훑으면, 추려 놓은 줄 알고 눌렀는데 다른 그룹으로
    // 문구가 나간다.
    var targets = filteredBoxes().filter(function (c) {
      return c.getAttribute("data-noreact") === "1";
    });
    if (!targets.length) { alert("반응이 없는 담당자가 없습니다."); return; }
    var allOn = targets.every(function (c) { return c.checked; });
    contactCbs().forEach(function (c) { c.checked = false; });
    if (!allOn) targets.forEach(function (c) { c.checked = true; });
    updateCounts();
    applyContactFilter();   // 켠 사람은 조건과 무관하게 계속 보인다
  });

  // 후속 관리·IR 관리에서 넘어오면 방식·대상·기업을 그대로 받는다.
  // 화면을 열자마자 보낼 준비가 되어 있어야 챙기던 일이 줄어든다.
  // 특히 IR 자료 전달은 "누구에게 어떤 기업 자료를" 이 이미 정해져 있다 —
  // 여기서 다시 고르게 하면 엉뚱한 기업을 보낼 여지가 생긴다.
  (function applyIncoming() {
    var params = new URLSearchParams(window.location.search);
    var wanted = params.get("mode");

    function check(boxes, raw) {
      var ids = (raw || "").split(",").map(function (v) { return v.trim(); })
        .filter(Boolean);
      if (!ids.length) return 0;
      var want = {};
      ids.forEach(function (id) { want[id] = true; });
      var hit = 0;
      boxes.forEach(function (c) {
        if (want[c.value]) { c.checked = true; hit += 1; }
      });
      return hit;
    }

    check(contactCbs(), params.get("contacts"));
    var picked = check(companyCbs(), params.get("companies"));

    if (wanted && document.querySelector('.mode-tab[data-mode="' + wanted + '"]')) {
      setMode(wanted);
    }
    // 받은 기업이 목록에 없으면(소개 불가로 빠졌거나 지워졌으면) 알려 준다.
    var asked = (params.get("companies") || "").split(",").filter(Boolean).length;
    if (asked && picked < asked) {
      warnBox.hidden = false;
      warnBox.textContent =
        "요청받은 기업 " + (asked - picked) + "개를 목록에서 찾지 못했습니다 — " +
        "IR 기업현황에서 등록 상태를 확인하세요.";
    }
    if (picked) applyCompanyFilter();
  })();

  syncChannel();
  updateCounts();
  loadTemplates();
})();
