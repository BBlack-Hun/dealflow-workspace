// 손으로 보낸 것 적기 — 딜 제안 관리의 [손으로 보냈다면] 칸.
//
// 프로그램으로 안 보내고 카톡에서 **손으로** 보내는 사람이 있다. 그 사람이 한
// 일은 지금 앱 어디에도 안 남아서, 업무 보고의 `딜 소개 총 N명` 도 진행 단계도
// 비어 있고 **리마인드가 아예 안 선다.**
//
// **위에서 고른 것을 그대로 읽는다.** 기업도 사람도 이 파일이 다시 고르게 하지
// 않는다 — `이번 주 딜소개는 8개 기업`, 대상 80명이 이미 골라져 있다. 고르는
// 목록을 한 벌 더 두면 둘 중 한쪽만 발송 대상 규칙(멈춘 사람 빼기·방 연결)을
// 따라가는 날이 온다.
//
// 걸음이 셋이다 — 되돌릴 수 있는 일이지만 80줄이 한 번에 들어온다.
//   ① 고른다 — 위 ①② 칸에서 이미 골라 둔 것.
//   ② 세어 본다 — 서버를 `confirm` 없이 한 번 불러 몇 줄이 새로 들어가고 몇
//      줄은 이미 있는지 받아 온다. 이때 서버는 한 줄도 안 적는다.
//   ③ 묻고 적는다 — 사람이 [확인] 을 누르면 그때 `confirm: true` 로 보낸다.
// (확인을 브라우저에만 두지 않는 이유는 서버 쪽에 적어 두었다 —
//  `routers/deals.py` 의 `create_manual_send`. `bulk-delete` 와 같은 결이다.)
(function () {
  var panel = document.getElementById("manual-send");
  if (!panel) return;                  // 다른 화면 — 아무 일도 하지 않는다

  var kindBox = document.getElementById("manual-kind");
  var dayBox = document.getElementById("manual-day");
  var countBox = document.getElementById("manual-count");
  var countWrap = document.getElementById("manual-count-wrap");
  var button = document.getElementById("manual-btn");
  var note = document.getElementById("manual-note");
  var state = document.getElementById("manual-state");
  var batchBox = document.getElementById("manual-batches");
  var batchList = document.getElementById("manual-batch-list");

  // 서버가 실어 준 값. **여기서 다시 적지 않는다** — 규칙이 바뀌는 날
  // 화면만 옛말을 한다(예약 시각 폭을 서버가 실어 주는 것과 같은 이유).
  var TODAY = panel.getAttribute("data-today") || "";
  var BASE_NOTE = note ? note.textContent : "";
  var WITH_COMPANIES = (panel.getAttribute("data-with-companies") || "")
    .split(",").filter(Boolean);

  function kind() { return kindBox.value; }
  function needsCompanies() { return WITH_COMPANIES.indexOf(kind()) >= 0; }

  // 위 ① 칸에서 고른 기업. **번호는 deals.js 가 붙여 둔 차례**(`data-pick-order`)
  // 를 따른다 — 사람이 고른 차례가 곧 소개 차례라, DOM 순서로 읽으면 그 차례가
  // 사라진다.
  function pickedCompanies() {
    var boxes = Array.prototype.slice.call(
      document.querySelectorAll("#company-list .company-cb"))
      .filter(function (c) { return c.checked; });
    function order(cb) {
      var card = cb.closest(".pick-card");
      return Number(card && card.getAttribute("data-pick-order")) || 0;
    }
    boxes.sort(function (a, b) { return order(a) - order(b); });
    return boxes;
  }

  // 위 ② 칸에서 고른 담당자. **투자사 담당자 목록만** 본다 — 손으로 보낸 것을
  // 적는 자리는 담당자 줄(`vc_contacts`)이고, 딜 소싱 명단은 다른 표다.
  function pickedContacts() {
    return Array.prototype.slice.call(
      document.querySelectorAll("#contact-list .contact-cb"))
      .filter(function (c) { return c.checked; });
  }

  function refresh() {
    var people = pickedContacts().length;
    var companies = needsCompanies() ? pickedCompanies().length : 0;
    var onCount = needsCompanies() && companies === 0;

    // 기업을 고르면 [개수만] 칸은 잠근다 — 고른 개수가 곧 답이다.
    countBox.disabled = !onCount;
    countBox.hidden = !needsCompanies();
    countWrap.hidden = !needsCompanies();
    if (!onCount) countBox.value = "";

    button.textContent = people
      ? "손으로 보낸 것으로 기록 (" + people + "명)"
      : "손으로 보낸 것으로 기록";
    button.disabled = people === 0;

    // **날짜가 무엇을 뜻하는지 미리 말한다.** 적고 나서 알면 이미 늦다.
    // 글자의 뼈대는 서버가 준 것이고, 여기서는 오늘인지 아닌지만 덧붙인다.
    var today = dayBox.value === TODAY;
    note.textContent = BASE_NOTE +
      (dayBox.value
        ? (today ? " — 오늘 날짜입니다. 리마인드가 잡힙니다."
                 : " — 지난 날짜입니다. 기록만 남습니다.")
        : "");
    note.className = "hint" + (dayBox.value && !today ? " muted" : "");
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  function say(text, cls) {
    state.hidden = !text;
    state.textContent = text || "";
    state.className = "hint " + (cls || "");
  }

  // 확인창 — **무엇이 몇 줄 들어가고 몇 줄은 이미 있는지**, 그리고 리마인드가
  // 서는지. 리마인드가 이 기능의 절반이라 여기서 말하지 않으면 사람은 소급
  // 입력에 왜 아무 일도 안 일어나는지 모른다.
  function planText(plan) {
    var lines = [plan.kind_label + " — " + plan.day + " 에 손으로 보낸 것으로 적습니다.", ""];
    lines.push("· 대상 " + plan.total + "명 중 " + plan.adding + "줄이 새로 들어갑니다.");
    if (plan.already) {
      lines.push("· " + plan.already + "줄은 같은 날 같은 묶음으로 이미 적혀 있어 건너뜁니다.");
    }
    if (plan.company_count) {
      lines.push("· 기업 " + plan.company_count + "개사" +
        (plan.companies.length ? " (" + plan.companies.slice(0, 5).join(", ") +
          (plan.companies.length > 5 ? " 외 " + (plan.companies.length - 5) : "") + ")"
          : " — 이름 없이 개수만"));
    }
    lines.push("");
    lines.push(plan.will_remind
      ? "· 오늘 날짜라 리마인드가 함께 잡힙니다."
      : "· 지난 날짜라 리마인드는 잡히지 않습니다 (기록만 남습니다).");
    lines.push("");
    lines.push("적을까요?");
    return lines.join("\n");
  }

  function body(confirmed) {
    var count = parseInt(countBox.value, 10);
    return {
      contact_ids: pickedContacts().map(function (c) { return parseInt(c.value, 10); }),
      company_ids: needsCompanies()
        ? pickedCompanies().map(function (c) { return parseInt(c.value, 10); }) : [],
      company_count: (needsCompanies() && !isNaN(count) && count > 0) ? count : null,
      kind: kind(),
      day: dayBox.value,
      confirm: !!confirmed
    };
  }

  button.addEventListener("click", function () {
    if (!pickedContacts().length) return;
    button.disabled = true;
    say("");

    // ② 먼저 세어 본다 — 이 부름은 한 줄도 적지 않는다.
    post("/api/deals/manual-sends", body(false)).then(function (res) {
      if (!res.ok) { alert((res.d && res.d.detail) || "적을 것을 확인하지 못했습니다"); refresh(); return; }
      var plan = res.d.plan || {};
      if (!plan.adding) {
        alert("고른 " + plan.total + "명은 " + plan.day +
              " 에 같은 묶음으로 이미 적혀 있습니다 — 새로 들어갈 줄이 없습니다.");
        refresh();
        return;
      }
      if (!confirm(planText(plan))) { refresh(); return; }

      // ③ 여기서만 참으로 적는다.
      post("/api/deals/manual-sends", body(true)).then(function (out) {
        if (!out.ok) { alert((out.d && out.d.detail) || "기록 실패"); refresh(); return; }
        // 결과 한 줄은 **서버가 지은 것을 그대로** 띄운다 — 여기서 다시
        // 지으면 두 벌이 되고, 둘이 어긋나도 아무도 모른다.
        say(out.d.note, "ok");
        refresh();
        loadBatches(true);
      }).catch(function () { alert("기록 요청 오류"); refresh(); });
    }).catch(function () { alert("기록 요청 오류"); refresh(); });
  });

  // ── 되돌리기 ──────────────────────────────────────────────────────────────
  var loaded = false;

  function loadBatches(force) {
    if (loaded && !force) return;
    loaded = true;
    fetch("/api/deals/manual-sends")
      .then(function (r) { return r.json(); })
      .then(function (d) { renderBatches((d && d.batches) || []); })
      .catch(function () { batchList.innerHTML = '<p class="muted">목록을 불러오지 못했습니다.</p>'; });
  }

  function renderBatches(rows) {
    if (!rows.length) {
      batchList.innerHTML = '<p class="muted">손으로 적은 기록이 아직 없습니다.</p>';
      return;
    }
    batchList.innerHTML = "";
    rows.forEach(function (b) {
      var line = document.createElement("div");
      line.className = "manual-batch" + (b.is_undone ? " undone" : "");
      var what = b.kind_label + " · " + (b.day || "-") + " · " + b.rows + "줄";
      if (b.company_count) what += " · " + b.company_count + "개사";
      var text = document.createElement("span");
      text.textContent = what;
      line.appendChild(text);
      if (b.is_undone) {
        // **되돌린 판도 목록에 남긴다.** 사라지면 사람은 자기가 되돌렸는지
        // 애초에 안 적었는지를 알 수 없다.
        var tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = "되돌림";
        line.appendChild(tag);
      } else {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "linkbtn";
        btn.textContent = "되돌리기";
        btn.addEventListener("click", function () { undo(b, btn); });
        line.appendChild(btn);
      }
      batchList.appendChild(line);
    });
  }

  function undo(batch, btn) {
    btn.disabled = true;
    var url = "/api/deals/manual-sends/" + encodeURIComponent(batch.batch_key) + "/undo";
    post(url, { confirm: false }).then(function (res) {
      if (!res.ok) { alert((res.d && res.d.detail) || "되돌릴 수 없습니다"); btn.disabled = false; return; }
      var plan = res.d.plan || {};
      if (!confirm(plan.kind_label + " · " + plan.day + " 로 적은 " + plan.rows +
                   "줄을 되돌립니다.\n\n지우지 않고 숨깁니다 — 보고·진행 단계·" +
                   "이력 어디에서도 안 읽힙니다.\n\n되돌릴까요?")) {
        btn.disabled = false;
        return;
      }
      post(url, { confirm: true }).then(function (out) {
        if (!out.ok) { alert((out.d && out.d.detail) || "되돌리기 실패"); btn.disabled = false; return; }
        say(out.d.undone + "줄을 되돌렸습니다.", "ok");
        loadBatches(true);
      }).catch(function () { alert("되돌리기 요청 오류"); btn.disabled = false; });
    }).catch(function () { alert("되돌리기 요청 오류"); btn.disabled = false; });
  }

  if (batchBox) batchBox.addEventListener("toggle", function () {
    if (batchBox.open) loadBatches(false);
  });

  kindBox.addEventListener("change", refresh);
  dayBox.addEventListener("change", refresh);
  // 위 칸에서 고른 것이 바뀌면 이 칸의 수도 따라 바뀌어야 한다.
  document.addEventListener("change", function (e) {
    if (e.target.classList &&
        (e.target.classList.contains("company-cb") ||
         e.target.classList.contains("contact-cb"))) refresh();
  });
  // [전체선택]·[전체해제]는 상자를 코드로 켜고 끈다 — `change` 가 안 난다.
  ["select-all-contacts", "clear-all-contacts", "select-noreact"].forEach(function (id) {
    var b = document.getElementById(id);
    if (b) b.addEventListener("click", function () { setTimeout(refresh, 0); });
  });

  refresh();
})();
