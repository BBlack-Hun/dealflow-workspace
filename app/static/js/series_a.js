// IR 기업 현황 메뉴의 `Series A 이상 딜 소싱` 탭 — 검색 · 머리글 필터 · 정렬 ·
// 줄 번호 · 저장 뒤처리 · 추가 · 삭제.
//
// 칸을 눌러 고치는 일은 공통 부품(`inline_edit.js`)이, 거르는 일은
// `filters.js` 가, 세우는 일은 `table_sort.js` 가 한다 — 이 파일은 그 셋을
// 이 표에 거는 것과, **서버만 아는 값**을 저장 뒤에 받아 적는 것만 한다.
// 옆 두 탭(`companies.js`)과 같은 짜임이다.
(function () {
  var table = document.getElementById("sa-table");
  if (!table) return;

  var search = document.getElementById("sa-search");
  var note = document.getElementById("sa-note");

  function rows() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-id]"));
  }

  // 검색창은 컬럼 필터 위에 AND 로 얹는다 — 둘이 각자 tr.hidden 을 만지면
  // 검색과 필터가 번갈아 서로를 지운다(`companies.js` 와 같은 이유).
  function textMatch(tr) {
    var q = (search.value || "").trim().toLowerCase();
    if (!q) return true;
    return (tr.getAttribute("data-search") || "").indexOf(q) !== -1;
  }

  // 줄 번호는 **보이는 것 기준**이다 — 걸러낸 뒤 몇 건인지 세려고.
  function renumber() {
    var n = 0;
    rows().forEach(function (tr) {
      var cell = tr.querySelector(".rowno");
      if (!cell) return;
      if (tr.hidden) { cell.textContent = ""; return; }
      n += 1;
      cell.textContent = n;
    });
  }

  function afterApply() {
    var total = rows().length;
    var shown = rows().filter(function (tr) { return !tr.hidden; }).length;
    renumber();
    note.hidden = shown === total;
    note.textContent = shown !== total ? shown + " / " + total + "건 표시 중" : "";
  }

  var filters = null;
  if (window.DealflowFilters) {
    filters = window.DealflowFilters.init({
      table: "#sa-table",
      unit: "건",
      extra: textMatch,
      onChange: afterApply
    });
  }

  function apply() {
    if (filters) { filters.apply(); return; }
    rows().forEach(function (tr) { tr.hidden = !textMatch(tr); });
    afterApply();
  }
  search.addEventListener("input", apply);

  // 머리글을 눌러 세운다. 세운 뒤 **번호를 다시 매긴다** — 이 표의 `NO` 는
  // 지금 서 있는 차례 그 자체라, 안 매기면 `3,5,1,…` 로 남는다.
  var sort = window.DealflowSort && window.DealflowSort.init({
    table: "#sa-table",
    onChange: renumber
  });

  // ── 저장 뒤처리 ──────────────────────────────────────────────────────
  //
  // 응답(`routers/series_a._result`)이 주는 값으로 **화면이 다시 만들 수 없는
  // 것**을 고쳐 적는다. 규칙을 여기 또 적으면 서버와 두 벌이 된다.
  //   · 고친 칸 — **서버가 저장한 값**으로 다시 그린다. 서버가 받지 않은 값도
  //     있다(기업명은 비울 수 없어 옛 이름이 돌아온다). 적힌 그대로 두면 화면만
  //     빈 이름으로 남는다. 필터 값도 같은 값으로 맞춘다.
  //   · `투자라운드` — 칸에는 괄호 앞(`series_short`), 필터도 그 값.
  //   · `수신 일자` — 세울 값(`received_sort`). 날짜 모양도 서버가 맞춘다.
  //   · 검색 글자(`data-search`) — 안 고치면 고친 값이 새로고침 전까지 안 걸린다.
  //   · `IR 현황` 딱지 — 기업명을 고치면 맞는 기업이 달라진다.
  //   · 나머지 칸 · `IR 기업:` 표시 — 기업명을 넣어 IR 기업에 이어지면 서버가 대표자 ·
  //     매출 · 금액 빈칸을 IR 값으로 채운다(`services/company_sync.py`). 새로고침 없이
  //     보이게 줄의 칸을 전부 응답으로 다시 그린다.
  table.addEventListener("inline-saved", function (e) {
    var data = e.detail.data || {};
    var row = e.detail.row;
    var cell = e.detail.cell;
    if (!row || !("id" in data)) return;
    var field = cell && cell.getAttribute("data-field");

    if (field === "series") {
      cell.textContent = data.series_short || "";
      cell.setAttribute("data-value", data.series || "");
      if (cell.parentNode) cell.parentNode.title = data.series || "";
      row.setAttribute("data-f-series", data.series_short || "");
    } else if (field && field in data) {
      cell.textContent = data[field] || "";
      var fkey = cell.getAttribute("data-filter-key");
      if (fkey && row.hasAttribute("data-f-" + fkey)) {
        row.setAttribute("data-f-" + fkey, data[field] || "");
      }
    }
    Array.prototype.forEach.call(row.querySelectorAll(".cell[data-field]"), function (other) {
      var key = other.getAttribute("data-field");
      if (other !== cell && key !== "series" && key in data) other.textContent = data[key] || "";
    });
    if (data.ir_link) renderIrLink(row.querySelector(".sa-ir-link"), data.ir_link);
    if ("search" in data) row.setAttribute("data-search", data.search || "");
    row.setAttribute("data-s-received_at", data.received_sort || "");

    var link = row.querySelector(".ir-link");
    if (link) {
      link.hidden = !data.ir_name;
      link.setAttribute("href", "/companies?q=" + encodeURIComponent(data.ir_name || ""));
    }
    // `공유 심사역` 을 고치면 후보가 바뀌고, 다른 사람으로 고쳤으면 확정도 풀린다
    // (`routers/series_a._assign`) — 응답대로 다시 그린다.
    if (data.sharer) renderSharer(row.querySelector(".sa-sharer"), data.sharer);
    // 세울 값을 다시 읽는다 — 위에서 고쳐 적은 뒤라 한 박자 뒤에.
    if (sort) window.setTimeout(sort.refresh, 0);
  });

  // ── 공유 심사역 확정 ──────────────────────────────────────────────────
  //
  // `공유 심사역` 은 사람이 시트에 적은 글자라 Series A 딜 공유가 "이 딜을 넘겨 준
  // 분께는 빼고 보낸다" 를 이름 · 회사로 짐작한다(`series_a_share.is_own`). 칸 아래에
  // 딜 소싱 명단에서 이름이 같은 분을 후보로 띄우고, [이 분으로 확정]을 누르면 그
  // 뒤로는 그 분만 본다. 무엇을 띄울지는 서버가 정해 실어 준다(`data-sharer` —
  // `series_a_share.sharer_views`) — 이름을 맞추는 규칙을 여기 또 적지 않는다.
  //
  // 글자는 `textContent` 로만 넣는다 — 이름 · 회사는 시트에서 온 말이다.
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // 후보 · 확정 딱지. 칸(124px)보다 긴 이름 · 회사는 `…` 로 잘리므로
  // (app.css `.sa-sharer-name`) 다 적은 글을 풍선말로 단다.
  function nameTag(cls, text) {
    var tag = el("span", cls + " sa-sharer-name", text);
    tag.setAttribute("title", text);
    return tag;
  }

  function renderSharer(box, info) {
    if (!box) return;
    info = info || {};
    box.innerHTML = "";
    var confirmed = info.confirmed;
    var cands = info.candidates || [];
    if (confirmed) {
      box.appendChild(nameTag("tag ok", "확정 · " + confirmed.label));
      var clear = el("button", "linkbtn js-sharer-clear", "해제");
      clear.setAttribute("type", "button");
      clear.setAttribute("title", "확정을 풀고 다시 이름 · 회사로 짐작합니다");
      box.appendChild(clear);
    } else {
      cands.forEach(function (c) {
        box.appendChild(nameTag("tag soft",
                                c.label + (c.auto ? " · 이름 · 회사 같음" : " · 이름만 같음")));
        var pick = el("button", "linkbtn js-sharer-pick", "이 분으로 확정");
        pick.setAttribute("type", "button");
        pick.setAttribute("data-contact", String(c.id));
        pick.setAttribute("title", "Series A 딜 공유에서 이 분께만 이 딜을 뺍니다");
        box.appendChild(pick);
      });
    }
    box.hidden = !confirmed && !cands.length;
    renderPhone(box.closest("tr"), confirmed);
  }

  // `휴대폰` 칸(#25) — 확정한 분의 딜 소싱 줄 번호. 확정한 분이 없으면 빈칸이고
  // `cell` 을 떼어 눌러도 안 열린다(서버도 막는다 — `routers/series_a._set_sharer_phone`).
  function renderPhone(tr, confirmed) {
    var cell = tr && tr.querySelector(".sa-sharer-phone");
    if (!cell) return;
    cell.textContent = confirmed ? (confirmed.phone || "") : "";
    cell.classList.toggle("cell", !!confirmed);
    if (confirmed && !cell.hasAttribute("tabindex")) cell.setAttribute("tabindex", "0");
  }

  rows().forEach(function (tr) {
    var box = tr.querySelector(".sa-sharer");
    if (!box) return;
    var info = null;
    try { info = JSON.parse(box.getAttribute("data-sharer") || "null"); }
    catch (e) { info = null; }
    renderSharer(box, info);
  });

  // ── IR 기업 연결 표시 ────────────────────────────────────────────────
  //
  // 기업명 밑 `IR 기업: ○○ (자동 연결 · 연결 풀기)` — 투자컨설턴트 표와 같은 글자다.
  // 무엇을 보일지는 서버가 정해 실어 준다(`data-ir-link` · 저장 응답의 `ir_link` —
  // `services/ir_link.badge`). 이어지지 않았고 이름이 같은 IR 기업도 없으면 숨는다.
  function linkTo(text, href) {
    var a = el("a", "", text);
    a.setAttribute("href", href || "#");
    return a;
  }

  function renderIrLink(box, info) {
    if (!box) return;
    info = info || {};
    box.innerHTML = "";
    box.hidden = !info.linked && !info.candidates;
    if (box.hidden) return;
    box.appendChild(el("span", "", "IR 기업: "));
    if (info.linked) {
      box.appendChild(linkTo(info.name, info.company_href));
      if (info.auto) {
        box.appendChild(el("span", "", " (자동 연결 · "));
        box.appendChild(linkTo("연결 풀기", info.link_href));
        box.appendChild(el("span", "", ")"));
      } else {
        box.appendChild(el("span", "", " (연결됨)"));
      }
    } else {
      box.appendChild(el("span", "", "연결 안 됨 → "));
      box.appendChild(linkTo("연결하기", info.link_href));
    }
  }

  rows().forEach(function (tr) {
    var box = tr.querySelector(".sa-ir-link");
    if (!box) return;
    var info = null;
    try { info = JSON.parse(box.getAttribute("data-ir-link") || "null"); }
    catch (e) { info = null; }
    renderIrLink(box, info);
  });

  // ── 더하기 · 지우기 ───────────────────────────────────────────────────

  function send(method, url, body) {
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  // 기업명만 받아 **오늘 받은 딜**로 세운다(나머지는 표에서 눌러 고친다).
  document.getElementById("sa-add").addEventListener("click", function () {
    var name = (window.prompt("받은 딜의 기업명") || "").trim();
    if (!name) return;
    send("POST", "/api/series-a-companies", { name: name }).then(function (res) {
      if (!res.ok) { alert(res.d.detail || "추가하지 못했습니다"); return; }
      window.location.reload();
    }).catch(function () { alert("추가 요청 오류"); });
  });

  // 무엇을 지우는지 **이름으로** 묻는다 — "이 줄" 만으로는 어느 줄을 눌렀는지
  // 확신할 수 없다(옆 탭의 [삭제] 와 같은 이유).
  // [이 분으로 확정] · [해제] — 서버가 돌려준 대로 다시 그린다.
  table.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-sharer-pick") || e.target.closest(".js-sharer-clear");
    if (!btn) return;
    var tr = btn.closest("tr");
    var box = tr && tr.querySelector(".sa-sharer");
    var raw = btn.getAttribute("data-contact");
    var id = raw ? parseInt(raw, 10) : null;
    send("PUT", "/api/series-a-companies/" + tr.getAttribute("data-id") + "/sharer",
         { contact_id: id })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "확정하지 못했습니다"); return; }
        renderSharer(box, res.d.sharer);
      }).catch(function () { alert("확정 요청 오류"); });
  });

  table.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-sa-delete");
    if (!btn) return;
    var tr = btn.closest("tr");
    var nameCell = tr.querySelector('[data-field="name"]');
    var name = nameCell ? nameCell.textContent.trim() : "";
    // Series A 딜 공유 기록이 이 줄을 가리키면 **함께 지워진다**(서버 —
    // `series_a_share.delete_for_company`). 몇 명 몫인지 확인창에서 말한다.
    var shared = parseInt(tr.getAttribute("data-shared") || "0", 10) || 0;
    var also = shared
      ? "\n이 기업을 받은 심사역 " + shared + "명의 Series A 딜 공유 기록도 함께 지워집니다" +
        "(이미 나간 문구는 발송 이력에 남습니다)."
      : "";
    if (!window.confirm("'" + name + "' 줄을 지웁니다. 되돌릴 수 없습니다." + also)) return;
    send("DELETE", "/api/series-a-companies/" + tr.getAttribute("data-id"))
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "지우지 못했습니다"); return; }
        window.location.reload();
      }).catch(function () { alert("삭제 요청 오류"); });
  });

  apply();
})();
