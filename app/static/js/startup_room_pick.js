/* 스타트업 카톡방 매칭 — 찾기 · 확정 · 직접 적기 · 방 연결 확인.
 * (node tests/js/startup_room_pick_test.js)
 *
 * ## 여기서 판단하지 않는다  ★
 *
 * 어느 줄을 찾을지, 어느 제목을 확정할 수 있는지는 **서버가 정한다**
 * (`services/startup_room_pick.py`). 화면은 누른 것을 그대로 보낸다 — 찾기는
 * 줄 번호 없이 보내 서버가 고르게 하고, 확정은 **누른 그 제목 글자 그대로**
 * 보낸다(서버가 후보에 있는지 다시 본다).
 *
 * ## 저절로 아무것도 하지 않는다
 *
 * 후보가 하나뿐이어도 화면이 확정하지 않는다 — 누르는 것은 사람이다. 확정 전에
 * 어느 방인지 한 번 더 묻는다(제목이 길어 비슷한 방을 잘못 누르기 쉽다).
 *
 * 직접 적기는 수정창과 **같은 길**이다(`PATCH /api/contacts/{id}`) — 글자가
 * 바뀌면 확인이 풀리는 규칙이 거기 있다(`services/room_joined`).
 */
(function () {
  "use strict";

  var table = document.getElementById("room-pick-table");
  if (!table) return;
  var errorBox = document.getElementById("room-pick-error");

  function setError(text) {
    if (errorBox) errorBox.textContent = text || "";
  }

  function send(method, url, payload) {
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  function goJob(res, fallback) {
    if (!res.ok) { setError(res.d.detail || fallback); return; }
    window.location.href = res.d.href || ("/jobs/" + res.d.job_id);
  }

  // ── [방 후보 찾기] — 찾을 줄은 서버가 고른다 ─────────────────────────────
  var searchBtn = document.getElementById("room-search-btn");
  if (searchBtn) {
    searchBtn.addEventListener("click", function () {
      var n = parseInt(searchBtn.getAttribute("data-count") || "0", 10) || 0;
      if (!n) return;
      if (!window.confirm(n + "곳을 회사명으로 카톡에서 찾습니다.\n" +
          "카카오톡이 켜져 있어야 하며, 찾는 중에는 PC 조작을 멈춰주세요.\n" +
          "(문구는 전송하지 않습니다 · 방 이름도 바꾸지 않습니다 — 후보만 가져옵니다)")) return;
      setError("");
      searchBtn.disabled = true;
      send("POST", "/api/startup-rooms/search", {})
        .then(function (res) { searchBtn.disabled = false; goJob(res, "찾기 요청 실패"); })
        .catch(function () { searchBtn.disabled = false; setError("찾기 요청 오류"); });
    });
  }

  // ── [방 연결 확인] — 적어 둔 이름을 카톡에서 대조한다 ─────────────────────
  var verifyBtn = document.getElementById("room-verify-btn");
  if (verifyBtn) {
    verifyBtn.addEventListener("click", function () {
      var ids = (verifyBtn.getAttribute("data-ids") || "").split(",")
        .filter(Boolean).map(function (v) { return parseInt(v, 10); });
      if (!ids.length) return;
      if (!window.confirm(ids.length + "곳의 카톡방을 확인합니다.\n" +
          "카카오톡이 켜져 있어야 하며, 확인 중에는 PC 조작을 멈춰주세요.\n" +
          "(문구는 전송하지 않습니다)")) return;
      setError("");
      send("POST", "/api/contacts/verify-rooms", { contact_ids: ids })
        .then(function (res) { goJob(res, "확인 요청 실패"); })
        .catch(function () { setError("확인 요청 오류"); });
    });
  }

  // ── 줄 안의 단추 — [이 방으로 확정] · 직접 적기 [저장] ───────────────────
  table.addEventListener("click", function (e) {
    var t = e.target;
    var confirmBtn = t && t.closest ? t.closest(".room-confirm") : null;
    if (confirmBtn) {
      e.preventDefault();
      var room = confirmBtn.getAttribute("data-room") || "";
      if (!room) return;
      if (!window.confirm("이 방으로 확정합니다.\n\n" + room + "\n\n" +
          "확정하면 이 방이 '확인됨' 이 되고 안내 카톡이 이 방으로 나갑니다.")) return;
      setError("");
      confirmBtn.disabled = true;
      send("POST", "/api/startup-rooms/" + confirmBtn.getAttribute("data-id") + "/confirm",
           { room: room })
        .then(function (res) {
          if (!res.ok) { confirmBtn.disabled = false; setError(res.d.detail || "확정 실패"); return; }
          if (!res.d.room_ready) {
            // `방 나감` · `참여 안 함` 으로 적힌 줄 — 방 이름은 들어갔지만 확인은
            // 안 달린다(`room_joined`). 조용히 넘어가면 확정된 줄 안다.
            window.alert("방 이름은 넣었지만 '확인됨' 이 되지 않았습니다 — 이 줄의 연결 " +
                         "단계가 '방 나감' 또는 '참여 안 함' 입니다. 스타트업 화면에서 " +
                         "연결 단계를 고친 뒤 [방 연결 확인] 을 눌러 주세요.");
          }
          window.location.reload();
        })
        .catch(function () { confirmBtn.disabled = false; setError("확정 오류"); });
      return;
    }
    var saveBtn = t && t.closest ? t.closest(".room-direct-save") : null;
    if (saveBtn) {
      e.preventDefault();
      var row = saveBtn.closest("tr");
      var input = row ? row.querySelector(".room-direct") : null;
      if (!input) return;
      setError("");
      send("PATCH", "/api/contacts/" + saveBtn.getAttribute("data-id"),
           { kakao_room_name: input.value })
        .then(function (res) {
          if (!res.ok) { setError(res.d.detail || "방 제목 저장 실패"); return; }
          window.location.reload();
        })
        .catch(function () { setError("방 제목 저장 오류"); });
    }
  });
})();
