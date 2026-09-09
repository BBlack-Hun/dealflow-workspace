// 수정창(우측 슬라이드 상세 패널)을 **모달**로 세우는 공통 부품.
//
// ── 왜 한 벌이어야 하는가 ────────────────────────────────────────────────
//
// 창을 여닫는 판단은 화면마다 같다: 뒷막을 세운다 · Escape 로 닫는다 ·
// **적어 두고 아직 저장 안 한 것이 있으면 묻는다**. 그런데 이 판단이 화면마다
// 한 벌씩 있으면 반드시 한쪽이 낡는다 — 실제로 그랬다:
//
//   · 투자사 관리 현황(`contacts.js`) 은 뒷막도 Escape 도 아예 없었다.
//     그래서 창을 열어 둔 채 표의 칸을 눌러 고칠 수 있었고, 칸 위에 뜨는
//     편집창(`.cell-pop`, z-60)이 수정창(z-40) 위에 겹쳐 그려졌다.
//   · 딜 기업 DB(`companies.js`) 는 뒷막을 세우긴 했는데 **뒷막을 누르면
//     그대로 닫혔다** — 적던 값이 아무 말 없이 사라졌다.
//
// 그래서 여는 자리·닫는 자리·묻는 자리를 여기 하나로 모은다. 화면이 넘겨 주는
// 것은 "지금 폼이 어떻게 생겼나"(`snapshot`) 하나뿐이고, 나머지 판단은 전부
// 여기 있다.
//
// ── 쓰는 법 ──────────────────────────────────────────────────────────────
//
//   var modal = window.PanelModal.init({
//     panel: "#detail-panel",            // 창 자체 (필수)
//     backdrop: "#detail-backdrop",      // 뒷막 — 없으면 안 세운다
//     closers: ["#detail-close"],        // [닫기] 단추들
//     snapshot: function () { return JSON.stringify(readForm()); },
//     ask: "…"                           // 물을 말 (없으면 기본 문구)
//   });
//
//   modal.open();          창·뒷막을 세우고 **지금 폼을 기준선으로 잡는다**
//   modal.mark();          기준선을 다시 잡는다 (폼을 나중에 채우는 화면용)
//   modal.isDirty();       기준선과 달라졌는가
//   modal.allowLeave(말);  안 달라졌으면 그냥 true, 달라졌으면 묻는다
//   modal.close();         묻고 나서 닫는다 · close(true) 는 묻지 않고 닫는다
//
// **`snapshot` 은 저장할 때 보내는 것과 같은 것을 읽어야 한다.** 화면에 보이는
// 글자를 따로 긁어 모으면, 저장에는 가는데 기준선에는 없는 칸이 생겨 "안 고쳤는데
// 묻는" 창이 된다 — 그러면 사람은 곧 확인창을 안 읽고 누른다.
(function (global) {
  "use strict";

  var ASK = "고친 내용이 아직 저장되지 않았습니다. 버리고 닫을까요?\n\n" +
            "[취소] 를 누르면 창에 그대로 남습니다 — 남기려면 [저장] 을 누르세요.";

  function node(x) {
    if (!x) return null;
    return typeof x === "string" ? document.querySelector(x) : x;
  }

  function init(opts) {
    opts = opts || {};
    var panel = node(opts.panel);
    // 창이 없는 화면에서도 나머지가 죽지 않아야 한다 — 이 파일은 화면 여럿이
    // 함께 부르고, 그중에는 창을 안 그리는 화면이 있다.
    if (!panel) return null;

    var backdrop = node(opts.backdrop);
    var snapshot = typeof opts.snapshot === "function" ? opts.snapshot : null;
    var base = null;      // 기준선. null = 아직 안 잡았다(= 안 열려 있다)

    function isOpen() { return !panel.hidden; }

    // 지금 폼 모습을 기준선으로 잡는다. **채워 넣은 바로 뒤에** 부른다 —
    // 채우기 전에 잡으면 채운 것 자체가 '고친 것'이 되어 매번 묻는다.
    function mark() { base = snapshot ? snapshot() : null; }

    function isDirty() {
      if (!snapshot || !isOpen() || base === null) return false;
      return snapshot() !== base;
    }

    // 이 창을 떠나도 되는가. 떠나는 길이 여럿이라(뒷막 · Escape · [닫기] ·
    // 다른 줄 누르기) 판단은 여기 하나로 둔다.
    function allowLeave(message) {
      if (!isDirty()) return true;
      return !!global.confirm(message || opts.ask || ASK);
    }

    function open() {
      panel.hidden = false;
      if (backdrop) backdrop.hidden = false;
      mark();
    }

    // `force === true` 면 묻지 않는다 — 저장·삭제처럼 사람이 이미 정한 길.
    function close(force) {
      if (force !== true && !allowLeave()) return false;
      panel.hidden = true;
      if (backdrop) backdrop.hidden = true;
      base = null;
      if (typeof opts.onClose === "function") opts.onClose();
      return true;
    }

    // 뒷막을 누르면 **묻고 나서** 닫는다. 그냥 닫으면 적던 값이 아무 말 없이
    // 사라진다 — 딜 기업 DB 가 그랬다.
    if (backdrop) backdrop.addEventListener("click", function () { close(); });

    (opts.closers || []).forEach(function (sel) {
      var btn = node(sel);
      if (btn) btn.addEventListener("click", function () { close(); });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape" || !isOpen()) return;
      close();
    });

    return {
      open: open, close: close, mark: mark,
      isDirty: isDirty, allowLeave: allowLeave, isOpen: isOpen,
      panel: panel, backdrop: backdrop
    };
  }

  global.PanelModal = { init: init };
})(window);
