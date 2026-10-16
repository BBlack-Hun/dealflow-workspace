// 참고 자료 표 — 머리글과 칸을 눌러 바로 고친다.
//
// 보기만 되던 자료다. 스크립트·성격 정리는 쓰면서 다듬는 것이라, 고치려고
// 구글 시트를 따로 열어야 하면 화면 안으로 들여온 뜻이 없다.
//
// **머리글도 칸과 같은 길을 지난다** — 같은 `.ref-cell`, 같은 손잡이, 같은
// 입력칸, 같은 되돌리기. 표를 화면에서 세울 수 있게 되면서 머리글이
// `칸 1 · 칸 2 …` 로 서는데, 한 표 안에서 머리글과 칸을 고치는 법이 다르면
// 쓰는 사람이 헷갈리고 나중에 한쪽만 고쳐진다. 다른 것은 **어디에 저장하는가
// 하나뿐**이다(아래 `saveTo`).
//
// 투자사 표의 inline_edit 와 저장 모양이 다르다(칸을 줄·열 번호로 가리킨다)
// 그래서 여기만 따로 둔다.
(function () {
  "use strict";

  var table = document.getElementById("ref-table");
  if (!table) return;
  var id = table.getAttribute("data-ref-id");
  var editing = null;

  table.addEventListener("click", function (e) {
    var cell = e.target.closest(".ref-cell");
    if (!cell || cell === editing) return;
    start(cell);
  });

  // 어디에 저장하는가. 머리글은 `columns[col]`, 칸은 `rows[row][col]` —
  // 자료에서 서로 다른 자리라 주소도 따로다(routers/contacts.py 참고:
  // 빈 값 규칙이 서로 반대여서 한 손잡이로 묶지 않았다).
  function saveTo(cell) {
    var col = parseInt(cell.getAttribute("data-col"), 10);
    if (cell.classList.contains("ref-head")) {
      return { url: "/api/ref-sheets/" + id + "/column", body: { col: col } };
    }
    return {
      url: "/api/ref-sheets/" + id + "/cell",
      body: { row: parseInt(cell.getAttribute("data-row"), 10), col: col }
    };
  }

  // ## 칸은 **여러 줄**이다 — 엔터는 줄바꿈, 저장은 Ctrl/Cmd+Enter
  //
  // 이 표에 들어오는 것은 딜소개 스크립트처럼 **문단**이다. 예전에는 한 줄
  // 높이(`rows = 1`)로 열리고 엔터가 곧 저장이었다. 그래서 긴 스크립트를 붙여
  // 넣으면 한 줄만 보였고(헤드리스 크롬 실측: 쉰 줄 950px 이 29px 칸 안),
  // 줄을 나누려고 엔터를 치는 순간 칸이 닫히며 저장됐다 — "스크롤이 안
  // 내려가고 내용 기입이 안 된다" 는 말이 그것이다.
  //
  // 키는 이 앱의 **다른 여러 줄 칸과 같다**(투자컨설턴트 현황의 `multi` 칸 —
  // consulting.js · 공통 편집기 inline_edit.js 의 긴 글 칸). 같은 일을 하는
  // 칸이 화면마다 다른 키를 쓰면 한쪽에서 익힌 손이 다른 쪽에서 글을 날린다.
  //
  // **머리글은 한 줄이다.** 칸 이름에 줄바꿈이 들어갈 일이 없고, 들어가면
  // 머리행만 두 줄로 부푼다. 그래서 머리글은 엔터가 곧 저장이다 — 투자컨설턴트
  // 현황에서 `multi` 가 아닌 칸이 그런 것과 같은 갈래다. 같은 손잡이·같은
  // 입력칸을 지나고 **엔터의 뜻만** 다르다.
  function start(cell) {
    if (editing) return;
    editing = cell;
    var before = cell.textContent.trim();
    var multi = !cell.classList.contains("ref-head");

    var input = document.createElement("textarea");
    input.className = "cell-input";
    input.rows = multi ? 3 : 1;
    input.value = before;

    // 빠져나갈 길을 먼저 만든다 — focus 가 던지면 blur 가 안 붙어 칸에 갇힌다.
    input.addEventListener("blur", finish);
    input.addEventListener("keydown", function (e) {
      // **한글을 조합하는 중에는 비켜선다.** 입력기가 글자를 굳히려고 친
      // 엔터를 여기서 가로채면 만들던 글자째 칸이 닫힌다(inline_edit.js 와
      // 같은 막음이다 — `keyCode 229` 는 옛 브라우저의 같은 말).
      if (e.isComposing || e.keyCode === 229) return;
      if (e.key === "Escape") {
        e.preventDefault();
        input.value = before;
        input.blur();
        return;
      }
      if (e.key === "Enter" && (!multi || e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        input.blur();
      }
    });
    // **쓰는 만큼 칸이 자란다.** 높이를 못 박아 두면 긴 글이 칸 안에서만
    // 굴러 어디를 고치는지 안 보인다. 상한을 두지 않는다 — 표가 화면 높이로
    // 잘리지 않으므로(_ref_panel.html 의 감싸개 주석) 페이지가 그대로 굴러간다.
    input.addEventListener("input", grow);

    cell.textContent = "";
    cell.appendChild(input);
    // 무엇을 누르면 저장되는지 **칸 밑에 적는다.** 엔터가 줄바꿈이 된 것을
    // 모르면 저장하려고 엔터를 치다 줄만 늘어난다.
    var hint = document.createElement("div");
    hint.className = "cell-pop-hint";
    hint.textContent = multi ? "Enter 줄바꿈 · ⌘/Ctrl+Enter 저장 · Esc 취소"
                             : "Enter 저장 · Esc 취소";
    cell.appendChild(hint);
    grow();
    try { input.focus(); } catch (err) { /* 포커스 실패해도 갇히지 않는다 */ }

    // 머리글도 같이 자란다 — 한 줄짜리라도 이름이 칸보다 길면 접혀 두 줄이
    // 되는데, 높이가 한 줄에 묶여 있으면 접힌 뒤가 안 보인다.
    function grow() {
      input.style.height = "auto";
      // 그림이 없는 자리(검사)에서는 `scrollHeight` 가 없다 — 숫자가 아니면
      // 높이를 건드리지 않는다(`NaNpx` 를 적으면 브라우저가 통째로 버린다).
      var h = input.scrollHeight;
      if (typeof h === "number" && h > 0) input.style.height = (h + 2) + "px";
    }

    function finish() {
      var after = input.value.trim();
      cell.textContent = after;
      editing = null;
      if (after === before) return;
      var to = saveTo(cell);
      to.body.value = after;
      fetch(to.url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(to.body)
      }).then(function (r) {
        if (r.ok) return;
        // **왜 안 됐는지 그대로 옮긴다.** '저장하지 못했습니다' 만 뜨면 빈
        // 머리글을 물린 것인지 연결이 끊긴 것인지 알 수 없어 같은 것을 또 누른다.
        return r.json().then(function (d) { return d && d.detail; },
                             function () { return ""; }).then(failed);
      }).catch(function () { failed(); });
    }

    // 저장이 **조용히 삼켜지지 않게** 한다 — 화면에는 고친 글자가, 서버에는
    // 옛 글자가 남으면 새로고침 전까지 아무도 모른다.
    function failed(why) {
      cell.textContent = before;
      alert(why ? "저장하지 못했습니다 — " + why : "저장하지 못했습니다.");
    }
  }
})();
