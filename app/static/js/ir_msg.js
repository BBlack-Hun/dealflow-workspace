/* IR 기업현황 탭 — 💬 스타트업으로 카톡보내기 · 카톡방 찾기·확인 (11/11 · 이름은 i248).
 * (node tests/js/ir_msg_test.js)
 *
 * 스타트업 화면의 안내 카톡(`startup_msg.js`)과 같은 일을 **IR 기업 표 위에서** 한다.
 * 무엇을 왜 그렇게 하는지는 `services/ir_outreach.py` 머리말에 있다.
 *
 * ## 여기서 판단하지 않는다  ★
 *
 * 어느 기업에 보낼 수 있는지(방 확인 · 딜소개 불가 · 폐업 · 최근 받음)는 **서버가
 * 정한다** — [미리보기] 가 묻고(`/api/ir-msg/preview` → `ir_outreach.rows`), 그 답의
 * `ready_ids` 만 [대기 목록 만들기] 가 싣는다. 채움말(`{대표명}` …)도 여기서 채우지
 * 않는다(`startup_outreach.render`). 같은 규칙을 자바스크립트로 한 벌 더 적으면 한쪽만
 * 고쳐지는 날 미리보기와 대표가 받는 글이 갈린다.
 *
 * ## 미리보기를 본 그대로만 보낸다  ★
 *
 * 고른 기업 · 문구 · 글 · `N일` 중 하나라도 바뀌면 [대기 목록 만들기] 를 다시 잠근다 —
 * 미리보기에 없던 기업이나 글이 나가면 안 된다. 서버도 한 번 더 같은 판정을 한다.
 *
 * ## 보이는 줄만 고른다
 *
 * 거르개(머리글 필터 · 검색)로 감춘 줄은 **체크를 푼다**(`companies.js` 가 거를 때마다
 * `refresh` 를 부른다). 감춘 채 체크가 남으면 사람은 보이는 줄만 보고 누른다.
 */
(function () {
  "use strict";

  var table = document.getElementById("co-table");
  var panel = document.getElementById("irm-panel");
  if (!table || !panel) return;

  var fold = document.getElementById("irm-fold");
  var countBox = document.getElementById("irm-count");
  var allBox = document.getElementById("irm-pick-all");
  var bodyBox = document.getElementById("irm-body");
  var daysBox = document.getElementById("irm-days");
  var titleBox = document.getElementById("irm-title");
  var whenBox = document.getElementById("irm-when");
  var previewBtn = document.getElementById("irm-preview-btn");
  var sendBtn = document.getElementById("irm-send-btn");
  var roomBtn = document.getElementById("irm-room-check-btn");
  var roomsLink = document.getElementById("irm-rooms-link");
  var errorBox = document.getElementById("irm-error");
  var previewBox = document.getElementById("irm-preview");
  var previewList = document.getElementById("irm-preview-list");
  var skippedList = document.getElementById("irm-skipped-list");
  var previewNote = document.getElementById("irm-preview-note");
  var sender = panel.getAttribute("data-sender") || "";
  var roomsHref = panel.getAttribute("data-rooms-href") || "/deals/startup-ir/rooms";

  // 미리보기가 `보낼 수 있다` 고 한 기업 — 비어 있으면 [대기 목록 만들기] 가 잠긴다.
  var ready = [];
  // 처음 하나를 고르면 칸을 저절로 편다 — **한 번만**(사람이 접으면 그대로 둔다).
  var opened = false;

  function rows() {
    return Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-id]"));
  }
  function boxOf(tr) { return tr.querySelector(".irm-pick"); }

  function setError(text) { if (errorBox) errorBox.textContent = text || ""; }

  function picked() {
    var out = [];
    rows().forEach(function (tr) {
      var cb = boxOf(tr);
      if (cb && cb.checked && !tr.hidden) out.push(parseInt(cb.value, 10));
    });
    return out;
  }

  function topic() { return bodyBox ? bodyBox.getAttribute("data-topic") || "" : ""; }
  function days() { return daysBox ? (parseInt(daysBox.value, 10) || 0) : 0; }

  // 미리보기를 본 뒤 무언가 바뀌었다 — 다시 보기 전에는 못 보낸다(머리말).
  function stale() {
    ready = [];
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = "미리보기를 먼저 보세요";
    }
  }

  function refresh() {
    var dropped = false;
    rows().forEach(function (tr) {
      var cb = boxOf(tr);
      if (cb && tr.hidden && cb.checked) { cb.checked = false; dropped = true; }  // 보이는 줄만(머리말)
    });
    if (dropped) stale();      // 고른 기업이 바뀌었다 — 미리보기를 다시 봐야 한다
    var ids = picked();
    var n = ids.length;
    if (countBox) countBox.textContent = n + "곳 선택";
    if (previewBtn) {
      previewBtn.disabled = false;
      previewBtn.textContent = "미리보기 (" + n + "곳)";
    }
    if (roomBtn) {
      roomBtn.disabled = n === 0;
      roomBtn.textContent = "카톡방 찾기·확인 (" + n + "곳)";
    }
    // 고른 기업으로 맞추기 화면을 연다 — 계약을 안 한 기업도 거기 선다.
    if (roomsLink) roomsLink.href = roomsHref + (n ? "?ids=" + ids.join(",") : "");
    if (n && !opened && fold && !fold.open) fold.open = true;
    if (n) opened = true;
  }

  function changed() { stale(); refresh(); }

  table.addEventListener("change", function (e) {
    var t = e.target;
    if (t && t.classList && t.classList.contains("irm-pick")) changed();
  });
  if (allBox) {
    allBox.addEventListener("change", function () {
      rows().forEach(function (tr) {
        var cb = boxOf(tr);
        if (cb && !tr.hidden) cb.checked = !!allBox.checked;
      });
      changed();
    });
  }

  // ── 문구 셋 — 화면을 다시 받지 않고 갈아 끼운다(수백 줄의 체크가 풀린다) ──
  Array.prototype.forEach.call(panel.querySelectorAll(".irm-topic"), function (btn) {
    btn.addEventListener("click", function () {
      Array.prototype.forEach.call(panel.querySelectorAll(".irm-topic"), function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      if (bodyBox) {
        bodyBox.value = btn.getAttribute("data-body") || "";
        bodyBox.setAttribute("data-topic", btn.getAttribute("data-topic") || "");
      }
      if (titleBox) titleBox.value = btn.getAttribute("data-title") || "";
      changed();
    });
  });
  if (bodyBox) bodyBox.addEventListener("input", stale);
  if (daysBox) {
    daysBox.addEventListener("input", stale);
    daysBox.addEventListener("change", stale);
  }

  function post(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    });
  }

  function clear(node) {
    while (node && node.children && node.children.length) node.removeChild(node.children[0]);
  }

  // ── 미리보기 — 서버가 채운 글 · 빠지는 까닭을 그대로 ───────────────────────
  function renderPreview(d, asked) {
    clear(previewList);
    clear(skippedList);
    (d.previews || []).forEach(function (p) {
      var item = document.createElement("div");
      item.className = "msg-preview-item";
      var head = document.createElement("b");
      head.textContent = [p.firm, p.name].filter(Boolean).join(" · ") +
        (p.room ? "  →  " + p.room : "") +
        (p.last_date ? "  (이 문구 마지막 발송 " + p.last_date + ")" : "");
      var text = document.createElement("pre");
      // 글자 그대로 — 대표가 받는 글이다. HTML 로 넣지 않는다.
      text.textContent = p.message;
      item.appendChild(head);
      item.appendChild(text);
      previewList.appendChild(item);
    });
    (d.skipped || []).forEach(function (s) {
      var li = document.createElement("li");
      li.textContent = s.firm + " — 빠짐: " + s.reason;
      skippedList.appendChild(li);
    });
    if (previewNote) {
      previewNote.textContent = d.sample
        ? "— 아직 아무 곳도 안 골라 지어낸 줄로 보여 줍니다"
        : "— 고른 " + asked + "곳 중 " + (d.ready_ids || []).length + "곳에 이 글이 나갑니다" +
          ((d.skipped || []).length ? " · " + d.skipped.length + "곳은 빠집니다(아래 까닭)" : "");
    }
    if (previewBox) previewBox.hidden = false;
  }

  if (previewBtn) {
    previewBtn.addEventListener("click", function () {
      setError("");
      var ids = picked();
      post("/api/ir-msg/preview", { topic: topic(), body: bodyBox ? bodyBox.value : "",
                                    company_ids: ids, days: days() })
        .then(function (res) {
          if (!res.ok) { setError(res.d.detail || "미리보기 실패"); stale(); return; }
          renderPreview(res.d, ids.length);
          ready = (res.d.ready_ids || []).slice();
          if (sendBtn) {
            sendBtn.disabled = ready.length === 0;
            // **몇 곳에 가는지 단추에 적는다** — 누른 뒤에 아는 것은 늦다.
            sendBtn.textContent = ready.length
              ? ready.length + "곳 대기 목록 만들기"
              : (res.d.sample ? "기업을 고르세요" : "보낼 수 있는 곳이 없습니다");
          }
        })
        .catch(function () { setError("미리보기 오류"); stale(); });
    });
  }

  // ── 대기 목록 만들기 — 미리보기가 `보낼 수 있다` 고 한 곳만 ─────────────────
  if (sendBtn) {
    sendBtn.addEventListener("click", function () {
      if (!ready.length) return;
      setError("");
      if (!window.confirm(ready.length + "곳짜리 대기 목록을 만듭니다.\n" +
          (sender ? sender + " 계정 PC 의 카톡에서 나갑니다.\n" : "") +
          "아직 보내지 않습니다 — 진행 화면에서 [발송 시작] 을 눌러야(또는 고른 " +
          "시각이 되어야) 나갑니다.")) return;
      sendBtn.disabled = true;
      post("/api/ir-msg/send", {
        topic: topic(), body: bodyBox ? bodyBox.value : "", company_ids: ready.slice(),
        days: days(), title: titleBox ? titleBox.value : "",
        scheduled_at: whenBox ? whenBox.value : ""
      })
        .then(function (res) {
          if (!res.ok) { setError(res.d.detail || "대기 목록을 만들지 못했습니다"); stale(); return; }
          window.location.href = res.d.href || ("/jobs/" + res.d.job_id);
        })
        .catch(function () { setError("대기 목록 만들기 오류"); stale(); });
    });
  }

  // ── [카톡방 찾기·확인] — 방 단추는 하나다(스타트업 화면과 같다) ─────────────
  //
  // 기업마다 대조할지 찾을지는 서버가 고른다(`ir_outreach.room_task`). 진행 화면을 못
  // 보는 사람(회차는 보내는 계정 것)은 맞추기 화면으로 간다 — 거기 결과가 선다.
  if (roomBtn) {
    roomBtn.addEventListener("click", function () {
      var ids = picked();
      if (!ids.length) return;
      setError("");
      if (!window.confirm(ids.length + "곳의 대표 카톡방을 " +
          (sender ? sender + " 계정 PC 의 " : "") + "카톡에서 찾고 확인합니다.\n" +
          "· 방 이름이 적힌 곳 — 그 이름 그대로 확인\n" +
          "· 방 이름이 없는 곳 — 회사명으로 찾아 후보만 모음([대표 카톡방 맞추기] 에서 골라 확정)\n" +
          "그 PC 의 카카오톡이 켜져 있어야 합니다. (문구는 전송하지 않습니다)")) return;
      roomBtn.disabled = true;
      post("/api/ir-rooms/check", { company_ids: ids })
        .then(function (res) {
          roomBtn.disabled = false;
          if (!res.ok) { setError(res.d.detail || "찾기 요청 실패"); return; }
          if (res.d.href) { window.location.href = res.d.href; return; }
          window.alert(res.d.total + "곳을 " + (res.d.sender || "보내는") + " 계정 PC 에서 " +
                       "찾고 확인합니다(회차 #" + res.d.job_id + ").\n끝나면 [대표 카톡방 " +
                       "맞추기] 에서 상태 · 후보를 보고 고르세요.");
          window.location.href = res.d.rooms_href || roomsHref;
        })
        .catch(function () { roomBtn.disabled = false; setError("찾기 요청 오류"); });
    });
  }

  window.DealflowIrMsg = { refresh: refresh };
  stale();
  refresh();
})();
