/* IR 기업 연결 — [연결 해제] 확인 · 일괄 연결 확인 화면의 수 세기.
 * (node tests/js/ir_link_test.js)
 *
 * ## 여기서 판단하지 않는다  ★
 *
 * 어느 줄을 이을 수 있는지, 후보가 무엇인지는 **서버가 정한다**
 * (`routers/ir_link.py`). 단추는 전부 폼이라 이 파일이 없어도 화면은 돈다 —
 * 여기서 하는 일은 둘뿐이다.
 *
 *   1. [연결 해제] 는 누르기 전에 한 번 묻는다. 푼 줄은 `후보` 로 돌아가는데,
 *      그 기업이 이름이 다른 곳이면(직접 찾아 이은 줄) 다시 찾아야 한다.
 *   2. 일괄 연결 확인 화면에서 체크를 풀면 **단추의 수**가 따라간다. 처음 수
 *      그대로 두면 `12줄 연결` 이라 적힌 단추가 10줄을 잇는다.
 */
(function () {
  "use strict";

  // ── 1. [연결 해제] ──────────────────────────────────────────────────────
  Array.prototype.forEach.call(document.querySelectorAll(".ir-unlink-form"), function (form) {
    form.addEventListener("submit", function (e) {
      var btn = form.querySelector(".ir-unlink-btn");
      var name = btn ? btn.getAttribute("data-name") || "" : "";
      var company = btn ? btn.getAttribute("data-company") || "" : "";
      if (!window.confirm("'" + name + "' 줄을 IR 기업 '" + company + "' 에서 풉니다.\n" +
          "(줄도 IR 기업도 지워지지 않습니다 — 이은 것만 풉니다)")) {
        e.preventDefault();
      }
    });
  });

  // ── 2. 일괄 연결 확인 화면 ─────────────────────────────────────────────
  var bulk = document.getElementById("ir-link-bulk-form");
  if (!bulk) return;
  var picks = bulk.querySelectorAll(".ir-bulk-pick");
  var go = document.getElementById("ir-link-bulk-go");
  var count = document.getElementById("ir-link-bulk-n");

  function picked() {
    var n = 0;
    Array.prototype.forEach.call(picks, function (box) { if (box.checked) n += 1; });
    return n;
  }

  function refresh() {
    var n = picked();
    if (count) count.textContent = String(n);
    var label = go ? go.querySelector(".ir-bulk-label") : null;
    if (label) label.textContent = n + "줄 연결";
    if (go) go.disabled = n === 0;
  }

  Array.prototype.forEach.call(picks, function (box) {
    box.addEventListener("change", refresh);
  });
  // 이 화면이 곧 확인 단계다 — 한 번 더 묻지 않는다. 다 풀었으면 보내지 않는다.
  bulk.addEventListener("submit", function (e) {
    if (!picked()) e.preventDefault();
  });
  refresh();
})();
