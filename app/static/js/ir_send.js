// IR 진행 관리의 [자료 보내기] — **그 자리에서 끝낸다.**
//
// 예전에는 딜 제안 관리(`/deals`)로 화면을 통째로 옮겼다. 옮겨 간 화면은
// 기업 고르기·담당자 고르기·예약 큐까지 다 붙어 있는 넓은 자리인데, 여기서
// 넘어온 사람이 할 일은 이미 정해져 있다 — **이 담당자에게, 이 기업들 자료를,
// 지금 보낸다.** 그 한 가지를 하려고 화면을 옮기면 돌아올 길을 스스로 찾아야
// 하고, 옮긴 화면에서 체크가 하나 풀리면 어디가 달라졌는지도 모른다.
//
// ## 여기서 새로 만드는 것은 **없다**
//
//   번호·파일명·문구   서버 미리보기(`POST /api/deals/preview`)를 그대로 받는다
//   목록 그리기        `ir_attach_list.js` — 딜 제안 관리와 **같은 한 벌**
//   문구 복사          같은 파일의 같은 함수
//   발송               `POST /api/deals/send` — 딜 제안 관리가 쓰는 그 길
//
// 같은 결정을 두 군데 적어 두면 한쪽이 낡는다. 실제로 화면이 센 번호와 문구의
// 번호가 갈렸던 적이 있어서, **번호도 문구도 서버가 한 응답에 실어 준 것만**
// 쓴다. 자료를 누가 붙이는가(발송기냐 사람이냐)도 서버 한 곳이 정한다
// (`app/services/ir_attach.py: auto_attach_enabled`) — 창의 머리말은 그 판단을
// 서버가 그려 준 것이다(`ir.html`).
//
// ## 스크립트가 죽어도 길은 남는다
//
// 단추는 여전히 **폼**이다(`/ir/deliver-guide` → 딜 제안 관리). 이 파일이 그
// 폼의 `submit` 을 가로채 창을 열 뿐이라, 스크립트가 안 실리거나 예외가 나면
// 예전 그대로 딜 제안 관리로 간다. 문구를 손보거나 담당자를 더하려면 그 화면이
// 필요해서, 창 안에도 그리로 가는 길을 남겨 두었다.
"use strict";
(function () {
  var forms = Array.prototype.slice.call(
    document.querySelectorAll("form.deliver-form"));
  var modal = document.getElementById("ir-send-modal");
  // 창이 없으면(화면이 낡았거나 보낼 것이 없으면) 아무것도 가로채지 않는다 —
  // 폼은 폼대로 간다.
  if (!forms.length || !modal || !window.IrAttach) return;

  var el = function (id) { return document.getElementById(id); };
  var links = el("ir-links");
  var body = el("ir-send-message");
  var warnBox = el("ir-send-warnings");
  var stateLine = el("ir-send-state");
  var copyBtn = el("ir-send-copy");
  var goBtn = el("ir-send-go");
  var closeBtn = el("ir-send-close");
  var dealsLink = el("ir-send-open-deals");
  var GO_LABEL = goBtn.textContent;

  // 지금 창이 다루고 있는 건. 응답이 늦게 와도 **연 뒤에 바뀐 대상**을 덮지
  // 않게, 열 때마다 번호를 올리고 그 번호가 아직 유효할 때만 그린다.
  var seq = 0;
  var open = null;
  var backdrop = null;

  function setWarn(text) {
    warnBox.hidden = !text;
    warnBox.textContent = text || "";
  }

  function setState(text, kind) {
    stateLine.textContent = text || "";
    stateLine.className = "hint " + (kind || "muted");
    stateLine.hidden = !text;
  }

  // 뒷막은 **띄울 때 만들고 닫을 때 지운다.** `hidden` 으로 숨겨 두면
  // `.layout:has(.guard-backdrop) .sidebar` 가 계속 맞아떨어져, 창이 닫혀
  // 있는데도 좌측 메뉴가 어두운 채로 남는다(`:has()` 는 숨김을 안 본다).
  function showModal() {
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.className = "guard-backdrop";
      backdrop.addEventListener("click", close);
      // 창과 **같은 부모**에 붙인다 — `.layout:has(.guard-backdrop)` 이
      // 좌측 메뉴를 어둡게 하는 규칙이 그 안에 있을 때만 맞는다.
      // 앞뒤 차례는 상관없다: 위아래는 z-index 가 정한다(뒷막 39 · 창 40).
      modal.parentNode.appendChild(backdrop);
    }
    modal.hidden = false;
  }

  function close() {
    modal.hidden = true;
    if (backdrop && backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
    backdrop = null;
    open = null;
  }

  // 보낸 뒤 그 자리가 **눈에 띄게 달라져야 한다.** 창만 닫히면 방금 누른 것이
  // 아무 일도 안 한 것처럼 보여서 한 번 더 누른다.
  //
  // 요청 줄이 목록에서 곧바로 사라지지는 않는다 — 닫는 것은 발송기가 실제로
  // 보내고 난 뒤다(`pipeline.close_requests_for`). 그래서 여기서는 **사라졌다고
  // 하지 않고** 대기 중이라고 적는다. 없앤 것처럼 굴다가 새로고침에 되살아나면
  // 보낸 것인지 아닌지 알 수 없다.
  function markSent(form, jobId) {
    var head = form.parentNode;
    form.hidden = true;
    var badge = document.createElement("span");
    badge.className = "room-badge ok ir-sent-badge";
    badge.textContent = "✅ 발송 목록에 올렸습니다";
    head.appendChild(badge);
    var link = document.createElement("a");
    link.className = "linkbtn";
    link.href = "/jobs/" + jobId;
    link.textContent = "발송 진행 보기";
    head.appendChild(link);
  }

  function fill(preview) {
    // 번호가 왜 그렇게 적혔는지 말하던 줄은 이 창에서 뺐다 — note 칸을 안 주면
    // 공용 한 벌이 조용히 건너뛴다. 딜 제안 관리에는 그대로 있다.
    window.IrAttach.renderList(links, null, preview);
    body.value = preview.message || "";
    // 서버가 미리 잡아 준 걱정거리 — 자료 파일명이 빈 기업, 방 미등록.
    // **삼키지 않는다.** 발송이 막히는 사유가 여기 그대로 적힌다.
    var warns = (preview.warnings || []).slice();
    if (!preview.room_name) {
      warns.unshift((preview.room_warning || "카톡방 이름 미등록")
        + " — 투자사 관리 현황에서 방 이름을 넣어야 보낼 수 있습니다.");
    }
    setWarn(warns.join("\n"));
    copyBtn.disabled = false;
    // 방이 없으면 서버가 어차피 거절한다. 눌러 보고 알기보다 **왜 못 누르는지**
    // 위에 적힌 채로 막아 둔다. 복사는 막지 않는다 — 손으로 붙여 넣는 길은
    // 방 이름과 무관하다.
    goBtn.disabled = !preview.room_name;
    setState(preview.room_name ? ("💬 " + preview.room_name + " 로 나갑니다") : "",
              "muted");
  }

  function loadPreview(item) {
    var mine = item.seq;
    setState("미리보기를 불러오는 중…", "muted");
    fetch("/api/deals/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "ir", contact_ids: [item.contactId],
                             company_ids: item.companyIds })
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (res) {
        if (!open || open.seq !== mine) return;      // 그 사이 다른 건을 열었다
        if (!res.ok || !res.d.previews || !res.d.previews.length) {
          failLoad(res.d && res.d.detail);
          return;
        }
        fill(res.d.previews[0]);
      })
      .catch(function () { if (open && open.seq === mine) failLoad(""); });
  }

  // 미리보기를 못 받으면 **보내기를 막는다.** 무엇이 나갈지 못 본 채로 누르는
  // 자리가 되면 안 된다. 대신 딜 제안 관리로 가는 길은 그대로 열어 둔다.
  function failLoad(detail) {
    body.value = "";
    links.innerHTML = "";
    setWarn("미리보기를 불러오지 못했습니다"
      + (detail ? " — " + detail : "")
      + ". 딜 제안 관리에서 열어 확인해 주세요.");
    setState("", "muted");
    goBtn.disabled = true;
    copyBtn.disabled = true;
  }

  function send() {
    if (!open) return;
    var item = open;
    if (!window.confirm(item.name + " 님에게 " + item.companyIds.length
                        + "개 기업 IR 자료 전달 문구를 발송합니다.\n"
                        + "방 이름을 최종 확인하셨나요?")) return;
    goBtn.disabled = true;
    goBtn.textContent = "보내는 중…";
    fetch("/api/deals/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "ir", contact_ids: [item.contactId],
                             company_ids: item.companyIds })
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (res) {
        goBtn.textContent = GO_LABEL;
        if (!res.ok) {
          // 서버가 막은 사유는 그대로 보여 준다(방 미등록·자료 파일명 없음·
          // 검토중단). 조용히 삼키면 왜 안 나갔는지 알 길이 없다.
          setWarn("발송 목록을 만들지 못했습니다 — "
                  + ((res.d && res.d.detail) || "다시 시도해 주세요"));
          goBtn.disabled = false;
          return;
        }
        markSent(item.form, res.d.job_id);
        sentState(res.d.job_id);
      })
      .catch(function () {
        goBtn.textContent = GO_LABEL;
        setWarn("발송 요청이 실패했습니다 — 잠시 뒤 다시 시도해 주세요.");
        goBtn.disabled = false;
      });
  }

  function sentState(jobId) {
    setWarn("");
    setState("✅ 발송 목록을 만들었습니다 — 발송 프로그램이 보냅니다. "
             + "보내고 나면 이 요청은 [보낼 자료] 에서 자동으로 빠집니다.",
             "all-clear");
    goBtn.hidden = true;
    dealsLink.hidden = true;
    var jobs = el("ir-send-job");
    jobs.href = "/jobs/" + jobId;
    jobs.hidden = false;
    closeBtn.textContent = "닫기";
  }

  function openFor(form) {
    seq += 1;
    var ids = (form.querySelector('[name="company_ids"]').value || "")
      .split(",").filter(function (v) { return v.trim() !== ""; })
      .map(function (v) { return parseInt(v, 10); });
    open = {
      seq: seq,
      form: form,
      contactId: parseInt(form.querySelector('[name="contact_id"]').value, 10),
      companyIds: ids,
      name: form.getAttribute("data-name") || ""
    };
    // 딜 제안 관리로 가는 길 — 문구를 손보거나 담당자를 더할 때 필요하다.
    // 주소는 예전에 넘어가던 그것과 같다(`/ir/deliver-guide` 가 만들던 주소).
    dealsLink.href = "/deals?mode=ir&contacts=" + open.contactId
      + "&companies=" + ids.join(",") + "&attach=1";
    // 창을 다시 열 때는 지난번 결과가 남아 있으면 안 된다.
    links.innerHTML = "";
    body.value = "";
    setWarn("");
    goBtn.hidden = false;
    goBtn.disabled = true;
    goBtn.textContent = GO_LABEL;
    copyBtn.disabled = true;
    dealsLink.hidden = false;
    el("ir-send-job").hidden = true;
    showModal();
    loadPreview(open);
  }

  forms.forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      openFor(form);
    });
  });

  copyBtn.addEventListener("click", function () {
    window.IrAttach.copyText(body, copyBtn);
  });
  goBtn.addEventListener("click", send);
  closeBtn.addEventListener("click", close);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) close();
  });
}());
