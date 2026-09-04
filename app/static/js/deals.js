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
  // 아래 단추를 매는 자리보다 **위**에서 잡아 둔다 — 셈을 다시 하는
  // `updateCounts()` 가 이 단추를 켜고 끄기 때문에, 매는 순서가 바뀌어도
  // 첫 셈에서 조용히 빠지는 일이 없어야 한다.
  var clearAllBtn = document.getElementById("clear-all-contacts");
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
  // **지금 열어 둔 미리보기 탭**(담당자 하나). [보낼 자료] 목록의 번호가 이
  // 탭을 따른다 — 번호는 담당자마다 다르기 때문에 "누구 것인지" 없이는 적을
  // 수 없다(`renderIrLinks` 설명 참고).
  var currentPreview = 0;
  // 복사 단추의 글자. **공용 한 벌에서 읽는다** — 복사가 끝나면 그쪽이
  // 이 글자로 되돌리므로, 여기 따로 적어 두면 둘이 갈리는 날 단추가
  // 딴 글자로 바뀐 채 남는다.
  var COPY_LABEL = window.IrAttach.COPY_LABEL;

  // ── 고른 차례 ─────────────────────────────────────────────
  //
  // 문구는 `1) …` `2) …` 로 나가고 투자사는 **그 번호로 기억해서** "2번 자료
  // 주세요" 라고 답한다. 그래서 어느 기업이 몇 번인지가 이 화면의 알맹이다.
  //
  // `querySelectorAll` 이 주는 것은 **목록에 그려진 차례**다. 그것만 쓰면 3번째
  // 기업을 먼저 고르고 1번째를 나중에 골라도 목록 차례로 나가서, 사람이 머리에
  // 담은 차례와 실제로 나간 번호가 어긋난다.
  //
  // ## 차례를 어디에 담는가 — **카드에 적는다**(`data-pick-order`)
  //
  // 화면 안 변수에 따로 들고 있지 않는다. 그러면 "무엇을 골랐나"(체크박스)와
  // "몇 번째로 골랐나"(변수)가 **두 벌**이 되고, 어느 한쪽만 바뀌는 길이 생기면
  // 화면에 보이는 번호와 서버로 나가는 차례가 조용히 갈린다 — 이 저장소가
  // 반복해 겪은 일이다. 카드 하나에 둘을 함께 두면 갈릴 자리가 없다.
  //
  // 카드에 둔 덕에 **번호를 따로 그리지 않아도 된다** — CSS 가 이 속성을 그대로
  // 읽어 배지로 띄운다(`#company-list .pick-card[data-pick-order]::before`).
  // 번호를 화면에 한 번 더 적어 두면 그 순간 두 벌이 된다.
  //
  // 새로고침하면 **번호는 사라진다.** 서버가 그리는 체크박스는 전부 꺼진 채라
  // 고른 것 자체가 없어지기 때문이고, 그게 맞다 — 화면이 서버가 모르는 차례를
  // 기억하고 있으면 안 된다. 차례가 오래 남는 곳은 보내거나 예약한 뒤의 서버
  // 쪽이다(`DealBatchCompany.position` · `DealQueueCompany.position`).
  //
  // ## 자료 전달에서는 **고른 차례가 번호가 아니다**
  //
  // 그때의 번호는 딜 소개에서 이미 붙인 번호다(`services/deal_numbers.py`).
  // 투자사가 "2번 주세요" 라고 답한 그 번호라 담당자마다 다르고, 카드 하나에
  // 적을 수 있는 값이 아니다. 그런데도 고른 차례를 배지로 띄우면 화면은 `1`,
  // 문구는 `2번 기업 …` 이 되어 **어느 쪽이 맞는지 알 수 없다.** 그래서 이
  // 탭에서는 배지를 비운다(`no-pick-badge`) — 실제 번호는 담당자별 미리보기
  // 문구에 그대로 적혀 있다. 차례 자체는 그대로 쓴다: 문구가 기업을 짚는
  // 차례이자 [보낼 자료] 목록의 차례다.
  function cardOf(cb) { return cb.closest(".pick-card"); }

  function pickOrderOf(card) {
    var n = parseInt(card.getAttribute("data-pick-order") || "0", 10);
    return n > 0 ? n : 0;
  }

  // 고른 카드를 **고른 차례대로**. 번호를 다시 매기는 일도 여기서 함께 한다.
  function renumberPicks() {
    var numbered = [];   // 이미 번호가 있는 것
    var fresh = [];      // 방금 켠 것 — 아직 번호가 없다
    companyCbs().forEach(function (cb) {
      var card = cardOf(cb);
      if (!card) return;
      // 체크를 풀면 번호를 지운다. 남겨 두면 다시 골랐을 때 **아까 쓰던 번호로
      // 되돌아가** 방금 고른 것이 앞으로 끼어든 줄 모른 채 나간다.
      if (!cb.checked) { card.removeAttribute("data-pick-order"); return; }
      (pickOrderOf(card) ? numbered : fresh).push(card);
    });
    numbered.sort(function (a, b) { return pickOrderOf(a) - pickOrderOf(b); });
    // 빈 번호 없이 1부터 다시 붙인다 — 가운데를 풀면 뒤가 당겨져야 화면의
    // 번호와 문구의 `1) 2) 3)` 이 같아진다.
    var picked = numbered.concat(fresh);
    picked.forEach(function (card, i) {
      card.setAttribute("data-pick-order", String(i + 1));
    });
    return picked;
  }

  // **읽으면서 번호를 다시 매긴다.** 읽는 자리와 번호를 붙이는 자리를 떼어
  // 놓으면, 한쪽만 불린 길에서 화면의 번호와 나가는 차례가 갈린다.
  function selectedCompanyIds() {
    return renumberPicks().map(function (card) {
      return parseInt(card.querySelector(".company-cb").value, 10);
    });
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

  function bindFilter(id, set, onPick) {
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
      // 갈래를 누르면 **그 갈래 문구**가 떠야 한다. 목록만 걸러 놓으면
      // M&A 를 골라 놓고 시리즈 A 문구를 보며 발송을 누르게 된다.
      // (사람을 고른 뒤에는 그 사람의 갈래가 이기므로 달라지지 않는다)
      if (onPick) onPick();
    });
    return bar;
  }
  var bucketBar = bindFilter("bucket-filter", function (v) { bucketFilter = v; },
                             schedulePreview);
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

  // ── 고른 사람이 어느 그룹에 걸쳐 있는가 ───────────────────────────────────
  //
  // 그룹 칩은 한 번에 하나만 켜지는데, 고르기는 그 위에 쌓인다 — 1군을 고르고
  // 2군으로 옮겨 [전체선택]을 누르면 발송 대상에 두 그룹이 함께 있다. 그런데
  // 요약 줄은 `곽○○ … 외 119명` 이라고만 적어서, **무엇으로 골랐는지가 화면
  // 에서 사라졌다.** 필터 칩은 지금 걸린 조건 하나만 말하지, 이미 담아 둔 것을
  // 말해 주지 않는다.
  //
  // **그래서 그룹 이름은 하나도 안 줄인다.** 자를 만한 자리를 재 봤는데, 이
  // 칸은 3열 그리드의 가운데라 280px(한글 26자)뿐이다 — 글자 수로 자르면
  // 그룹 이름이 반토막 나서 다른 그룹으로 읽힌다. 같은 시트에서 온 소싱 갈래
  // 이름이 이미 28자까지 간다. 줄여 적느니 **줄을 넘겨 다 적는 편**이 맞다.
  // 길어져도 바로 위 그룹 칩 줄이 같은 이름을 이미 다 그리고 있으니, 이 줄이
  // 화면에 없던 높이를 새로 만들지는 않는다.
  //
  // 한 그룹뿐이면 적지 않는다 — 섞이지 않았다는 뜻이고, 그건 위 칩이 이미
  // 말하고 있다(바로 위 갈래 안내와 같은 규칙).
  function groupMixHtml(picked) {
    // 소싱 명단에는 그룹이라는 것이 없다 — 그쪽은 갈래가 같은 일을 한다.
    if (mode === "sourcing" || !groupBar) return "";
    // 순서는 **목록에 나온 차례** 그대로다. 서버가 정한 정렬(인원 많은 순 ·
    // 비어 있음 마지막)을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모른다.
    var order = [], count = {};
    picked.forEach(function (c) {
      var card = c.closest(".pick-card");
      if (!card) return;
      var name = (card.getAttribute("data-group") || "").trim() || EMPTY_GROUP;
      if (!count[name]) { count[name] = 0; order.push(name); }
      count[name] += 1;
    });
    if (order.length < 2) return "";
    return '<span class="pick-groups">그룹 ' + order.map(function (name) {
      // 그룹 이름은 시트에서 온 말이다 — 그대로 넣지 않는다.
      return '<span class="tag soft">' + escapeHtml(name) +
        " " + count[name] + "명</span>";
    }).join("") + "</span>";
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
      include_opening: greet ? greet.checked : true,
      // 딜 소싱은 갈래마다 문구가 다르다. 아직 아무도 안 골랐을 때
      // 어느 갈래를 보여 줄지는 **누른 칩**이 정한다.
      bucket: bucketFilter || ""
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
      : (mode === "ir" ? "자료는 PC 카톡에서 직접 첨부하고, 여기서는 문구만 보냅니다"
                       : (nc > MAX_COMPANIES ? "기업은 최대 " + MAX_COMPANIES + "개까지" : ""));
    if (mode === "ir") renderIrLinks();

    syncBucketMixNote();
    // 고른 사람 이름을 보여준다 — 숫자만으로는 누구를 넣었는지 알 수 없다.
    var picked = contactCbs().filter(function (c) { return c.checked; });
    var names = picked.map(function (c) { return c.getAttribute("data-name"); });
    if (names.length) {
      contactSummary.hidden = false;
      contactSummary.innerHTML = groupMixHtml(picked) +
        '<span class="pick-names">' + escapeHtml(names.length <= 6
          ? names.join(", ")
          : names.slice(0, 6).join(", ") + " 외 " + (names.length - 6) + "명") +
        "</span>";
    } else {
      contactSummary.hidden = true;
      contactSummary.innerHTML = "";
    }

    // [전체해제]는 **셀 것이 있을 때만** 눌린다. 눌러도 아무 일이 없는 단추는
    // "왜 안 되지" 를 만든다. 켜고 끄는 판단을 여기서 하는 이유는, 옆 알약이
    // `nt` 명이라고 적는 바로 그 자리이기 때문이다 — 다른 곳에서 따로 세면
    // `0명` 인데 해제가 눌리거나 `12명` 인데 안 눌리는 날이 온다.
    if (clearAllBtn) clearAllBtn.disabled = nt < 1;

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

  // 고른 기업의 IR 자료를 띄운다 — **번호와 파일 이름**이다.
  //
  // 자동 첨부를 켠 계정은 발송기가 이 차례로 파일을 붙여 보내고, 켜지 않은
  // 계정은 사람이 이 목록을 보고 PC 카톡에 붙인다. 어느 쪽이든 이 목록이
  // **무엇을 어떤 차례로 보내는가**를 말한다.
  //
  // **그리는 일은 여기 없다.** IR 진행 관리의 [자료 보내기] 창도 똑같은 목록을
  // 그려서, 한 벌을 같이 쓴다(`ir_attach_list.js`) — 번호를 적는 규칙이 두
  // 벌이 되면 고칠 때 한쪽만 고쳐진다. 왜 화면이 번호를 셀 수 없는지도 그
  // 파일에 적어 두었다.
  //
  // 담당자를 여럿 고르면 번호도 여럿이라 목록에 하나로 적을 수 없다. 미리보기는
  // 담당자별로 한 통씩 보여 주므로(탭 하나가 담당자 하나) 이 목록은 **지금 열어
  // 둔 그 탭**을 따른다. 탭을 바꾸면 번호도 함께 바뀐다.
  function renderIrLinks() {
    var box = document.getElementById("ir-attach");
    if (!box) return;
    box.hidden = mode !== "ir";
    if (mode !== "ir") return;
    window.IrAttach.renderList(
      document.getElementById("ir-links"),
      document.getElementById("ir-no-note"),
      lastPreviews[currentPreview] || lastPreviews[0]);
  }

  // ── 보내는 방식 전환 ───────────────────────────────────────
  function setMode(next) {
    mode = next;
    var askMode = !needsCompanies();
    document.querySelectorAll(".mode-tab").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    companyPanel.classList.toggle("dimmed", askMode);
    // 자료 전달에서는 고른 차례가 번호가 아니다 — 배지를 비운다(위 설명 참고).
    companyPanel.classList.toggle("no-pick-badge", mode === "ir");
    // 대상 목록 자체를 바꾼다 — 소싱은 받는 사람이 다른 명단에 있다.
    var sourcingMode = mode === "sourcing";
    var contactBox = document.getElementById("contact-list");
    var sourcingBox = document.getElementById("sourcing-list");
    if (contactBox) contactBox.hidden = sourcingMode;
    if (sourcingBox) sourcingBox.hidden = !sourcingMode;
    // `연결이 안 끝나 목록에 없는 사람`은 **투자사 담당자 목록의 사정**이다.
    // 소싱은 아예 다른 표(SourcingContact)라 연결 단계라는 것이 없는데, 그
    // 목록 위에 "19명이 연결이 안 끝나 빠졌다" 가 그대로 남아 있으면 지금
    // 보이는 명단에서 19명이 빠진 것으로 읽힌다.
    var missBox = document.getElementById("blocked-contacts");
    if (missBox) missBox.hidden = sourcingMode;
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
    // 예약 큐는 **딜 소개 탭의 것**이다. 후속 문구(리마인드·미팅 요청 …)와
    // 소싱은 그때그때 사람을 골라 보내는 일이라 줄 세울 것이 없고, 큐가
    // 그대로 떠 있으면 지금 탭에서 [시작] 을 누르면 이 탭의 문구가 나가는
    // 줄로 읽힌다 — 실제로 나가는 것은 딜 소개다.
    var queuePanel = document.getElementById("deal-queue");
    if (queuePanel) queuePanel.hidden = mode !== "deal";
    applyContactFilter();
    // 설명 줄은 화면에서 뺐다. 없어도 터지지 않아야 한다.
    var help = document.getElementById("mode-help");
    if (help) help.textContent =
      mode === "ir"
        ? "요청받은 기업을 고르세요 — 자료 파일은 PC 카톡에서 직접 첨부하고, 안내 문구만 여기서 보냅니다"
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
    currentPreview = 0;
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
  // 여러 통으로 나뉘어 나가는 문구가 있으면 몇 통인지 보여 준다. 무엇이 어떤
  // 순서로 나가는지 보이지 않으면 확인할 수가 없다.
  // (자료 전달은 링크 방식을 폐기한 뒤로 한 통이라 여기 걸리지 않는다.)
  // 여기서 고치면 **한 통으로** 나간다(어디서 끊을지는 고친 사람만 안다).
  function splitNotice(p) {
    var parts = p.parts || [];
    if (parts.length < 2) return "";
    var heads = parts.map(function (t, i) {
      return '<li><b>' + (i + 1) + '통</b> ' +
        escapeHtml(t.split("\n")[0].slice(0, 40)) + '</li>';
    }).join("");
    return '<div class="split-notice">' +
      '<b>' + parts.length + '통으로 나갑니다</b> — 위에서부터 차례대로' +
      '<ol>' + heads + '</ol>' +
      '<span class="muted">여기서 고치면 한 통으로 나갑니다</span></div>';
  }

  // 미리보기 문구를 클립보드로 — **문구는 사람이 손으로 보낸다.**
  //
  // 담당자를 여럿 고르면 문구도 여럿인데, 이 단추는 **지금 열어 둔 탭**의
  // 문구만 담는다 — 붙여 넣을 카톡 창도 한 번에 하나이고, 옆에 선 [보낼 자료]
  // 목록의 번호도 같은 탭을 따른다. 둘이 다른 담당자를 가리키면 엉뚱한 자료가
  // 붙는다.
  //
  // 복사 자체는 IR 진행 관리의 [자료 보내기] 창과 **같은 한 벌**이다
  // (`ir_attach_list.js` — 클립보드가 없는 화면에서 어떻게 물러서는지도 거기 있다).
  function copyMessage(ta, btn) { window.IrAttach.copyText(ta, btn); }

  function renderPreview(idx) {
    var p = lastPreviews[idx];
    if (!p) { previewArea.innerHTML = '<p class="muted">미리보기 없음</p>'; return; }
    // [보낼 자료] 목록의 번호가 **이 탭을 따른다.** 번호는 담당자마다 달라서,
    // 여기서 알려 주지 않으면 목록은 앞 담당자의 번호를 그대로 달고 있는다.
    currentPreview = idx;
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
      // 문구는 **사람이 손으로 보낸다** — 카톡 창에 붙여 넣어야 하니 여기서
      // 집어갈 수 있어야 한다. 담을 것은 아래 칸의 값 그대로다(장식·머리말이
      // 섞이면 그것까지 붙는다).
      '<button type="button" class="linkbtn" id="copy-message">' + COPY_LABEL + '</button>' +
      '<button type="button" class="linkbtn" id="revert-edit"' +
      (p.edited ? '' : ' hidden') + '>고친 것 되돌리기</button>';

    var ta = document.getElementById("bubble-edit");
    ta.value = p.message;               // innerHTML 이 아니라 value 로 넣어야 안전하다
    // 이 탭의 자료 목록·번호. 문구와 같은 응답에서 나온다.
    renderIrLinks();
    var copyBtn = document.getElementById("copy-message");
    if (copyBtn) copyBtn.addEventListener("click", function () { copyMessage(ta, copyBtn); });
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
        // 다시 그릴 때는 늘 첫 탭이다. 앞서 세 번째 탭을 열어 두었는데 담당자를
        // 줄이면 그 자리가 없어져, [보낼 자료] 목록만 없는 담당자의 번호를 단다.
        if (lastPreviews.length) renderPreview(0);
        else { currentPreview = 0; renderIrLinks(); }
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

  // ── 예약 큐 ───────────────────────────────────────────────────────────────
  //
  // 줄 하나가 **그룹 + 기업 묶음 + 문구**다. 여기서 하는 일은 셋뿐이다:
  // 줄 세우기 · 시작 · 취소. **보내는 길은 새로 만들지 않는다** — [시작] 은
  // 서버에서 기존 발송 목록 생성(`/api/deals/send` 와 같은 함수)을 그대로 탄다.
  //
  // **대상 명단은 화면이 들고 있지 않다.** 이 줄에 담긴 것은 그룹 이름뿐이고,
  // 서버가 누를 때 다시 센다. 화면이 명단을 들고 보내면 예약해 둔 사이에
  // 카톡방을 나간 분께 그대로 나간다.
  function queuePost(url, body, done) {
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "요청 실패"); done(null); return; }
        done(res.d);
      })
      .catch(function () { alert("요청 오류"); done(null); });
  }

  var queueAdd = document.getElementById("queue-add");
  if (queueAdd) queueAdd.addEventListener("click", function () {
    var cids = selectedCompanyIds();
    if (!cids.length) { alert("① 에서 기업을 먼저 고르세요."); return; }
    var group = document.getElementById("queue-group");
    var tpl = selectedTemplateIds();
    queueAdd.disabled = true;
    queuePost("/api/deals/queue", {
      group_name: group ? group.value : "",
      company_ids: cids,
      title: (document.getElementById("batch-title").value || "").trim(),
      opening_template_id: tpl.opening_template_id,
      closing_template_id: tpl.closing_template_id
    }, function (d) {
      queueAdd.disabled = false;
      // 줄 목록은 서버가 그린다(대상 수가 **지금 센 값**이어야 한다).
      // 화면에서 줄을 흉내 내 붙이면 그 수는 붙인 순간 낡는다.
      if (d) window.location.reload();
    });
  });

  // 줄 단추는 목록이 다시 그려져도 살아 있어야 한다 — 줄마다 거는 대신
  // 목록이 대신 듣는다.
  var queueList = document.getElementById("queue-list");
  if (queueList) queueList.addEventListener("click", function (e) {
    var startBtn = e.target.closest(".queue-start");
    var cancelBtn = e.target.closest(".queue-cancel");
    var row = e.target.closest(".queue-row");
    if (!row || (!startBtn && !cancelBtn)) return;
    var id = row.getAttribute("data-id");
    var group = row.getAttribute("data-group") || "";

    if (cancelBtn) {
      if (!confirm("[" + group + "] 예약을 취소합니다.")) return;
      cancelBtn.disabled = true;
      queuePost("/api/deals/queue/" + id + "/cancel", {}, function (d) {
        cancelBtn.disabled = false;
        if (d) window.location.reload();
      });
      return;
    }

    // **화면에 적혀 있던 수를 함께 보낸다.** 서버가 지금 다시 센 수와 다르면
    // 보내지 않고 그 차이를 말로 돌려준다 — 조용히 다른 수로 나가면, 몇 명
    // 에게 나갔는지 아무도 모르는 채로 되돌릴 수 없는 일이 끝나 있다.
    var shown = parseInt(row.getAttribute("data-count"), 10);
    startBtn.disabled = true;
    function go(confirmed) {
      queuePost("/api/deals/queue/" + id + "/start",
                { shown: isNaN(shown) ? null : shown, confirmed: !!confirmed },
                function (d) {
        if (!d) { startBtn.disabled = false; return; }
        if (d.needs_confirm) {
          // 확인창의 말은 **서버가 만든 것을 그대로** 띄운다. 여기서 다시
          // 지어내면 두 벌이 되고, 둘이 어긋나도 아무도 모른다 — 사람이
          // 마지막으로 읽는 자리라 특히 그렇다.
          if (!confirm(d.message)) { startBtn.disabled = false; return; }
          go(true);
          return;
        }
        window.location.href = "/jobs/" + d.job_id;
      });
    }
    if (!confirm("[" + group + "] 예약을 시작합니다.\n" +
                 "대상 " + (isNaN(shown) ? "?" : shown) + "명 기준입니다 — " +
                 "누르는 순간 다시 세므로 수가 달라졌으면 한 번 더 여쭙습니다.")) {
      startBtn.disabled = false;
      return;
    }
    go(false);
  });

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

  // ── [전체해제] ────────────────────────────────────────────────────────────
  //
  // **[전체선택]을 다시 누르는 것과는 다른 일이다.** 그쪽은 지금 걸러진 범위만
  // 되돌린다 — 그 좁힘이 이 화면의 안전장치라 넓힐 수 없다(그룹으로 추려 놓고
  // 누른 조작이 다른 그룹을 건드리면 남의 카톡방으로 문구가 나간다).
  //
  // 그 대신 조건 밖에서 고른 사람은 손이 안 닿는 채로 발송에 남았다. 1군에서
  // 고르고 2군으로 옮기면 [전체선택]을 두 번 눌러도 1군은 그대로다 — 필터를
  // 되돌리거나 새로고침해야 했고, 그 사이 요약 줄은 계속 그 사람을 세고 있다.
  // 여기서는 **거른 것과 상관없이 지금 목록의 체크를 전부 끈다.**
  //
  // 훑는 상자는 [전체선택]과 똑같이 `contactCbs()` 다 — 지금 보이는 목록
  // 하나뿐이다. 연결이 안 끝나 접힌 칸(`#blocked-contacts`)은 그 상자 밖이라
  // 켜는 쪽에도 끄는 쪽에도 애초에 안 들어온다(`tests/js/deals_select_all_test.js`).
  if (clearAllBtn) clearAllBtn.addEventListener("click", function () {
    contactCbs().forEach(function (c) { c.checked = false; });
    updateCounts();          // 알약 · 요약 줄 · 이 단추가 여기서 함께 0 이 된다
    applyContactFilter();
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

    // `ordered` 는 **받은 차례가 곧 번호**인 목록(기업)에만 준다.
    //
    // 목록에 그려진 차례로 훑으면서 켜면 주소에 적힌 차례가 사라진다 —
    // IR 관리에서 `?companies=203,201` 로 넘어오는데, 그 차례는 그 담당자가
    // 요청한 차례이고 자료도 그 차례로 한 통씩 날아가야 한다.
    // 받는 사람(`contacts`)에는 차례가 없다 — 번호를 붙여 나가지 않는다.
    function check(boxes, raw, ordered) {
      var ids = (raw || "").split(",").map(function (v) { return v.trim(); })
        .filter(Boolean);
      // 같은 번호가 두 번 적혀 있어도 한 번만 센다(상자는 하나다).
      ids = ids.filter(function (id, i) { return ids.indexOf(id) === i; });
      if (!ids.length) return 0;
      var byValue = {};
      boxes.forEach(function (c) { byValue[c.value] = c; });
      var hit = 0;
      ids.forEach(function (id, i) {
        var c = byValue[id];
        if (!c) return;
        c.checked = true;
        hit += 1;
        // 목록에 없는 번호가 섞여 있으면 여기서 번호가 비는데, 바로 아래
        // `updateCounts()` 안의 `renumberPicks()` 가 1부터 다시 붙인다.
        if (ordered) {
          var card = cardOf(c);
          if (card) card.setAttribute("data-pick-order", String(i + 1));
        }
      });
      return hit;
    }

    check(contactCbs(), params.get("contacts"));
    var picked = check(companyCbs(), params.get("companies"), true);

    if (wanted && document.querySelector('.mode-tab[data-mode="' + wanted + '"]')) {
      setMode(wanted);
    }
    // 받은 기업이 목록에 없으면(소개 불가로 빠졌거나 지워졌으면) 알려 준다.
    var asked = (params.get("companies") || "").split(",").filter(Boolean).length;
    if (asked && picked < asked) {
      warnBox.hidden = false;
      warnBox.textContent =
        "요청받은 기업 " + (asked - picked) + "개를 목록에서 찾지 못했습니다 — " +
        "IR 기업 현황에서 등록 상태를 확인하세요.";
    }
    if (picked) applyCompanyFilter();
  })();

  syncChannel();
  updateCounts();
  loadTemplates();
})();
