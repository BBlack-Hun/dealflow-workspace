// 투자컨설턴트 현황 — 시트처럼 칸을 눌러 바로 고친다.
//
// 원본이 구글시트라 쓰는 사람은 "칸을 눌러 고친다"에 익숙하다. 상세 패널을 여닫게
// 하면 56줄을 훑으며 고치는 일이 배로 느려지므로, 표에서 바로 고치게 한다.
// 칸을 벗어날 때만 저장한다(글자마다 저장하면 요청이 쏟아진다).
(function () {
  var table = document.getElementById("cs-table");
  if (!table) return;

  var search = document.getElementById("cs-search");
  var note = document.getElementById("cs-note");
  var filter = "";
  var filterName = "";   // 지금 눌린 칩의 이름. 무엇으로 걸렀는지 글자로 남긴다.

  function rows() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-id]"));
  }

  // 줄이 걸린 마디들. 갈래 표시는 `data-f-mgmt` **하나**이고 관리 중 · 드랍 칩도
  // 그것을 나눠 본다 — 예전에는 `data-managed`/`data-dropped` 를 따로 두어,
  // 같은 판단이 화면·서버·여기 세 곳에 적혀 있었다.
  function tagsOf(tr) {
    // 빈 칸은 `"".split("|") === [""]` 이라 **태그 하나로 세어진다.** 그대로
    // 두면 `연락 기록 없음`(태그가 하나도 없는 줄)이 아무도 안 잡는다.
    // filters.js 의 `splitValues` 도 같은 이유로 빈 값을 떨어낸다.
    return (tr.getAttribute("data-f-mgmt") || "").split("|")
      .filter(function (t) { return t.length > 0; });
  }

  function hasTag(tr, tag) { return tagsOf(tr).indexOf(tag) >= 0; }

  // ── 검색 · 칩 · 컬럼 필터 ──────────────────────────────────
  //
  // 셋이 **AND** 로 묶여야 한다. 검색과 칩은 컬럼으로 표현할 수 없는 조건이라
  // filters.js 에 `extra` 로 넘긴다 — 둘이 따로 tr.hidden 을 쥐면 번갈아 서로를
  // 지운다(검색하면 컬럼 필터가 풀리고, 필터를 고르면 검색어가 풀린다).
  function passes(tr) {
    // `내용이 없습니다` 안내 행은 자료가 아니다 — 걸러서 감추면 왜 비었는지
    // 알려 줄 문구까지 같이 사라진다.
    if (!tr.getAttribute("data-id")) return true;
    var q = (search.value || "").trim().toLowerCase();
    var hit = !q || (tr.getAttribute("data-search") || "").indexOf(q) !== -1;
    return hit && (filter === ""
      || (filter === "managed" && hasTag(tr, "관리 중"))
      || (filter === "dropped" && hasTag(tr, "드랍"))
      // `그 외` — 적혀 있는데 위 두 마디가 아닌 줄. 이 칸은 자유 서술이라 값의
      // 종류가 무한해서 값마다 칩을 세울 수가 없다. 값별로 고르는 일은 머리글
      // `기업 관리 ▾` 가 이미 한다(`기타 메모`·`백업팀 전환` 이 따로 서 있다).
      // 서버는 `consulting_status.is_other` 가 같은 것을 본다.
      || (filter === "other" && tagsOf(tr).length > 0
          && !hasTag(tr, "관리 중") && !hasTag(tr, "드랍"))
      // `연락 기록 없음` — **아무것도 안 적힌 줄.** 예전에는 월별 리마인드 칸만
      // 봐서, `기업 관리` 에 적어 둔 줄이 리마인드가 비었다는 이유로 `관리 중`
      // 과 여기에 **동시에** 떴다. 두 칸을 같이 본다
      // (서버는 `consulting_status.no_contact`).
      //
      // 줄에 표시를 하나 더 두지 않고 **있는 값 둘에서 되짚는다** — 칸을 고치면
      // 그 둘은 `refreshRowFlags` 가 다시 적으므로, 새 표시를 두면 그것만 낡는다.
      || (filter === "nocontact" && tagsOf(tr).length === 0
          && tr.getAttribute("data-contacted") !== "1"));
  }

  // 몇 곳이 남았는지. 걸러 놓고 건수를 안 보여 주면 다 본 것인지 알 수 없다.
  //
  // **무엇으로 걸렀는지도 적는다.** 건수만 두면 `연락 기록 없음`(어느 달이든
  // 기록이 없는 곳)과 위 KPI 의 `미완료 기업`(지난달만 본다)이 서로 다른
  // 숫자인데도 구별할 방법이 없다 — 실데이터로 7곳과 20곳이다.
  function showNote(state) {
    var all = rows();
    var shown = all.filter(function (tr) { return !tr.hidden; }).length;
    var picked = state ? Object.keys(state).length : 0;
    var q = (search.value || "").trim();
    note.hidden = !(q || filter || picked);
    if (!note.hidden) {
      note.textContent = shown + " / " + all.length + "곳 표시 중"
        + (filterName ? " · " + filterName : "")
        + (q ? " (검색: " + q + ")" : "");
    }
  }

  // ── 위 KPI ────────────────────────────────────────────────
  //
  // KPI 는 **거른 결과가 아니라 이 탭 전체**를 센다. `드랍` 만 보는 중이라고
  // `관리 중` 이 0 이 되면 안 된다 — 그건 필터가 아니라 표의 성질이다.
  // (deals.js 가 `data-match` 와 `hidden` 을 갈라 둔 것과 같은 이유: "조건에
  //  맞는가" 를 "보이는가" 로 읽으면 안 된다. 여기서는 `tr.hidden` 을 아예
  //  안 본다.)
  //
  // 세는 규칙은 서버(`services/consulting_status.py`)와 같아야 한다. 그래서
  // 줄에 적힌 값만 보고 세고, `기업 관리` 칸의 문장을 여기서 다시 읽지 않는다.
  function syncKpi() {
    var all = rows();
    var n = { total: all.length, managed: 0, dropped: 0, pending: 0 };
    all.forEach(function (tr) {
      if (hasTag(tr, "관리 중")) n.managed += 1;
      if (hasTag(tr, "드랍")) n.dropped += 1;
      if (tr.getAttribute("data-contacted-prev") !== "1") n.pending += 1;
    });
    Object.keys(n).forEach(function (key) {
      // 표식이 없는 숫자는 안 건드린다 — `미완료 기업` 은 지난달 칸이 표에
      // 서 있을 때만 표식이 붙는다(접혀 있으면 다시 셀 근거가 화면에 없다).
      var el = document.querySelector('[data-kpi="' + key + '"]');
      if (el) el.textContent = String(n[key]);
    });
  }

  var columnFilters = window.DealflowFilters && window.DealflowFilters.init({
    table: "#cs-table",
    extra: passes,
    onChange: showNote
  });

  // 표를 다시 거른다. **행 값을 다시 읽는 것부터** 한다 — 칸을 고치면 그 줄의
  // `data-f-*` 가 바뀌는데, filters.js 는 처음 한 번 읽은 값으로 목록을 만들기
  // 때문에 다시 읽지 않으면 화면에는 `관리 중` 이라고 적혀 있는데 필터에는
  // 여전히 `드랍` 으로 남는다.
  function apply() {
    // 위 숫자는 걸린 조건과 무관하다 — 어느 길로 가든 먼저 센다.
    // (`columnFilters` 가 있으면 아래에서 바로 빠져나가므로 여기 말고는
    //  둘 다 거치는 자리가 없다.)
    syncKpi();
    if (columnFilters) { columnFilters.refresh(); return; }   // refresh 안에서 적용까지 한다
    // 공통 부품을 못 실었을 때(스크립트 순서가 틀어졌다든지)라도 검색·칩은 살아 있어야 한다.
    rows().forEach(function (tr) { tr.hidden = !passes(tr); });
    showNote(null);
  }

  search.addEventListener("input", apply);
  // 칩은 **한 번에 하나**다. 넷이 `기업 관리` 한 갈래를 서로 안 겹치게 나눠
  // 놓은 것이라서다 — 관리 중 · 드랍 · 그 외(적혀 있는데 둘 다 아님) · 아무것도
  // 안 적힌 줄. AND 로 묶으면 서로 배타적이라 늘 0줄이고, OR 로 묶으면 "관리
  // 중이거나 드랍인 곳" 이라는 아무도 안 찾는 목록이 된다. 한 갈래 **안에서**
  // 값을 여러 개 고르는 일은 머리글 `기업 관리 ▾` 가 이미 한다(컬럼 안에서는 OR).
  document.querySelectorAll("[data-cs-filter]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll("[data-cs-filter]").forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      filter = btn.getAttribute("data-cs-filter");
      filterName = filter ? (btn.textContent || "").trim() : "";
      apply();
    });
  });

  // ── 칸에서 바로 고치기 ─────────────────────────────────────
  var editing = null;

  // **값이 든 자리.** 칸에 따라 `td` 자체이기도 하고 그 안의 `.cell-main`
  // 이기도 하다.
  //
  // `수정한 날짜` 를 값 아래 잔글씨로 단 칸(`딜 소개문구` · `카톡 연결 여부` ·
  // 월별 리마인드)은 값과 날짜가 **한 `td` 안에** 같이 있다. 거기서 `td` 의
  // 글자를 그대로 읽으면 **날짜까지 값으로 딸려 들어가** 그대로 저장된다 —
  // 한 번 고치면 값 뒤에 날짜가 붙고, 다음에 고치면 날짜가 두 개 붙는다.
  //
  // 읽는 자리와 쓰는 자리가 **같은 함수 하나**를 지나야 한다. 한 곳만 고치면
  // 읽을 때는 값만 읽고 쓸 때는 잔글씨를 덮어써서 날짜가 사라진다.
  function valueBox(cell) {
    return cell.querySelector(".cell-main") || cell;
  }

  // 값 아래 잔글씨 상자. 없으면 만든다 — 서버는 **날짜가 있을 때만** 세운다
  // (344줄짜리 표에서 빈 상자를 늘 세우면 모든 줄의 키가 한 줄만큼 오른다).
  // 처음 고치는 칸에는 그래서 상자가 없고, 그 자리를 여기서 만든다.
  function stampBox(cell) {
    var box = cell.querySelector(".cell-sub");
    if (box) return box;
    box = document.createElement("div");
    box.className = "cell-sub muted";
    // 화면과 **같은 말**이다(consulting.html 의 `stamped` 매크로) — 잔글씨만
    // 보고는 이것이 그 칸의 날짜인지 줄 전체의 날짜인지 알 수 없다.
    box.title = "이 칸을 마지막으로 고친 시각";
    cell.appendChild(box);
    return box;
  }

  // 이 칸의 **수정한 날짜 열쇠.** 서버가 쓰는 것과 같은 꼴이다
  // (`routers/consulting.py` 의 `note_stamp_key`). 월별 리마인드는 석 달치가
  // `notes` 한 칸에 들어 있어서 열 id 로 갈라 찍는다.
  function stampKey(cell) {
    var noteId = cell.getAttribute("data-note");
    return noteId ? "note:" + noteId : cell.getAttribute("data-field");
  }

  // 고친 시각을 **그 자리에서** 바꾼다. 새로고침해야 날짜가 따라오면, 방금
  // 고친 칸 밑에 옛 날짜가 그대로 적혀 있어 화면이 거짓말을 한다
  // (IR 기업 현황·스타트업 명단이 같은 이유로 같은 일을 한다 —
  //  `companies.js` · `contacts.js` 의 `수정한 날짜`).
  //
  // **꼴을 여기서 만들지 않는다.** 서버가 `clock.stamp_text` 한 곳을 지나
  // 보내 준 글자를 그대로 적는다 — 여기서 다시 자르면 같은 값이 두 꼴로 보인다.
  function showStamp(cell, stamps) {
    if (!stamps) return;
    var at = stamps[stampKey(cell)];
    // 날짜를 보여 주는 칸이 아니면(서버가 안 실어 준다) 상자를 만들지 않는다.
    if (!at) return;
    stampBox(cell).textContent = at;
  }

  table.addEventListener("click", function (e) {
    var cell = e.target.closest("td.cell");
    if (!cell || cell === editing) return;
    // 남의 담당 줄은 **볼 수만** 있다. 서버가 이미 404 로 막지만
    // (`routers/consulting.py` 의 `owned`), 여기서 안 막으면 칸이 입력칸으로
    // 바뀌고 글자까지 쳐진 뒤에 저장만 실패한다 — 쓴 것이 그대로 사라진다.
    // 어느 줄이 그런지는 서버가 `data-readonly` 로 실어 준다. 판정을 브라우저가
    // 다시 하면(`역할 === "consultant"` 따위) 규칙이 두 벌이 된다.
    if (cell.closest("tr").hasAttribute("data-readonly")) return;
    startEdit(cell);
  });

  function startEdit(cell) {
    if (editing) finishEdit();
    editing = cell;
    // **값만** 읽는다 — 잔글씨(`수정한 날짜`)가 같은 칸에 있다(`valueBox`).
    var box = valueBox(cell);
    var before = box.textContent.trim();
    var multi = cell.classList.contains("multi");
    var input = document.createElement(multi ? "textarea" : "input");
    input.className = "cell-input";
    input.value = before;
    if (multi) input.rows = Math.min(6, Math.max(2, before.split("\n").length + 1));
    // 값 상자만 비운다. `cell` 을 통째로 비우면 잔글씨가 같이 사라져, 고치다
    // 취소(Escape)한 칸에서 날짜만 조용히 없어진다.
    box.textContent = "";
    box.appendChild(input);
    // 고르는 칩은 **칸에** 붙인다 — 값 상자 안에 넣으면 저장할 때 같이 지워질
    // 자리이고, 잔글씨 아래에 서는 편이 값을 안 가린다.
    addChoices(cell, input, before);
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);

    input.addEventListener("blur", finishEdit);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = before; input.blur(); }
      // 여러 줄 칸에서는 엔터가 줄바꿈이어야 한다. 저장은 Ctrl/Cmd+Enter.
      if (e.key === "Enter" && (!multi || e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        input.blur();
      }
    });

    function finishEdit() {
      if (editing !== cell) return;
      editing = null;
      var after = input.value.trim();
      box.textContent = after;
      // 고르는 칩은 편집이 끝나면 치운다 — 예전에는 `cell.textContent = …` 이
      // 칸을 통째로 비우면서 같이 사라졌는데, 이제 값 상자만 비우므로 남는다.
      var chips = cell.querySelector(".cell-pop-choices");
      if (chips) cell.removeChild(chips);
      if (after === before) return;
      save(cell, after, before);
    }
  }

  // 값이 몇 가지로 정해져 있는 칸(`계약서 수신여부` 의 O/X)은 **골라 넣게** 한다.
  //
  // 그냥 타이핑하게 두면 같은 뜻이 `O`·`o`·`ㅇ`·`○` 로 갈린다. 값이 두 가지뿐인
  // 칸에서 그건 곧 머리글 필터가 못 쓰게 된다는 뜻이다 — 목록에 네 줄이 서고,
  // `O` 를 골라도 `○` 로 적은 줄은 안 걸린다.
  //
  // 내 투자사 화면의 `카톡방 참여여부` 도 같은 O/X 인데, 그쪽은 공통 편집기의
  // `data-choices` 가 맡는다(inline_edit.js 의 `startPick`). 이 표만 편집기가
  // 따로라(`startEdit`) 목록을 세우는 부분을 여기에 한 벌 더 둔다 — 값을 어떻게
  // **판정**하는지는 여기에 없으므로(서버는 적힌 그대로 담는다) 서버와 갈릴
  // 규칙이 늘어나는 것은 아니다. 생김새는 같은 CSS(`.cell-pop-choice`)를 쓴다.
  function addChoices(cell, input, before) {
    var choices = (cell.getAttribute("data-choices") || "").split(",")
      .map(function (v) { return v.trim(); })
      .filter(function (v) { return v.length > 0; });
    if (!choices.length) return;
    var box = document.createElement("div");
    box.classList.add("cell-pop-choices");
    // 마지막은 **비우는** 단추다. `O`/`X` 만 세워 두면 잘못 누른 것을 되돌릴
    // 길이 없는데, 이 칸에서 빈칸은 `아직 안 정함` 이라는 뜻을 가진 값이다
    // (전부 `X` 로 시작하지 않는 이유가 그것이다 — 0047 참고).
    choices.concat([""]).forEach(function (value) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.classList.add("cell-pop-choice");
      // 지금 값에 표시를 남긴다 — 빈칸도 값 하나로 서야(`비움`) "아직 안 정했다"
      // 가 화면에서 읽힌다.
      if (value === before) chip.classList.add("on");
      chip.textContent = value || "비움";
      // mousedown 이라야 input 의 blur 보다 **먼저** 잡힌다. click 으로 달면
      // 먼저 blur 가 나 편집이 끝나고, 그때 단추는 이미 사라져 아무 일도
      // 일어나지 않는다.
      chip.addEventListener("mousedown", function (e) {
        e.preventDefault();
        input.value = value;
        input.blur();        // blur 가 finishEdit 을 부른다 — 저장은 거기 한 곳이다
      });
      box.appendChild(chip);
    });
    cell.appendChild(box);
  }

  function save(cell, value, before) {
    var tr = cell.closest("tr");
    var id = parseInt(tr.getAttribute("data-id"), 10);
    var body = {};
    var noteId = cell.getAttribute("data-note");
    if (noteId) {
      var notes = {};
      notes[noteId] = value;
      body.notes = notes;
    } else {
      body[cell.getAttribute("data-field")] = value;
    }
    cell.classList.add("saving");
    fetch("/api/consulting/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) {
        cell.classList.remove("saving");
        if (!r.ok) throw new Error();
        // 응답 본문이 없거나 깨져도 저장은 된 것이다 — 날짜만 못 바꾼다.
        return r.json().catch(function () { return {}; });
      })
      .then(function (data) {
        cell.classList.add("saved");
        setTimeout(function () { cell.classList.remove("saved"); }, 900);
        // **고친 시각을 그 자리에서.** 서버가 보내 준 글자를 그대로 적는다
        // (꼴을 정하는 자리는 `app/clock.py` 의 `stamp_text` 한 곳이다).
        showStamp(cell, data && data.stamps);
        refreshRowFlags(tr);
        // 플래그만 고치고 끝내면 **화면은 옛 조건 그대로**다. `드랍` 만 보는
        // 중에 한 곳을 `관리 중` 으로 바꾸면 이제 드랍이 아닌데도 목록에
        // 남아 있고, 위의 표시 건수도 안 맞는다 — 새로고침해야 사라진다.
        // 다른 화면(투자사·기업·딜 소싱)은 저장하면 필터가 곧바로 다시
        // 걸리므로, 여기만 다르게 두면 같은 조작이 화면마다 달리 동작한다.
        apply();
      })
      .catch(function () {
        cell.classList.remove("saving");
        cell.classList.add("save-failed");
        // 저장 못 했으면 화면도 되돌린다. **값 상자만** 되돌린다 — 칸을
        // 통째로 덮으면 잔글씨(`수정한 날짜`)가 같이 지워져, 실패했는데
        // 그 칸의 날짜만 사라진 화면이 된다.
        valueBox(cell).textContent = before;
        alert("저장하지 못했습니다. 잠시 후 다시 시도하세요.");
      });
  }

  // 계약 탭인가. `계약여부` 칸은 값이 `무료`/`유료` 라 추리지 않고 그대로 건다.
  var contractSheet = table.getAttribute("data-contract-sheet") === "1";

  // `기업 관리` 칸이 어느 갈래인가. **브라우저 쪽 규칙은 이 함수 하나뿐이다** —
  // 칩도 KPI 도 머리글 필터도 여기서 나온 태그를 나눠 볼 뿐, 칸의 문장을 다시
  // 읽지 않는다.
  //
  // 서버의 `services/consulting_status.py` 와 **같은 말을 같은 순서로** 봐야
  // 한다. 언어가 둘이라 한 벌씩은 어쩔 수 없지만, 어긋나면 고친 직후와
  // 새로고침 뒤에 같은 줄이 서로 다른 값으로 걸린다.
  // (같은 마디가 양쪽에 있는지는 `tests/test_filter_columns.py` 가 지킨다.)
  function managementTags(text) {
    // 계약 탭의 `계약여부` 는 이미 추려진 값이다. 아래 규칙을 태우면 `무료`·
    // `유료` 가 전부 `기타 메모` 로 묶여 고를 것이 없어진다.
    if (contractSheet) return text.trim();
    var tags = [];
    if (text.indexOf("관리") >= 0) tags.push("관리 중");
    if (text.indexOf("드랍") >= 0) tags.push("드랍");
    if (text.indexOf("백업팀") >= 0) tags.push("백업팀 전환");
    if (!tags.length && text.trim()) tags.push("기타 메모");
    return tags.join("|");
  }

  // 줄에 붙는 표시는 전부 칸의 내용에서 나온다 — 고치면 다 같이 따라가야 한다.
  // 칩도 KPI 도 머리글 필터도 **여기서 적은 값만** 본다.
  function refreshRowFlags(tr) {
    // **값만 읽는다** — 잔글씨(`수정한 날짜`)가 같은 칸에 있는 칸들이 있어서,
    // `td` 의 글자를 그대로 읽으면 갈래·검색·`연락 기록 없음` 이 전부 날짜를
    // 값으로 센다(`valueBox`). `기업 관리` 에는 잔글씨가 없지만 규칙을 칸마다
    // 갈라 두면 한 벌은 반드시 낡는다.
    var mgmt = tr.querySelector('[data-field="management"]');
    tr.setAttribute("data-f-mgmt",
                    managementTags(mgmt ? valueBox(mgmt).textContent : ""));
    // **행이 이미 그 값을 싣고 있을 때만** 다시 적는다 — 계약 탭에는 `월`
    // 머리글이 없어 이 값도 안 실려 있는데, 여기서 새로 만들면 아무도 안 보는
    // 죽은 속성이 생긴다(아래 고르는 칸들과 같은 규칙이다).
    var region = tr.querySelector('[data-field="region"]');
    if (region && tr.hasAttribute("data-f-region")) {
      tr.setAttribute("data-f-region", valueBox(region).textContent.trim());
    }
    // 탭마다 서는 고르는 칸들. **행이 이미 그 값을 싣고 있을 때만** 다시
    // 적는다 — 없는 속성을 여기서 새로 만들면 그 칸이 없는 탭에 아무도 안 보는
    // 죽은 값이 생긴다(머리글이 선언하지 않은 값이다).
    //
    // 적히는 것은 칸의 글자 그대로다 — 값이 몇 가지로 정해진 칸이라 판정할
    // 것이 없다(그래서 `consulting_status.py` 에 규칙이 늘지 않는다).
    //
    //   contract_received   `계약서 수신여부`(계약 탭) = `계약서 수신완료여부`
    //                       (관리 스타트업 탭). **같은 칸이라 키도 하나**다.
    //   contract_done       `계약완료여부` — 관리 스타트업 탭에만 있다.
    //   contract_management `견적서 첨부 여부` — 관리 스타트업 탭에만 있다.
    //                       칸 이름과 필터 키(`quote`)가 다르다.
    //   kakao_joined        `카톡 연결 여부` — 관리 스타트업 탭에만 있다.
    //                       칸 이름과 필터 키(`joined`)가 다르다. 이름이
    //                       `내 투자사` 화면의 칸과 같지만 **다른 표의 다른
    //                       칸**이다(`models.ConsultingCompany.kakao_joined`).
    //
    // 한 자리에서 돌린다 — 규칙이 칸마다 따로 적히면 한 벌은 반드시 낡는다.
    //   meeting_kind        `미팅종류` — 계약 탭에만 안 선다(저 탭의
    //                       `meeting_at` 은 `계약월` 이라는 다른 물음이다).
    //                       칸 이름과 필터 키(`meetkind`)가 다르다.
    [["contract_received", "data-f-received"],
     ["contract_done", "data-f-done"],
     ["contract_management", "data-f-quote"],
     ["kakao_joined", "data-f-joined"],
     ["meeting_kind", "data-f-meetkind"]].forEach(function (pair) {
      var td = tr.querySelector('[data-field="' + pair[0] + '"]');
      if (td && tr.hasAttribute(pair[1])) {
        tr.setAttribute(pair[1], valueBox(td).textContent.trim());
      }
    });
    // **적힌 것이 있는가**는 앞뒤 공백을 뗀 뒤에 본다. 서버도 같은 규칙이다
    // (`consulting_status.contacted`) — 예전에는 서버가 공백만 든 칸을 기록으로
    // 세서, 그런 줄이 아무 칸이나 고치는 순간 `연락 기록 없음` 으로 넘어갔다.
    // **날짜는 기록이 아니다.** 잔글씨까지 세면 달 칸을 채웠다가 도로 비운 줄이
    // 날짜만 남아 `연락했다` 로 걸린다 — `연락 기록 없음` 칩과 위 KPI 가 같이
    // 틀어진다. 값 상자만 본다.
    function filled(td) { return valueBox(td).textContent.trim().length > 0; }
    // **접어 둔 달의 기록도 기록이다.** 여기서 볼 수 있는 것은 펴 둔 달의 칸뿐이라,
    // 이 줄이 없으면 접힌 달에만 기록이 있는 줄이 칸을 고치는 순간 `연락 기록 없음`
    // 으로 뒤집힌다 — 화면에 안 보이는 사실이라 고친 사람은 이유를 알 수 없다.
    // 접힌 달의 사실은 서버가 `data-contacted-folded` 로 실어 준다.
    var hasNote = tr.getAttribute("data-contacted-folded") === "1"
      || Array.prototype.some.call(tr.querySelectorAll("[data-note]"), filled);
    tr.setAttribute("data-contacted", hasNote ? "1" : "0");
    // 위 KPI 의 `미완료 기업` 은 **지난달 칸만** 센다. 어느 칸이 지난달인지는
    // 서버가 `data-prev-note` 로 찍어 준다 — 열 이름이 자유 문장이라
    // (`8월 마지막주 리마인드 톡 or TEL`) 여기서 달을 읽게 두면 규칙이 또
    // 한 벌 생긴다. 지난달 열이 접혀 있으면 그 표가 아예 안 붙고, 그때는
    // KPI 에도 표식이 없어 이 값이 쓰이지 않는다.
    var prev = tr.querySelectorAll("[data-prev-note]");
    if (prev.length) {
      tr.setAttribute("data-contacted-prev",
                      Array.prototype.some.call(prev, filled) ? "1" : "0");
    }
    var parts = [];
    Array.prototype.forEach.call(tr.querySelectorAll("td.cell"), function (td) {
      // 날짜는 검색 재료가 아니다 — 서버도 `data-search` 에 안 넣는다
      // (`routers/consulting.py` 의 `search`). 여기서 넣으면 고치기 전후로
      // 검색 결과가 달라진다.
      parts.push(valueBox(td).textContent);
    });
    tr.setAttribute("data-search", parts.join(" ").toLowerCase());
  }

  // ── 추가 · 삭제 ────────────────────────────────────────────
  var addBtn = document.getElementById("cs-add");
  addBtn.addEventListener("click", function () {
    // 어느 탭에 들어가는지 물어볼 때 미리 알려 준다 — 딜 소싱의 `[○○에 추가]`와 같다.
    var sheet = (addBtn.getAttribute("data-sheet") || "").trim();
    var name = prompt("기업명을 입력하세요" + (sheet ? " (" + sheet + ")" : ""));
    if (!name || !name.trim()) return;
    // **지금 보고 있는 탭을 함께 보낸다.** 안 보내면 서버가 첫 탭에 넣어서,
    // 다른 탭에서 누른 사람에게는 추가가 안 된 것처럼 보였다(줄은 만들어졌지만
    // 보고 있는 탭에 없다). 서버는 `sheet` 가 없으면 예전처럼 첫 탭에 넣으므로,
    // 빈 값이면 아예 싣지 않아 옛 동작을 그대로 둔다.
    var body = { company_name: name.trim() };
    if (sheet) body.sheet = sheet;
    fetch("/api/consulting", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "추가 실패"); return; }
        window.location.reload();
      });
  });

  table.addEventListener("click", function (e) {
    if (!e.target.classList.contains("js-cs-del")) return;
    var tr = e.target.closest("tr");
    var name = valueBox(
      tr.querySelector('[data-field="company_name"]')).textContent.trim();
    if (!confirm("'" + name + "' 줄을 삭제할까요?")) return;
    fetch("/api/consulting/" + tr.getAttribute("data-id"), { method: "DELETE" })
      .then(function (r) {
        if (!r.ok) { alert("삭제 실패"); return; }
        tr.remove();
        apply();
      });
  });

  var importBtn = document.getElementById("cs-import-btn");
  var importPanel = document.getElementById("cs-import");
  importBtn.addEventListener("click", function () { importPanel.hidden = !importPanel.hidden; });
  document.getElementById("cs-import-close").addEventListener("click", function () {
    importPanel.hidden = true;
  });
})();
