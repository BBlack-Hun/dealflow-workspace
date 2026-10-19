// 선호 투자분야 — **분야 기준 목록에서 여러 개 골라** 적는다(개선 과제 #2).
//
// 이 칸은 자유 글이었다. 그래서 같은 분야가 `AI` · `인공지능` · `AI 관련 기업` 으로
// 갈렸고, 그룹 표시(`B`)나 통화 메모까지 함께 들어갔다. 이제 고를 거리는 관리자가
// 정한 **분야 기준 목록** 하나다(`services/taxonomy.picker_tree` → 화면의
// `#sector-taxonomy`). 대분류를 고르면 그 분야 전체, 소분류를 고르면 그것만이다.
//
// **목록 밖의 옛 값은 지우지 않는다.** 재분류(#30 — 10/18 에 한 번 반영하고 기능은
// 뺐다)가 못 맞춘 조각이나 그 뒤 들어온 줄에는 자유 글이 남아 있다. 고르는 창을
// 여는 것만으로 그 글이 사라지면 안 되므로 `목록 밖 값` 으로 체크된 채 보여 주고,
// 사람이 끄면 그때 빠진다.
//
// 쓰는 자리 둘이 이 부품 하나를 쓴다.
//   · 표의 칸(`data-type="sectors"`) — `inline_edit.js` 의 떠서 고치는 창 안에
//   · 수정창의 칸(`input[data-sector-picker]`) — 칸 아래에 펼치는 목록으로
// 두 벌로 만들면 "목록 밖 값을 어떻게 다루나" 가 갈린다.
(function (global) {
  "use strict";

  var SKIP = /[\s·ㆍ•‧・∙]+/g;

  // 견주는 꼴 — 서버의 `taxonomy.norm` 과 같은 자(가운뎃점·공백·대소문자를 안 본다).
  function norm(text) {
    return String(text == null ? "" : text).replace(SKIP, "").toLowerCase();
  }

  function split(value) {
    return String(value == null ? "" : value).split(",")
      .map(function (v) { return v.trim(); })
      .filter(function (v) { return v.length > 0; });
  }

  var cached = null;
  function tree() {
    if (cached) return cached;
    var holder = document.getElementById("sector-taxonomy");
    try {
      cached = JSON.parse((holder && holder.getAttribute("data-tree")) || "[]");
    } catch (err) {
      cached = [];
    }
    return cached;
  }

  // 목록의 이름 → 그 이름(같은 꼴이면 목록의 철자로 돌린다).
  function names() {
    var out = {};
    tree().forEach(function (major) {
      out[norm(major.name)] = major.name;
      (major.minors || []).forEach(function (minor) { out[norm(minor)] = minor; });
    });
    return out;
  }

  // `container` 를 고르는 목록으로 채운다. 고를 때마다 `onChange(값)` 을 부른다.
  // 돌려주는 것은 지금 값을 읽는 함수다.
  function build(container, value, onChange) {
    var known = names();
    // 지금 고른 것 — **적힌 차례 그대로**. 목록의 말은 목록의 철자로 돌린다.
    var chosen = [];
    split(value).forEach(function (v) {
      var name = known[norm(v)] || v;
      if (chosen.indexOf(name) === -1) chosen.push(name);
    });
    var outside = chosen.filter(function (v) { return !known[norm(v)]; });

    container.innerHTML = "";
    container.classList.add("sector-pick");

    function current() { return chosen.join(", "); }

    function box(name, label, extraClass) {
      var wrap = document.createElement("label");
      wrap.className = "sector-pick-item" + (extraClass ? " " + extraClass : "");
      var input = document.createElement("input");
      input.type = "checkbox";
      input.value = name;
      input.checked = chosen.indexOf(name) !== -1;
      input.addEventListener("change", function () {
        var at = chosen.indexOf(name);
        if (input.checked && at === -1) chosen.push(name);
        if (!input.checked && at !== -1) chosen.splice(at, 1);
        if (onChange) onChange(current());
      });
      wrap.appendChild(input);
      wrap.appendChild(document.createTextNode(" " + label));
      return wrap;
    }

    if (outside.length) {
      var old = document.createElement("div");
      old.className = "sector-pick-group outside";
      var head = document.createElement("div");
      head.className = "sector-pick-head";
      head.textContent = "목록 밖 값 — 끄면 빠집니다";
      old.appendChild(head);
      outside.forEach(function (v) { old.appendChild(box(v, v, "")); });
      container.appendChild(old);
    }

    tree().forEach(function (major) {
      var group = document.createElement("div");
      group.className = "sector-pick-group";
      group.appendChild(box(major.name, major.name + " (분야 전체)", "major"));
      (major.minors || []).forEach(function (minor) {
        group.appendChild(box(minor, minor, ""));
      });
      container.appendChild(group);
    });

    if (!tree().length) {
      var none = document.createElement("p");
      none.className = "hint";
      none.textContent = "분야 기준 목록이 비어 있습니다 — 관리자 메뉴에서 먼저 정합니다.";
      container.appendChild(none);
    }
    return current;
  }

  // 펼쳐 둔 목록을 접는 손잡이들. 수정창이 다른 줄로 바뀌면 접는다 —
  // 펼친 채로 두면 앞 사람의 체크가 남아 보인다(`contacts.js` 의 `fillForm`).
  var opened = [];
  function closeAll() { opened.forEach(function (close) { close(); }); }

  // 수정창의 칸 — 글자 칸은 **읽기만** 하고, 옆 [고르기] 로 목록을 펼친다.
  function attachInput(input) {
    if (!input || input.getAttribute("data-sector-ready")) return;
    input.setAttribute("data-sector-ready", "1");
    input.readOnly = true;
    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "linkbtn sector-pick-toggle";
    toggle.textContent = "목록에서 고르기";
    var panel = document.createElement("div");
    panel.hidden = true;
    input.insertAdjacentElement("afterend", toggle);
    toggle.insertAdjacentElement("afterend", panel);

    function open() {
      // 창을 열 때마다 **지금 칸의 값**으로 다시 세운다 — 수정창은 줄을 바꿔
      // 열 때 값만 갈아 끼운다(`contacts.js` 의 `fillForm`).
      build(panel, input.value, function (value) {
        input.value = value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
      panel.hidden = false;
      toggle.textContent = "목록 닫기";
    }
    function close() {
      panel.hidden = true;
      toggle.textContent = "목록에서 고르기";
    }
    toggle.addEventListener("click", function () {
      if (panel.hidden) open(); else close();
    });
    opened.push(close);
    input.addEventListener("click", function () { if (panel.hidden) open(); });
  }

  function init() {
    document.querySelectorAll("input[data-sector-picker]").forEach(attachInput);
  }

  global.DealflowSectorPicker = {
    build: build, attachInput: attachInput, split: split, norm: norm,
    tree: tree, init: init, closeAll: closeAll,
    // 검사가 목록을 갈아 끼울 때 쓴다.
    reset: function () { cached = null; }
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
