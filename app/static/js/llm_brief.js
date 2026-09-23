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
        var data = null;
        try { data = JSON.parse(text); } catch (e) { data = null; }
        // **시킬 말 + 자료를 한 덩어리로.** LLM 창에 그대로 붙여 넣으면 되게.
        //
        // 시킬 말은 여기서 짓지 않는다 — 서버가 자료에 실어 보낸 `prompt` 를
        // 그대로 앞에 붙인다. 화면이 제 문장을 들고 있으면 서버 쪽 문장과
        // 반드시 갈린다(이 저장소가 반복해 당한 사고다).
        //
        // **자료 부분은 서버가 준 글자 그대로다.** [화면에서 보기] 는 내보내기
        // 전에 사람이 눈으로 훑는 자리라, 여기 보이는 것과 실제로 나가는 것이
        // 다르면 그 확인이 거짓말이 된다.
        out.textContent = compose(data, text);
        out.hidden = false;
        copy.hidden = false;
        // 몇 건인지 먼저 말해 준다. 자료가 비어 있는데 그대로 붙여 넣고
        // "왜 아무것도 안 골라 주지" 하는 일이 없게.
        state.textContent = data
          ? ("투자사 " + data.investors.length + "곳 · 기업 "
             + data.companies.length + "곳 · " + data.scope)
          : "";
      })
      .catch(function () { state.textContent = "자료를 꺼내지 못했습니다."; });
  });

  // 시킬 말이 없으면(옛 서버) 자료만 담는다 — 붙여 넣을 것이 아예 없는 것보다
  // 낫고, 그때는 사람이 직접 시킬 말을 적으면 된다.
  function compose(data, text) {
    return (data && data.prompt ? data.prompt + "\n\n" : "") + text;
  }

  copy.addEventListener("click", function () {
    // 화면에 보이는 그것을 그대로 복사한다 — 시킬 말과 자료가 함께 들어간다.
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

  // 답은 **갈래마다 한 줄씩** 온다(서버의 시킬 말이 그 모양을 시킨다). 그래서
  // 여기도 갈래로 그린다 — 한 덩어리로 그리면 사람이 답을 다시 갈래로 갈라야
  // 하고, 갈래가 아홉이면 아홉 번이다.
  //
  // **갈래를 여기서 읽지 않는다.** 어느 번호가 어느 갈래의 몫인지는 서버가
  // 갈라서 보낸다(`services/llm_brief.parse_group_refs`) — 화면이 따로 읽으면
  // 앱이 아는 갈래 이름과 갈리고, 갈린 이름으로는 발송으로 옮길 수가 없다.
  function draw(data) {
    var groups = data.groups || [];
    var rows = data.investors.concat(data.companies);
    if (!rows.length) {
      // 번호가 하나도 없으면 **왜 없는지** 말해 준다. 맨숫자는 일부러 안 읽기
      // 때문에("30억" 을 번호로 읽으면 엉뚱한 사람이 뜬다), 그것을 모르면
      // 붙여 넣기가 잘못된 줄 안다.
      foundState.textContent = "번호를 찾지 못했습니다 — V-31 · C-7 처럼 적혀 있어야 합니다.";
      return;
    }
    var missing = rows.filter(function (r) { return !r.found; }).length;
    // 못 찾은 번호가 있으면 **왜 없는지**까지 말한다. 자료에 담기는 범위가
    // 좁아진 뒤로(내 담당 + 카톡방 확인됨), 못 찾는 번호는 대개 LLM 이 자료에
    // 없는 번호를 지어낸 것이다 — "내 담당이 아니다" 만으로는 그것을 모른다.
    foundState.textContent = rows.length + "개 번호"
      + (groups.length ? " · 갈래 " + groups.length + "개" : "")
      + (missing ? " · " + missing + "개는 이 자료에 없는 번호입니다" : "");

    // 갈래에 붙은 번호는 갈래 아래에만 그린다 — 아래 '갈래가 안 적힌' 자리에
    // 또 나오면 같은 기업이 두 번 뽑힌 것처럼 보인다.
    var placed = {};
    groups.forEach(function (group) {
      var head = document.createElement("div");
      head.classList.add("llm-found-group");
      head.textContent = group.name + " ";
      var count = document.createElement("span");
      count.classList.add("count");
      count.textContent = "· " + group.companies.length + "곳";
      head.appendChild(count);
      found.appendChild(head);
      if (!group.companies.length) {
        // 한 곳도 못 고른 갈래도 **줄을 남긴다** — 답에 그 갈래가 있었다는
        // 사실이 지워지면, 빠뜨린 것인지 맞는 곳이 없던 것인지 알 수 없다.
        var none = document.createElement("div");
        none.classList.add("llm-found-none");
        none.textContent = "고른 곳이 없습니다";
        found.appendChild(none);
        return;
      }
      group.companies.forEach(function (row) {
        placed[row.id] = true;
        found.appendChild(rowNode(row));
      });
    });

    // 갈래에 안 붙은 번호 — 투자사 번호와, 갈래 머리보다 앞에 적힌 기업 번호다.
    // **버리지 않는다**: 조용히 빠지면 다섯을 넣고 셋만 뜬 것을 눈치채지 못한다.
    var rest = data.investors.concat(data.companies.filter(function (row) {
      return !placed[row.id];
    }));
    if (rest.length && groups.length) {
      var head = document.createElement("div");
      head.classList.add("llm-found-group");
      head.textContent = "갈래가 안 적힌 번호";
      found.appendChild(head);
    }
    rest.forEach(function (row) { found.appendChild(rowNode(row)); });
  }

  function rowNode(row) {
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
      note.textContent = "이 자료에 담기지 않은 번호입니다 — "
        + "내 담당이 아니거나 카톡방이 확인되지 않은 곳입니다";
      item.appendChild(note);
    }
    return item;
  }
})();
