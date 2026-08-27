// 공통 컬럼 필터 드롭다운 (FEATURE_SPEC §8, 자동화 #3)
//
// 사용법 — 표에 data 속성만 붙이면 된다(화면마다 코드를 새로 쓰지 않게):
//   <th data-filters="stage:투자 단계|sector:섹터"> ... </th>
//   <tr data-f-stage="Seed|SeriesA" data-f-sector="AI"> ... </tr>
//   <div data-filter-chips></div>  <div data-filter-empty hidden>...</div>
//   DealflowFilters.init({ table: "#contacts-table" });
//
// 규칙: 컬럼 간 AND, 같은 컬럼 안에서는 OR. 상태는 URL 쿼리에 남겨 새로고침·공유해도
// 유지된다. 다중 값 셀(섹터 태그 등)은 "|" 로 나눠 태그 단위로 필터된다.
//
// 서버가 아니라 브라우저에서 거르는 이유: 대상이 수백 행(담당자 126명 규모)이라
// 왕복 없이 즉시 반응하는 편이 낫다. **1,000행을 넘기면 서버 필터로 전환**할 것
// (그때는 같은 쿼리스트링을 서버가 해석하면 되므로 URL 계약은 그대로 쓸 수 있다).
(function (global) {
  "use strict";

  var EMPTY = "(비어 있음)";

  // ── 머리글 단추 글자 ───────────────────────────────────────────────────
  // 꼬리표(`(1)` 과 `▾`) 앞은 **줄바꿈 없는 공백(U+00A0)** 이다.
  //
  // 컬럼 이름은 접혀도 된다 — 원본 시트 이름을 그대로 쓰는 표라
  // `TIPS 운영사 투자금 1-10억 …` 처럼 두 줄이 필요한 이름이 실제로 있다.
  // 그래서 머리글에 `white-space: nowrap` 을 거는 방법은 못 쓴다 — 걸면 그런
  // 이름이 한 줄로 쭉 늘어나 컬럼이 벌어진다(예전에 그렇게 해서 되돌렸다).
  //
  // 접히면 안 되는 것은 **꼬리표뿐**이다. 보통 공백이면 거기가 줄바꿈 자리가
  // 되어 `담당자` / `(1) ▾` 로 갈라졌고, 폭이 조금만 모자라면 이름과 `▾` 가
  // 갈라졌다. 줄바꿈 없는 공백으로 바꾸면 꼬리표는 앞 낱말에 붙어 다니고,
  // 이름 안의 진짜 띄어쓰기는 그대로 남아 긴 이름은 여전히 접힌다.
  //
  // 낱말 **안에서** 끊기는 것은 CSS 가 막는다(`.filter-btn { word-break: keep-all }`)
  // — 한글은 기본값이 글자 사이에서도 끊겨서 `담당자` 가 `담당` / `자` 가 된다.
  //
  // 눈에 안 보이는 글자라 **이스케이프로** 적는다. 그냥 붙여 넣으면 나중에
  // 보통 공백으로 되돌아가도 아무도 알아채지 못한다.
  var NBSP = "\u00a0";

  function buttonLabel(label, active) {
    return label + (active ? NBSP + "(" + active + ")" : "") + NBSP + "▾";
  }

  function splitValues(raw) {
    if (raw === undefined || raw === null) return [EMPTY];
    var parts = String(raw).split("|").map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
    return parts.length ? parts : [EMPTY];
  }

  // "?stage=Seed,SeriesA&status=active" → { stage: ["Seed","SeriesA"], status: ["active"] }
  function parseQuery(search, keys) {
    var state = {};
    var q = String(search || "").replace(/^\?/, "");
    if (!q) return state;
    q.split("&").forEach(function (pair) {
      if (!pair) return;
      var i = pair.indexOf("=");
      var key = decodeURIComponent(i < 0 ? pair : pair.slice(0, i));
      var raw = i < 0 ? "" : pair.slice(i + 1);
      if (keys && keys.indexOf(key) < 0) return;   // 필터와 무관한 쿼리는 건드리지 않는다
      var values = raw.split(",").map(function (v) {
        return decodeURIComponent(v.replace(/\+/g, " "));
      }).filter(function (v) { return v.length > 0; });
      if (values.length) state[key] = values;
    });
    return state;
  }

  function buildQuery(state) {
    var parts = [];
    Object.keys(state).sort().forEach(function (key) {
      var values = state[key] || [];
      if (!values.length) return;
      parts.push(encodeURIComponent(key) + "=" +
        values.map(encodeURIComponent).join(","));
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  // rowValues: { key: [값...] }  state: { key: [선택값...] }
  function matchRow(rowValues, state, skipKey) {
    return Object.keys(state).every(function (key) {
      if (key === skipKey) return true;
      var wanted = state[key] || [];
      if (!wanted.length) return true;
      var have = rowValues[key] || [EMPTY];
      return wanted.some(function (w) { return have.indexOf(w) >= 0; });
    });
  }

  // 다른 컬럼의 필터를 적용한 상태에서 이 컬럼의 고유값+건수를 센다.
  // (선택하면 몇 건이 남는지가 보여야 필터가 쓸모 있다)
  function facets(rows, key, state) {
    var counts = {};
    rows.forEach(function (rowValues) {
      if (state && !matchRow(rowValues, state, key)) return;
      splitUnique(rowValues[key]).forEach(function (v) {
        counts[v] = (counts[v] || 0) + 1;
      });
    });
    return Object.keys(counts).sort(compareValues).map(function (v) {
      return { value: v, count: counts[v] };
    });
  }

  function splitUnique(values) {
    var seen = {};
    return (values && values.length ? values : [EMPTY]).filter(function (v) {
      if (seen[v]) return false;
      seen[v] = true;
      return true;
    });
  }

  function compareValues(a, b) {
    if (a === EMPTY) return 1;      // "(비어 있음)" 은 항상 끝으로
    if (b === EMPTY) return -1;
    return a.localeCompare(b, "ko");
  }

  // ── DOM 연결 ──────────────────────────────────────────────────────────────

  function init(options) {
    var table = document.querySelector(options.table);
    if (!table) return null;
    var defs = [];
    Array.prototype.forEach.call(table.querySelectorAll("th[data-filters]"), function (th) {
      th.getAttribute("data-filters").split("|").forEach(function (spec) {
        var idx = spec.indexOf(":");
        if (idx < 0) return;
        defs.push({ key: spec.slice(0, idx).trim(), label: spec.slice(idx + 1).trim(), th: th });
      });
    });
    if (!defs.length) return null;

    var keys = defs.map(function (d) { return d.key; });
    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-f-" + keys[0] + "], tbody tr.data-row"));
    if (!rows.length) rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
    var rowData = rows.map(function (tr) {
      var values = {};
      keys.forEach(function (k) { values[k] = splitValues(tr.getAttribute("data-f-" + k)); });
      return values;
    });

    var chipBox = document.querySelector(options.chips || "[data-filter-chips]");
    var emptyBox = document.querySelector(options.empty || "[data-filter-empty]");
    var countBox = document.querySelector(options.count || "[data-filter-count]");
    var state = parseQuery(global.location ? global.location.search : "", keys);
    var openPanel = null;

    function apply() {
      var shown = 0;
      rows.forEach(function (tr, i) {
        // 컬럼 필터 + (있으면) 화면이 준 추가 조건. 검색창처럼 컬럼으로 표현할 수
        // 없는 조건을 여기서 AND 로 묶는다 — 둘이 서로 tr.hidden 을 덮어쓰면
        // 검색과 필터가 번갈아 서로를 지운다.
        var ok = matchRow(rowData[i], state) &&
          (typeof options.extra !== "function" || options.extra(tr, i));
        tr.hidden = !ok;
        if (ok) shown += 1;
      });
      if (emptyBox) emptyBox.hidden = shown !== 0;
      if (countBox) countBox.textContent = shown + " / " + rows.length + (options.unit || "명");
      renderChips();
      renderButtons();
      syncUrl();
      if (typeof options.onChange === "function") options.onChange(state, shown);
    }

    // 필터와 **무관한 쿼리는 그대로 둔다.** 읽을 때는 이미 그러고 있는데
    // (`parseQuery` 가 모르는 키를 건드리지 않는다) 쓸 때는 pathname 만 남기고
    // 다 버리고 있었다 — `/sourcing?tab=M&A 찾는 투자사` 를 열면 아무것도 안
    // 골랐는데도 주소가 곧바로 `/sourcing` 이 되어, 새로고침하면 다른 갈래가
    // 열렸다. 투자컨설턴트 현황은 `?sheet=` 가 곧 명단이라 더 나쁘다.
    function keptQuery() {
      var q = String((global.location && global.location.search) || "").replace(/^\?/, "");
      return q.split("&").filter(function (pair) {
        if (!pair) return false;
        var i = pair.indexOf("=");
        return keys.indexOf(decodeURIComponent(i < 0 ? pair : pair.slice(0, i))) < 0;
      });
    }

    function syncUrl() {
      if (!global.history || !global.history.replaceState) return;
      var parts = keptQuery();
      var mine = buildQuery(state).replace(/^\?/, "");
      if (mine) parts.push(mine);
      global.history.replaceState(null, "", global.location.pathname +
        (parts.length ? "?" + parts.join("&") : ""));
    }

    function renderButtons() {
      defs.forEach(function (def) {
        if (!def.btn) return;
        var active = (state[def.key] || []).length;
        def.btn.classList.toggle("on", !!active);
        def.btn.textContent = buttonLabel(def.label, active);
      });
    }

    function renderChips() {
      if (!chipBox) return;
      chipBox.innerHTML = "";
      var any = false;
      defs.forEach(function (def) {
        (state[def.key] || []).forEach(function (value) {
          any = true;
          var chip = document.createElement("button");
          chip.type = "button";
          chip.className = "filter-chip";
          chip.textContent = def.label + ": " + value + " ✕";
          chip.title = "이 조건 해제";
          chip.onclick = function () { toggle(def.key, value, false); };
          chipBox.appendChild(chip);
        });
      });
      if (any) {
        var reset = document.createElement("button");
        reset.type = "button";
        reset.className = "filter-chip reset";
        reset.textContent = "필터 초기화";
        reset.onclick = function () { state = {}; apply(); };
        chipBox.appendChild(reset);
      }
    }

    function toggle(key, value, on) {
      var list = state[key] ? state[key].slice() : [];
      var at = list.indexOf(value);
      if (on && at < 0) list.push(value);
      if (!on && at >= 0) list.splice(at, 1);
      if (list.length) state[key] = list; else delete state[key];
      apply();
    }

    function closePanel() {
      if (openPanel && openPanel.parentNode) openPanel.parentNode.removeChild(openPanel);
      openPanel = null;
    }

    function openFor(def) {
      closePanel();
      var panel = document.createElement("div");
      panel.className = "filter-panel";
      panel.onclick = function (e) { e.stopPropagation(); };

      var options = facets(rowData, def.key, state);
      var head = document.createElement("div");
      head.className = "filter-panel-head";
      head.innerHTML = "<b>" + escapeHtml(def.label) + "</b>";
      var all = document.createElement("button");
      all.type = "button"; all.className = "linkbtn"; all.textContent = "모두 선택";
      all.onclick = function () {
        state[def.key] = options.map(function (o) { return o.value; });
        apply(); openFor(def);
      };
      var none = document.createElement("button");
      none.type = "button"; none.className = "linkbtn"; none.textContent = "해제";
      none.onclick = function () { delete state[def.key]; apply(); openFor(def); };
      head.appendChild(all); head.appendChild(none);
      panel.appendChild(head);

      var list = document.createElement("div");
      list.className = "filter-options";
      if (options.length > 10) {
        var search = document.createElement("input");
        search.type = "text";
        search.className = "filter-search";
        search.placeholder = "값 검색";
        search.oninput = function () {
          var q = search.value.trim().toLowerCase();
          Array.prototype.forEach.call(list.children, function (el) {
            el.hidden = q && el.textContent.toLowerCase().indexOf(q) < 0;
          });
        };
        panel.appendChild(search);
      }
      options.forEach(function (opt) {
        var label = document.createElement("label");
        label.className = "filter-option";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = (state[def.key] || []).indexOf(opt.value) >= 0;
        cb.onchange = function () { toggle(def.key, opt.value, cb.checked); };
        label.appendChild(cb);
        label.appendChild(document.createTextNode(" " + opt.value + " (" + opt.count + ")"));
        list.appendChild(label);
      });
      if (!options.length) {
        var none2 = document.createElement("p");
        none2.className = "hint";
        none2.textContent = "표시할 값이 없습니다";
        list.appendChild(none2);
      }
      panel.appendChild(list);
      panel.setAttribute("data-key", def.key);   // 같은 버튼을 다시 누르면 닫히도록
      def.th.appendChild(panel);
      clampIntoView(panel);
      openPanel = panel;
    }

    // 필터 창은 누른 칸에 붙어서 뜬다. 표는 화면보다 넓어 가로로 밀리므로,
    // **오른쪽 칸일수록 창이 보이는 자리 밖으로 나간다** — 폰(390px)에서는
    // 목록의 오른쪽 절반이 잘려 무엇을 고르는지 안 보였다.
    // 칸에 붙여 두되, 삐져나온 만큼만 안쪽으로 끌어당긴다.
    function clampIntoView(panel) {
      var edge = 8;
      // 표가 가로로 밀리는 상자 안이면 그 상자가 보이는 범위다. 아니면 화면.
      var box = panel.parentNode;
      while (box && box !== document.body) {
        var ox = getComputedStyle(box).overflowX;
        if (ox === "auto" || ox === "scroll") break;
        box = box.parentNode;
      }
      var view = (box && box !== document.body)
        ? box.getBoundingClientRect()
        : { left: 0, right: document.documentElement.clientWidth };

      function shift(by) {
        panel.style.left = ((parseFloat(getComputedStyle(panel).left) || 0) + by) + "px";
      }
      var over = panel.getBoundingClientRect().right - (view.right - edge);
      if (over > 0) shift(-over);
      // 너무 당겨서 이번엔 왼쪽으로 나가면 안 된다(창이 보이는 자리보다 넓을 때).
      var under = (view.left + edge) - panel.getBoundingClientRect().left;
      if (under > 0) shift(under);
    }

    // 한 칸에 필터가 하나뿐이면 **그 단추가 컬럼 이름 자리를 대신한다.**
    // 예전에는 `계약여부` 라는 글자 밑에 `계약여부 ▾` 단추가 또 있어서
    // 같은 말이 두 번 나왔다 — 칸은 좁은데 자리만 두 배로 먹었다.
    // 필터가 둘인 칸(진행 단계 / 연결 상태)은 이름을 남긴다 — 단추만 남기면
    // 둘 중 어느 것이 그 칸의 이름인지 알 수 없다.
    defs.forEach(function (def) {
      def.solo = defs.filter(function (d) { return d.th === def.th; }).length === 1;
    });

    defs.forEach(function (def) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "filter-btn";
      if (def.solo) {
        def.th.classList.add("filter-only");
        // 이름 글자만 지운다 — `.th-filters` 와 `.th-note` 는 남겨야 한다.
        Array.prototype.slice.call(def.th.childNodes).forEach(function (n) {
          if (n.nodeType === 3) n.textContent = "";
        });
      }
      btn.textContent = buttonLabel(def.label, 0);
      btn.onclick = function (e) {
        e.stopPropagation();
        var wasOpen = openPanel && openPanel.parentNode === def.th &&
          openPanel.getAttribute("data-key") === def.key;
        closePanel();
        if (!wasOpen) openFor(def);
      };
      def.btn = btn;
      var host = def.th.querySelector(".th-filters") || def.th;
      host.appendChild(btn);
    });

    document.addEventListener("click", closePanel);

    // 빠른 필터 칩(프리셋) — 내부적으로는 같은 드롭다운 상태를 세팅할 뿐이다.
    Array.prototype.forEach.call(document.querySelectorAll("[data-preset]"), function (btn) {
      btn.addEventListener("click", function () {
        var preset = btn.getAttribute("data-preset");
        state = preset ? parseQuery("?" + preset, keys) : {};
        apply();
      });
    });

    apply();

    // 칸을 고치면 그 값도 필터에 나와야 한다 — **여기서 직접 듣는다.**
    // 화면마다 `inline-saved` 를 이어 주게 두었더니 딜 소싱만 빠져 있었고,
    // 빠진 화면은 값이 바뀌어도 필터 목록이 옛날 그대로였다(아무도 모른다).
    // 표를 읽는 쪽이 스스로 다시 읽는 편이 빠뜨릴 자리가 없다.
    //
    // 저장 직후가 아니라 **한 박자 뒤**에 읽는다. 같은 이벤트를 듣고 행을
    // 다듬는 화면이 있어서다(기업구분을 짧은 이름으로 되돌려 적는 등) —
    // 그 정리보다 먼저 읽으면 같은 값이 목록에 두 벌로 생긴다.
    table.addEventListener("inline-saved", function () {
      if (global && global.setTimeout) global.setTimeout(refresh, 0);
      else refresh();
    });

    // `rowData` 는 처음 한 번만 읽으므로, 고친 뒤 다시 읽어 주지 않으면
    // **값은 있는데 필터에는 없는** 상태가 된다 — 관심도를 채워 넣어도
    // 필터가 비어 있었다.
    function refresh() {
      rows.forEach(function (tr, i) {
        keys.forEach(function (k) {
          rowData[i][k] = splitValues(tr.getAttribute("data-f-" + k));
        });
      });
      apply();
    }

    return { apply: apply, refresh: refresh,
             getState: function () { return state; } };
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  var API = {
    EMPTY: EMPTY,
    splitValues: splitValues,
    parseQuery: parseQuery,
    buildQuery: buildQuery,
    matchRow: matchRow,
    facets: facets,
    init: init
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;  // node 테스트용
  if (global) global.DealflowFilters = API;
})(typeof window !== "undefined" ? window : null);
