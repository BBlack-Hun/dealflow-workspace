var MAX_COMPANIES = 10;   // 서버 MAX_COMPANIES_PER_SEND 와 동일하게 유지
var WARN_CHARS = 3000;    // 서버 MESSAGE_WARN_CHARS 와 동일하게 유지
// 딜소개 보내기 — selection, preview, send-list creation (FEATURE_SPEC §5).
(function () {
  // 고르는 기업 상자. **Series A 딜 공유**(딜 소싱 제안의 셋째 글)를 고르면
  // ① 칸이 `Series A 이상 기업` 고르개(`#series-a-list`)로 바뀌고, 고른 차례 ·
  // 번호 배지 · 10개 한도가 그 상자를 그대로 따른다 — 셈을 한 벌 더 두지 않는다.
  var companyCbs = function () {
    return Array.prototype.slice.call(document.querySelectorAll(
      isShare() ? "#series-a-list .sa-cb" : ".company-cb"));
  };
  // 대상 목록이 두 개다(투자사 담당자 / 딜 소싱 명단). **지금 보이는 쪽만**
  // 센다 — 숨은 목록에 체크가 남아 있는데 그것까지 보내면, 화면에 없는
  // 사람에게 나간다.
  var activeList = function () {
    return document.getElementById(mode === "sourcing" ? "sourcing-list" : "contact-list");
  };
  var contactCbs = function () {
    var box = activeList();
    return box ? Array.prototype.slice.call(box.querySelectorAll(".contact-cb")) : [];
  };
  var companyPill = document.getElementById("company-pill");
  var contactPill = document.getElementById("contact-pill");
  var contactSummary = document.getElementById("contact-summary");
  // 아래 단추를 매는 자리보다 **위**에서 잡아 둔다 — 셈을 다시 하는
  // `updateCounts()` 가 이 단추를 켜고 끄기 때문에, 매는 순서가 바뀌어도
  // 첫 셈에서 조용히 빠지는 일이 없어야 한다.
  var clearAllBtn = document.getElementById("clear-all-contacts");
  var ssCompanies = document.getElementById("ss-companies");
  var ssContacts = document.getElementById("ss-contacts");
  var ssNote = document.getElementById("ss-note");
  var companyPanel = document.querySelector("#company-list").closest(".panel");
  var mode = "deal";
  // 딜소개 말고는 전부 기업 목록 없이 문구만 나간다.
  // 이미 목록을 받은 사람에게 같은 목록을 다시 밀어 넣는 것은 후속이 아니라 재발송이다.
  var FOLLOW_UP = { ask: "선호 분야 묻기", remind: "리마인드", meeting: "미팅 요청",
                    review: "미팅 후기", ir: "IR 자료 전달",
                    sourcing: "딜 소싱 제안" };
  // ── 딜 소싱 제안의 [보낼 문구] ─────────────────────────────────────────
  //
  // 처음 참여 안내(`sourcing_intro`) / 월간 리마인드(`sourcing_remind`). 받는
  // 명단과 보내는 길은 같고 **글만 다르다** — 서버가 이 값을 받아 글을 고른다
  // (`routers/deals.py` 의 `_sourcing_topic`). 잡 종류는 둘 다 같다.
  //
  // 리마인드는 **이 달 딜 받음**(`data-received="1"`)인 분을 기본으로 뺀다 —
  // 이미 이 달 딜을 보내 주신 분께 "이번 달 딜 부탁드립니다" 가 가면 안 읽은
  // 사람으로 보인다. [이번 달 딜 받음 포함] 을 켜면 넣는다. 서버도 같은 판단을
  // 한 번 더 한다(`include_received`) — 화면을 연 뒤에 바뀐 표시가 있다.
  var INTRO = "sourcing_intro";
  var REMIND = "sourcing_remind";
  // ── Series A 딜 공유 ───────────────────────────────────────────────────
  //
  // 셋째 글 — 시리즈 A 갈래 심사역께 `Series A 이상 기업` 탭의 받은 딜을 소개한다
  // (`services/series_a_share.py`). 받는 갈래가 **하나뿐**이라 다른 갈래 카드는
  // 고를 수 없다(`data-bucket` — 서버가 칩에 실어 준다). 고른 기업을 **모두 이미
  // 받은 분**은 [이미 이 기업들을 받은 분 제외](기본 켬)로 빠진다 — 고른 채로
  // 두되(고른 사람은 언제나 보인다) 흐리게 하고 보내지 않는다. 일부만 받은 분은
  // 서버가 받은 기업을 빼고 짓는다. 끄면 `include_shared` 가 실려 다 보낸다.
  //
  // **본인이 공유한 딜**(`data-own-by`)은 그 분께 늘 빠진다(켜고 끄는 칸이 없다).
  // 그리고 사람마다 **사람당 N개**(`#sa-per-person`, 기본 2)만 간다 — 본인 공유 ·
  // 이미 받은 기업을 빼고 고른 차례 앞에서부터. 무엇을 보낼지는 서버가 정한다
  // (`series_a_share.plan`); 여기서는 **보낼 기업이 하나도 안 남는 분**을 빼고
  // (`isShareCovered`) 몇 곳이 빠지는지 말한다.
  var SHARE = "sourcing_deal_share";
  var shareChip = document.querySelector('#sourcing-topic .chip[data-value="' + SHARE + '"]');
  var SHARE_BUCKET = (shareChip && shareChip.getAttribute("data-bucket")) || "";
  var SHARE_LABEL = "Series A 딜 공유";
  // 미리보기 `뺀 기업` 줄에서 본인 공유를 도드라지게 — 서버의 `OWN_REASON` 글자.
  var OWN_REASON = "본인이 공유한 딜";
  var excludeShared = true;
  var sourcingTopic = INTRO;
  var includeReceived = false;
  function isRemind() { return mode === "sourcing" && sourcingTopic === REMIND; }
  function isShare() { return mode === "sourcing" && sourcingTopic === SHARE; }
  // 이 카드는 지금 **보낼 수 없는** 사람인가 — 리마인드에서 이 달 딜 받음이고,
  // 포함을 켜지 않았다. 또는 화면을 연 뒤에 딜 소싱 `불참여` 가 되었다
  // (`data-out` — 명단을 다시 읽을 때 선다). 불참여는 처음 안내도 리마인드도
  // 안 나간다 — 켜는 칸이 없다(서버도 막는다: `routers/deals.py` 의 `OUT_NOTE`).
  function isExcluded(card) {
    if (!card) return false;
    if (card.getAttribute("data-out") === "1") return true;
    // Series A 딜 공유는 그 갈래 분께만 — 다른 갈래 카드는 고를 자리가 아니다
    // (서버도 뺀다: `series_a_share.NOT_BUCKET_NOTE`).
    if (isShare() && (card.getAttribute("data-bucket") || "") !== SHARE_BUCKET) return true;
    return isRemind() && !includeReceived &&
      card.getAttribute("data-received") === "1";
  }

  // ── Series A 딜 공유 — 누가 무엇을 이미 받았나 ──────────────────────────
  //
  // 기업 카드의 `data-sent-to`(그 기업을 받은 심사역 번호들 — 서버가 대기 · 보낸
  // 것만 센다)를 한 번 읽어 둔다. 이 화면을 연 뒤에 나간 것은 서버가 발송 때
  // 한 번 더 본다(`create_send_list` — 이미 받은 기업은 빼고, 다 받은 분은 뺀다).
  var SENT_TO = {};
  // 기업 → **그 딜을 공유해 준** 심사역 번호들(`data-own-by` — 서버가 이름 ·
  // 회사로 맞춘다: `series_a_share.own_by_company`).
  var OWN_BY = {};
  function idSet(raw) {
    var set = {};
    (raw || "").split(",").forEach(function (v) { v = v.trim(); if (v) set[v] = true; });
    return set;
  }
  Array.prototype.slice.call(document.querySelectorAll("#series-a-list .sa-cb"))
    .forEach(function (cb) {
      var card = cb.closest(".pick-card");
      SENT_TO[cb.value] = idSet(card && card.getAttribute("data-sent-to"));
      OWN_BY[cb.value] = idSet(card && card.getAttribute("data-own-by"));
    });
  // ── 사람당 보낼 기업 수 ─────────────────────────────────────────────────
  // 서버 기본값 · 한도와 같다(`series_a_share.PER_PERSON_DEFAULT` · `_MAX`).
  // 칸이 비거나 엉뚱한 값이면 기본값으로 읽는다 — 서버는 1~10 밖이면 멈춘다.
  var PER_PERSON_DEFAULT = 2;
  var perPersonBox = document.getElementById("sa-per-person");
  var PER_PERSON_MAX = (perPersonBox && parseInt(perPersonBox.getAttribute("max"), 10))
    || MAX_COMPANIES;
  function readPerPerson() {
    var n = parseInt(perPersonBox ? perPersonBox.value : "", 10);
    if (!(n >= 1)) n = PER_PERSON_DEFAULT;
    return Math.min(n, PER_PERSON_MAX);
  }
  var perPerson = readPerPerson();
  // 고르개 옆 안내 — 서버가 처음 그린 글(`series_a_share.per_person_hint`)과 같은 식.
  function perPersonHint(n) {
    var top = Math.min(n * 2, PER_PERSON_MAX);
    var span = top > n ? n + "~" + top : String(n);
    return "기업을 " + span + "개 고르면 사람마다 본인 공유·이미 받은 기업을 빼고 " +
      "앞에서부터 " + n + "개씩 나갑니다.";
  }
  // 지금 고른 Series A 기업 번호(차례는 상관없다 — 견주기만 한다).
  function pickedSeriesA() {
    if (!isShare()) return [];
    return companyCbs().filter(function (c) { return c.checked; })
      .map(function (c) { return c.value; });
  }
  function cardId(card) {
    var cb = card && card.querySelector(".contact-cb");
    return cb ? String(cb.value) : "";
  }
  // 이 분께 고른 기업 중 — 본인이 공유한 곳(`own`, 늘 뺀다) · 이미 받은 곳
  // (`got`, 제외를 켰을 때 뺀다) · 남는 곳(`left`) · 실제로 갈 곳(`send` — 사람당 N개).
  // 서버의 `series_a_share.plan` 과 같은 셈이다(본인 공유가 이미 받음보다 먼저).
  function shareCounts(card, picks) {
    var id = cardId(card);
    var out = { own: 0, got: 0, left: 0, send: 0 };
    picks.forEach(function (p) {
      if ((OWN_BY[p] || {})[id]) { out.own += 1; return; }
      if ((SENT_TO[p] || {})[id]) {
        out.got += 1;
        if (excludeShared) return;
      }
      out.left += 1;
    });
    out.send = Math.min(out.left, perPerson);
    return out;
  }
  // 본인 공유 · 이미 받은 기업을 빼고 나니 **보낼 기업이 없어** 이번에 빠지는 분인가.
  function isShareCovered(card, picks) {
    if (!isShare() || !card) return false;
    picks = picks || pickedSeriesA();
    return picks.length > 0 && shareCounts(card, picks).left === 0;
  }
  // 요약줄·확인창이 부르는 이름. 리마인드를 `딜 소싱 제안` 이라고 적으면 무엇을
  // 보내는지 마지막 확인창에서도 안 갈린다.
  function modeLabel() {
    return isRemind() ? "딜 소싱 리마인드" : (isShare() ? SHARE_LABEL : FOLLOW_UP[mode]);
  }
  // IR 자료 전달은 기업을 고른다(무엇을 보내는지 알아야 한다).
  // 나머지 후속 문구는 기업과 무관하다.
  var NEEDS_COMPANIES = { deal: true, ir: true };
  function isFollowUp() { return !!FOLLOW_UP[mode]; }
  // Series A 딜 공유도 기업을 고른다(그 고르개 — `#series-a-list`).
  function needsCompanies() { return !!NEEDS_COMPANIES[mode] || isShare(); }
  // 회차명 — **방식마다 다르다.** 정규 발송(딜 소개)만 주차를 달고
  // (`09/16 (9월 3주차)`), 나머지는 주차 대신 무엇을 보내는지가 들어간다
  // (`09/09 (리마인드)`). 서버가 방식마다 한 벌씩 만들어 `data-titles` 에
  // 실어 준다 — 여기서 만들면 회차일·주차 규칙이 두 벌이 된다.
  //
  // 탭을 누르면 따라 바꿔야 한다. 서버가 처음 채워 준 것은 딜 소개 이름이라,
  // 그대로 두면 **딜소개 이름을 단 채 리마인드가 나간다** — 발송 이력에서
  // 무엇을 보낸 회차인지 이름으로는 갈라지지 않는다.
  var titleBox = document.getElementById("batch-title");
  var MODE_TITLES = (function () {
    if (!titleBox) return {};
    try { return JSON.parse(titleBox.getAttribute("data-titles") || "{}"); }
    catch (e) { return {}; }
  })();
  // **우리가 채워 넣은 값**. 사람이 손으로 고쳤는지 가리는 유일한 기준이다 —
  // 지금 칸이 이것과 다르면 사람이 쓴 이름이므로 덮어쓰지 않는다.
  var filledTitle = titleBox ? titleBox.value : "";
  // 열쇠는 방식이고, 딜 소싱 리마인드만 문구 종류다(서버가 `sourcing_remind`
  // 이름표도 함께 실어 준다 — `pages.py` 의 `TOPIC_TITLES`).
  function titleKey() { return isRemind() ? REMIND : (isShare() ? SHARE : mode); }
  function syncBatchTitle() {
    if (!titleBox) return;
    var next = MODE_TITLES[titleKey()] || MODE_TITLES[mode];
    if (!next) return;                       // 서버가 모르는 방식 — 그대로 둔다
    if (titleBox.value.trim() !== filledTitle.trim()) return;   // 사람이 고친 이름
    titleBox.value = next;
    filledTitle = next;
  }
  var previewTabs = document.getElementById("preview-tabs");
  var previewArea = document.getElementById("preview-area");
  var warnBox = document.getElementById("send-warnings");
  // 링크를 타고 들어오며 **못 고른 것**(담당자·기업). 미리보기 응답이 이 칸을
  // 통째로 다시 쓰기 때문에(`refreshPreview` 끝), 거기 그냥 적어 두면 화면을
  // 연 한 박자 뒤에 말없이 지워진다 — 실제로 그랬다. 그래서 따로 들고 있다가
  // 미리보기 경고와 **함께** 세운다. 방식 탭을 사람이 누르면 지운다(`setMode`).
  var incomingWarns = [];
  function showWarnings(extra) {
    var all = incomingWarns.concat(extra || []);
    warnBox.hidden = !all.length;
    warnBox.innerHTML = all.map(escapeHtml).join("<br>");
  }
  var sendBtn = document.getElementById("send-btn");
  var lastPreviews = [];
  // **지금 열어 둔 미리보기 탭**(담당자 하나). [보낼 자료] 목록의 번호가 이
  // 탭을 따른다 — 번호는 담당자마다 다르기 때문에 "누구 것인지" 없이는 적을
  // 수 없다(`renderIrLinks` 설명 참고).
  var currentPreview = 0;
  // 복사 단추의 글자. **공용 한 벌에서 읽는다** — 복사가 끝나면 그쪽이
  // 이 글자로 되돌리므로, 여기 따로 적어 두면 둘이 갈리는 날 단추가
  // 딴 글자로 바뀐 채 남는다.
  var COPY_LABEL = window.IrAttach.COPY_LABEL;

  // ── 고른 차례 ─────────────────────────────────────────────
  //
  // 문구는 `[기업1] …` `[기업2] …` 로 나가고 투자사는 **그 번호로 기억해서** "2번 자료
  // 주세요" 라고 답한다. 그래서 어느 기업이 몇 번인지가 이 화면의 알맹이다.
  //
  // `querySelectorAll` 이 주는 것은 **목록에 그려진 차례**다. 그것만 쓰면 3번째
  // 기업을 먼저 고르고 1번째를 나중에 골라도 목록 차례로 나가서, 사람이 머리에
  // 담은 차례와 실제로 나간 번호가 어긋난다.
  //
  // ## 차례를 어디에 담는가 — **카드에 적는다**(`data-pick-order`)
  //
  // 화면 안 변수에 따로 들고 있지 않는다. 그러면 "무엇을 골랐나"(체크박스)와
  // "몇 번째로 골랐나"(변수)가 **두 벌**이 되고, 어느 한쪽만 바뀌는 길이 생기면
  // 화면에 보이는 번호와 서버로 나가는 차례가 조용히 갈린다 — 이 저장소가
  // 반복해 겪은 일이다. 카드 하나에 둘을 함께 두면 갈릴 자리가 없다.
  //
  // 카드에 둔 덕에 **번호를 따로 그리지 않아도 된다** — CSS 가 이 속성을 그대로
  // 읽어 배지로 띄운다(`#company-list .pick-card[data-pick-order]::before`).
  // 번호를 화면에 한 번 더 적어 두면 그 순간 두 벌이 된다.
  //
  // 새로고침하면 **번호는 사라진다.** 서버가 그리는 체크박스는 전부 꺼진 채라
  // 고른 것 자체가 없어지기 때문이고, 그게 맞다 — 화면이 서버가 모르는 차례를
  // 기억하고 있으면 안 된다. 차례가 오래 남는 곳은 보내거나 예약한 뒤의 서버
  // 쪽이다(`DealBatchCompany.position` · `DealQueueCompany.position`).
  //
  // ## 자료 전달에서는 **고른 차례가 번호가 아니다**
  //
  // 그때의 번호는 딜 소개에서 이미 붙인 번호다(`services/deal_numbers.py`).
  // 투자사가 "2번 주세요" 라고 답한 그 번호라 담당자마다 다르고, 카드 하나에
  // 적을 수 있는 값이 아니다. 그런데도 고른 차례를 배지로 띄우면 화면은 `1`,
  // 문구는 `[기업2] …` 가 되어 **어느 쪽이 맞는지 알 수 없다.** 그래서 이
  // 탭에서는 배지를 비운다(`no-pick-badge`) — 실제 번호는 담당자별 미리보기
  // 문구에 그대로 적혀 있다. 차례 자체는 그대로 쓴다: 문구가 기업을 짚는
  // 차례이자 [보낼 자료] 목록의 차례다.
  function cardOf(cb) { return cb.closest(".pick-card"); }

  function pickOrderOf(card) {
    var n = parseInt(card.getAttribute("data-pick-order") || "0", 10);
    return n > 0 ? n : 0;
  }

  // 고른 카드를 **고른 차례대로**. 번호를 다시 매기는 일도 여기서 함께 한다.
  function renumberPicks() {
    var numbered = [];   // 이미 번호가 있는 것
    var fresh = [];      // 방금 켠 것 — 아직 번호가 없다
    companyCbs().forEach(function (cb) {
      var card = cardOf(cb);
      if (!card) return;
      // 체크를 풀면 번호를 지운다. 남겨 두면 다시 골랐을 때 **아까 쓰던 번호로
      // 되돌아가** 방금 고른 것이 앞으로 끼어든 줄 모른 채 나간다.
      if (!cb.checked) { card.removeAttribute("data-pick-order"); return; }
      (pickOrderOf(card) ? numbered : fresh).push(card);
    });
    numbered.sort(function (a, b) { return pickOrderOf(a) - pickOrderOf(b); });
    // 빈 번호 없이 1부터 다시 붙인다 — 가운데를 풀면 뒤가 당겨져야 화면의
    // 번호와 문구의 `[기업1] [기업2] [기업3]` 이 같아진다.
    var picked = numbered.concat(fresh);
    picked.forEach(function (card, i) {
      card.setAttribute("data-pick-order", String(i + 1));
    });
    return picked;
  }

  // **읽으면서 번호를 다시 매긴다.** 읽는 자리와 번호를 붙이는 자리를 떼어
  // 놓으면, 한쪽만 불린 길에서 화면의 번호와 나가는 차례가 갈린다.
  function selectedCompanyIds() {
    var box = isShare() ? ".sa-cb" : ".company-cb";
    return renumberPicks().map(function (card) {
      return parseInt(card.querySelector(box).value, 10);
    });
  }
  function selectedContactIds() {
    return sendableBoxes().map(function (c) { return parseInt(c.value, 10); });
  }
  // **보낼** 체크 — 리마인드에서 뺀 사람은 체크가 남아 있어도 보내지 않는다
  // (`dropExcluded` 가 체크를 끄지만, 끄는 길을 하나라도 놓치면 여기서 걸린다).
  // Series A 딜 공유에서 고른 기업을 다 받은 분은 체크를 **남긴 채** 뺀다 —
  // 기업을 바꾸면 다시 들어와야 하기 때문이다.
  function sendableBoxes() {
    var picks = pickedSeriesA();
    return contactCbs().filter(function (c) {
      var card = c.closest(".pick-card");
      return c.checked && !isExcluded(card) && !isShareCovered(card, picks);
    });
  }


  // ── 기업 검색 ─────────────────────────────────────────────
  // 소개 가능한 기업이 100개를 넘어가면 목록을 훑어서 고르기 어렵다.
  // 검색으로 좁히되, **선택한 항목은 검색어와 무관하게 항상 보이게** 한다
  // (검색어를 바꾸다 이미 고른 기업이 사라지면 몇 개 골랐는지 알 수 없다).
  function applyCompanyFilter() {
    if (isShare()) { applySeriesAFilter(); return; }
    var box = document.getElementById("company-search");
    var onlyPicked = document.getElementById("only-picked");
    var note = document.getElementById("company-filter-note");
    if (!box) return;

    var hideRecent = document.getElementById("hide-recent");
    var q = (box.value || "").trim().toLowerCase();
    var pickedOnly = onlyPicked && onlyPicked.checked;
    var skipRecent = hideRecent && hideRecent.checked;
    var shown = 0, total = 0;

    document.querySelectorAll("#company-list .pick-card").forEach(function (card) {
      var cb = card.querySelector(".company-cb");
      var picked = cb && cb.checked;
      var hay = card.getAttribute("data-search") || "";
      var hit = !q || hay.indexOf(q) !== -1;
      var recent = card.getAttribute("data-recent") === "1";
      total += 1;
      // 선택한 항목은 언제나 보인다.
      var visible = picked || (hit && !pickedOnly && !(skipRecent && recent));
      card.hidden = !visible;
      if (visible) shown += 1;
    });

    if (note) {
      if (q || pickedOnly) {
        note.hidden = false;
        note.textContent = shown + " / " + total + "개 표시 중" + (q ? " (검색: " + box.value.trim() + ")" : "");
      } else {
        note.hidden = true;
      }
    }
  }


  // ── Series A 이상 기업 고르개(Series A 딜 공유) ─────────────────────────
  // IR 기업 검색과 같은 규칙: **고른 기업은 검색어와 무관하게 늘 보인다.**
  // 카드마다 `이미 받은 분 N명` — 지금 고른 받는 분 중 이 기업을 받은 분 수.
  // 받는 분을 바꾸면 따라 바뀐다(`updateCounts` 가 부른다).
  function applySeriesAFilter() {
    var box = document.getElementById("sa-pick-search");
    var onlyPicked = document.getElementById("sa-only-picked");
    var onlyFresh = document.getElementById("sa-only-fresh");
    var note = document.getElementById("sa-filter-note");
    var q = ((box && box.value) || "").trim().toLowerCase();
    var pickedOnly = !!(onlyPicked && onlyPicked.checked);
    var freshOnly = !!(onlyFresh && onlyFresh.checked);
    // 지금 고른 받는 분(갈래 밖 · 불참여로 빠진 분은 안 센다).
    var who = contactCbs().filter(function (c) {
      return c.checked && !isExcluded(c.closest(".pick-card"));
    }).map(function (c) { return String(c.value); });
    var shown = 0, total = 0;
    document.querySelectorAll("#series-a-list .pick-card").forEach(function (card) {
      var cb = card.querySelector(".sa-cb");
      if (!cb) return;
      var sent = SENT_TO[cb.value] || {};
      var hit = !q || (card.getAttribute("data-search") || "").indexOf(q) !== -1;
      var fresh = !Object.keys(sent).length;
      var visible = cb.checked || (hit && !pickedOnly && (!freshOnly || fresh));
      card.hidden = !visible;
      total += 1;
      if (visible) shown += 1;
      var got = who.filter(function (id) { return sent[id]; }).length;
      var tag = card.querySelector(".sa-got");
      if (tag) {
        tag.hidden = !got;
        tag.textContent = got ? "이미 받은 분 " + got + "명" : "";
      }
      // 지금 고른 받는 분 중 **이 딜을 공유해 준** 분 — 그 분께는 늘 빠진다.
      var ownBy = OWN_BY[cb.value] || {};
      var own = who.filter(function (id) { return ownBy[id]; }).length;
      var ownTag = card.querySelector(".sa-own");
      if (ownTag) {
        ownTag.hidden = !own;
        ownTag.textContent = own ? "본인 공유 " + own + "명 제외" : "";
      }
    });
    if (note) {
      note.hidden = !(q || pickedOnly || freshOnly);
      note.textContent = note.hidden ? "" : shown + " / " + total + "개 표시 중" +
        (q ? " (검색: " + box.value.trim() + ")" : "");
    }
  }

  // ① 칸을 지금 글에 맞춘다 — Series A 딜 공유면 그 고르개, 아니면 IR 기업 목록.
  // 문구만 나가는 글이면 흐리게(`dimmed`), 자료 전달이면 번호 배지를 비운다.
  var saPicker = document.getElementById("series-a-picker");
  function syncCompanyPanel() {
    var share = isShare();
    companyPanel.classList.toggle("dimmed", !needsCompanies());
    // 자료 전달에서는 고른 차례가 번호가 아니다 — 배지를 비운다(위 설명 참고).
    companyPanel.classList.toggle("no-pick-badge", mode === "ir");
    if (saPicker) saPicker.hidden = !share;
    ["company-list", "company-picker-search", "company-filter-note"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el && share) el.hidden = true;
      else if (el && id !== "company-filter-note") el.hidden = false;
    });
    var hint = document.getElementById("company-hint");
    if (hint) hint.hidden = share || mode === "ir";
  }

  // ── 담당자 검색 ───────────────────────────────────────────
  // 116명 중에서 몇 명을 골라야 한다. 기업 검색과 같은 규칙을 쓴다:
  // **선택한 담당자는 검색어와 무관하게 항상 보인다** — 검색어를 바꾸다
  // 이미 고른 사람이 사라지면 몇 명 골랐는지 알 수 없다.
  function applyContactFilter() {
    var box = document.getElementById("contact-search");
    var onlyPicked = document.getElementById("only-picked-contacts");
    var note = document.getElementById("contact-filter-note");
    if (!box) return;

    var q = (box.value || "").trim().toLowerCase();
    var pickedOnly = onlyPicked && onlyPicked.checked;
    var shown = 0, total = 0, outside = 0;
    // 지금 조건(검색 · 갈래 · 담당) 안에서 이 달 딜 받음인 사람 — 리마인드의
    // `이번 달 딜 받음 N명 제외` 가 이 수다.
    var receivedInView = 0;

    // Series A 딜 공유 — 보낼 기업이 안 남는 분(`covered`) · 본인 공유가 든 분 ·
    // 이미 받은 기업이 든 분 수.
    var picks = pickedSeriesA();
    var coveredInView = 0, ownInView = 0, gotInView = 0;

    var list = activeList();
    (list ? list.querySelectorAll(".pick-card") : []).forEach(function (card) {
      var cb = card.querySelector(".contact-cb");
      var picked = cb && cb.checked;
      var hit = !q || (card.getAttribute("data-search") || "").indexOf(q) !== -1;
      // 갈래 필터는 소싱 목록에만 있다. 고른 사람은 갈래를 바꿔도 계속 보인다 —
      // 사라지면 몇 명 골랐는지 알 수 없다(검색과 같은 규칙).
      var inBucket = !bucketFilter || card.getAttribute("data-bucket") === bucketFilter;
      var inAssignee = !assigneeFilter ||
        card.getAttribute("data-assignee") === assigneeFilter;
      var inGroup = matchesGroup(card);
      // 리마인드에서 뺀 사람은 **조건에도 안 맞고 보이지도 않는다** — 고른 채였어도
      // (`dropExcluded` 가 체크를 끈다). [전체선택]도 그래서 안 닿는다.
      var excluded = isExcluded(card);
      if (mode === "sourcing" && hit && inBucket && inAssignee &&
          card.getAttribute("data-received") === "1") receivedInView += 1;
      // 본인 공유 · 이미 받은 기업을 빼니 보낼 기업이 없어 이번에 빠지는 분 —
      // **조건에 안 맞는 것으로 친다**([전체선택]이 안 켠다). 이미 고른 채면
      // 그대로 보이되 흐리다(보내지 않는다).
      var counts = (isShare() && !excluded && picks.length) ? shareCounts(card, picks) : null;
      var covered = !excluded && isShareCovered(card, picks);
      if (counts && hit && inBucket && inAssignee) {
        if (covered) coveredInView += 1;
        else {
          if (counts.own) ownInView += 1;
          if (counts.got) gotInView += 1;
        }
      }
      syncShareTag(card, counts, covered);
      card.classList.toggle("share-covered", covered);
      total += 1;
      // **조건에 맞는가(match)와 화면에 보이는가(visible)는 다르다.**
      // 고른 사람은 조건에서 벗어나도 계속 보인다(몇 명 골랐는지 알아야 한다).
      // 그래서 `보이는 것 = 조건에 맞는 것` 이라고 읽으면, 그룹으로 추려 놓고
      // [전체선택]을 눌렀을 때 **아까 고른 다른 그룹 사람까지 함께 켜진다** —
      // 실제 투자사에게 문구가 나가는 자리라 그 차이를 여기서 갈라 적어 둔다.
      var matched = hit && inBucket && inAssignee && inGroup && !excluded && !covered;
      var visible = (picked && !excluded) || (matched && !pickedOnly);
      card.setAttribute("data-match", matched ? "1" : "0");
      card.hidden = !visible;
      if (visible) shown += 1;
      if (picked && !matched && !excluded && !covered) outside += 1;
    });
    syncReceivedNote(receivedInView);
    syncSharedNote(coveredInView, ownInView, gotInView);

    if (note) {
      if (q || pickedOnly || bucketFilter || assigneeFilter || groupFilter) {
        note.hidden = false;
        note.textContent = shown + " / " + total + "명 표시 중" +
          (q ? " (검색: " + box.value.trim() + ")" : "") +
          (groupFilter ? " (그룹: " + groupFilter + ")" : "") +
          (bucketFilter ? " (갈래: " + bucketFilter + ")" : "") +
          (assigneeFilter ? " (담당: " + assigneeFilter + ")" : "") +
          // 조건 밖인데 이미 고른 사람은 그대로 발송에 들어간다 — 숫자만
          // 줄어든 줄 알고 보내면 안 되므로 몇 명인지 말해 준다.
          (outside ? " · 조건 밖에서 고른 " + outside + "명이 함께 있습니다" : "");
      } else {
        note.hidden = true;
      }
    }
  }

  // ── 소싱 필터(갈래 · 담당) ────────────────────────────────
  // 갈래는 곧 문구이고, 담당은 누구를 챙길 차례인가다. 둘 다 이름을 검색창에
  // 쳐서 찾게 하면 무엇이 몇 개인지도 모른 채 골라야 한다.
  var bucketFilter = "";
  var assigneeFilter = "";
  var filterBox = document.getElementById("sourcing-filters");

  // ── 그룹 필터(투자사 담당자) ──────────────────────────────
  // 투자사 관리 현황의 `그룹` 칸(`data-f-group`)이 거르는 그 값이다. 표 필터
  // (`filters.js`)는 `th[data-filters]` 와 `tbody tr` 을 걸어 다녀서 카드 묶음인
  // 이 목록에는 붙지 않는다 — 그래서 바로 위 갈래·담당과 **같은 칩 방식**을 쓴다.
  //
  // `(비어 있음)` 이라는 말은 서버가 실어 보낸다(`data-empty`). 여기 한글을
  // 박아 두면 표 쪽 말이 바뀌는 날 한쪽만 고쳐져, 같은 조건인데 두 화면이
  // 서로 다른 사람을 고르게 된다.
  var groupFilter = "";
  var groupBox = document.getElementById("contact-filters");
  var groupBar = document.getElementById("group-filter");
  var EMPTY_GROUP = (groupBar && groupBar.getAttribute("data-empty")) || "";

  function matchesGroup(card) {
    if (!groupFilter) return true;
    // 소싱 명단에는 그룹이라는 것이 없다 — 그쪽 카드까지 걸러 버리면
    // 목록이 통째로 빈다.
    if (mode === "sourcing") return true;
    var value = (card.getAttribute("data-group") || "").trim();
    return groupFilter === EMPTY_GROUP ? value === "" : value === groupFilter;
  }

  function bindFilter(id, set, onPick) {
    var bar = document.getElementById(id);
    if (!bar) return null;
    bar.addEventListener("click", function (e) {
      var chip = e.target.closest(".chip");
      if (!chip) return;
      set(chip.getAttribute("data-value") || "");
      bar.querySelectorAll(".chip").forEach(function (c) {
        c.classList.toggle("active", c === chip);
      });
      applyContactFilter();
      // 갈래를 누르면 **그 갈래 문구**가 떠야 한다. 목록만 걸러 놓으면
      // M&A 를 골라 놓고 시리즈 A 문구를 보며 발송을 누르게 된다.
      // (사람을 고른 뒤에는 그 사람의 갈래가 이기므로 달라지지 않는다)
      if (onPick) onPick();
    });
    return bar;
  }
  var bucketBar = bindFilter("bucket-filter", function (v) { bucketFilter = v; },
                             schedulePreview);
  var assigneeBar = bindFilter("assignee-filter", function (v) { assigneeFilter = v; });
  bindFilter("group-filter", function (v) { groupFilter = v; });

  // [보낼 문구] — 누르면 글이 바뀐다. 문구 고르개(종류가 다르다) · 회차명 ·
  // 미리보기가 따라오고, 리마인드면 이 달 딜 받음인 분이 빠진다.
  var topicBar = document.getElementById("sourcing-topic");
  function markTopicChip() {
    if (topicBar) topicBar.querySelectorAll(".chip").forEach(function (c) {
      c.classList.toggle("active", c.getAttribute("data-value") === sourcingTopic);
    });
  }
  function pickTopic(value) {
    sourcingTopic = value === REMIND ? REMIND : (value === SHARE ? SHARE : INTRO);
    markTopicChip();
    // Series A 딜 공유면 ① 칸이 그 기업 고르개로 바뀐다.
    syncCompanyPanel();
    // 처음 안내용으로 고쳐 둔 글이 리마인드에 얹히면 엉뚱한 말이 나간다
    // (방식을 바꿀 때와 같은 까닭 — `setMode`).
    savedEdits = {};
    dropExcluded();
    syncBatchTitle();
    renderTemplates();
    updateCounts();          // 목록 거르기 · 미리보기가 여기서 따라온다
  }
  if (topicBar) topicBar.addEventListener("click", function (e) {
    var chip = e.target.closest(".chip");
    if (chip) pickTopic(chip.getAttribute("data-value"));
  });

  var includeBox = document.getElementById("include-received");
  if (includeBox) includeBox.addEventListener("change", function () {
    includeReceived = !!includeBox.checked;
    dropExcluded();
    updateCounts();
  });

  // 뺀 사람의 체크를 끈다. 숨기기만 하면 [전체해제] 를 눌러도 안 보이는 체크가
  // 남아 요약줄이 그 사람을 계속 센다.
  function dropExcluded() {
    var box = document.getElementById("sourcing-list");
    if (!box) return;
    box.querySelectorAll(".pick-card").forEach(function (card) {
      if (!isExcluded(card)) return;
      var cb = card.querySelector(".contact-cb");
      if (cb) cb.checked = false;
    });
  }

  // `이번 달 딜 받음 N명 제외` — 몇 명을 뺐는지 말한다. 조용히 빼면 왜 사람이
  // 적은지 모른다. 포함을 켰으면 그 사람들이 들어간다고 말한다.
  function syncReceivedNote(count) {
    var note = document.getElementById("received-note");
    if (!note) return;
    note.hidden = !isRemind();
    var text = document.getElementById("received-count");
    if (!text || note.hidden) return;
    text.textContent = includeReceived
      ? "이번 달 딜 받음 " + count + "명 포함 — 이미 이 달 딜을 보내 주신 분께도 나갑니다"
      : "이번 달 딜 받음 " + count + "명 제외";
  }

  // 받는 분 카드의 딱지(Series A 딜 공유에서만) — 고른 기업 중 무엇이 빠지고
  // 몇 곳이 가는지. 본인 공유 · 이미 받은 곳이 없으면 안 선다(모두 앞에서부터 N개).
  function syncShareTag(card, counts, covered) {
    var tag = card.querySelector(".share-tag");
    if (!tag) return;
    tag.hidden = !(isShare() && counts && (counts.own || counts.got));
    if (tag.hidden) { tag.textContent = ""; return; }
    if (covered) {
      tag.textContent = "보낼 기업 없음 (본인 공유/이미 받음) — 이번엔 빠집니다";
      return;
    }
    var parts = [];
    if (counts.own) parts.push("본인 공유 " + counts.own + "곳 빼고");
    if (counts.got) {
      parts.push(excludeShared ? "이미 받은 " + counts.got + "곳 빼고"
                               : "이미 받은 " + counts.got + "곳도 다시");
    }
    tag.textContent = parts.join(" · ") + " — " + counts.send + "곳 보냅니다";
  }

  // `이미 이 기업들을 받은 분 제외` 줄 — 몇 명이 빠지고 몇 명이 덜 받는지 말한다.
  // 조용히 빼면 왜 사람이 적은지 모른다(이 달 딜 받음 줄과 같은 이유).
  function syncSharedNote(covered, own, got) {
    var note = document.getElementById("shared-note");
    if (!note) return;
    note.hidden = !isShare();
    var text = document.getElementById("shared-count");
    if (!text || note.hidden) return;
    if (!pickedSeriesA().length) {
      text.textContent = "기업을 고르면 본인 공유 · 이미 받은 분을 셉니다";
      return;
    }
    var parts = [];
    if (covered) parts.push("보낼 기업 없는 분 " + covered + "명 제외");
    if (own) parts.push("본인 공유 딜이 든 분 " + own + "명은 그 기업을 빼고");
    if (got) {
      parts.push(excludeShared ? "이미 받은 분 " + got + "명은 받은 기업을 빼고"
                               : "이미 받은 분 " + got + "명에게도 받은 기업을 다시");
    }
    text.textContent = (parts.length ? parts.join(" · ") + " — " : "") +
      "사람마다 앞에서부터 " + perPerson + "개씩 보냅니다";
  }

  var excludeBox = document.getElementById("exclude-shared");
  if (excludeBox) excludeBox.addEventListener("change", function () {
    excludeShared = !!excludeBox.checked;
    updateCounts();
  });

  // 사람당 보낼 기업 수 — 바꾸면 안내 · 딱지 · 미리보기가 따라온다. 칸을 비우거나
  // 범위 밖 값을 넣으면 손을 뗄 때(`change`) 읽은 값으로 되돌려 적는다.
  function syncPerPerson(fix) {
    perPerson = readPerPerson();
    if (fix && perPersonBox) perPersonBox.value = String(perPerson);
    var hint = document.getElementById("sa-per-person-hint");
    if (hint) hint.textContent = perPersonHint(perPerson);
    updateCounts();
  }
  if (perPersonBox) {
    perPersonBox.addEventListener("input", function () { syncPerPerson(false); });
    perPersonBox.addEventListener("change", function () { syncPerPerson(true); });
  }

  function resetSourcingTopic() {
    sourcingTopic = INTRO;
    includeReceived = false;
    if (includeBox) includeBox.checked = false;
    // 제외는 **켠 채로** 되돌린다 — 기본이 켬이다.
    excludeShared = true;
    if (excludeBox) excludeBox.checked = true;
    markTopicChip();
  }

  // ── 딜 소싱 명단을 **다시 읽는다** — 담당 · 이 달 딜 받음 ──────────────────
  //
  // 이 화면은 그릴 때 명단을 한 번 싣는다. 열어 둔 채 딜 소싱 메뉴에서 담당을
  // 바꾸거나 `딜 받음` 을 누르면(메일 확인이 세우기도 한다) 칩과 카드가 옛
  // 값이다 — [딜 소싱 제안] 탭을 열 때와 이 창으로 돌아올 때 서버에서 다시
  // 읽는다(`/api/sourcing/state`). 담당을 자르는 규칙(`가 > 10/13 나` → `나`)은
  // 서버 한 곳에 있다 — 여기서 다시 자르지 않는다.
  var stateSeq = 0;
  function refreshSourcingState() {
    if (mode !== "sourcing") return;
    var seq = ++stateSeq;
    fetch("/api/sourcing/state", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (seq !== stateSeq || !res.ok) return;   // 늦게 온 옛 답은 버린다
        applySourcingState(res.d || {});
      })
      .catch(function () { /* 못 읽어도 화면을 그린 때의 값으로 고를 수 있다 */ });
  }

  function applySourcingState(d) {
    var byId = {};
    (d.rows || []).forEach(function (r) { byId[String(r.id)] = r; });
    var changed = false;
    var box = document.getElementById("sourcing-list");
    (box ? box.querySelectorAll(".pick-card") : []).forEach(function (card) {
      var cb = card.querySelector(".contact-cb");
      var row = cb && byId[String(cb.value)];
      // 그 사이 지워진 줄은 그린 때 그대로 둔다 — 발송은 서버가 다시 본다.
      if (!row) return;
      var who = row.assignee || "";
      var got = row.received ? "1" : "0";
      // 그 사이 `불참여` 가 된 분(딜 소싱 화면 · 투자사 관리 현황의 X).
      var out = row.out ? "1" : "0";
      if (card.getAttribute("data-assignee") !== who ||
          card.getAttribute("data-received") !== got ||
          (card.getAttribute("data-out") || "0") !== out) changed = true;
      card.setAttribute("data-assignee", who);
      card.setAttribute("data-received", got);
      card.setAttribute("data-out", out);
      var outTag = card.querySelector(".out-tag");
      if (outTag) outTag.hidden = !row.out;
      var tag = card.querySelector(".received-tag");
      if (tag) {
        tag.hidden = !row.received;
        if (d.month_label) tag.textContent = d.month_label + " 딜 받음";
      }
    });
    if (rebuildAssigneeChips(d.assignees || [])) changed = true;
    if (!changed) return;      // 그대로면 미리보기를 또 부르지 않는다
    dropExcluded();
    updateCounts();
  }

  // [담당] 칩을 서버가 센 대로 다시 세운다. 고르던 담당이 아직 있으면 그대로,
  // 없어졌으면 [전체]로 — 없는 칩이 켜진 채면 왜 아무도 안 보이는지 모른다.
  function rebuildAssigneeChips(list) {
    if (!assigneeBar) return false;
    var chips = Array.prototype.slice.call(assigneeBar.querySelectorAll(".chip")).slice(1);
    var sig = function (name, count) { return name + "\u0000" + count; };
    var before = chips.map(function (c) {
      return sig(c.getAttribute("data-value") || "", c.getAttribute("data-count") || "");
    }).join("\u0001");
    var after = list.map(function (a) { return sig(a.name, String(a.count)); }).join("\u0001");
    if (before === after) return false;
    chips.forEach(function (c) { assigneeBar.removeChild(c); });
    list.forEach(function (a) {
      var b = document.createElement("button");
      b.setAttribute("type", "button");
      b.className = "chip";
      b.setAttribute("data-value", a.name);
      b.setAttribute("data-count", String(a.count));
      b.innerHTML = escapeHtml(a.name) + " <b>" + Number(a.count) + "</b>";
      assigneeBar.appendChild(b);
    });
    var still = list.some(function (a) { return a.name === assigneeFilter; });
    if (!still) assigneeFilter = "";
    assigneeBar.querySelectorAll(".chip").forEach(function (c) {
      c.classList.toggle("active", (c.getAttribute("data-value") || "") === assigneeFilter);
    });
    return true;
  }

  function refreshWhenBack() {
    if (mode === "sourcing" && !document.hidden) refreshSourcingState();
  }
  document.addEventListener("visibilitychange", refreshWhenBack);
  if (window.addEventListener) window.addEventListener("focus", refreshWhenBack);

  function resetGroupFilter() {
    groupFilter = "";
    if (!groupBar) return;
    groupBar.querySelectorAll(".chip").forEach(function (c, i) {
      c.classList.toggle("active", i === 0);
    });
  }

  function resetSourcingFilters() {
    bucketFilter = "";
    assigneeFilter = "";
    [bucketBar, assigneeBar].forEach(function (bar) {
      if (!bar) return;
      bar.querySelectorAll(".chip").forEach(function (c, i) {
        c.classList.toggle("active", i === 0);
      });
    });
  }

  function syncBucketMixNote() {
    var note = document.getElementById("bucket-mix-note");
    if (!note) return;
    if (mode !== "sourcing") { note.hidden = true; return; }
    var picked = {};
    contactCbs().forEach(function (c) {
      if (!c.checked) return;
      var card = c.closest(".pick-card");
      if (card) picked[card.getAttribute("data-bucket") || ""] = true;
    });
    var names = Object.keys(picked);
    // 갈래를 섞어도 사람마다 제 갈래의 문구가 나간다 — 사고는 아니지만
    // 모르고 섞으면 미리보기에서 다른 문구를 보고 놀란다.
    note.hidden = names.length < 2;
    if (!note.hidden) {
      note.textContent = "갈래 " + names.length + "개가 섞여 있습니다 — " +
        "갈래마다 다른 문구가 나갑니다 (" + names.join(" · ") + ")";
    }
  }

  // ── 고른 사람이 어느 그룹에 걸쳐 있는가 ───────────────────────────────────
  //
  // 그룹 칩은 한 번에 하나만 켜지는데, 고르기는 그 위에 쌓인다 — 1군을 고르고
  // 2군으로 옮겨 [전체선택]을 누르면 발송 대상에 두 그룹이 함께 있다. 그런데
  // 요약 줄은 `곽○○ … 외 119명` 이라고만 적어서, **무엇으로 골랐는지가 화면
  // 에서 사라졌다.** 필터 칩은 지금 걸린 조건 하나만 말하지, 이미 담아 둔 것을
  // 말해 주지 않는다.
  //
  // **그래서 그룹 이름은 하나도 안 줄인다.** 자를 만한 자리를 재 봤는데, 이
  // 칸은 3열 그리드의 가운데라 280px(한글 26자)뿐이다 — 글자 수로 자르면
  // 그룹 이름이 반토막 나서 다른 그룹으로 읽힌다. 같은 시트에서 온 소싱 갈래
  // 이름이 이미 28자까지 간다. 줄여 적느니 **줄을 넘겨 다 적는 편**이 맞다.
  // 길어져도 바로 위 그룹 칩 줄이 같은 이름을 이미 다 그리고 있으니, 이 줄이
  // 화면에 없던 높이를 새로 만들지는 않는다.
  //
  // 한 그룹뿐이면 적지 않는다 — 섞이지 않았다는 뜻이고, 그건 위 칩이 이미
  // 말하고 있다(바로 위 갈래 안내와 같은 규칙).
  function groupMixHtml(picked) {
    // 소싱 명단에는 그룹이라는 것이 없다 — 그쪽은 갈래가 같은 일을 한다.
    if (mode === "sourcing" || !groupBar) return "";
    // 순서는 **목록에 나온 차례** 그대로다. 서버가 정한 정렬(인원 많은 순 ·
    // 비어 있음 마지막)을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모른다.
    var order = [], count = {};
    picked.forEach(function (c) {
      var card = c.closest(".pick-card");
      if (!card) return;
      var name = (card.getAttribute("data-group") || "").trim() || EMPTY_GROUP;
      if (!count[name]) { count[name] = 0; order.push(name); }
      count[name] += 1;
    });
    if (order.length < 2) return "";
    return '<span class="pick-groups">그룹 ' + order.map(function (name) {
      // 그룹 이름은 시트에서 온 말이다 — 그대로 넣지 않는다.
      return '<span class="tag soft">' + escapeHtml(name) +
        " " + count[name] + "명</span>";
    }).join("") + "</span>";
  }

  ["contact-search", "only-picked-contacts"].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", applyContactFilter);
    el.addEventListener("change", applyContactFilter);
  });

  // ── 문구(템플릿) 선택 ─────────────────────────────────────
  // 상황마다 인사말·안내문이 달라진다(첫 연락/재연락, 연말 인사 …).
  // /templates 에서 만들어 둔 문구를 회차마다 골라 쓴다. 고르지 않으면 기본 동작.
  var templateCache = null;

  function loadTemplates(force) {
    if (templateCache && !force) { renderTemplates(); return; }
    fetch("/api/templates").then(function (r) { return r.json(); }).then(function (d) {
      templateCache = d.templates || [];
      renderTemplates();
    }).catch(function () { /* 문구 목록 실패해도 기본 문구로 발송 가능 */ });
  }

  // 같은 이름('팀 기본')이 둘 이상 뜨면 어느 것을 고르는지 알 수 없다.
  // 종류를 함께 보여준다.
  var KIND_NOTE = {
    opening_first: "첫 연락", opening_re: "재연락",
    closing_day1: "딜소개", closing_remind: "리마인드",
    closing_meeting: "미팅 요청", ask_preference: "선호 분야",
    meeting_review: "미팅 후기", ir_delivery: "IR 자료 전달"
  };
  // 고르지 않았을 때 쓰는 문구의 이름. '기본' 만으로는 무엇의 기본인지 모른다.
  var CLOSING_DEFAULT = {
    deal: "기본 안내문", remind: "기본 안내문", meeting: "기본 안내문",
    review: "기본 문구", ask: "기본 문구", ir: "기본 문구",
    sourcing: "갈래별 기본 문구"
  };

  function renderTemplates() {
    var byKind = {};
    (templateCache || []).forEach(function (t) {
      (byKind[t.kind] = byKind[t.kind] || []).push(t);
    });
    // 팀 기본은 첫 연락·재연락 두 개지만 시스템이 알아서 고른다.
    // 목록에 둘 다 올리면 같은 이름이 두 번 뜨고, 골라도 자동 선택이 막힌다.
    var openings = (byKind["opening_first"] || []).concat(byKind["opening_re"] || [])
      .filter(function (t) { return t.mine; });
    fill("tpl-opening", openings, "기본 인삿말 (첫 연락 / 재연락 자동)");
    // 문구만 보낼 때는 안내문이 아니라 그 방식의 문구를 고른다.
    var kindByMode = { ask: "ask_preference", remind: "closing_remind",
                       meeting: "closing_meeting", review: "meeting_review",
                       deal: "closing_day1", ir: "ir_delivery",
                       sourcing: "sourcing_intro" };
    // 딜 소싱은 [보낼 문구]가 종류를 정한다(처음 안내 / 월간 리마인드).
    var closingKind = mode === "sourcing" ? sourcingTopic : kindByMode[mode];
    fill("tpl-closing", byKind[closingKind] || [],
         CLOSING_DEFAULT[mode] || "기본 안내문");
    fillSubjects(byKind["mail_subject"] || []);
  }

  // ── 메일 제목 문구 ───────────────────────────────────────────────────────
  //
  // 위 `fill` 과 다른 손을 쓰는 까닭: 인사말·안내문은 **고른 번호를 그대로**
  // 서버로 보내는데(`opening_template_id`), 제목은 **고르면 칸에 채운다.**
  // 격주로 나가는 제목은 회차마다 한 마디가 달라서(“9월 3주차”), 고른 뒤
  // 손볼 수 없으면 결국 또 처음부터 적게 된다. 채우고 나면 나갈 제목은
  // `#mail-subject` 한 칸이라, 서버로 가는 길은 지금까지와 같다.
  function fillSubjects(list) {
    var sel = document.getElementById("mail-subject-tpl");
    var wrap = document.getElementById("mail-subject-tpl-wrap");
    var none = document.getElementById("mail-subject-none");
    if (!sel) return;
    // 고를 것이 없으면 빈 고르개를 세우지 않고 만들러 가는 길을 띄운다.
    if (wrap) wrap.hidden = !list.length;
    if (none) none.hidden = list.length > 0;

    var keep = sel.value;
    sel.innerHTML = "";
    var base = document.createElement("option");
    base.value = "";
    base.textContent = "직접 입력";
    sel.appendChild(base);
    list.forEach(function (t) {
      var o = document.createElement("option");
      o.value = String(t.id);
      // 이름이 비슷하면 이름만으로 구별이 안 된다 — 첫 줄을 함께 적는다
      // (문구 화면의 `_snippet` 과 같은 뜻).
      o.textContent = t.name + " — " + subjectLine(t.body).slice(0, 30);
      sel.appendChild(o);
    });
    if (keep && sel.querySelector('option[value="' + keep + '"]')) sel.value = keep;
    if (!sel.dataset.bound) {
      sel.addEventListener("change", applySubject);
      sel.dataset.bound = "1";
    }
  }

  // 제목은 **한 줄**이다. 문구 칸은 여러 줄을 받으므로(textarea), 줄바꿈이
  // 섞인 문구를 그대로 넣으면 메일 헤더에 못 실린다 — 한 줄로 편다.
  function subjectLine(body) {
    return String(body || "").replace(/\s+/g, " ").trim();
  }

  function applySubject() {
    var sel = document.getElementById("mail-subject-tpl");
    var box = document.getElementById("mail-subject");
    if (!sel || !box || !sel.value) return;   // '직접 입력' 은 칸을 건드리지 않는다
    var id = parseInt(sel.value, 10);
    var hit = (templateCache || []).filter(function (t) { return t.id === id; })[0];
    if (hit) box.value = subjectLine(hit.body);
  }

  function fill(selectId, list, defaultLabel) {
    var sel = document.getElementById(selectId);
    if (!sel) return;
    var keep = sel.value;
    sel.innerHTML = "";
    var base = document.createElement("option");
    base.value = "";
    base.textContent = defaultLabel;
    sel.appendChild(base);

    list.forEach(function (t) {
      var o = document.createElement("option");
      o.value = t.id;
      var note = KIND_NOTE[t.kind];
      o.textContent = t.name + (note ? " · " + note : "") +
        " — " + t.body.replace(/\n/g, " ").slice(0, 26);
      sel.appendChild(o);
    });
    // 방식을 바꿔도 고르던 문구가 그 목록에 있으면 유지한다.
    if (keep && sel.querySelector('option[value="' + keep + '"]')) sel.value = keep;

    if (!sel.dataset.bound) {
      sel.addEventListener("change", refreshPreview);
      sel.dataset.bound = "1";
    }
  }

  function currentChannel() {
    var picked = document.querySelector('input[name="channel"]:checked');
    return picked ? picked.value : "kakao";
  }

  // 메일과 카톡은 나가는 길이 다르다 — 고른 채널에 맞춰 화면도 바뀐다.
  function syncChannel() {
    var email = currentChannel() === "email";
    var box = document.getElementById("mail-fields");
    if (box) box.hidden = !email;
    updateCounts();
  }

  document.querySelectorAll('input[name="channel"]').forEach(function (radio) {
    radio.addEventListener("change", syncChannel);
  });

  function selectedTemplateIds() {
    var o = document.getElementById("tpl-opening");
    var c = document.getElementById("tpl-closing");
    var greet = document.getElementById("include-opening");
    return {
      opening_template_id: o && o.value ? parseInt(o.value, 10) : null,
      closing_template_id: c && c.value ? parseInt(c.value, 10) : null,
      mode: mode,
      include_opening: greet ? greet.checked : true,
      // 딜 소싱은 갈래마다 문구가 다르다. 아직 아무도 안 골랐을 때
      // 어느 갈래를 보여 줄지는 **누른 칩**이 정한다.
      // Series A 딜 공유는 받는 갈래가 하나뿐이라 그 갈래 문구다.
      bucket: isShare() ? SHARE_BUCKET : (bucketFilter || ""),
      // 딜 소싱 제안의 [보낼 문구] · 리마인드에 이 달 딜 받음을 넣을지.
      // 다른 방식은 빈 값이다(서버가 그 방식에서는 읽지 않는다).
      topic: mode === "sourcing" ? sourcingTopic : "",
      include_received: isRemind() && includeReceived,
      // Series A 딜 공유 — 이미 받은 기업도 다시 보낼지([… 받은 분 제외]를 끈 것) ·
      // 사람당 몇 개(서버가 1~10 밖이면 멈춘다).
      include_shared: isShare() && !excludeShared,
      per_person: perPerson
    };
  }

  // 고른 기업을 서버가 받는 칸으로 — IR 기업(`company_ids`)과 Series A 이상
  // 기업(`series_a_ids`)은 다른 표라 칸도 다르다. 미리보기와 발송이 같은 손을 지난다.
  function pickedPayload(cids, tids) {
    return { company_ids: isShare() ? [] : cids, contact_ids: tids,
             series_a_ids: isShare() ? cids : [] };
  }

  // 인사말을 끄면 인사말 문구를 고르는 칸은 의미가 없다.
  function syncOpeningToggle() {
    var greet = document.getElementById("include-opening");
    var wrap = document.getElementById("tpl-opening-wrap");
    if (wrap) wrap.hidden = !greet.checked;
  }

  // 몇 개/몇 명 골랐는지는 발송 직전에 가장 궁금한 값이라
  // 패널 제목 옆(알약)과 발송 요약 두 곳에 크게 띄운다.
  // 고르는 대로 미리보기가 따라온다. 갱신 버튼을 누르게 두면 안 누른 채로
  // 발송을 눌러, 화면에 보이는 것과 실제로 나가는 것이 달라진다.
  //
  // 다만 체크할 때마다 서버를 부르면 7개 고르는 동안 7번 나간다 — 손이
  // 멈춘 뒤 한 번만 부른다.
  var previewTimer = null;
  function schedulePreview() {
    var state = document.getElementById("preview-state");
    if (state) state.textContent = "고르는 중…";
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(function () {
      previewTimer = null;
      if (state) state.textContent = "고르는 대로 바로 나옵니다";
      refreshPreview();
    }, 400);
  }

  function updateCounts() {
    var nc = selectedCompanyIds().length;
    var nt = selectedContactIds().length;
    var askMode = !needsCompanies();

    companyPill.innerHTML = "<b>" + nc + "</b> / " + MAX_COMPANIES;
    companyPill.classList.toggle("on", nc > 0);
    contactPill.innerHTML = "<b>" + nt + "</b>명";
    contactPill.classList.toggle("on", nt > 0);

    ssCompanies.innerHTML = "<b>" + nc + "</b>개 기업";
    ssCompanies.hidden = askMode;                 // 문구만 보낼 때는 기업 수가 의미 없다
    document.querySelector(".ss-arrow").hidden = askMode;
    ssContacts.textContent = nt;
    schedulePreview();
    ssNote.textContent = askMode
      ? modeLabel() + " — 기업 목록 없이 문구만 나갑니다"
      : (mode === "ir" ? irSummaryNote()
                       : (nc > MAX_COMPANIES ? "기업은 최대 " + MAX_COMPANIES + "개까지"
                          : (isShare() ? SHARE_LABEL + " — 사람마다 본인 공유·이미 받은 기업을 빼고 " +
                                         "앞에서부터 " + perPerson + "개씩 나갑니다"
                                       : "")));
    if (mode === "ir") renderIrLinks();

    syncBucketMixNote();
    // 고른 사람 이름을 보여준다 — 숫자만으로는 누구를 넣었는지 알 수 없다.
    // **보낼 사람만** 적는다 — 고른 기업을 다 받아 빠지는 분은 옆 알약 수에도 없다.
    var picked = sendableBoxes();
    var names = picked.map(function (c) { return c.getAttribute("data-name"); });
    if (names.length) {
      contactSummary.hidden = false;
      contactSummary.innerHTML = groupMixHtml(picked) +
        '<span class="pick-names">' + escapeHtml(names.length <= 6
          ? names.join(", ")
          : names.slice(0, 6).join(", ") + " 외 " + (names.length - 6) + "명") +
        "</span>";
    } else {
      contactSummary.hidden = true;
      contactSummary.innerHTML = "";
    }

    // [전체해제]는 **셀 것이 있을 때만** 눌린다. 눌러도 아무 일이 없는 단추는
    // "왜 안 되지" 를 만든다. 켜고 끄는 판단을 여기서 하는 이유는, 옆 알약이
    // `nt` 명이라고 적는 바로 그 자리이기 때문이다 — 다른 곳에서 따로 세면
    // `0명` 인데 해제가 눌리거나 `12명` 인데 안 눌리는 날이 온다.
    if (clearAllBtn) clearAllBtn.disabled = nt < 1;

    // 상한을 넘기면 더 못 고르게 막는다
    if (nc >= MAX_COMPANIES) {
      companyCbs().forEach(function (c) { if (!c.checked) c.disabled = true; });
    } else {
      companyCbs().forEach(function (c) { c.disabled = false; });
    }
    sendBtn.disabled = askMode
      ? nt < 1
      : !(nc >= 1 && nc <= MAX_COMPANIES && nt >= 1);
    applyCompanyFilter();   // 선택 항목은 검색 중에도 계속 보이게
    applyContactFilter();
  }

  // 자료 전달 요약줄. **자료를 누가 붙이는가**를 말한다 — 바로 위 [보낼 자료]
  // 칸의 머리말과 같은 뜻이어야 한다. 붙박이 글자였던 탓에, 자료 폴더를 등록해
  // 발송기가 파일을 붙이는 계정에도 "PC 카톡에서 직접 첨부하고" 가 떴다.
  // 머리말은 발송기가 붙인다고 하는데 그 아래 줄은 손으로 붙이라고 하니,
  // 그 말대로 하면 **같은 자료가 두 번 나간다.**
  //
  // 판단은 서버 한 곳이고(`services/ir_attach.py`), 화면은 서버가 칸에 적어 준
  // 값을 읽을 뿐이다 — 여기서 다시 판단하지 않는다.
  function irSummaryNote() {
    var box = document.getElementById("ir-attach");
    return (box && box.getAttribute("data-auto") === "1")
      ? "자료 파일은 발송 프로그램이 붙여 보냅니다"
      : "자료는 PC 카톡에서 직접 첨부하고, 여기서는 문구만 보냅니다";
  }

  // 고른 기업의 IR 자료를 띄운다 — **번호와 파일 이름**이다.
  //
  // 자동 첨부를 켠 계정은 발송기가 이 차례로 파일을 붙여 보내고, 켜지 않은
  // 계정은 사람이 이 목록을 보고 PC 카톡에 붙인다. 어느 쪽이든 이 목록이
  // **무엇을 어떤 차례로 보내는가**를 말한다.
  //
  // **그리는 일은 여기 없다.** IR 진행 관리의 [자료 보내기] 창도 똑같은 목록을
  // 그려서, 한 벌을 같이 쓴다(`ir_attach_list.js`) — 번호를 적는 규칙이 두
  // 벌이 되면 고칠 때 한쪽만 고쳐진다. 왜 화면이 번호를 셀 수 없는지도 그
  // 파일에 적어 두었다.
  //
  // 담당자를 여럿 고르면 번호도 여럿이라 목록에 하나로 적을 수 없다. 미리보기는
  // 담당자별로 한 통씩 보여 주므로(탭 하나가 담당자 하나) 이 목록은 **지금 열어
  // 둔 그 탭**을 따른다. 탭을 바꾸면 번호도 함께 바뀐다.
  function renderIrLinks() {
    var box = document.getElementById("ir-attach");
    if (!box) return;
    box.hidden = mode !== "ir";
    if (mode !== "ir") return;
    window.IrAttach.renderList(
      document.getElementById("ir-links"),
      document.getElementById("ir-no-note"),
      lastPreviews[currentPreview] || lastPreviews[0]);
  }

  // ── 보내는 방식 전환 ───────────────────────────────────────
  function setMode(next) {
    mode = next;
    // [보낼 문구]는 탭을 바꾸면 처음 안내로 돌아간다 — 필터와 같은 까닭(켜 둔 채
    // 다른 탭에 갔다 오면 왜 사람이 적은지 모른다). 회차명보다 먼저 되돌린다.
    resetSourcingTopic();
    syncBatchTitle();
    var askMode = !needsCompanies();
    document.querySelectorAll(".mode-tab").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    // 흐리게 · 번호 배지 · 어느 기업 고르개를 세울지 — 한 손(`syncCompanyPanel`).
    syncCompanyPanel();
    // 대상 목록 자체를 바꾼다 — 소싱은 받는 사람이 다른 명단에 있다.
    var sourcingMode = mode === "sourcing";
    var contactBox = document.getElementById("contact-list");
    var sourcingBox = document.getElementById("sourcing-list");
    if (contactBox) contactBox.hidden = sourcingMode;
    if (sourcingBox) sourcingBox.hidden = !sourcingMode;
    // `연결이 안 끝나 목록에 없는 사람`은 **투자사 담당자 목록의 사정**이다.
    // 소싱은 아예 다른 표(SourcingContact)라 연결 단계라는 것이 없는데, 그
    // 목록 위에 "19명이 연결이 안 끝나 빠졌다" 가 그대로 남아 있으면 지금
    // 보이는 명단에서 19명이 빠진 것으로 읽힌다.
    var missBox = document.getElementById("blocked-contacts");
    if (missBox) missBox.hidden = sourcingMode;
    var contactHead = document.getElementById("contact-head");
    if (contactHead) contactHead.textContent = sourcingMode ? "② 딜 소싱 대상" : "② 대상 담당자";
    var noReactBtn = document.getElementById("select-noreact");
    // 소싱 명단에는 '반응' 이라는 개념이 없다 — 아직 보낸 적이 없다.
    if (noReactBtn) noReactBtn.hidden = sourcingMode;
    if (filterBox) {
      filterBox.hidden = !sourcingMode;
      // 필터를 켜 둔 채 다른 탭으로 갔다 오면, 왜 사람이 적은지 모른다.
      resetSourcingFilters();
    }
    // 탭을 열 때마다 명단의 담당 · 딜 받음을 다시 읽는다(위 `refreshSourcingState`).
    if (sourcingMode) refreshSourcingState();
    // 그룹은 투자사 담당자 목록에만 있다. **필터 줄을 감출 때는 조건도 함께
    // 푼다** — 켜져 있는데 보이지 않는 필터가 제일 나쁘다(왜 사람이 적은지
    // 알 길이 없고, [전체선택]이 무엇에 걸리는지도 알 수 없다).
    if (groupBox) {
      groupBox.hidden = sourcingMode;
      if (sourcingMode) resetGroupFilter();
    }
    // 예약 큐는 **딜 소개 탭의 것**이다. 후속 문구(리마인드·미팅 요청 …)와
    // 소싱은 그때그때 사람을 골라 보내는 일이라 줄 세울 것이 없고, 큐가
    // 그대로 떠 있으면 지금 탭에서 [시작] 을 누르면 이 탭의 문구가 나가는
    // 줄로 읽힌다 — 실제로 나가는 것은 딜 소개다.
    var queuePanel = document.getElementById("deal-queue");
    // `data-off` 가 붙어 있으면 **화면에서 뺀 것**이다(`deals.html`) — 방식이
    // 바뀌었다고 다시 켜면 안 뺀 것이 된다. 감추는 결정은 화면 한 곳에 있다.
    if (queuePanel && !queuePanel.hasAttribute("data-off")) {
      queuePanel.hidden = mode !== "deal";
    }
    applyContactFilter();
    // 설명 줄은 화면에서 뺐다. 없어도 터지지 않아야 한다.
    var help = document.getElementById("mode-help");
    if (help) help.textContent =
      mode === "ir"
        ? "요청받은 기업을 고르세요 — 자료 파일은 PC 카톡에서 직접 첨부하고, 안내 문구만 여기서 보냅니다"
        : (sourcingMode
            ? "딜 소싱 명단에서 대상을 고르면, 갈래(시리즈 A 이상 · 투자사 대표 · 개인 참여 …)에 맞는 문구가 나갑니다"
            : (askMode ? FOLLOW_UP[mode] + " — 기업 목록 없이 문구만 보냅니다 (기업 선택 불필요)"
                       : "기업 1~10개 선택 → 대상 담당자 체크 → 담당자별 미리보기 → 발송"));
    var companyHint = document.getElementById("company-hint");
    if (companyHint) companyHint.hidden = mode === "ir";
    renderIrLinks();
    var closingWrap = document.getElementById("tpl-closing-wrap");
    if (closingWrap) closingWrap.querySelector("span").textContent = askMode ? "문구" : "안내문";
    // 인사말은 **기본으로 붙인다.** 빼는 것은 선호 분야를 되물을 때뿐이다 —
    // 그건 이미 대화가 오간 방에 한 줄만 덧붙이는 것이라 다시 인사하면 어색하다.
    // (자료 전달 문구는 그 자체가 "○○ 님 안녕하세요" 로 시작하므로 서버가
    //  중복을 걸러낸다 — deals.py 의 FOLLOW_UP_MODES 참고.)
    // 켜고 끄는 것은 그대로 사람이 정한다.
    var greet = document.getElementById("include-opening");
    if (greet) { greet.checked = (mode !== "ask"); syncOpeningToggle(); }
    lastPreviews = [];
    currentPreview = 0;
    // 방식을 바꾸면 고친 것도 버린다 — 딜소개용으로 고친 문구가 IR 자료
    // 전달에 얹히면 엉뚱한 말이 나간다.
    savedEdits = {};
    previewTabs.innerHTML = "";
    previewArea.innerHTML = '<p class="muted">불러오는 중…</p>';
    // 링크로 받은 경고도 여기서 지운다 — 사람이 방식을 직접 바꾼 순간부터는
    // 넘어오며 못 골랐다는 말이 지금 화면의 이야기가 아니다.
    incomingWarns = [];
    showWarnings([]);
    loadTemplates(true);
    updateCounts();   // 여기서 미리보기가 따라온다
  }

  ["company-search", "only-picked", "hide-recent",
   "sa-pick-search", "sa-only-picked", "sa-only-fresh"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", applyCompanyFilter);
    if (el) el.addEventListener("change", applyCompanyFilter);
  });

  // 미리보기는 **그대로 고쳐서 보낼 수 있다**.
  // 자동 조합이 늘 완벽할 수는 없어서, 담당자별로 한 줄 덧붙이거나 표현을 바꾸는 일이 잦다.
  // 고친 내용은 lastPreviews[i].message 에 남고 발송 시 그 문장이 그대로 나간다.
  // 여러 통으로 나뉘어 나가는 문구가 있으면 몇 통인지 보여 준다. 무엇이 어떤
  // 순서로 나가는지 보이지 않으면 확인할 수가 없다.
  // (자료 전달은 링크 방식을 폐기한 뒤로 한 통이라 여기 걸리지 않는다.)
  // 여기서 고치면 **한 통으로** 나간다(어디서 끊을지는 고친 사람만 안다).
  function splitNotice(p) {
    var parts = p.parts || [];
    if (parts.length < 2) return "";
    var heads = parts.map(function (t, i) {
      return '<li><b>' + (i + 1) + '통</b> ' +
        escapeHtml(t.split("\n")[0].slice(0, 40)) + '</li>';
    }).join("");
    return '<div class="split-notice">' +
      '<b>' + parts.length + '통으로 나갑니다</b> — 위에서부터 차례대로' +
      '<ol>' + heads + '</ol>' +
      '<span class="muted">여기서 고치면 한 통으로 나갑니다</span></div>';
  }

  // 미리보기 문구를 클립보드로 — **문구는 사람이 손으로 보낸다.**
  //
  // 담당자를 여럿 고르면 문구도 여럿인데, 이 단추는 **지금 열어 둔 탭**의
  // 문구만 담는다 — 붙여 넣을 카톡 창도 한 번에 하나이고, 옆에 선 [보낼 자료]
  // 목록의 번호도 같은 탭을 따른다. 둘이 다른 담당자를 가리키면 엉뚱한 자료가
  // 붙는다.
  //
  // 복사 자체는 IR 진행 관리의 [자료 보내기] 창과 **같은 한 벌**이다
  // (`ir_attach_list.js` — 클립보드가 없는 화면에서 어떻게 물러서는지도 거기 있다).
  function copyMessage(ta, btn) { window.IrAttach.copyText(ta, btn); }

  // Series A 딜 공유 — 이 분께 **나가는 기업**과 **뺀 기업(까닭)**. 서버가 지은
  // 그대로 적는다(`series_a_share.plan_view`) — 까닭 글자를 여기서 짓지 않는다.
  function sharePlanHtml(p) {
    var plan = p.series_a;
    if (!plan) return "";
    var send = (plan.send || []).map(function (c) {
      return escapeHtml(c.label + " " + c.name);
    }).join(" · ");
    var dropped = (plan.dropped || []).map(function (c) {
      return '<span class="sa-drop' + (c.reason === OWN_REASON ? " own" : "") + '">' +
        escapeHtml(c.name) + " — " + escapeHtml(c.reason) + "</span>";
    }).join(" · ");
    return '<div class="sa-plan" data-testid="sa-plan">' +
      '<div><b>보내는 기업</b> ' +
      (send || '<span class="sa-drop own">없음 — 이번 목록에서 빠집니다</span>') + "</div>" +
      (dropped ? '<div><b>뺀 기업</b> ' + dropped + "</div>" : "") + "</div>";
  }

  function renderPreview(idx) {
    var p = lastPreviews[idx];
    if (!p) { previewArea.innerHTML = '<p class="muted">미리보기 없음</p>'; return; }
    // [보낼 자료] 목록의 번호가 **이 탭을 따른다.** 번호는 담당자마다 달라서,
    // 여기서 알려 주지 않으면 목록은 앞 담당자의 번호를 그대로 달고 있는다.
    currentPreview = idx;
    Array.prototype.slice.call(previewTabs.children).forEach(function (t, i) {
      t.classList.toggle("active", i === idx);
    });
    var roomLine = p.room_name
      ? ("💬 " + p.room_name + (p.room_from ? " (" + p.room_from + ")" : ""))
      : ("⚠ " + (p.room_warning || "방 미등록"));
    // 기본 문구는 아직 아무에게도 가지 않는다 — 진짜 사람에게 갈 문구로
    // 읽히면 확인만 하려다 그대로 보내게 된다.
    var meta = p.sample
      ? '<div class="bubble-meta sample">기본 문구 — 아직 대상을 고르지 않았습니다. ' +
        '담당자를 고르면 그 사람 이름으로 바뀝니다.' +
        ' <span class="edited-flag" id="edited-flag" hidden>· 수정함</span></div>'
      : '<div class="bubble-meta">' + escapeHtml(p.name) + " " + escapeHtml(p.title || "") +
        " · " + escapeHtml(roomLine) + (p.has_history ? " · 재연락" : " · 첫연락") +
        ' <span class="edited-flag" id="edited-flag" hidden>· 수정함</span></div>';
    previewArea.innerHTML =
      meta +
      sharePlanHtml(p) +
      splitNotice(p) +
      '<textarea class="bubble-edit" id="bubble-edit" spellcheck="false"></textarea>' +
      '<div class="charcount" id="charcount"></div>' +
      // 문구는 **사람이 손으로 보낸다** — 카톡 창에 붙여 넣어야 하니 여기서
      // 집어갈 수 있어야 한다. 담을 것은 아래 칸의 값 그대로다(장식·머리말이
      // 섞이면 그것까지 붙는다).
      '<button type="button" class="linkbtn" id="copy-message">' + COPY_LABEL + '</button>' +
      '<button type="button" class="linkbtn" id="revert-edit"' +
      (p.edited ? '' : ' hidden') + '>고친 것 되돌리기</button>';

    var ta = document.getElementById("bubble-edit");
    ta.value = p.message;               // innerHTML 이 아니라 value 로 넣어야 안전하다
    // 이 탭의 자료 목록·번호. 문구와 같은 응답에서 나온다.
    renderIrLinks();
    var copyBtn = document.getElementById("copy-message");
    if (copyBtn) copyBtn.addEventListener("click", function () { copyMessage(ta, copyBtn); });
    var flag = document.getElementById("edited-flag");
    flag.hidden = !p.edited;
    updateCharCount(ta.value);

    ta.addEventListener("input", function () {
      p.message = ta.value;
      // 고치는 즉시 남겨 둔다. 저장 단추가 따로 없으니, 여기서 안 남기면
      // 담당자를 하나 더 체크하는 순간 사라진다.
      if (ta.value.trim() && ta.value !== p.original) {
        savedEdits[p.contact_id] = ta.value;
      } else {
        delete savedEdits[p.contact_id];
      }
      p.edited = ta.value !== p.original;
      flag.hidden = !p.edited;
      updateCharCount(ta.value);
      markTabEdited(idx, p.edited);
      if (revert) revert.hidden = !p.edited;
    });

    // 되돌릴 수 없으면 고치기가 부담스럽다 — 손댄 뒤 원래 문구를 다시 못 본다.
    var revert = document.getElementById("revert-edit");
    if (revert) revert.addEventListener("click", function () {
      delete savedEdits[p.contact_id];
      p.message = p.original;
      p.edited = false;
      ta.value = p.original;
      flag.hidden = true;
      revert.hidden = true;
      updateCharCount(ta.value);
      markTabEdited(idx, false);
    });
  }

  function updateCharCount(text) {
    var el = document.getElementById("charcount");
    if (!el) return;
    var n = text.length;
    el.textContent = n + "자";
    el.className = "charcount" + (n > WARN_CHARS ? " over" : "");
  }

  function markTabEdited(idx, edited) {
    var tab = previewTabs.children[idx];
    if (tab) tab.classList.toggle("edited", !!edited);
  }

  // 고친 문구만 서버로 보낸다. 안 고친 담당자는 서버가 다시 조합한다.
  // 고친 문구를 담당자별로 들고 있는다 — 미리보기를 다시 그려도 남아야 한다.
  var savedEdits = {};
  // 미리보기 요청 번호. 늦게 온 옛 응답이 새 것을 덮지 않게 한다.
  var previewSeq = 0;

  function editedOverrides() {
    return lastPreviews
      .filter(function (p) { return p.edited && (p.message || "").trim(); })
      .map(function (p) { return { contact_id: p.contact_id, message: p.message }; });
  }

  function refreshPreview() {
    var cids = selectedCompanyIds();
    var tids = selectedContactIds();
    // 아무도 안 골랐어도 **기본 문구**를 부른다. 문구를 확인하려고 아무나
    // 한 명 체크했다가 그대로 발송을 누르는 일이 있었다.
    // (딜 소개는 기업까지 골라야 목록이 채워지지만, 인사말·안내문 모양은
    //  기업 없이도 보인다)
    // 요청마다 번호를 붙인다. 39명을 고른 요청은 느리고 전부 해제한 요청은
    // 빠른데, 순서를 안 지키면 **늦게 도착한 옛 응답이 새 것을 덮는다** —
    // 전체선택을 두 번 눌러 다 껐는데 미리보기에 투자사가 그대로 남았다.
    var seq = ++previewSeq;
    fetch("/api/deals/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign(pickedPayload(cids, tids), selectedTemplateIds()))
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (seq !== previewSeq) return;      // 그 사이 새 요청이 나갔다
        if (!res.ok) { previewArea.innerHTML = '<p class="muted">' + escapeHtml(res.d.detail || "미리보기 실패") + "</p>"; return; }
        lastPreviews = res.d.previews || [];
        // 고친 문구를 되살린다. 담당자를 하나 더 체크하면 미리보기가 새로
        // 그려지는데, 그때마다 앞서 고쳐 둔 것이 **말없이 사라졌다** —
        // 열 명을 고치고 한 명 더 넣으면 열 명분이 날아간다.
        lastPreviews.forEach(function (p) {
          p.original = p.message;
          var kept = savedEdits[p.contact_id];
          if (kept !== undefined && kept !== p.message) {
            p.message = kept;
            p.edited = true;
          } else {
            p.edited = false;
          }
        });
        previewTabs.innerHTML = "";
        lastPreviews.forEach(function (p, i) {
          var b = document.createElement("button");
          b.className = "preview-tab";
          b.textContent = p.sample ? "기본 문구" : p.name;
          b.onclick = function () { renderPreview(i); };
          previewTabs.appendChild(b);
        });
        // 다시 그릴 때는 늘 첫 탭이다. 앞서 세 번째 탭을 열어 두었는데 담당자를
        // 줄이면 그 자리가 없어져, [보낼 자료] 목록만 없는 담당자의 번호를 단다.
        if (lastPreviews.length) renderPreview(0);
        else { currentPreview = 0; renderIrLinks(); }
        var warns = [];
        lastPreviews.forEach(function (p) {
          (p.warnings || []).forEach(function (w) { warns.push(p.name + ": " + w); });
        });
        showWarnings(warns);
      })
      .catch(function () {
        if (seq !== previewSeq) return;
        previewArea.innerHTML = '<p class="muted">미리보기 요청 오류</p>';
      });
  }

  // ── 예약 큐 ───────────────────────────────────────────────────────────────
  //
  // 줄 하나가 **그룹 + 기업 묶음 + 문구**다. 여기서 하는 일은 셋뿐이다:
  // 줄 세우기 · 시작 · 취소. **보내는 길은 새로 만들지 않는다** — [시작] 은
  // 서버에서 기존 발송 목록 생성(`/api/deals/send` 와 같은 함수)을 그대로 탄다.
  //
  // **대상 명단은 화면이 들고 있지 않다.** 이 줄에 담긴 것은 그룹 이름뿐이고,
  // 서버가 누를 때 다시 센다. 화면이 명단을 들고 보내면 예약해 둔 사이에
  // 카톡방을 나간 분께 그대로 나간다.
  function queuePost(url, body, done) {
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.d.detail || "요청 실패"); done(null); return; }
        done(res.d);
      })
      .catch(function () { alert("요청 오류"); done(null); });
  }

  var queueAdd = document.getElementById("queue-add");
  if (queueAdd) queueAdd.addEventListener("click", function () {
    var cids = selectedCompanyIds();
    if (!cids.length) { alert("① 에서 기업을 먼저 고르세요."); return; }
    var group = document.getElementById("queue-group");
    var tpl = selectedTemplateIds();
    queueAdd.disabled = true;
    queuePost("/api/deals/queue", {
      group_name: group ? group.value : "",
      company_ids: cids,
      title: (document.getElementById("batch-title").value || "").trim(),
      opening_template_id: tpl.opening_template_id,
      closing_template_id: tpl.closing_template_id
    }, function (d) {
      queueAdd.disabled = false;
      // 줄 목록은 서버가 그린다(대상 수가 **지금 센 값**이어야 한다).
      // 화면에서 줄을 흉내 내 붙이면 그 수는 붙인 순간 낡는다.
      if (d) window.location.reload();
    });
  });

  // 줄 단추는 목록이 다시 그려져도 살아 있어야 한다 — 줄마다 거는 대신
  // 목록이 대신 듣는다.
  var queueList = document.getElementById("queue-list");
  if (queueList) queueList.addEventListener("click", function (e) {
    var startBtn = e.target.closest(".queue-start");
    var cancelBtn = e.target.closest(".queue-cancel");
    var row = e.target.closest(".queue-row");
    if (!row || (!startBtn && !cancelBtn)) return;
    var id = row.getAttribute("data-id");
    var group = row.getAttribute("data-group") || "";

    if (cancelBtn) {
      if (!confirm("[" + group + "] 예약을 취소합니다.")) return;
      cancelBtn.disabled = true;
      queuePost("/api/deals/queue/" + id + "/cancel", {}, function (d) {
        cancelBtn.disabled = false;
        if (d) window.location.reload();
      });
      return;
    }

    // **화면에 적혀 있던 수를 함께 보낸다.** 서버가 지금 다시 센 수와 다르면
    // 보내지 않고 그 차이를 말로 돌려준다 — 조용히 다른 수로 나가면, 몇 명
    // 에게 나갔는지 아무도 모르는 채로 되돌릴 수 없는 일이 끝나 있다.
    var shown = parseInt(row.getAttribute("data-count"), 10);
    startBtn.disabled = true;
    function go(confirmed) {
      queuePost("/api/deals/queue/" + id + "/start",
                { shown: isNaN(shown) ? null : shown, confirmed: !!confirmed },
                function (d) {
        if (!d) { startBtn.disabled = false; return; }
        if (d.needs_confirm) {
          // 확인창의 말은 **서버가 만든 것을 그대로** 띄운다. 여기서 다시
          // 지어내면 두 벌이 되고, 둘이 어긋나도 아무도 모른다 — 사람이
          // 마지막으로 읽는 자리라 특히 그렇다.
          if (!confirm(d.message)) { startBtn.disabled = false; return; }
          go(true);
          return;
        }
        tellSkipped(d.skipped);
        window.location.href = "/jobs/" + d.job_id;
      });
    }
    if (!confirm("[" + group + "] 예약을 시작합니다.\n" +
                 "대상 " + (isNaN(shown) ? "?" : shown) + "명 기준입니다 — " +
                 "누르는 순간 다시 세므로 수가 달라졌으면 한 번 더 여쭙습니다.")) {
      startBtn.disabled = false;
      return;
    }
    go(false);
  });

  // 고른 예약 시각. 안 골랐으면 빈 글자, **고를 수 없는 시각이면 `null`**.
  //
  // 화면에서도 막는다 — 서버가 다시 보지만(`services/scheduled_send.py: check`),
  // 여기서 걸러 주면 왜 안 되는지를 누르는 그 자리에서 안다. 폭(09~19시)은
  // 서버가 화면에 실어 준 값이다(`send_earliest_hour`) — 여기 숫자를 적으면
  // 두 벌이 된다.
  function scheduledAt() {
    var box = document.getElementById("send-at");
    var value = (box && box.value) || "";
    if (!value) return "";
    var early = Number(box.getAttribute("data-earliest"));
    var late = Number(box.getAttribute("data-latest"));
    var hour = parseInt(value.slice(11, 13), 10);
    if (early && late && !(hour >= early && hour < late)) {
      alert("예약은 " + early + ":00~" + late + ":00 안에서만 고를 수 있습니다 — "
            + "받는 분들의 업무시간입니다.");
      return null;
    }
    return value;
  }

  function send() {
    var cids = selectedCompanyIds();
    var tids = selectedContactIds();
    var title = (document.getElementById("batch-title").value || "딜소개 회차").trim();
    var edits = editedOverrides();
    var editNote = edits.length ? "\n직접 수정한 문구 " + edits.length + "건이 그대로 발송됩니다." : "";
    var via = currentChannel() === "email" ? "이메일로 " : "";
    var what = mode === "ir"
      ? cids.length + "개 기업 IR 자료 전달"
      : (isShare() ? SHARE_LABEL + " — " + cids.length + "개 기업 중 사람마다 " +
                     perPerson + "개씩 (본인 공유 · 이미 받은 기업 빼고)"
         : (isFollowUp() ? modeLabel() + " 문구 (기업 목록 없음)"
                         : cids.length + "개 기업 딜소개"));
    var lastCheck = currentChannel() === "email"
      ? "\n받는 주소를 최종 확인하셨나요?"
      : "\n방 이름을 최종 확인하셨나요?";
    // **언제 보낼까.** 비어 있으면 지금까지와 똑같이 바로 나간다.
    var at = scheduledAt();
    if (at === null) return;  // 고른 시각이 창 밖이다 — 이미 말했다
    // 확인창이 **언제 나가는지**를 말한다. 고른 값을 그대로 읽어 적는다 —
    // 여기서 날짜를 다시 지으면 서버가 회차 화면에 적는 문장과 두 벌이 된다.
    var when = at ? ("\n" + at.replace("T", " ") + " 에 나갑니다 (지금은 나가지 않습니다).") : "";
    if (!confirm(what + "\n" + via + "대상 " + tids.length + "명에게 발송합니다."
                 + when + editNote + lastCheck)) return;
    sendBtn.disabled = true;
    fetch("/api/deals/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign(
        pickedPayload(cids, tids),
        { title: title,
          overrides: editedOverrides(), channel: currentChannel(),
          scheduled_at: at,
          subject: (document.getElementById("mail-subject") || {}).value || null },
        selectedTemplateIds()))
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { alert("발송 목록 생성 실패: " + (res.d.detail || "")); sendBtn.disabled = false; return; }
        tellSkipped(res.d.skipped);
        window.location.href = "/jobs/" + res.d.job_id;
      })
      .catch(function () { alert("발송 요청 오류"); sendBtn.disabled = false; });
  }

  // 다른 팀원 몫으로 이미 나가 **목록에서 뺀 분**. 조용히 빼지 않는다 — 몇 명에게
  // 나갔는지 사람이 알아야 한다(이유는 서버가 짓는다: `services/twin_send`).
  function tellSkipped(list) {
    if (!list || !list.length) return;
    alert("목록에서 뺀 분 " + list.length + "명:\n" + list.map(function (x) {
      return "· " + x.name + " — " + x.reason;
    }).join("\n"));
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  document.addEventListener("change", function (e) {
    var cls = e.target.classList;
    if (cls.contains("company-cb") || cls.contains("contact-cb") || cls.contains("sa-cb")) updateCounts();
  });
  document.getElementById("refresh-preview").addEventListener("click", refreshPreview);
  document.getElementById("send-btn").addEventListener("click", send);
  // **지금 조건에 맞는 사람**만. `card.hidden` 만 보면 안 된다 — 이미 고른
  // 사람은 조건에서 벗어나도 계속 보이게 두기 때문에(몇 명 골랐는지 알아야
  // 한다), `안 숨겨졌다 = 조건에 맞다` 로 읽으면 그룹으로 추려 놓고 누른
  // [전체선택]에 **다른 그룹 사람까지 딸려 온다.** 실제 투자사에게 문구가
  // 나가는 자리다.
  function filteredBoxes() {
    return contactCbs().filter(function (c) {
      var card = c.closest(".pick-card");
      if (!card) return true;
      // 아직 한 번도 안 걸렀으면(속성 없음) 전부 조건에 맞는 것이다.
      return card.getAttribute("data-match") !== "0" && !card.hidden;
    });
  }

  var selAll = document.getElementById("select-all-contacts");
  if (selAll) selAll.addEventListener("click", function () {
    var boxes = filteredBoxes();
    if (!boxes.length) return;
    var allOn = boxes.every(function (c) { return c.checked; });
    boxes.forEach(function (c) { c.checked = !allOn; });
    updateCounts();
    applyContactFilter();   // 켠 사람은 검색어와 무관하게 계속 보인다
  });

  // ── [전체해제] ────────────────────────────────────────────────────────────
  //
  // **[전체선택]을 다시 누르는 것과는 다른 일이다.** 그쪽은 지금 걸러진 범위만
  // 되돌린다 — 그 좁힘이 이 화면의 안전장치라 넓힐 수 없다(그룹으로 추려 놓고
  // 누른 조작이 다른 그룹을 건드리면 남의 카톡방으로 문구가 나간다).
  //
  // 그 대신 조건 밖에서 고른 사람은 손이 안 닿는 채로 발송에 남았다. 1군에서
  // 고르고 2군으로 옮기면 [전체선택]을 두 번 눌러도 1군은 그대로다 — 필터를
  // 되돌리거나 새로고침해야 했고, 그 사이 요약 줄은 계속 그 사람을 세고 있다.
  // 여기서는 **거른 것과 상관없이 지금 목록의 체크를 전부 끈다.**
  //
  // 훑는 상자는 [전체선택]과 똑같이 `contactCbs()` 다 — 지금 보이는 목록
  // 하나뿐이다. 연결이 안 끝나 접힌 칸(`#blocked-contacts`)은 그 상자 밖이라
  // 켜는 쪽에도 끄는 쪽에도 애초에 안 들어온다(`tests/js/deals_select_all_test.js`).
  if (clearAllBtn) clearAllBtn.addEventListener("click", function () {
    contactCbs().forEach(function (c) { c.checked = false; });
    updateCounts();          // 알약 · 요약 줄 · 이 단추가 여기서 함께 0 이 된다
    applyContactFilter();
  });

  document.querySelectorAll(".mode-tab").forEach(function (b) {
    b.addEventListener("click", function () { setMode(b.getAttribute("data-mode")); });
  });

  var greetBox = document.getElementById("include-opening");
  if (greetBox) greetBox.addEventListener("change", function () {
    syncOpeningToggle();
    refreshPreview();
  });
  syncOpeningToggle();

  var noreactBtn = document.getElementById("select-noreact");
  if (noreactBtn) noreactBtn.addEventListener("click", function () {
    // [전체선택]과 같은 규칙이다 — 그룹으로 추려 놓았으면 그 안에서만 고른다.
    // 여기만 전체 목록을 훑으면, 추려 놓은 줄 알고 눌렀는데 다른 그룹으로
    // 문구가 나간다.
    var targets = filteredBoxes().filter(function (c) {
      return c.getAttribute("data-noreact") === "1";
    });
    if (!targets.length) { alert("반응이 없는 담당자가 없습니다."); return; }
    var allOn = targets.every(function (c) { return c.checked; });
    contactCbs().forEach(function (c) { c.checked = false; });
    if (!allOn) targets.forEach(function (c) { c.checked = true; });
    updateCounts();
    applyContactFilter();   // 켠 사람은 조건과 무관하게 계속 보인다
  });

  // 후속 관리·IR 관리에서 넘어오면 방식·대상·기업을 그대로 받는다.
  // 화면을 열자마자 보낼 준비가 되어 있어야 챙기던 일이 줄어든다.
  // 특히 IR 자료 전달은 "누구에게 어떤 기업 자료를" 이 이미 정해져 있다 —
  // 여기서 다시 고르게 하면 엉뚱한 기업을 보낼 여지가 생긴다.
  (function applyIncoming() {
    var params = new URLSearchParams(window.location.search);
    var wanted = params.get("mode");

    // `ordered` 는 **받은 차례가 곧 번호**인 목록(기업)에만 준다.
    //
    // 목록에 그려진 차례로 훑으면서 켜면 주소에 적힌 차례가 사라진다 —
    // IR 관리에서 `?companies=203,201` 로 넘어오는데, 그 차례는 그 담당자가
    // 요청한 차례이고 자료도 그 차례로 한 통씩 날아가야 한다.
    // 받는 사람(`contacts`)에는 차례가 없다 — 번호를 붙여 나가지 않는다.
    function check(boxes, raw, ordered) {
      var ids = (raw || "").split(",").map(function (v) { return v.trim(); })
        .filter(Boolean);
      // 같은 번호가 두 번 적혀 있어도 한 번만 센다(상자는 하나다).
      ids = ids.filter(function (id, i) { return ids.indexOf(id) === i; });
      if (!ids.length) return 0;
      var byValue = {};
      boxes.forEach(function (c) { byValue[c.value] = c; });
      var hit = 0;
      ids.forEach(function (id, i) {
        var c = byValue[id];
        if (!c) return;
        c.checked = true;
        hit += 1;
        // 목록에 없는 번호가 섞여 있으면 여기서 번호가 비는데, 바로 아래
        // `updateCounts()` 안의 `renumberPicks()` 가 1부터 다시 붙인다.
        if (ordered) {
          var card = cardOf(c);
          if (card) card.setAttribute("data-pick-order", String(i + 1));
        }
      });
      return hit;
    }

    // 딜 소싱으로 여는 링크의 `contacts` 는 **딜 소싱 명단** 번호다 — 투자사
    // 담당자 목록에 대고 켜면 번호만 같은 엉뚱한 담당자가 켜진 채 남는다(다른
    // 탭으로 옮기는 순간 그 사람에게 나갈 수 있다). 그래서 방식을 바꾼 뒤에 켠다.
    var toSourcing = wanted === "sourcing";
    var gotWho = toSourcing ? 0 : check(contactCbs(), params.get("contacts"));
    var picked = check(companyCbs(), params.get("companies"), true);

    if (wanted && document.querySelector('.mode-tab[data-mode="' + wanted + '"]')) {
      setMode(wanted);
    }
    // `?mode=sourcing&topic=sourcing_remind` — 월간 리마인드로 바로 연다.
    // `?mode=sourcing&topic=sourcing_deal_share` — Series A 딜 공유(딜 소싱 화면의
    // [Series A 딜 소개]가 여는 주소다).
    var topicParam = params.get("topic");
    if (toSourcing && (topicParam === REMIND || topicParam === SHARE)) pickTopic(topicParam);
    // 딜 소싱 명단 · Series A 이상 기업을 미리 켠다(`contacts` · `series_a`).
    // 받는 갈래가 아니거나 불참여인 분은 켜지 않는다(`dropExcluded`) — 몇 명이
    // 그랬는지는 아래에서 말한다.
    var askedSourcing = 0, keptSourcing = 0, askedSeries = 0, gotSeries = 0;
    if (toSourcing && mode === "sourcing") {
      check(contactCbs(), params.get("contacts"));
      dropExcluded();
      keptSourcing = contactCbs().filter(function (c) { return c.checked; }).length;
      askedSourcing = (params.get("contacts") || "").split(",")
        .map(function (v) { return v.trim(); }).filter(Boolean)
        .filter(function (v, i, a) { return a.indexOf(v) === i; }).length;
      if (isShare()) {
        askedSeries = (params.get("series_a") || "").split(",")
          .map(function (v) { return v.trim(); }).filter(Boolean)
          .filter(function (v, i, a) { return a.indexOf(v) === i; }).length;
        gotSeries = check(companyCbs(), params.get("series_a"), true);
      }
    }
    var warns = [];
    if (askedSourcing && keptSourcing < askedSourcing) {
      warns.push("딜 소싱 대상 " + (askedSourcing - keptSourcing) + "명은 고르지 " +
        "않았습니다 — 불참여이거나 명단에서 빠졌거나" +
        (isShare() ? ", 이 글을 받는 갈래(" + SHARE_BUCKET + ")가 아닌 분입니다."
                   : " 지금 고를 수 없는 분입니다."));
    }
    if (askedSeries && gotSeries < askedSeries) {
      warns.push("Series A 이상 기업 " + (askedSeries - gotSeries) + "개를 목록에서 " +
        "찾지 못했습니다 — IR 기업 현황 › Series A 이상 기업 탭에서 확인하세요.");
    }
    // 넘겨받은 담당자가 **이 목록에 없을 수 있다.** 이 화면의 대상은 `내
    // 담당` 보다 좁다 — 딜 소개 명단에 있고 카톡방 연결까지 끝난 사람만
    // 선다(`sheet_owner.recipients`). 담당이 넘어간 뒤의 IR 요청 줄에서
    // 넘어오면 남의 담당자라 아예 없다.
    //
    // 그때 조용히 아무도 안 골라 두면, 화면은 "고를 준비가 된 척" 을 하고
    // 사람은 왜 비었는지 모른 채 이름을 찾아 헤맨다. 못 골랐다고 말한다.
    // (소싱은 대상 목록이 아예 다른 표라 여기서 세면 안 된다 — 위 `check` 는
    // 방식을 바꾸기 전, 즉 투자사 담당자 목록을 보고 있다.)
    var askedWho = (params.get("contacts") || "").split(",")
      .map(function (v) { return v.trim(); }).filter(Boolean)
      .filter(function (v, i, a) { return a.indexOf(v) === i; }).length;
    if (askedWho && gotWho < askedWho && wanted !== "sourcing") {
      warns.push("담당자 " + (askedWho - gotWho) + "명을 대상 목록에서 찾지 " +
        "못했습니다 — 내 담당이 아니거나, 딜 소개 명단·카톡방 연결이 아직 " +
        "끝나지 않은 담당자입니다.");
    }
    // 받은 기업이 목록에 없으면(소개 불가로 빠졌거나 지워졌으면) 알려 준다.
    var asked = (params.get("companies") || "").split(",").filter(Boolean).length;
    if (asked && picked < asked) {
      warns.push("요청받은 기업 " + (asked - picked) + "개를 목록에서 찾지 못했습니다 — " +
        "IR 기업 현황에서 등록 상태를 확인하세요.");
    }
    incomingWarns = warns;
    showWarnings([]);
    if (picked) applyCompanyFilter();
  })();

  syncChannel();
  updateCounts();
  loadTemplates();
})();
