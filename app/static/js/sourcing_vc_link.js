// 딜 소싱 — 투자사 관리 현황과 **사람이 확정해 잇기** ([이 분으로 확정], #28).
//
// `시리즈 A 이상 딜 소싱 참여 심사역` 갈래의 줄은 이름 · 번호가 둘 다 같은 투자사
// 줄이 딱 하나일 때만 저절로 이어진다(`sourcing_sync.auto_link`). 이름만 · 번호만
// 같거나 번호가 여러 줄에 맞으면 서버가 그 줄들을 후보로 실어 주고
// (`data-vc-picks` — `sourcing_sync.link_candidates`), 여기서 이름 아래에 그린다.
// [이 분으로 확정]을 누르면 그 줄과 잇고, 그 자리에 연결 표시
// (`🔗 투자사 관리 현황: ○○ 명단`)를 그린다. 무엇이 후보인지는 서버가 정한다 —
// 이름 · 번호를 맞추는 규칙을 여기 또 적지 않는다. IR 기업 현황 › Series A 이상
// 딜 소싱 탭의 [이 분으로 확정](`series_a.js`)과 같은 짜임이다.
//
// 연결 표시는 서버가 그리는 것(`sourcing.html` 의 `sourcing-vc-link`)과 같은 모양이고
// 같은 값(`sourcing_sync.badges`)을 쓴다 — 풍선말도 서버가 실어 준다(`title`).
//
// 글자는 `textContent` 로만 넣는다 — 이름 · 회사는 사람이 적은 말이다.
(function () {
  var table = document.getElementById("sourcing-table");
  if (!table) return;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // 무엇이 같은가 — 서버가 실어 준 두 값 그대로 읽는다.
  function why(c) {
    if (c.name_match && c.phone_match) return "이름 · 번호 같음";
    if (c.phone_match) return "번호만 같음";
    return "이름만 같음";
  }

  function renderPicks(box, cands) {
    if (!box) return;
    box.innerHTML = "";
    cands = cands || [];
    if (cands.length) box.appendChild(el("span", "muted", "투자사 관리 현황 후보:"));
    cands.forEach(function (c) {
      box.appendChild(el("span", "tag soft vc-pick-name",
                         c.label + " · " + c.sheet + " 명단 · " + why(c)));
      var pick = el("button", "linkbtn js-vc-pick", "이 분으로 확정");
      pick.setAttribute("type", "button");
      pick.setAttribute("data-contact", String(c.id));
      pick.setAttribute("data-label", c.label || "");
      pick.setAttribute("data-sheet", c.sheet || "");
      pick.setAttribute("title", "투자사 관리 현황의 이 줄과 잇습니다 — 그쪽 `Series A 딜 소싱` " +
                                 "칸이 이 줄의 참여(O/X)로 섭니다");
      box.appendChild(pick);
    });
    box.hidden = !cands.length;
  }

  function renderLinked(box, link) {
    if (!box || !link) return;
    box.innerHTML = "";
    var a = el("a", "tag soft", "🔗 투자사 관리 현황: " + link.sheet + " 명단");
    a.setAttribute("href", link.href || "");
    a.setAttribute("title", link.title || "");
    box.appendChild(a);
    if (link.diff && link.diff.length) {
      var diff = el("span", "muted", "다른 칸: " + link.diff.join(" · "));
      diff.setAttribute("data-testid", "sourcing-vc-diff");
      diff.setAttribute("title", "이을 때 이미 달랐던 칸입니다 — 어느 쪽에서든 한 번 고치면 같아집니다");
      box.appendChild(diff);
    }
    box.setAttribute("data-testid", "sourcing-vc-link");
    box.hidden = false;
  }

  // 이으면서 **빈 칸이 채워졌을 수 있다**(`sourcing_sync.link` — 소싱 줄의 빈 칸만
  // 투자사 줄 값으로). 서버가 실어 준 같은 칸 값으로 그 줄의 칸 · 풍선말 · 거를
  // 값을 맞춘다. 방금 사람이 고친 칸(`skip`)은 `inline_edit.js` 가 이미 그렸다.
  function fill(tr, fields, skip) {
    Object.keys(fields || {}).forEach(function (field) {
      var cell = tr.querySelector('.cell[data-field="' + field + '"]');
      if (!cell || cell === skip) return;
      var value = fields[field] || "";
      cell.textContent = value;
      if (cell.hasAttribute("title")) cell.setAttribute("title", value);
      else if (cell.parentNode && cell.parentNode.hasAttribute &&
               cell.parentNode.hasAttribute("title")) cell.parentNode.setAttribute("title", value);
      if (tr.hasAttribute("data-f-" + field)) tr.setAttribute("data-f-" + field, value);
    });
  }

  function show(tr, data, skip) {
    var box = tr && tr.querySelector(".sourcing-vc-picks");
    if (!box) return;
    if (data.vc_link) {
      renderLinked(box, data.vc_link);
      fill(tr, data.fields, skip);
    } else if (data.vc_picks) {
      renderPicks(box, data.vc_picks);
    }
  }

  Array.prototype.slice.call(table.querySelectorAll(".sourcing-vc-picks")).forEach(function (box) {
    var cands = null;
    try { cands = JSON.parse(box.getAttribute("data-vc-picks") || "[]"); }
    catch (e) { cands = []; }
    renderPicks(box, cands);
  });

  // 이름 · 번호를 고치면 서버가 다시 본다(`routers/sourcing.update_row`) — 이어졌으면
  // 연결 표시, 아니면 새 후보가 응답에 실려 온다.
  table.addEventListener("inline-saved", function (e) {
    var d = (e && e.detail) || {};
    if (!d.row || !d.data) return;
    show(d.row, d.data, d.cell);
  });

  // [이 분으로 확정] — 되돌리는 단추가 없는 일이라 **누구를 어느 줄과** 잇는지
  // 확인창에 적는다(잘못 이은 줄은 딜 소싱에서 그 줄을 지워야 풀린다).
  table.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest ? e.target.closest(".js-vc-pick") : null;
    if (!btn) return;
    var tr = btn.closest("tr");
    if (!tr) return;
    var nameCell = tr.querySelector('[data-field="name"]');
    var who = ((nameCell && nameCell.textContent) || "").trim();
    if (!window.confirm("'" + who + "' 님을 투자사 관리 현황의 " + btn.getAttribute("data-sheet") +
        " 명단 줄(" + btn.getAttribute("data-label") + ")과 잇습니다.\n" +
        "그쪽 `Series A 딜 소싱` 칸이 이 줄의 참여(O/X)로 서고, 이름 · 회사 · 휴대폰처럼 " +
        "두 표에 다 있는 칸은 어느 쪽에서 고쳐도 같이 바뀝니다. 화면에서 푸는 단추는 없습니다.")) return;
    btn.disabled = true;
    fetch("/api/sourcing/" + tr.getAttribute("data-id") + "/link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact_id: parseInt(btn.getAttribute("data-contact"), 10) })
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
      if (!res.ok) {
        alert(res.d.detail || "잇지 못했습니다.");
        btn.disabled = false;
        return;
      }
      show(tr, res.d, null);
    }).catch(function () {
      alert("확정 요청 오류");
      btn.disabled = false;
    });
  });
})();
