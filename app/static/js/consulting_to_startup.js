// 투자컨설턴트 `관리 스타트업` 탭 → **스타트업 명단으로 보내기** (여러 줄).
//
// `이관` 이 아니다. 이 저장소에서 이관(`sheet_owner.move_to`)은 줄 하나의
// 담당을 바꾸고 옛 명단에서 빼는 일인데, 여기는 표가 아예 다르고 **이 표의
// 줄은 그대로 남는다.** 그래서 단추 글자도 확인창 글자도 다른 말을 쓴다 —
// 누른 사람이 이 표에서 빠진 줄 알면 안 된다.
//
// 모양과 함정은 투자사 풀의 [내 명단으로 할당](`pool_assign.js`)을 그대로
// 따른다. 여러 줄을 고르는 자리가 화면마다 다르게 생기면 같은 일을 두 번
// 배우게 된다.
(function () {
  var bar = document.getElementById("cs-startup-bar");
  if (!bar) return;

  var table = document.getElementById("cs-table");
  if (!table) return;

  var pickAll = document.getElementById("cs-pick-all");
  var countBox = document.getElementById("cs-pick-count");
  var target = document.getElementById("cs-startup-target");
  var button = document.getElementById("cs-startup-send");
  // 보낼 화면의 이름. **여기 글자로 안 적는다** — 좌측 메뉴가 그 이름을 들고
  // 있고(`ui.MENU`), 서버가 그것을 막대에 실어 준다. 여기 적으면 메뉴를 고친
  // 날 이 확인창만 옛 이름으로 남는다.
  var pageLabel = bar.getAttribute("data-page-label") || "";

  // 이 막대를 감싼 **접었다 펴는 상자.** 기본은 닫힘이다(consulting.html).
  // 없을 수도 있다 — 여닫이는 화면 쪽 일이라 이 파일이 그것에 기대지 않는다.
  var fold = document.getElementById("cs-startup-fold");
  // 사람이 **직접 접은 적이 있는가.** 한 번 접으면 그 뒤로는 안 건드린다 —
  // 접어 둔 것을 줄을 고를 때마다 자꾸 펴면 그것도 화면이 말을 안 듣는 것이다.
  var closedByHand = false;
  if (fold) {
    fold.addEventListener("toggle", function () {
      if (!fold.open) closedByHand = true;
    });
  }

  // **처음 하나를 고르면 저절로 펴진다.** 체크 칸은 표 안에 있어 접어도 그대로
  // 보이는데, 접힌 채로는 [보내기] 단추도 명단 고르는 자리도 안 보인다 —
  // 줄을 골라 놓고 아무 일도 못 하는 상태가 된다.
  //
  // 펼친 상태를 어딘가에 **기억시키지는 않는다.** 고르고 보내는 동안 화면이
  // 다시 그려지지 않아서다(검색·칩·머리글 필터는 줄을 감추거나 주소만 고치고,
  // 칸 고치기는 그 칸만 고쳐 적는다). 다시 받는 자리는 보내고 난 뒤와 탭을
  // 바꾸는 링크뿐인데, 둘 다 고른 체크가 풀리는 자리라 펴진 채로 열리면
  // `0개 선택` 이라고 적힌 빈 막대가 자리만 먹는다.
  function openForPick() {
    if (fold && !fold.open && !closedByHand) fold.open = true;
  }

  function boxes() {
    return Array.prototype.slice.call(table.querySelectorAll(".cs-pick"));
  }

  // **검색·필터로 숨긴 줄은 [전체 선택]에 안 걸린다.** 화면에 없는 기업이
  // 스타트업 명단에 서면, 누른 사람은 자기가 무엇을 보냈는지 모른다.
  // (`pool_assign.js` 가 같은 함정을 같은 방식으로 피한다. 이 화면이 줄을
  //  감추는 자리는 `consulting.js` 의 `tr.hidden` 하나다.)
  function visibleBoxes() {
    return boxes().filter(function (cb) {
      var tr = cb.closest("tr");
      return tr && !tr.hidden;
    });
  }

  function picked() {
    return boxes().filter(function (cb) { return cb.checked; });
  }

  function refresh() {
    var n = picked().length;
    // **여는 줄에 적힌다**(consulting.html 의 `<summary>`). 접힌 채로도 몇 개
    // 골랐는지 보여야, 줄을 골라 놓고 아무것도 안 보이는 상태가 안 된다.
    countBox.textContent = n + "개 선택";
    button.disabled = n === 0;
    if (n) openForPick();
  }

  table.addEventListener("change", function (e) {
    if (e.target.classList.contains("cs-pick")) refresh();
  });

  pickAll.addEventListener("change", function () {
    visibleBoxes().forEach(function (cb) { cb.checked = pickAll.checked; });
    refresh();
  });

  // 확인창에 **어느 기업인지** 적는다. 개수만 적으면 검색으로 걸러 놓고
  // [전체 선택] 을 누른 뒤 무엇이 걸렸는지 확인할 길이 없다.
  //
  // **`기업명` 칸 글자를 안 읽는다.** 그 칸에는 계약일·무료유료·보수율이 함께
  // 적혀 있을 수 있어서(`라마바이오 / 무료 / 3%`), 그대로 물으면 확인창의
  // 이름과 실제로 서는 이름이 다르다. 꺼내는 규칙은 서버 한 곳이고
  // (`startup_handoff.company_name_of`) 그 결과가 줄에 실려 온다.
  function names(list) {
    return list.map(function (cb) {
      return (cb.getAttribute("data-firm") || "").trim();
    }).filter(Boolean);
  }

  button.addEventListener("click", function () {
    var chosen = picked();
    if (!chosen.length) return;
    var ids = chosen.map(function (cb) { return parseInt(cb.value, 10); });
    var label = target.value;
    var shown = names(chosen).slice(0, 5).join(", ");
    if (names(chosen).length > 5) shown += " 외 " + (names(chosen).length - 5) + "곳";
    if (!confirm(ids.length + "개 기업을 '" + label + "' 명단에 세웁니다.\n" +
                 shown + "\n\n" +
                 "투자컨설턴트 표에서는 빠지지 않습니다.")) return;

    button.disabled = true;
    fetch("/api/contacts/from-consulting", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_ids: ids, label: label })
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (res) {
        if (!res.ok) {
          alert((res.d && res.d.detail) || "보내기 실패");
          button.disabled = false;
          return;
        }
        // **무엇이 어떻게 됐는지 적는다.** 건너뛴 기업을 말하지 않으면 사람은
        // 다 들어간 줄 알고, 정작 그 기업은 어느 화면에도 새로 안 선다.
        var d = res.d;
        var lines = [d.added.length + "개 기업을 '" + d.label + "' 명단에 세웠습니다."];
        if (d.skipped.length) {
          lines.push("이미 있어 건너뜀 " + d.skipped.length + "곳: " +
                     d.skipped.join(", "));
        }
        if (d.blank.length) {
          lines.push("기업명을 읽지 못해 건너뜀 " + d.blank.length + "줄 — " +
                     "기업명 칸을 확인하세요.");
        }
        // **어디로 갈지 사람이 고른다.** 여기서 못 박으면 한쪽이 늘 틀린다 —
        // 확인하러 가고 싶은 사람과, 이어서 더 고르려는 사람이 둘 다 있다.
        //
        // 스타트업 화면 주소는 **서버가 준다**(`d.href` = `sheet_owner.page_href`).
        // 화면에 `/startup` 이라고 적어 두면 명단이 사는 화면이 바뀌는 날
        // 남의 화면으로 튀고, 거기엔 그 탭이 없어 빈 표가 뜬다.
        //
        // 어느 쪽을 골라도 **화면을 다시 받는다.** 방금 보낸 줄에는 `✓` 가
        // 서야 하는데(같은 기업이 두 화면에 있다는 표시), 그 표시는 서버가
        // 그리는 것이라 그대로 두면 다음에 또 고를 수 있는 것처럼 보인다.
        if (d.added.length &&
            confirm(lines.join("\n") + "\n\n" + pageLabel + " 화면에서 확인할까요?")) {
          window.location.href = d.href;
          return;
        }
        if (!d.added.length) alert(lines.join("\n"));
        window.location.reload();
      })
      .catch(function () { alert("보내기 요청 오류"); button.disabled = false; });
  });

  refresh();
})();
