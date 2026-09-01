// LLM 에 물어보기 — 자료를 꺼내 보여주고, 답해 온 번호를 이름으로 되돌린다.
//
// **화면이 부르는 주소는 API 그대로다.** [자료 내려받기] 는 링크일 뿐이고
// [화면에서 보기] 도 같은 `/api/llm-brief.json` 을 부른다. 화면용 경로를 따로
// 두면 한쪽이 낡는다 — 이 저장소가 반복해 당한 사고다.
(function () {
  var toggle = document.getElementById("llm-toggle");
  var body = document.getElementById("llm-body");
  if (!toggle || !body) return;

  var download = document.getElementById("llm-download");
  var show = document.getElementById("llm-show");
  var copy = document.getElementById("llm-copy");
  var out = document.getElementById("llm-out");
  var state = document.getElementById("llm-state");
  var answer = document.getElementById("llm-answer");
  var resolve = document.getElementById("llm-resolve");
  var found = document.getElementById("llm-found");
  var foundState = document.getElementById("llm-found-state");

  // 자료를 꺼내는 주소는 **내려받기 링크에서 읽는다.** 여기에 주소를 또 적으면
  // 주소가 바뀔 때 링크만 고쳐지고 [화면에서 보기] 는 옛 주소를 부른다.
  var BRIEF_URL = (download && download.getAttribute("href")) || "/api/llm-brief.json";

  toggle.addEventListener("click", function () {
    var open = body.hidden;
    body.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.textContent = open ? "접기" : "펼치기";
  });

  // --- 자료 꺼내 보기 -------------------------------------------------------

  show.addEventListener("click", function () {
    state.textContent = "꺼내는 중…";
    fetch(BRIEF_URL)
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (text) {
        out.textContent = text;
        out.hidden = false;
        copy.hidden = false;
        // 몇 건인지 먼저 말해 준다. 자료가 비어 있는데 그대로 붙여 넣고
        // "왜 아무것도 안 골라 주지" 하는 일이 없게.
        var data = null;
        try { data = JSON.parse(text); } catch (e) { data = null; }
        state.textContent = data
          ? ("투자사 " + data.investors.length + "곳 · 기업 "
             + data.companies.length + "곳 · " + data.scope)
          : "";
      })
      .catch(function () { state.textContent = "자료를 꺼내지 못했습니다."; });
  });

  copy.addEventListener("click", function () {
    var text = out.textContent;
    // 클립보드 권한이 없거나 http 로 열었으면 `navigator.clipboard` 가 없다.
    // 그때는 조용히 실패하지 말고 **직접 복사할 수 있게** 골라 준다 —
    // 눌렀는데 아무 일도 안 나면 복사된 줄 알고 빈 것을 붙여 넣는다.
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        state.textContent = "복사했습니다.";
      }, selectAll);
    } else {
      selectAll();
    }
  });

  function selectAll() {
    var range = document.createRange();
    range.selectNodeContents(out);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    state.textContent = "골라 두었습니다 — Ctrl/⌘+C 로 복사하세요.";
  }

  // --- 번호를 이름으로 ------------------------------------------------------

  resolve.addEventListener("click", function () {
    var text = (answer.value || "").trim();
    found.innerHTML = "";
    if (!text) {
      foundState.textContent = "답한 내용을 붙여 넣어 주세요.";
      return;
    }
    foundState.textContent = "찾는 중…";
    fetch("/api/llm-brief/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text })
    })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(draw)
      .catch(function () { foundState.textContent = "찾지 못했습니다."; });
  });

  function draw(data) {
    var rows = data.investors.concat(data.companies);
    if (!rows.length) {
      // 번호가 하나도 없으면 **왜 없는지** 말해 준다. 맨숫자는 일부러 안 읽기
      // 때문에("30억" 을 번호로 읽으면 엉뚱한 사람이 뜬다), 그것을 모르면
      // 붙여 넣기가 잘못된 줄 안다.
      foundState.textContent = "번호를 찾지 못했습니다 — V-31 · C-7 처럼 적혀 있어야 합니다.";
      return;
    }
    var missing = rows.filter(function (r) { return !r.found; }).length;
    foundState.textContent = rows.length + "개 번호"
      + (missing ? " · " + missing + "개는 내 담당에 없습니다" : "");

    rows.forEach(function (row) {
      var item = document.createElement("div");
      item.classList.add("llm-found-row");
      // 못 찾은 번호는 흐리게 남긴다 — 지우면 다섯을 넣고 셋만 뜬 것을 모른다.
      if (!row.found) item.classList.add("missing");
      var tag = document.createElement("span");
      tag.classList.add("llm-ref");
      tag.textContent = row.id;
      item.appendChild(tag);

      if (row.found) {
        var link = document.createElement("a");
        link.href = row.href;
        link.textContent = row.name + (row.firm ? " · " + row.firm : "");
        item.appendChild(link);
      } else {
        var note = document.createElement("span");
        note.classList.add("muted");
        note.textContent = "내 담당에 없는 번호입니다";
        item.appendChild(note);
      }
      found.appendChild(item);
    });
  }
})();
