// 공통 표 정렬 — **머리글을 눌러서** 오름/내림.
//
// 사용법 — 표에 data 속성만 붙이면 된다(화면마다 코드를 새로 쓰지 않게):
//   <th data-sort="due">일시</th>
//   <tr data-s-due="2026-08-07" data-s-status="0"> ... </tr>
//   <a href="/todo?week=…" data-sort-keep>← 지난 주</a>
//   DealflowSort.init({ table: "#task-table" });
//
// `data-f-*`(필터)와 같은 결로 `data-s-*` 에 **정렬용 값**을 적는다. 화면에 뜬
// 글자를 쓰지 않는 이유가 두 가지다.
//   · `8/7(금)` 처럼 사람이 읽는 모양으로 그려진 칸은 글자로 세우면 8/7 이
//     12/1 보다 뒤에 온다. 값은 `2026-08-07` 로 적어 두면 그냥 맞는다.
//   · **상태는 글자순이 아니다.** `진행중 → 예정 → 완료` 라는 일하는 차례가
//     따로 있어서, 서버가 그 차례(`STATUS_ORDER`)를 숫자로 적어 준다. 화면이
//     제 손으로 다시 매기면 두 벌이 되어 한쪽만 고쳐지는 날이 온다.
//
// ── 세 번 누르면 원래대로 ─────────────────────────────────────────────────
// 같은 머리글을 누를 때마다 **오름 → 내림 → 끔** 으로 돈다. 끄면 서버가 그려 준
// 차례로 돌아간다 — 주간 업무는 그 차례가 `상태 → 일시 → position → id` 라
// (`services/weekly.py`), 정렬을 켜기 전 화면과 정확히 같아야 한다. 그래서 처음
// 줄 차례를 통째로 기억해 두었다가 그대로 되돌린다.
//
// ── 주소에 남긴다 ─────────────────────────────────────────────────────────
// `?sort=due` · `?sort=-due`(내림). 필터가 이미 쓰는 계약이고(`filters.js`),
// 그래야 새로고침해도 남는다. 주간 업무는 [← 지난 주] 가 **링크**라 한 번
// 새로 그려지는데, 그때도 보던 차례가 남아야 한다 — `data-sort-keep` 이 붙은
// 링크에는 지금 정렬을 실어 준다. 남의 쿼리(`?week=`)는 그대로 둔다.
//
// 서버가 아니라 브라우저에서 세우는 이유: 한 주가 60줄 안팎이라 왕복 없이 즉시
// 반응하는 편이 낫다. **1,000행을 넘기면 서버 정렬로 전환**할 것(그때는 같은
// 쿼리스트링을 서버가 해석하면 되므로 URL 계약은 그대로 쓸 수 있다) —
// `filters.js` 가 같은 기준을 남겨 두었다.
(function (global) {
  "use strict";

  var ASC = "asc";
  var DESC = "desc";
  // 세워져 있지 않은 칸에도 **꼬리표를 남긴다**(`↕`). 눌러야 세워지는 칸인지
  // 아닌지가 안 보이면, 세 칸만 정렬되는 표에서 사람이 아무 머리글이나 눌러
  // 보게 된다 — 필터가 `▾` 를 늘 달아 두는 것과 같은 이유다. 흐리게 그려
  // 세워져 있는 칸의 `▲`/`▼` 와 구별한다(`.sort-btn::after`).
  var MARK = { asc: "▲", desc: "▼", off: "↕" };

  // "-due" → { key: "due", dir: "desc" } · "due" → { key: "due", dir: "asc" }
  function parseSort(raw) {
    var value = String(raw || "").trim();
    if (!value) return null;
    var desc = value.charAt(0) === "-";
    var key = desc ? value.slice(1) : value;
    return key ? { key: key, dir: desc ? DESC : ASC } : null;
  }

  function formatSort(state) {
    if (!state) return "";
    return (state.dir === DESC ? "-" : "") + state.key;
  }

  // 눌린 칸의 다음 차례. **오름 → 내림 → 끔.** 다른 칸을 누르면 오름부터.
  function nextState(state, key) {
    if (!state || state.key !== key) return { key: key, dir: ASC };
    if (state.dir === ASC) return { key: key, dir: DESC };
    return null;
  }

  function isEmpty(v) { return v === undefined || v === null || v === ""; }

  // 값 둘 중 어느 것이 앞인가. **빈 값은 여기서 다루지 않는다** — 방향에 따라
  // 뒤집히면 안 되는 규칙이라 `order` 가 따로 본다(바로 아래).
  //
  // 숫자로 읽히는 값은 숫자로 센다. 상태 차례(`0`·`1`·`2`)와 자릿수가 다른
  // 숫자 칸이 글자순으로 서면 `10` 이 `9` 보다 앞에 온다.
  function compare(a, b) {
    var na = Number(a);
    var nb = Number(b);
    if (!isNaN(na) && !isNaN(nb)) return na < nb ? -1 : (na > nb ? 1 : 0);
    return String(a).localeCompare(String(b), "ko");
  }

  // rows: [{ values: {key: 값}, at: 처음 차례 }] → 정렬된 차례(원본 색인 배열)
  function order(rows, state) {
    var out = rows.map(function (row, i) { return i; });
    if (!state) return out;                  // 끄면 서버가 그려 준 차례 그대로
    var sign = state.dir === DESC ? -1 : 1;
    out.sort(function (x, y) {
      var a = rows[x].values[state.key];
      var b = rows[y].values[state.key];
      // **빈 값은 방향과 상관없이 늘 끝으로** 간다. 방향을 따르게 두면 일시가
      // 비어 있는 줄이 내림차순에서 맨 위로 올라와, 아직 날짜를 안 정한 일이
      // 제일 급한 일처럼 보인다(`filters.js` 도 `(비어 있음)` 을 끝에 둔다).
      // 그래서 뒤집는 곱셈 **밖**에 둔다 — 안에 두면 같이 뒤집힌다.
      if (isEmpty(a) || isEmpty(b)) {
        if (isEmpty(a) && isEmpty(b)) return x - y;
        return isEmpty(a) ? 1 : -1;
      }
      var by = compare(a, b) * sign;
      // 값이 같으면 **처음 차례를 지킨다.** 상태로 세워도 그 안에서는 서버가
      // 매긴 일시·position 차례가 그대로 남아야 한다.
      return by ? by : x - y;
    });
    return out;
  }

  // ── DOM 연결 ──────────────────────────────────────────────────────────────

  function init(options) {
    var table = document.querySelector(options.table);
    if (!table) return null;

    var defs = [];
    Array.prototype.forEach.call(table.querySelectorAll("th[data-sort]"), function (th) {
      var key = (th.getAttribute("data-sort") || "").trim();
      if (key) defs.push({ key: key, label: (th.textContent || "").trim(), th: th });
    });
    if (!defs.length) return null;

    var keys = defs.map(function (d) { return d.key; });
    var body = table.querySelector("tbody");
    if (!body) return null;
    // 값이 적힌 줄만 세운다. `업무가 없습니다` 같은 안내 줄은 `data-s-*` 가
    // 없어서 여기 안 들어오고, 그래서 자리도 안 바뀐다.
    var rows = Array.prototype.slice.call(
      body.querySelectorAll("tr[data-s-" + keys[0] + "]"));
    if (!rows.length) return null;

    var data = rows.map(function (tr, i) {
      var values = {};
      keys.forEach(function (k) { values[k] = tr.getAttribute("data-s-" + k); });
      return { values: values, at: i };
    });

    var param = options.param || "sort";
    var state = null;
    if (global.location) {
      var q = String(global.location.search || "").replace(/^\?/, "");
      q.split("&").forEach(function (pair) {
        var at = pair.indexOf("=");
        if (at < 0) return;
        if (decodeURIComponent(pair.slice(0, at)) !== param) return;
        state = parseSort(decodeURIComponent(pair.slice(at + 1).replace(/\+/g, " ")));
      });
    }
    if (state && keys.indexOf(state.key) < 0) state = null;   // 모르는 칸이면 무시

    // 세우는 줄들이 서 있던 블록 **바로 뒤**에 있던 줄. 늘 그 앞에 꽂아 넣으면,
    // 값이 없어 세우지 않는 줄(안내 줄·합계 줄)이 제자리에 그대로 남는다.
    // 끝에 붙이기만 하면 그런 줄이 통째로 표 맨 위로 밀려 올라간다.
    var tail = rows[rows.length - 1].nextSibling;

    function apply() {
      order(data, state).forEach(function (at) {
        // 이미 이 tbody 안에 있는 줄이라 **옮겨진다**(복사가 아니다).
        // 차례대로 한 바퀴 돌면 그 차례가 된다.
        body.insertBefore(rows[at], tail);
      });
      defs.forEach(function (def) {
        var dir = state && state.key === def.key ? state.dir : null;
        // 지금 무엇으로 세워져 있는지 화면에도, 읽어 주는 기계에도 보여야 한다.
        def.th.setAttribute("aria-sort",
          dir === ASC ? "ascending" : dir === DESC ? "descending" : "none");
        def.btn.classList.toggle("on", !!dir);
        // 꼬리표는 **글자가 아니라 `::after`** 로 그린다. 이름과 꼬리표의
        // 흐리기가 달라야 하고, 붙여 두는 공백도 CSS 가 줄바꿈 없는 것으로
        // 넣는다 — 보통 공백이면 폭이 조금만 모자랄 때 `일시` / `▲` 로 갈린다.
        def.btn.setAttribute("data-mark", MARK[dir || "off"]);
        def.btn.setAttribute("title", def.label + (
          !dir ? " 오름차순으로 정렬" :
          dir === ASC ? " 내림차순으로 정렬" : " 정렬 끄기"));
      });
      syncUrl();
      keepLinks();
      if (typeof options.onChange === "function") options.onChange(state);
    }

    // 정렬과 **무관한 쿼리는 그대로 둔다.** 주간 업무는 `?week=` 가 곧 보고 있는
    // 주라, 버리면 머리글 한 번 누르는 것이 이번 주로 튀는 일이 된다.
    function keptQuery() {
      var q = String((global.location && global.location.search) || "").replace(/^\?/, "");
      return q.split("&").filter(function (pair) {
        if (!pair) return false;
        var at = pair.indexOf("=");
        return decodeURIComponent(at < 0 ? pair : pair.slice(0, at)) !== param;
      });
    }

    function query() {
      var parts = keptQuery();
      var mine = formatSort(state);
      if (mine) parts.push(encodeURIComponent(param) + "=" + encodeURIComponent(mine));
      return parts.length ? "?" + parts.join("&") : "";
    }

    function syncUrl() {
      if (!global.history || !global.history.replaceState) return;
      global.history.replaceState(null, "", global.location.pathname + query());
    }

    // 주를 옮기는 링크에 지금 정렬을 실어 준다. 링크는 한 번 새로 그려지는
    // 길이라, 안 실어 주면 [다음 주 →] 한 번에 세워 둔 차례가 풀린다.
    // **어느 링크인지는 화면이 정한다**(`data-sort-keep`) — 같은 주소로 가는
    // 링크를 코드가 알아서 고르기 시작하면, 정렬을 실으면 안 되는 링크가
    // 생겼을 때 그것을 막을 자리가 없다.
    function keepLinks() {
      Array.prototype.forEach.call(
        document.querySelectorAll("a[data-sort-keep]"), function (a) {
          var href = a.getAttribute("data-sort-href");
          if (href === null) {
            href = a.getAttribute("href") || "";
            a.setAttribute("data-sort-href", href);   // 정렬 없는 원래 주소
          }
          var mine = formatSort(state);
          if (!mine) { a.setAttribute("href", href); return; }
          a.setAttribute("href", href + (href.indexOf("?") < 0 ? "?" : "&") +
            encodeURIComponent(param) + "=" + encodeURIComponent(mine));
        });
    }

    // 머리글 이름 자리를 **단추가 대신한다.** 이름 옆에 단추를 또 두면 같은
    // 말이 두 번 나오고, 좁은 칸에서 이름이 접힌다(`filters.js` 의 `filter-only`
    // 와 같은 판단). 단추라 키보드로도 닿는다 — Tab 으로 옮겨 Enter·Space.
    defs.forEach(function (def) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sort-btn";
      btn.textContent = def.label;
      btn.onclick = function () {
        state = nextState(state, def.key);
        apply();
      };
      def.btn = btn;
      def.th.classList.add("sort-th");
      // 이름 글자만 지운다 — 칸에 다른 것이 얹혀 있으면 그것은 남긴다.
      Array.prototype.slice.call(def.th.childNodes).forEach(function (n) {
        if (n.nodeType === 3) n.textContent = "";
      });
      def.th.appendChild(btn);
    });

    apply();
    return { apply: apply, getState: function () { return state; } };
  }

  var API = {
    parseSort: parseSort,
    formatSort: formatSort,
    nextState: nextState,
    compare: compare,
    order: order,
    init: init
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;  // node 테스트용
  if (global) global.DealflowSort = API;
})(typeof window !== "undefined" ? window : null);
