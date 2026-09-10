// 내 투자사 — 상세 패널 · CRUD · 방 연결 확인 (FEATURE_SPEC §3, ROADMAP 2.2/2.5)
(function () {
  "use strict";

  var FIELDS = ["name", "title", "firm", "group_name", "kakao_room_name", "invited_status",
    "status", "stages", "sectors", "round_size", "email", "phone", "memo",
    // 시트에 있는데 표에는 안 넣은 값들 — 표에 다 넣으면 20칸이 되어
    // 정작 매일 보는 칸이 눌린다. 가끔 찾는 값은 상세에서 본다.
    // 표에는 있는데 이 목록에 없으면 **상세 창에서 적을 수가 없다** —
    // 칸을 그려 놔도 값이 안 채워지고 저장도 안 된다.
    "kakao_joined", "sourcing_note", "tips_note",
    "assignee_name", "department", "office_phone", "office_fax",
    "address", "card_registered_at", "interest_level",
    // 연결 상태. `<select>` 라 값 읽기·쓰기는 다른 칸과 같다.
    // 이 목록에서 빠지면 창은 멀쩡히 그려지는데 값이 안 채워지고 저장도
    // 안 된다 — 스키마·저장 목록·되읽기 응답·화면 넷 중 하나만 빠져도
    // 증상이 똑같이 조용하다(예전에 `kakao_joined` 가 그랬다).
    "connect_stage"];
  var CHECKS = ["channel_kakao", "channel_email"];
  var KIND_KO = {
    deal_intro: "딜소개", ir_request: "IR 요청", meeting: "미팅",
    // 자료를 보낸 뒤의 미팅 요청을 **사람이 카톡에서 직접 보내고 표시한** 줄
    // (`services/pipeline.MEETING_ASK_KIND`). 여기 없으면 이력에 코드값
    // `meeting_ask` 가 그대로 찍힌다.
    memo: "메모", ir_delivery: "IR 전달", meeting_ask: "미팅 요청"
  };

  var panel = document.getElementById("detail-panel");
  var table = document.getElementById("contacts-table");
  var msg = document.getElementById("detail-msg");
  var current = null;   // null = 새 담당자 추가 모드
  var filters = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }
  function el(id) { return document.getElementById(id); }
  // **없는 단추에 손을 대도 나머지가 죽지 않게 한다.**
  //
  // 이 파일은 화면 둘이 같이 쓴다(투자사 관리 현황 · 스타트업). 뒤쪽
  // 화면에는 투자사 전용 단추가 없는데(방 연결 확인 · 담당자 추가 · 현황 업로드),
  // `el("verify-btn").addEventListener(...)` 처럼 바로 붙이면 그 줄에서 예외가
  // 나면서 **그 아래가 통째로 안 걸린다** — 필터도 검색도 안 붙는데 표는 멀쩡히
  // 그려져서, 화면만 보고는 무엇이 고장인지 알 수가 없다(실제로 그랬다).
  function on(id, event, fn) {
    var node = el(id);
    if (node) node.addEventListener(event, fn);
    return node;
  }
  function setMsg(text, isError) {
    msg.textContent = text || "";
    msg.className = "hint" + (isError ? " error" : "");
  }

  // 수정창을 **모달**로 세운다 — 뒷막 · Escape · 미저장 확인은 공통 부품이
  // 맡는다(`panel_modal.js`). 딜 기업 DB 도 같은 부품을 쓴다: 같은 판단이 두
  // 곳에 있으면 반드시 한쪽이 낡는다.
  //
  // **뒷막이 표를 덮는 것이 이 고침의 핵심이다.** 수정창이 열려 있는 동안에는
  // 표의 칸을 누를 수 없고, 그래서 칸 위에 뜨는 편집창(`.cell-pop`, z-60)이
  // 수정창(z-40) 위에 겹쳐 그려지는 일 자체가 없어진다. 같은 칸을 두 자리에서
  // 서로 다른 시점에 저장하다 값이 조용히 되돌아가던 것도 함께 막힌다.
  var modal = window.PanelModal.init({
    panel: "#detail-panel",
    backdrop: "#detail-backdrop",
    closers: ["#detail-close"],
    // 저장할 때 보내는 것과 **같은 것**을 읽는다. 화면 글자를 따로 긁어 모으면
    // 저장에는 가는데 기준선에는 없는 칸이 생겨 안 고쳐도 묻는 창이 된다.
    snapshot: function () { return JSON.stringify(readForm()); }
  });

  // 다른 줄로 넘어갈 때 묻는 말. 닫을 때와 하는 일이 달라 문구도 다르다 —
  // "닫을까요" 라고 물어 놓고 다른 줄을 여는 창이면 무엇을 누른 건지 모른다.
  var ASK_SWITCH = "고친 내용이 아직 저장되지 않았습니다. 버리고 다른 줄을 열까요?\n\n" +
    "[취소] 를 누르면 지금 창에 그대로 남습니다 — 남기려면 [저장] 을 누르세요.";

  function openPanel(title) {
    el("detail-title").textContent = title;
    // 창을 세우면서 **지금 폼을 기준선으로 잡는다.** 부르는 자리들이 모두
    // 채운 다음에 이것을 부르므로(loadContact · [담당자 추가]) 기준선은 늘
    // "막 채워 넣은 그대로" 다.
    modal.open();
    showTab("info");
  }

  function showTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll(".detail-tab"), function (b) {
      b.classList.toggle("active", b.getAttribute("data-tab") === name);
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-panel]"), function (p) {
      p.hidden = p.getAttribute("data-panel") !== name;
    });
  }

  // 그 명단에만 있는 칸들. **이름을 여기 적어 두지 않는다** — 서버가 그린
  // 칸에 붙은 `data-note` 를 그대로 읽는다. 손으로 적어 두면 칸이 하나 늘 때
  // 여기 넣는 것을 잊는 순간, 창은 멀쩡히 그려지는데 값이 안 채워지고 저장도
  // 안 된다(예전에 `kakao_joined` 가 그랬다).
  function noteInputs() {
    return Array.prototype.slice.call(panel.querySelectorAll("[data-note]"));
  }

  function fillForm(c) {
    FIELDS.forEach(function (f) { if (el("f-" + f)) el("f-" + f).value = c[f] || ""; });
    // 명단이 정한 칸만 그려지므로 없는 칸이 있다 — 없으면 건너뛴다.
    // 여기서 그냥 두면 스타트업 명단을 열자마자 창이 통째로 안 채워진다.
    CHECKS.forEach(function (f) { if (el("f-" + f)) el("f-" + f).checked = !!c[f]; });
    var notes = c.notes || {};
    noteInputs().forEach(function (input) {
      input.value = notes[input.getAttribute("data-note")] || "";
    });
    // 지금 감춰져 있는 줄인가. 단추 글자가 곧 되돌리는 길이다.
    var hide = el("hide-btn");
    if (hide) {
      hide.setAttribute("data-hidden", c.is_hidden ? "1" : "0");
      hide.textContent = c.is_hidden ? "이 줄 다시 보이기" : "이 줄 감추기";
    }
  }

  function readForm() {
    var body = {};
    FIELDS.forEach(function (f) { if (el("f-" + f)) body[f] = el("f-" + f).value.trim(); });
    CHECKS.forEach(function (f) { if (el("f-" + f)) body[f] = el("f-" + f).checked ? 1 : 0; });
    var notes = {};
    noteInputs().forEach(function (input) {
      notes[input.getAttribute("data-note")] = input.value.trim();
    });
    if (noteInputs().length) body.notes = notes;
    return body;
  }

  // 활동 이력은 **월 단위로 묶어** 보여준다. 시트가 월별 컬럼이었기 때문에
  // 사용자의 머릿속 단위도 '8월에 뭘 보냈지'다. 회차는 '몇째 주·요일·몇 개사'로 읽힌다.
  function renderTimeline(items) {
    var list = el("timeline");
    if (!items.length) {
      list.innerHTML = '<li class="muted">기록이 없습니다.</li>';
      return;
    }
    items.sort(function (a, b) {
      var x = a.date || a.month || "", y = b.date || b.month || "";
      return x < y ? 1 : (x > y ? -1 : 0);
    });

    var html = "";
    var lastMonth = null;
    items.forEach(function (t) {
      var month = t.month || (t.date ? t.date.slice(0, 7) : "");
      if (month !== lastMonth) {
        lastMonth = month;
        html += '<li class="tl-month">' + esc(monthLabel(month)) + "</li>";
      }
      html += '<li class="tl-item tl-' + esc(t.kind) + '">' +
        '<span class="tl-date tabular">' + esc(dayLabel(t)) + "</span>" +
        '<span class="tl-kind">' + esc(KIND_KO[t.kind] || t.kind) + "</span>" +
        '<span class="tl-body">' + bodyHtml(t) + "</span>" +
        (t.source === "import" ? '<span class="tl-src">시트</span>' : "") +
        "</li>";
    });
    list.innerHTML = html;
  }

  function monthLabel(month) {
    if (!month) return "날짜 미상";
    var parts = month.split("-");
    return parts.length > 1 ? parts[0] + "년 " + parseInt(parts[1], 10) + "월" : month;
  }

  function dayLabel(t) {
    if (!t.date) return "";
    var d = t.date.slice(5).replace("-", ".");
    return d + (t.weekday ? "(" + t.weekday + ")" : "");
  }

  function bodyHtml(t) {
    var head = "";
    if (t.week) head += '<span class="tl-week">' + t.week + "주차</span> ";
    if (t.company_count) head += "<b>" + t.company_count + "개사</b> ";
    if (t.companies && t.companies.length) {
      // 딜 기업 DB에 있는 기업은 표시만 다르게(없는 기업이 더 많아 오류로 다루지 않는다).
      return head + t.companies.map(function (c) {
        return '<span class="tl-co' + (c.known ? " known" : "") + '">' + esc(c.name) + "</span>";
      }).join(" ");
    }
    return head + esc(t.content);
  }

  function loadContact(id) {
    // **적어 둔 것을 확인 없이 덮지 않는다.** 예전에는 수정창에 타이핑만 해
    // 두고 표의 다른 줄을 누르면 fillForm 이 폼을 통째로 갈아 끼워, 적던 것이
    // 아무 말 없이 사라졌다. 안 고쳤으면 묻지 않는다(창이 닫혀 있을 때도 같다).
    if (!modal.allowLeave(ASK_SWITCH)) return;
    fetch("/api/contacts/" + id)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.contact) { setMsg("담당자를 불러오지 못했습니다", true); return; }
        current = d.contact.id;
        fillForm(d.contact);
        renderTimeline(d.timeline || []);
        openPanel(d.contact.name + " " + (d.contact.title || "") + " · " + (d.contact.firm || ""));
        setMsg("");
      })
      .catch(function () { setMsg("조회 오류", true); });
  }

  function save() {
    var body = readForm();
    if (!body.name) { setMsg("담당자명을 입력하세요", true); return; }
    var url = current ? "/api/contacts/" + current : "/api/contacts";
    fetch(url, {
      method: current ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { setMsg(res.d.detail || "저장 실패", true); return; }
        // 서버가 저 혼자 바꾼 것이 있으면 **말해 준다.** 방 이름을 지우면
        // 연결 상태가 따라 바뀌는데, 그동안 아무 말이 없어서 대시보드에
        // `지금 연결 중` 으로 계속 뜨는 이유를 아무도 알 수 없었다.
        // 새로고침이 뒤따르므로 화면에 적어 두면 그대로 지나간다 — 멈춰 세운다.
        if (res.d.connect_note) alert(res.d.connect_note);
        // 표의 집계값(최근 딜소개·반응)은 서버에서 만든다 → 새로고침이 가장 정확하다.
        window.location.reload();
      })
      .catch(function () { setMsg("저장 오류", true); });
  }

  function remove() {
    // 새로 넣던 줄이면 지울 것이 없다 — 창만 닫는다. 사람이 [삭제] 를
    // 눌러 버리기로 정한 길이라 다시 묻지 않는다.
    if (!current) { modal.close(true); return; }
    if (!confirm("이 담당자를 삭제할까요? 활동 이력도 함께 지워집니다.\n" +
      "(이직·투자사 변경이면 삭제 대신 '검토중단' 을 권합니다 — 이력이 남습니다)")) return;
    // **서버가 준 사유를 그대로 띄운다.**
    //
    // 여기는 `.then(reload)` 한 줄이었다 — 응답이 409 든 500 이든 보지 않고
    // 화면만 다시 그렸다. 그래서 발송 기록·미팅이 걸린 줄을 지우려 하면
    // 아무 말 없이 새로 그려지고, 사람은 **지워진 줄 알았다가 그 줄이 그대로
    // 있는 것을 나중에 발견했다.** 왜 안 되는지 물을 자리조차 없었다.
    //
    // 그래서 실패하면 멈춰 세우고(`alert`) 창에도 남긴다(`setMsg`). 둘 다
    // 하는 이유는, 확인창은 누르면 사라져서 무엇이 몇 건 걸렸는지 다시 볼 수
    // 없기 때문이다 — 수정창에 남아 있으면 [이 줄 감추기] 를 누르기 전에
    // 다시 읽을 수 있다.
    fetch("/api/contacts/" + current, { method: "DELETE" })
      .then(function (r) {
        // 사유가 본문에 없을 수도 있다(502 · 빈 응답) — 그때도 성공으로
        // 넘어가지 않게 `ok` 는 응답에서 읽는다.
        return r.json().then(
          function (d) { return { ok: r.ok, d: d || {} }; },
          function () { return { ok: r.ok, d: {} }; });
      })
      .then(function (res) {
        if (!res.ok) {
          var why = res.d.detail || "삭제하지 못했습니다 (사유를 받지 못했습니다)";
          setMsg(why, true);
          alert(why);
          return;
        }
        window.location.reload();
      })
      .catch(function () { setMsg("삭제 오류", true); });
  }

  // 줄 하나를 다른 담당자에게 넘기기(이관).
  //
  // 확인창에 **누구를 누구에게** 넘기는지 적는다 — 딜 소싱의 삭제 확인창과
  // 같은 방식이다(`sourcing.html`). 되돌리기 번거로운 조작에서 사람이 마지막에
  // 보는 것이 이 한 줄이라, 여기에 이름이 없으면 엉뚱한 줄을 넘겨도 모른다.
  //
  // **월별 기록 이야기를 반드시 함께 적는다.** 달마다 늘어나는 칸은 명단마다
  // 따로라(`ContactColumn.sheet`), 넘기고 나면 옛 명단에 적어 둔 월별 기록이
  // 새 명단의 수정창에 안 보인다. 지워지는 것은 아니지만 **사람 눈에는 사라진
  // 것과 같다** — 말해 주지 않으면 기록이 날아간 줄 알고 다시 적는다.
  // 값을 옮기려 들지는 않는다. 칸이 서로 짝이 안 맞아 어느 칸에 넣어야 할지
  // 정할 근거가 없다.
  function transfer() {
    var pick = el("transfer-target");
    if (!current) { setMsg("먼저 줄을 고르세요", true); return; }
    var label = pick.value;
    if (!label) { setMsg("넘길 명단을 고르세요", true); return; }
    var opt = pick.options[pick.selectedIndex];
    var owner = (opt && opt.getAttribute("data-owner")) || "";
    var who = (el("f-name") && el("f-name").value.trim()) ||
              el("detail-title").textContent.trim();
    if (!confirm(
      "'" + who + "' 님을 '" + owner + "' 님의 명단 '" + label + "' 로 넘길까요?\n\n" +
      "· 지금 명단에서 빠지고 " + owner + " 님의 담당이 됩니다 — " +
      "이 줄은 " + owner + " 님의 대시보드와 딜 소개 발송 대상으로 옮겨 갑니다.\n" +
      "· 월별 기록은 명단마다 칸이 따로라, 지금까지 적어 둔 월별 기록은 " +
      "새 명단의 수정창에 보이지 않습니다. 지워지지는 않고, 도로 넘기면 다시 보입니다.")) return;
    var btn = el("transfer-btn");
    btn.disabled = true;
    fetch("/api/contacts/" + current + "/transfer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: label })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { setMsg(res.d.detail || "이관 실패", true); btn.disabled = false; return; }
        // **어디서 어디로 갔는지 멈춰 세우고 알린다.** 되돌리려면 옛 명단
        // 이름을 알아야 하는데, 뒤이어 새로고침이 오므로 화면에 적어 두면
        // 그대로 지나간다(저장 뒤 `connect_note` 를 알리는 것과 같은 이유다).
        alert("'" + who + "' 님을 넘겼습니다.\n" + (res.d.moved || "") +
              "\n\n되돌리려면 " + owner + " 님이(또는 관리자가) 같은 자리에서 도로 넘기면 됩니다.");
        // 명단별 인원(탭)·전체 수·필터의 `N / M명` 은 모두 서버가 그린다 —
        // 줄만 지우면 숫자가 옛것으로 남는다.
        window.location.reload();
      })
      .catch(function () { setMsg("이관 요청 오류", true); btn.disabled = false; });
  }

  function visibleIds() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr.data-row"))
      .filter(function (tr) { return !tr.hidden; })
      .map(function (tr) { return parseInt(tr.getAttribute("data-id"), 10); });
  }

  function verify(ids, label) {
    if (!ids.length) { alert("확인할 담당자가 없습니다."); return; }
    if (!confirm(label + " " + ids.length + "명의 카톡방 이름을 확인합니다.\n" +
      "카카오톡이 켜져 있어야 하며, 확인 중에는 PC 조작을 멈춰주세요.\n" +
      "(문구는 전송하지 않습니다)")) return;
    fetch("/api/contacts/verify-rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact_ids: ids })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "확인 요청 실패"); return; }
        window.location.href = "/jobs/" + res.d.job_id;
      })
      .catch(function () { alert("확인 요청 오류"); });
  }

  // ── 이벤트 ────────────────────────────────────────────────────────────────
  if (table) {
    table.addEventListener("click", function (e) {
      var tr = e.target.closest ? e.target.closest("tr.data-row") : null;
      if (!tr) return;
      if (e.target.tagName === "A") return;      // 바로가기 링크는 그대로
      // 눌러서 바로 고치는 칸(메모·방 이름)은 상세 패널을 열지 않는다 —
      // 고치려고 누를 때마다 패널이 튀어나오면 고칠 수가 없다.
      if (e.target.closest(".cell[data-field]")) return;
      if (e.target.classList.contains("cell-input")) return;
      loadContact(parseInt(tr.getAttribute("data-id"), 10));
    });
  }

  // [닫기 ✕] · 뒷막 · Escape 는 모두 공통 부품이 맡는다(`closers`) — 닫는 길이
  // 셋인데 미저장 확인이 그중 하나에만 걸려 있으면 나머지 둘로 값이 샌다.
  on("save-btn", "click", save);
  on("delete-btn", "click", remove);
  // 줄 감추기 — **지우기가 아니다.** 표에서 안 보이게 하고 발송 대상에서 뺀다.
  // 같은 단추가 감춘 줄에서는 [다시 보이기] 가 된다(fillForm 참고).
  var hideBtn = el("hide-btn");
  if (hideBtn) {
    hideBtn.addEventListener("click", function () {
      if (!current) { setMsg("먼저 줄을 고르세요", true); return; }
      var next = hideBtn.getAttribute("data-hidden") === "1" ? 0 : 1;
      fetch("/api/contacts/" + current, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_hidden: next })
      })
        .then(function (r) {
          if (!r.ok) throw new Error();
          window.location.reload();
        })
        .catch(function () { setMsg("감추지 못했습니다", true); });
    });
  }
  on("transfer-btn", "click", transfer);
  on("verify-one-btn", "click", function () {
    if (current) verify([current], "선택한 담당자");
  });
  on("verify-btn", "click", function () {
    verify(visibleIds(), "현재 목록의");
  });
  on("add-btn", "click", function () {
    // 고치던 줄을 두고 새 줄로 넘어가는 것도 폼을 갈아 끼우는 일이다 —
    // 다른 줄을 누를 때와 같은 확인을 거친다.
    if (!modal.allowLeave(ASK_SWITCH)) return;
    current = null;
    // 연결 상태는 **비워 두지 않는다.** `<select>` 를 빈 값으로 두면 아무
    // 보기도 안 골라진 채로 서서, 새로 넣는 사람마다 값이 제각각이 된다.
    fillForm({ status: "active", channel_kakao: 1, connect_stage: "not_started" });
    if (el("f-channel_kakao")) el("f-channel_kakao").checked = true;
    openPanel("담당자 추가");
    setMsg("투자사명을 넣으면 카톡방 이름이 자동 생성됩니다(비워둘 경우).");
  });
  Array.prototype.forEach.call(document.querySelectorAll(".detail-tab"), function (b) {
    b.addEventListener("click", function () { showTab(b.getAttribute("data-tab")); });
  });
  var density = el("density-toggle");
  if (density) {
    density.addEventListener("change", function () {
      table.classList.toggle("dense", density.checked);
    });
  }

  if (window.DealflowFilters && table) {
    // 검색은 컬럼 필터와 **AND** 로 묶는다 — 둘이 서로 tr.hidden 을 덮어쓰면
    // 검색과 필터가 번갈아 서로를 지운다(딜 소싱 표와 같은 규칙).
    var box = document.getElementById("vc-search");
    filters = window.DealflowFilters.init({
      table: "#contacts-table",
      extra: function (tr) {
        var q = ((box && box.value) || "").trim().toLowerCase();
        return !q || (tr.getAttribute("data-search") || "").indexOf(q) !== -1;
      }
    });
    if (box) box.addEventListener("input", function () { filters && filters.apply(); });
    // 칸을 고치면 그 값도 필터에 나와야 한다 — 값은 있는데 필터에는 없는
    // 상태가 되면, 있는 줄 알고 골랐다가 아무것도 안 나온다.
    table.addEventListener("inline-saved", function () {
      if (filters && filters.refresh) filters.refresh();
    });
  }

  // 대시보드의 '내 투자사 선호'에서 눌러 오면 그 사람 상세를 바로 연다.
  // 목록만 띄우면 333명 중에서 다시 찾아야 한다 — 무엇을 좋아하는지 보려고
  // 누른 것이므로 선호 분야·라운드 사이즈가 바로 보여야 한다.
  //
  // 이 블록이 **상세 패널과 같은 IIFE 안**에 있어야 하는 이유:
  // loadContact 은 panel·current·msg 처럼 이 안에서만 사는 상태를 닫아 쥐고 있다.
  // 예전에는 이 몇 줄만 파일 끝의 다른 IIFE 로 떨어져 있었고, 그쪽에서는
  // loadContact 이라는 이름 자체가 없어 ReferenceError 로 죽었다 — 화면에는
  // 아무 일도 안 일어난 것처럼 보여서(오류는 콘솔에만) 오래 눈에 안 띄었다.
  // window 로 내보내 부르는 방법도 있지만, 부르는 곳이 여기 한 군데뿐인 함수를
  // 페이지 전역에 올려 두면 다음 사람은 어디서 불러도 되는 함수로 읽는다.
  if (window.DEALFLOW_OPEN_CONTACT) loadContact(window.DEALFLOW_OPEN_CONTACT);
})();

// NO 는 **보이는 것** 기준으로 1부터. 걸러낸 뒤 몇 명인지 그 자리에서 세기 위해서다
// (시트에서 옮겨 온 번호는 중간이 비어 있어 셀 수가 없다).
//
// 이 블록만 따로 떼어 둔 것은 위 상세 패널의 무엇도 쓰지 않기 때문이다 — 표만 있으면 돈다.
// 반대로 위 코드의 함수가 필요한 것을 여기에 적으면 이름이 안 닿아 ReferenceError 로 죽는다.
//
// **이름 정렬도 여기 있다.** 세우는 일과 번호를 다시 매기는 일이 한 짝이기
// 때문이다 — 줄 차례가 바뀌면 `NO` 는 반드시 다시 매겨져야 한다(보이는 것
// 기준의 1,2,3… 이라 차례가 곧 번호다). 정렬을 화면(`contacts.html`)에서
// 따로 걸면 그 짝이 두 파일로 갈라져, 다음 사람이 정렬만 옮겨 붙이는 날
// 번호가 조용히 옛 자리에 남는다.
(function () {
  var table = document.getElementById("contacts-table");
  if (!table) return;

  function renumber() {
    var n = 0;
    table.querySelectorAll("tbody tr.data-row").forEach(function (tr) {
      var cell = tr.querySelector(".rowno");
      if (!cell) return;
      if (tr.hidden) { cell.textContent = ""; return; }
      cell.textContent = ++n;
    });
  }

  renumber();
  // 필터가 행을 숨기면 번호를 다시 매긴다.
  new MutationObserver(renumber).observe(table.querySelector("tbody"), {
    attributes: true, attributeFilter: ["hidden"], subtree: true
  });

  // 이름 머리글을 눌러 오름/내림/끔. **주간 업무가 쓰는 그 부품 그대로다**
  // (`table_sort.js`) — 화면마다 정렬기를 새로 만들면 "빈 값은 어디로 가나",
  // "같은 값끼리는 무슨 차례인가" 같은 판단이 두 벌이 되어 한쪽만 낡는다.
  //
  // 여기서 정하는 것은 **어느 칸을 세우는가**뿐이고(화면의 `data-sort`),
  // 나머지는 그 부품이 이미 정해 둔 대로다:
  //   · 빈 이름은 **방향과 상관없이 늘 끝** — 내림차순에서 이름 없는 줄이
  //     맨 위로 올라오면 목록의 머리가 빈칸이 된다.
  //   · 같은 이름끼리는 **처음 차례를 지킨다**(서버가 그려 준 차례).
  //   · 한 번 더 누르면 끔 — 서버가 그려 준 차례로 돌아온다.
  //   · `?sort=name` 으로 주소에 남아 새로고침해도 살아 있다. 필터 쿼리
  //     (`?room=…`)는 서로 건드리지 않는다 — 두 부품 다 남의 쿼리를 남긴다.
  //
  // 거르는 일(`filters.js`)과 싸우지 않는다: 필터는 줄을 `hidden` 으로
  // 감출 뿐 차례를 안 보고, 정렬은 감춘 줄까지 함께 옮기므로 세우고 나서도
  // 걸려 있던 조건이 그대로 남는다.
  var sort = window.DealflowSort &&
    window.DealflowSort.init({ table: "#contacts-table", onChange: renumber });

  // 이름을 눌러 고치면(`inline_edit.js`) 세울 값도 다시 읽는다. 안 읽으면
  // 화면에는 새 이름이 떠 있는데 머리글을 누르면 옛 이름 자리에 선다.
  if (sort) {
    table.addEventListener("inline-saved", function () {
      sort.refresh();
    });
  }
})();
