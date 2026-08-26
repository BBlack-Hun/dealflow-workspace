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

    function syncUrl() {
      if (!global.history || !global.history.replaceState) return;
      var qs = buildQuery(state);
      global.history.replaceState(null, "", global.location.pathname + qs);
    }

    function renderButtons() {
      defs.forEach(function (def) {
        if (!def.btn) return;
        var active = (state[def.key] || []).length;
        def.btn.classList.toggle("on", !!active);
        def.btn.textContent = def.label + (active ? " (" + active + ")" : "") + " ▾";
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
      openPanel = panel;
    }

    // 한 칸에 필터가 하나뿐이면 **그 단추가 컬럼 이름 자리를 대신한다.**
    // 예전에는 `계약여부` 라는 글자 밑에 `계약여부 ▾` 단추가 또 있어서
    // 같은 말이 두 번 나왔다 — 칸은 좁은데 자리만 두 배로 먹었다.
    // 필터가 둘인 칸(투자분야 / 라운드사이즈)은 이름을 남긴다.
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
      btn.textContent = def.label + " ▾";
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
    // 칸을 고치면 그 값도 필터에 나와야 한다. `rowData` 는 처음 한 번만
    // 읽으므로, 고친 뒤 다시 읽어 주지 않으면 **값은 있는데 필터에는 없는**
    // 상태가 된다 — 관심도를 채워 넣어도 필터가 비어 있었다.
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
