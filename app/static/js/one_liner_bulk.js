/* [전체 자동조합] — 미리보기 → 줄마다 고르기 → 적용 → 되돌리기.
 *
 * 한 곳씩 눌러야 하던 자동 조합을 표 전체에 건다. 다만 이건 **빈 칸을 채우는
 * 일이 아니라 이미 적힌 문장을 갈아엎는 일**이다(운영과 같은 사본 344곳에서
 * 45곳만 빈 칸이고 181곳은 사람이 쓴 값을 덮는다). 그래서 누르면 바로 바뀌지
 * 않고 **먼저 다 보여준다.**
 *
 * 무엇이 바뀔지는 **서버가 정한다**(`/api/one-liner/bulk`). 여기서 조합 규칙을
 * 다시 구현하지 않는다 — 두 벌이 되면 "미리보기엔 A 인데 눌렀더니 B" 가 된다.
 * 적용도 id 만 보내고, 서버가 목록을 다시 만들어 그 안에 있는 것만 바꾼다.
 */
(function () {
  "use strict";

  var panel = document.getElementById("ol-bulk");
  if (!panel) return;                       // 관리자가 아니면 패널 자체가 없다

  var openBtn = document.getElementById("ol-bulk-btn");
  var closeBtn = document.getElementById("ol-bulk-close");
  var list = document.getElementById("ol-list");
  var summary = document.getElementById("ol-summary");
  var pickAll = document.getElementById("ol-pick-all");
  var countEl = document.getElementById("ol-count");
  var applyBtn = document.getElementById("ol-apply");
  var undoBtn = document.getElementById("ol-undo");
  var undoNote = document.getElementById("ol-undo-note");
  var loaded = false;

  function boxes() {
    return Array.prototype.slice.call(list.querySelectorAll(".ol-cb"));
  }
  function picked() {
    return boxes().filter(function (b) { return b.checked; });
  }
  function refresh() {
    var n = picked().length;
    countEl.textContent = n + "곳 선택";
    applyBtn.disabled = n === 0;
    var all = boxes().length;
    pickAll.checked = all > 0 && n === all;
  }

  /* 표의 그 칸을 그 자리에서 되칠한다. 새로고침을 시키면 방금 무엇이 바뀌었는지
   * 눈에서 사라지고, 스크롤 위치와 걸어 둔 필터도 함께 날아간다. */
  function paintRow(id, text) {
    var tr = document.querySelector('tr[data-id="' + id + '"]');
    if (!tr) return;
    var cell = tr.querySelector('[data-field="one_liner"]');
    if (!cell) return;
    cell.textContent = text;
    // 잘려 보이는 칸이라 전체 글자는 칸의 `title` 에 있다 — 같이 안 고치면
    // 마우스를 올렸을 때 **옛 문장**이 뜬다.
    var td = cell.closest("td");
    if (td) td.setAttribute("title", text);
  }

  /* 자식을 지운다. `innerHTML = ""` 한 줄로 끝내지 않는 것은, 다시 그릴 때
   * 줄이 쌓이는 고장을 검사가 볼 수 있어야 하기 때문이다(tests/js/_dom.js). */
  function clear(node) {
    while (node.childNodes.length) node.removeChild(node.childNodes[node.childNodes.length - 1]);
  }

  function line(row) {
    // 반 이름은 `className =` 이 아니라 `classList.add` 로 붙인다 —
    // 뒤에서 `muted` 를 하나 더 얹는 자리가 있어서, 두 방식을 섞으면 나중에
    // 붙인 것이 통째로 날아간다.
    var wrap = document.createElement("label");
    wrap.classList.add("ol-row");

    var cb = document.createElement("input");
    cb.setAttribute("type", "checkbox");
    cb.type = "checkbox";
    cb.classList.add("ol-cb");
    cb.value = String(row.id);

    var name = document.createElement("span");
    name.classList.add("ol-name");
    name.textContent = row.name;

    var now = document.createElement("span");
    now.classList.add("ol-now");
    now.classList.add("clamp2");
    // 빈 칸과 '글자가 있는데 안 보이는 것' 은 화면에서 달라야 한다.
    now.textContent = row.filled ? row.current : "(비어 있음)";
    if (!row.filled) now.classList.add("muted");
    // 두 줄로 잘라 놓았으니 전체 글자는 `title` 에 남긴다.
    now.setAttribute("title", row.current);

    var next = document.createElement("span");
    next.classList.add("ol-new");
    next.classList.add("clamp2");
    next.textContent = row.suggestion;
    next.setAttribute("title", row.suggestion);

    wrap.appendChild(cb);
    wrap.appendChild(name);
    wrap.appendChild(now);
    wrap.appendChild(next);
    return wrap;
  }

  function render(state) {
    var c = state.counts;
    clear(list);
    state.rows.forEach(function (r) { list.appendChild(line(r)); });
    // 왜 344곳인데 이만큼뿐인지 함께 적는다 — 숫자가 안 맞으면 빠뜨렸다고 읽는다.
    summary.textContent =
      "기업 " + c.total + "곳 중 바뀔 곳 " + c.changes + "곳" +
      " (사람이 쓴 값을 덮는 곳 " + c.filled + " · 빈 칸을 채우는 곳 " + c.empty + ")." +
      " 이미 조합값과 같은 곳 " + c.unchanged + " · 재료가 없어 만들 수 없는 곳 " +
      c.no_source + " 는 목록에 없습니다.";

    var u = state.undo || {};
    if (u.count) {
      undoBtn.hidden = false;
      undoNote.textContent = "직전 적용 " + u.count + "곳을 되돌릴 수 있습니다.";
    } else {
      undoBtn.hidden = true;
      undoNote.textContent = "";
    }
    pickAll.checked = false;
    refresh();
  }

  function load() {
    summary.textContent = "불러오는 중…";
    fetch("/api/one-liner/bulk")
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { summary.textContent = res.d.detail || "불러오지 못했습니다"; return; }
        loaded = true;
        render(res.d);
      })
      .catch(function () { summary.textContent = "불러오지 못했습니다"; });
  }

  openBtn.addEventListener("click", function () {
    panel.hidden = !panel.hidden;
    if (!panel.hidden && !loaded) load();
  });
  closeBtn.addEventListener("click", function () { panel.hidden = true; });

  list.addEventListener("change", function (e) {
    if (e.target && e.target.classList && e.target.classList.contains("ol-cb")) refresh();
  });

  pickAll.addEventListener("change", function () {
    boxes().forEach(function (b) { b.checked = pickAll.checked; });
    refresh();
  });

  applyBtn.addEventListener("click", function () {
    var rows = picked();
    if (!rows.length) return;
    if (!confirm(rows.length + "곳의 한줄 소개를 자동 조합으로 바꿉니다.\n"
                 + "바꾸기 전 값은 저장되고 [되돌리기] 로 한 번에 되돌릴 수 있습니다.")) return;
    // 바꾼 뒤 표를 되칠하려면 어느 줄에 무엇이 들어갔는지 알아야 한다.
    var wrote = rows.map(function (b) {
      var row = b.closest(".ol-row");
      var el = row ? row.querySelector(".ol-new") : null;
      return { id: Number(b.value), text: el ? el.textContent : "" };
    });
    applyBtn.disabled = true;
    fetch("/api/one-liner/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_ids: wrote.map(function (w) { return w.id; }) })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "적용하지 못했습니다"); refresh(); return; }
        wrote.forEach(function (w) { paintRow(w.id, w.text); });
        render(res.d);
        alert(res.d.applied + "곳을 바꿨습니다.");
      })
      .catch(function () { alert("적용하지 못했습니다"); refresh(); });
  });

  undoBtn.addEventListener("click", function () {
    if (!confirm("직전 [전체 자동조합] 을 되돌립니다.")) return;
    undoBtn.disabled = true;
    fetch("/api/one-liner/bulk/undo", { method: "POST" })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        undoBtn.disabled = false;
        if (!res.ok) { alert(res.d.detail || "되돌리지 못했습니다"); return; }
        (res.d.restored_rows || []).forEach(function (w) { paintRow(w.id, w.one_liner); });
        render(res.d);
        // 되돌리지 **않은** 줄이 있으면 반드시 말한다 — 조용히 넘어가면
        // "되돌렸다" 는 말과 화면이 어긋난다.
        alert(res.d.restored + "곳을 되돌렸습니다."
              + (res.d.kept ? "\n" + res.d.kept + "곳은 그 뒤에 손으로 고쳐서 그대로 두었습니다." : ""));
      })
      .catch(function () { undoBtn.disabled = false; alert("되돌리지 못했습니다"); });
  });
})();
