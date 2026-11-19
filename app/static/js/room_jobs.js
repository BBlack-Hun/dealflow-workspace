// 방 찾기 화면의 **아직 도는 회차** — 진행 셈과 [중단] (`_room_jobs.html`).
// (node tests/js/room_jobs_test.js)
//
// 발송 진행 화면(`progress.js`)과 같은 자리를 같은 간격으로 묻는다 — 셈은
// `/api/jobs/{id}`, [중단]은 `/api/jobs/{id}/cancel`(남은 건은 찾기 전 그대로 남는다).
// 회차가 끝나면(다 돌았거나 중단) 화면을 새로 열어 표가 결과를 보이게 한다.
(function () {
  var POLL_MS = 2000;
  var ENDED = { done: 1, done_with_errors: 1, canceled: 1 };

  Array.prototype.forEach.call(document.querySelectorAll(".js-room-job"), function (box) {
    var id = box.getAttribute("data-job");
    var done = box.querySelector(".js-room-job-done");
    var stop = box.querySelector(".js-room-job-stop");

    function later() { setTimeout(ask, POLL_MS); }
    function ask() {
      fetch("/api/jobs/" + id, { headers: { "Accept": "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) return;                         // 볼 수 없는 회차 — 그만 묻는다
          if (ENDED[d.status]) { location.reload(); return; }
          if (done && d.counts) done.textContent = d.counts.sent + d.counts.failed;
          later();
        })
        .catch(later);
    }
    later();

    if (stop) stop.addEventListener("click", function () {
      if (!confirm("카톡방 찾기를 중단하시겠습니까? 남은 분은 찾기 전 그대로 남습니다.")) return;
      stop.disabled = true;
      fetch("/api/jobs/" + id + "/cancel", { method: "POST" })
        .then(function (r) {
          if (!r.ok) throw new Error();
          location.reload();
        })
        .catch(function () {
          stop.disabled = false;
          alert("중단하지 못했습니다 — 이 회차를 건 계정으로 다시 눌러 보세요");
        });
    });
  });
})();
