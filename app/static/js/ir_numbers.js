// IR 요청 기록 — 지난 회차의 **번호**로 고른다.
//
// 투자사는 "4번, 6번 주세요" 라고 답한다. 그 번호가 어느 기업인지 사람이
// 지난 카톡을 뒤져 맞추고 있었다. 담당자를 고르면 그 사람에게 마지막으로 보낸
// 회차의 번호를 그대로 보여주고, 눌러서 기록하게 한다.
(function () {
  var form = document.getElementById("new-request");
  if (!form) return;

  var select = form.querySelector('select[name="contact_id"]');
  var box = document.getElementById("last-batch");
  var title = document.getElementById("last-batch-title");
  var pick = document.getElementById("num-pick");
  var textarea = document.getElementById("request-companies");
  if (!select || !box || !pick || !textarea) return;

  // 응답이 오는 사이에 또 부르면 두 응답이 **모두** 그려져 번호가 두 줄로 나온다
  // (담당자를 빠르게 바꾸거나, 화면이 열리면서 한 번 더 부를 때). 마지막으로
  // 부른 것만 그린다.
  var turn = 0;

  function load() {
    var id = select.value;
    var mine = ++turn;
    box.hidden = true;
    pick.innerHTML = "";
    if (!id) return;

    fetch("/api/ir/last-batch/" + id)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (mine !== turn) return;          // 그 사이 다른 담당자를 골랐다
        if (!d || !d.items || !d.items.length) return;
        pick.innerHTML = "";
        box.hidden = false;
        title.textContent = d.title + (d.sent_date ? " · " + d.sent_date : "");
        d.items.forEach(function (item) {
          var b = document.createElement("button");
          b.type = "button";
          b.className = "num-chip" + (item.has_link ? "" : " no-link");
          b.textContent = item.position + ") " + item.name;
          b.title = item.has_link ? item.name : item.name + " — IR 자료 링크 없음";
          b.addEventListener("click", function () { toggle(b, item.name); });
          pick.appendChild(b);
        });
      })
      .catch(function () { /* 지난 회차가 없어도 직접 적으면 된다 */ });
  }

  function toggle(button, name) {
    var lines = textarea.value.split("\n").map(function (v) { return v.trim(); })
      .filter(Boolean);
    var at = lines.indexOf(name);
    if (at >= 0) {
      lines.splice(at, 1);
      button.classList.remove("picked");
    } else {
      lines.push(name);
      button.classList.add("picked");
    }
    textarea.value = lines.join("\n");
  }

  select.addEventListener("change", load);
  load();
})();

// 전달한 자료에서 바로 미팅 잡기.
//
// 미팅은 **자료를 보낸 그 건**에서 이어진다 — 담당자·기업을 처음부터 다시
// 고르게 하면 이미 아는 정보를 사람이 또 타이핑하는 셈이고, 그러다 다른
// 담당자를 골라 엉뚱한 곳에 미팅이 잡힌다.
(function () {
  var box = document.getElementById("new-meeting");
  if (!box) return;

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-book-meeting");
    if (!btn) return;

    var contact = btn.getAttribute("data-contact");
    var company = btn.getAttribute("data-company") || "";
    // 미팅 후기에서 넘어오면 다음 차수를 미리 골라 준다(1차 → 2차).
    // 흐름은 일직선이 아니다 — 검토 중이면 다시 미팅으로 돌아간다.
    var kind = btn.getAttribute("data-kind") || "";

    var select = box.querySelector('select[name="contact_id"]');
    if (select) select.value = contact;
    var companyInput = box.querySelector('input[name="company_name"]');
    if (companyInput) companyInput.value = company;
    var kindSelect = box.querySelector('select[name="kind"]');
    if (kindSelect && kind) kindSelect.value = kind;

    box.hidden = false;
    box.scrollIntoView({ block: "center" });
    var when = box.querySelector('input[name="scheduled_at"]');
    if (when) when.focus();
  });
})();
