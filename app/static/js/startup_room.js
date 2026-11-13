/* 대표 카톡방 맞추기 — **후보를 누르면 그 줄의 칸에 넣는다.** 그게 전부다.
 * (node tests/js/startup_room_test.js)
 *
 * ## 여기서 판단하지 않는다  ★
 *
 * 어느 후보가 그 회사 것인지, 초안이 맞는지는 **서버가 정해서 보내 준다**
 * (`services/room_match.has_company_name` · `draft`). 여기서 회사명을 다시
 * 견주면 같은 규칙이 파이썬과 자바스크립트 두 벌이 되고, 한쪽만 고쳐지는
 * 날 화면이 도드라지게 세운 후보와 서버가 맞다고 본 후보가 갈린다.
 * 그래서 이 파일은 **글자를 옮기는 일만** 한다.
 *
 * ## 저절로 넣지 않는다  ★
 *
 * 후보가 하나뿐인 줄에도 자동으로 채우지 않는다. 채워 두면 사람은 이미
 * 확인된 값으로 읽고 그대로 저장한다 — 회사명이 든 방이 꼭 대표와의 방인
 * 것은 아니라서, 그 한 번이 엉뚱한 방으로 가는 발송이 된다.
 *
 * ## 하나만 고른다 · 줄마다 [확정] (11/13)
 *
 * 사용자: "IR 기업 현황에서 방 찾기 확인을 했을 때 투자사 방 찾기처럼 별도의 체크하는
 * 화면". 누른 후보에 `picked` 가 서고 **같은 줄의** 다른 후보는 풀린다(라디오처럼 — 칸에
 * 든 글자가 곧 고른 것이라 둘이 따로 놀지 않게, 칸을 고치면 표시도 따라간다).
 * 줄의 [확정] 은 그 줄만 같은 저장 자리로 보낸다(`only` — `routers/startup_send.save_rooms`)
 * — **새로고침하지 않고** 그 줄의 확인 · 찾기 결과 칸만 서버가 준 말로 고친다. 다른 줄에서
 * 고르던 것이 날아가지 않는다. 여기서 확인됨인지 판정하지 않는다(서버가 후보 그대로인지 본다).
 *
 * ## 이 파일이 없어도 표는 쓸 수 있다
 *
 * 후보는 눌러서 넣는 **단추**이기도 하고 눈으로 읽는 **글자**이기도 하다.
 * 스크립트가 안 돌면 보고 옮겨 적으면 된다 — 저장은 평범한 폼 전송이다
 * ([고른 것 확정]. 줄의 [확정] 은 스크립트로만 돈다).
 */
(function () {
  "use strict";

  var form = document.getElementById("room-match");
  if (!form) return;

  // 줄 안에서 칸을 찾는다. `closest("tr")` 로 그 줄에 갇히는 것이 핵심이다 —
  // 표 전체에서 첫 칸을 찾으면 어느 줄을 눌러도 맨 윗줄에 들어간다.
  function inputOf(button) {
    var row = button.closest("tr");
    return row ? row.querySelector(".room-input") : null;
  }

  // 그 줄의 후보 중 칸의 글자와 **같은 것만** 골라진 것으로 세운다(하나만 — 라디오처럼).
  function markPicked(row, value) {
    if (!row) return;
    var picks = row.querySelectorAll(".room-pick");
    for (var i = 0; i < picks.length; i += 1) {
      var on = (picks[i].getAttribute("data-room") || "") === value;
      picks[i].classList.toggle("picked", on);
      picks[i].setAttribute("aria-pressed", on ? "true" : "false");
    }
  }

  var errorBox = document.getElementById("room-match-error");
  function say(text, bad) {
    if (!errorBox) return;
    errorBox.textContent = text || "";
    errorBox.className = "hint " + (bad ? "error" : "muted");
  }

  function setBadge(row, sel, text, ok) {
    var badge = row.querySelector(sel);
    if (!badge || !text) return;
    badge.textContent = text;
    badge.classList.toggle("ok", !!ok);
    badge.classList.toggle("muted", !ok);
    badge.classList.remove("warn");
  }

  // 줄의 [확정] — 그 줄만 같은 저장 자리로(`only`). 서버가 준 말로 그 줄만 고친다.
  function confirmRow(button) {
    var row = button.closest("tr");
    var input = row ? row.querySelector(".room-input") : null;
    if (!row || !input) return;
    var id = button.getAttribute("data-id") || "";
    var ids = form.querySelector('input[name="ids"]');
    var body = "company_ids=" + encodeURIComponent(id) +
      "&rooms=" + encodeURIComponent(input.value || "") +
      "&ids=" + encodeURIComponent(ids ? ids.value : "") +
      "&only=" + encodeURIComponent(id);
    if (button.disabled) return;
    button.disabled = true;
    say("");
    fetch(form.getAttribute("action"), {
      method: "POST",
      headers: { "Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded" },
      body: body
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (d) { return { ok: r.ok && !!d.ok, d: d }; });
    }).then(function (res) {
      button.disabled = false;
      if (!res.ok) { say(res.d.detail || "확정하지 못했습니다 — 화면을 새로 열어 보세요", true); return; }
      var d = res.d;
      if (typeof d.room === "string") input.value = d.room;
      setBadge(row, ".room-state", d.state_label, d.state === "verified");
      setBadge(row, ".room-find", d.find_label, d.find === "verified");
      var firstCell = row.querySelector("td");
      var name = firstCell ? String(firstCell.textContent || "").trim() : "";
      say((name ? name + " — " : "") + (d.msg || "확정했습니다"));
    }).catch(function () {
      button.disabled = false;
      say("확정 요청 오류 — 다시 눌러 보세요", true);
    });
  }

  // 한 자리에서 위임으로 받는다. 줄마다 따로 걸면 수십 개가 매달리고,
  // 줄이 다시 그려질 때 걸어 둔 것이 떨어진다.
  form.addEventListener("click", function (e) {
    var confirmBtn = e.target.closest(".room-confirm");
    if (confirmBtn) {
      e.preventDefault();
      confirmRow(confirmBtn);
      return;
    }
    var button = e.target.closest(".room-pick");
    if (!button) return;
    // 단추는 `type="button"` 이지만 그것만 믿지 않는다 — 폼 안이라 하나라도
    // 빠뜨리면 **후보를 누른 것이 저장으로** 이어진다.
    e.preventDefault();

    var input = inputOf(button);
    if (!input) return;
    input.value = button.getAttribute("data-room") || "";
    markPicked(button.closest("tr"), input.value);
    // 넣은 자리에 초점을 둔다. 띄어쓰기 하나를 고쳐야 하는 경우가 흔한데
    // (카톡 제목과 우리가 아는 회사명이 다르게 띄어져 있다), 초점이 없으면
    // 사람이 그 칸을 다시 찾아 눌러야 한다.
    if (typeof input.focus === "function") input.focus();
  });

  // 칸을 손으로 고치면 고른 표시도 따라간다 — 한 글자라도 다르면 그 후보가 아니다.
  form.addEventListener("input", function (e) {
    var t = e.target;
    if (!t || !t.classList || !t.classList.contains("room-input")) return;
    markPicked(t.closest("tr"), t.value || "");
  });
})();
