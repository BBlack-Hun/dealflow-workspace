/* 스타트업 명단 수정창의 **IR 기업 연결 표시** — `IR 기업: ○○ (연결됨)` / `연결 안 됨 → 연결하기`.
 * (node tests/js/ir_link_test.js)
 *
 * 무엇을 보일지는 서버가 정해 보낸다(`GET /api/contacts/{id}` 의 `ir_link` —
 * `services/ir_link.badge`). 여기서는 그 값을 글자로 옮기기만 한다.
 *
 * 수정창 부품(`contacts.js`)이 줄을 불러올 때마다 `IrLinkBadge.show(값)` 을
 * 부른다. 새 줄을 넣을 때는 `show(null)` — 아직 없는 줄에는 이을 것이 없다.
 * 이 칸이 없는 화면(투자사 관리 현황)에서는 아무 일도 하지 않는다.
 */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function html(info) {
    if (info.linked) {
      return 'IR 기업: <a href="' + esc(info.company_href) + '">' + esc(info.name) +
        '</a> <span class="room-badge ok">연결됨</span> · ' +
        '<a class="linkbtn" href="' + esc(info.link_href) + '">바꾸기</a>';
    }
    var hint = info.candidates ? " (이름이 같은 IR 기업 " + info.candidates + "곳)" : "";
    return 'IR 기업: <span class="muted">연결 안 됨' + esc(hint) + '</span> → ' +
      '<a class="linkbtn" href="' + esc(info.link_href) + '">연결하기</a>';
  }

  window.IrLinkBadge = {
    show: function (info) {
      var box = document.getElementById("ir-link-badge");
      if (!box) return;
      if (!info) {
        box.hidden = true;
        box.innerHTML = "";
        return;
      }
      box.innerHTML = html(info);
      box.hidden = false;
    }
  };
})();
