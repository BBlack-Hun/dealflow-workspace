// 딜 제안 관리(`app/templates/deals.html`)의 `② 대상 담당자` 칸을 세우는 자리.
// (node tests/js/_deals_dom.js — 혼자 돌면 아무 일도 안 한다)
//
// 규칙을 옮겨 적어 검사하면 두 벌이 되어 어긋나도 모른다. 그래서 검사들은
// **deals.js 를 그대로 실행**하고, 이 파일이 그 밑에 화면을 세워 준다.
//
// **여러 검사가 이 한 벌을 같이 쓴다.** 각자 한 벌씩 들고 있으면 화면이 바뀔 때
// 한쪽만 고쳐져, 나머지는 없는 화면 위에서 조용히 통과한다(`_dom.js` 와 같은 뜻).
// 여기 세운 아이디·속성이 **실제로 그려진 화면과 같은지**는 파이썬 쪽
// (`tests/test_deals_recipients.py`)이 따로 본다.
"use strict";
const dom_ = require("./_dom.js");
const makeEl = dom_.makeEl;
const el = dom_.el;

// 서버가 `sheet_owner.EMPTY_GROUP` 으로 실어 보내는 말. 표 필터(filters.js)의
// `EMPTY` 와 같은 글자여야 한다 — 그 짝은 파이썬 쪽 검사가 지킨다.
const EMPTY_GROUP = "(비어 있음)";

const PEOPLE = [
  // id, 이름(가상), 그룹, 반응 없음
  [1, "가담당", "1군", true],
  [2, "나담당", "1군", false],
  [3, "다담당", "2군", true],
  [4, "라담당", "2군", false],
  [5, "마담당", "", false]      // 그룹을 안 정해 둔 사람
];

function contactCard(id, name, group, noreact) {
  const cb = el("input", {
    id: "cb-" + id, class: "contact-cb", value: String(id),
    "data-name": name, "data-noreact": noreact ? "1" : "0"
  });
  return el("label", {
    class: "pick-card", "data-group": group || "",
    "data-search": (name + " " + (group || "")).toLowerCase()
  }, [cb]);
}

// **발송 목록에 없는** 사람. 사유는 둘이고 같은 칸에 나란히 선다 —
// 연결이 안 끝난 사람(`sheet_owner.blocked_stages`)과 딜 소개를 멈춰 둔
// 사람(`sheet_owner.paused_block`).
//
// 화면은 이 자리에 입력칸을 두지 않지만, 여기서는 **일부러 체크박스를 붙인다.**
// 검사가 지키려는 것은 "화면이 체크박스를 안 그린다" 가 아니라 **"목록 밖의
// 체크박스는 어떤 조작에도 안 딸려 온다"** 이기 때문이다 — deals.js 가 고르는
// 상자를 `#contact-list` 안으로 좁혀 둔(`contactCbs`) 덕이고, 그 좁힘이 풀리면
// 연결도 안 된 사람에게 문구가 나간다. 되돌릴 수 없는 일이라 여기서 못박는다.
//
// **두 사유 모두에 하나씩 붙인다.** 사유가 하나 늘 때 그 줄만 좁힘 밖에 서는
// 일이 생기면, 멈춰 달라고 한 투자사에게 그대로 문구가 나간다.
function blockedBlock() {
  function missCb(id, name) {
    return el("input", {
      id: "cb-" + id, class: "contact-cb", value: String(id),
      "data-name": name, "data-noreact": "1"
    });
  }
  const held = missCb(98, "멈춘담당");        // 검토중단 — 연결은 끝난 사람
  const cb = missCb(99, "못보낼담당");        // 연결이 안 끝난 사람
  return el("details", { id: "blocked-contacts", class: "miss-box" }, [
    el("summary", {}, []),
    el("div", { class: "miss-stage" },
       [el("p", { class: "miss-people name-line" }, [held])]),
    el("div", { class: "miss-stage" },
       [el("p", { class: "miss-people name-line" }, [cb])])
  ]);
}

// 딜 소싱 명단. **투자사 담당자와 다른 표라 그룹 칸이 아예 없다** — 그 대신
// 갈래(`data-bucket`)가 같은 일을 한다. 두 목록이 서로 섞이지 않는지 보려면
// 이쪽에도 고를 것이 있어야 한다.
const SOURCING = [
  [101, "가소싱", "시리즈 A 이상 딜소싱 참여 심사역"],
  [102, "나소싱", "M&A 찾는 투자사"]
];

function sourcingCard(id, name, bucket) {
  const cb = el("input", {
    id: "scb-" + id, class: "contact-cb", value: String(id), "data-name": name
  });
  return el("label", {
    class: "pick-card", "data-bucket": bucket, "data-assignee": "",
    "data-search": (name + " " + bucket).toLowerCase()
  }, [cb]);
}

// ① 소개할 기업 목록. **화면에 그려진 차례**가 곧 고르는 차례가 아니다 —
// 3번째를 먼저 고르고 1번째를 나중에 골라도 고른 차례대로 나가야 한다.
// 실제 화면(`deals.html`)과 같은 모양으로 세운다: `label.pick-card` 안에
// 체크박스가 들어 있고, 고른 차례는 **카드**에 적힌다(`data-pick-order`).
const COMPANIES = [
  // id, 이름(가상)
  [201, "가나애그"],
  [202, "다라헬스"],
  [203, "마바로보"]
];

function companyCard(id, name) {
  const cb = el("input", {
    id: "ccb-" + id, class: "company-cb", value: String(id),
    "data-name": name, "data-thin": "0", "data-ir-url": "https://example.test/" + id
  });
  return el("label", {
    class: "pick-card", "data-recent": "0",
    "data-search": name.toLowerCase()
  }, [cb, el("div", { class: "pick-body" }, [el("div", { class: "pick-name" }, [])])]);
}

// 예약 큐 한 줄. **`data-count` 가 화면이 지금 말하고 있는 수**다 — [시작] 이
// 이 값을 서버로 함께 보내야, 서버가 다시 센 수와 다를 때 되물을 수 있다.
// 실제 화면이 같은 속성을 그리는지는 파이썬 쪽(`tests/test_deal_queue.py`)이 본다.
function queueRow(id, group, count) {
  return el("div", { class: "queue-row", "data-id": String(id),
                     "data-group": group, "data-count": String(count) }, [
    el("button", { class: "primary-btn inline queue-start" }),
    el("button", { class: "linkbtn danger queue-cancel" })
  ]);
}

function buildDom(people) {
  dom_.resetHandlers();
  const root = makeEl("html");
  const roster = people || PEOPLE;

  const cards = roster.map(function (p) { return contactCard(p[0], p[1], p[2], p[3]); });
  const contactList = el("div", { id: "contact-list", class: "card-list" }, cards);
  const blocked = blockedBlock();
  const sourcingCards = SOURCING.map(function (s) { return sourcingCard(s[0], s[1], s[2]); });
  const sourcingList = el("div", { id: "sourcing-list", class: "card-list" }, sourcingCards);
  const companyCards = COMPANIES.map(function (c) { return companyCard(c[0], c[1]); });
  const companyList = el("div", { id: "company-list", class: "card-list" }, companyCards);
  const companyPanel = el("section", { class: "panel" }, [companyList]);

  // 그룹 칩은 명단에 실제로 있는 그룹만큼 선다(서버의 `sheet_owner.group_rows`).
  const groups = [];
  roster.forEach(function (p) {
    if (p[2] && groups.indexOf(p[2]) < 0) groups.push(p[2]);
  });
  const chips = [el("button", { class: "chip active", "data-value": "" })]
    .concat(groups.map(function (g) {
      return el("button", { class: "chip", "data-value": g });
    }))
    .concat([el("button", { class: "chip", "data-value": EMPTY_GROUP })]);
  const groupBar = el("div", { id: "group-filter", "data-empty": EMPTY_GROUP }, chips);
  const groupBox = el("div", { id: "contact-filters", class: "pick-filters" }, [groupBar]);

  // 갈래 칩. **딜 소싱은 갈래가 곧 문구**라, 이 칩은 목록만 거르는 것이 아니라
  // 미리보기를 바꾼다 — 그 이음새를 보려면 진짜 칩이 서 있어야 한다.
  // (실제 화면이 같은 아이디·속성을 그리는지는 파이썬 쪽이 따로 본다)
  const bucketNames = [];
  SOURCING.forEach(function (s) {
    if (bucketNames.indexOf(s[2]) < 0) bucketNames.push(s[2]);
  });
  const bucketChips = [el("button", { class: "chip active", "data-value": "" })]
    .concat(bucketNames.map(function (b) {
      return el("button", { class: "chip", "data-value": b });
    }));
  const bucketBar = el("div", { id: "bucket-filter" }, bucketChips);
  const sourcingBox = el("div", { id: "sourcing-filters", class: "pick-filters" },
                         [bucketBar]);

  const simple = ["company-pill", "contact-pill", "contact-summary", "ss-companies",
                  "ss-contacts", "ss-note", "preview-tabs", "preview-area",
                  "send-warnings", "send-btn", "refresh-preview", "contact-search",
                  "only-picked-contacts", "company-search", "only-picked",
                  "company-filter-note", "contact-filter-note", "bucket-mix-note",
                  "select-all-contacts", "clear-all-contacts", "select-noreact",
                  "batch-title", "include-opening", "tpl-opening", "tpl-closing",
                  "tpl-opening-wrap", "ir-attach", "ir-links",
                  "mail-fields", "mail-subject", "company-hint", "mode-help"]
    .map(function (id) { return el("div", { id: id }); });
  // 방식을 바꾸면 이 칸의 이름표(`안내문`/`문구`)를 고쳐 쓴다 — 속 `span` 이
  // 없으면 탭을 누르는 순간 화면 코드가 그대로 죽는다(실제 화면에는 있다).
  simple.push(el("div", { id: "tpl-closing-wrap" }, [el("span", {})]));

  const arrow = el("span", { class: "ss-arrow" });
  const modeTabs = ["deal", "ir", "remind", "meeting", "review", "ask", "sourcing"]
    .map(function (m, i) {
      return el("button", { class: i === 0 ? "mode-tab active" : "mode-tab", "data-mode": m });
    });
  const channel = el("input", { name: "channel", value: "kakao" });
  channel.checked = true;

  const queueRows = [queueRow(7, "1군", 24)];
  const queueList = el("div", { id: "queue-list" }, queueRows);
  const queuePanel = el("section", { id: "deal-queue", class: "panel" }, [
    el("select", { id: "queue-group" }, []),
    el("button", { id: "queue-add" }),
    queueList
  ]);

  [companyPanel, contactList, blocked, sourcingList, groupBox, sourcingBox,
   arrow, channel, queuePanel]
    .concat(simple).concat(modeTabs)
    .forEach(function (node) { root.appendChild(node); });

  // `blockedCbs` 는 접힌 칸의 체크박스 **전부**다. 하나만 들고 보면 사유가
  // 하나 늘었을 때 그 줄만 좁힘 밖에 서 있어도 검사가 통과한다.
  const blockedCbs = Array.prototype.slice.call(
    blocked.querySelectorAll(".contact-cb"));
  return { root: root, document: dom_.makeDocument(root), cards: cards,
           sourcingCards: sourcingCards, companyCards: companyCards,
           // deals.js 가 `#company-list` 에서 거슬러 올라가 잡는 바로 그 칸
           // (`.closest(".panel")`). 방식에 따라 여기에 표시가 붙는다 —
           // `dimmed`(문구만 보낼 때) · `no-pick-badge`(자료 전달).
           companyPanel: companyPanel,
           queuePanel: queuePanel, queueRows: queueRows,
           blocked: blocked, blockedCbs: blockedCbs,
           blockedCb: blockedCbs[blockedCbs.length - 1] };
}

// deals.js 를 이 화면 위에서 그대로 돌린다.
//
// `opts` 로 `fetch`·`confirm`·`alert` 를 갈아 끼울 수 있다 — 예약 큐 검사는
// **서버가 돌려준 말이 확인창에 그대로 뜨는지**를 봐야 해서 둘 다 필요하다.
// 안 주면 지금까지와 똑같다(절대 안 풀리는 약속 · 확인창은 늘 아니오).
//
// `opts.search` 는 주소 뒤에 붙는 물음표 뒷부분이다(`?companies=203,201`).
// IR 관리에서 넘어오면 화면이 그것을 읽어 기업을 미리 켜 둔다 — 그 차례까지
// 지켜지는지 보려면 이 자리가 필요하다.
function run(people, opts) {
  const fs = require("fs");
  const path = require("path");
  const vm = require("vm");
  const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "deals.js");
  const src = fs.readFileSync(SRC, "utf8");

  opts = opts || {};
  const dom = buildDom(people);
  // `reload` 는 예약 큐가 줄을 다시 그리려고 부른다(대상 수는 서버가 센 값이라
  // 화면이 흉내 내면 붙인 순간 낡는다). 몇 번 불렸는지 세어 둔다.
  const win = { location: { search: opts.search || "", href: "", reloads: 0,
                            reload: function () { this.reloads += 1; } } };
  const ctx = {
    document: dom.document, console: console, window: win,
    // 미리보기는 손이 멈춘 뒤에 부른다(`schedulePreview`). 기본값은 지금까지와
    // 같이 **안 부르는 것**이고, 그 부름까지 보려는 검사만 갈아 끼운다.
    setTimeout: opts.setTimeout || function () { return 0; },
    clearTimeout: function () {},
    URLSearchParams: URLSearchParams,
    alert: opts.alert || function () {},
    confirm: opts.confirm || function () { return false; },
    fetch: opts.fetch || function () {
      // 문구 목록·미리보기는 이 검사들과 무관하다. 절대 안 풀리는 약속을 준다.
      return { then: function () { return this; }, catch: function () { return this; } };
    }
  };
  ctx.window = win;
  Object.assign(win, { location: win.location, document: dom.document });
  vm.runInNewContext(src, ctx, { filename: "deals.js" });
  dom.window = win;
  return dom;
}

// ── 아주 작은 fetch 대역 ───────────────────────────────────────────────────
//
// 오간 요청을 그대로 모아 두고, 미리 정해 둔 답을 차례대로 돌려준다(약속은
// 곧바로 풀린다 — 검사가 기다릴 것이 없다). **여기 한 벌만 둔다** — 검사마다
// 한 벌씩 들고 있으면 한쪽만 고쳐져 나머지는 딴 것을 보증한다(`_dom.js` 와 같은 뜻).
function fakeFetch(replies) {
  const calls = [];
  // `.then()` 이 또 약속을 돌려주면 **펴 준다**(진짜 Promise 처럼). deals.js 가
  // `r.json().then(...)` 을 바깥 `.then` 에서 돌려주는데, 안 펴 주면 다음
  // 단계가 값 대신 약속을 받아 엉뚱한 곳에서 죽는다.
  function settled(value) {
    return {
      __settled: true,
      then: function (fn) {
        const next = fn(value);
        return (next && next.__settled) ? next : settled(next);
      },
      catch: function () { return this; }
    };
  }
  const fn = function (url, init) {
    const body = JSON.parse((init && init.body) || "{}");
    calls.push({ url: url, body: body });
    // 문구 목록(GET)은 이 검사들과 무관하다 — 안 풀리는 약속을 준다.
    if (!init || init.method !== "POST") {
      return { then: function () { return this; }, catch: function () { return this; } };
    }
    const reply = replies.length ? replies.shift() : { ok: true, d: {} };
    return settled({
      ok: reply.ok !== false,
      json: function () { return settled(reply.d); }
    });
  };
  fn.calls = calls;
  return fn;
}

// ── 기업 고르기 ────────────────────────────────────────────────────────────

function companyBox(dom, name) {
  const cb = dom.companyCards
    .map(function (card) { return card.querySelector(".company-cb"); })
    .filter(function (c) { return c.getAttribute("data-name") === name; })[0];
  require("assert").ok(cb, "기업 카드를 못 찾았다: " + name);
  return cb;
}

// 사람이 카드를 누르는 것과 같다 — 체크를 뒤집고 `change` 를 흘린다.
function toggleCompany(dom, name) {
  const cb = companyBox(dom, name);
  cb.checked = !cb.checked;
  cb.fire("change");
  return cb;
}

// 카드에 **보이는 번호**. 안 고른 카드는 `null` 이다.
// 화면에 뜨는 번호와 서버로 나가는 차례가 **같은 한 자리**에서 나와야 하므로
// (`data-pick-order`), 검사도 그 한 자리를 본다.
function pickNumbers(dom) {
  const out = {};
  dom.companyCards.forEach(function (card) {
    out[card.querySelector(".company-cb").getAttribute("data-name")] =
      card.getAttribute("data-pick-order");
  });
  return out;
}

function boxes(dom) {
  return dom.cards.map(function (card) { return card.querySelector(".contact-cb"); });
}
function checkedNames(dom) {
  return boxes(dom).filter(function (cb) { return cb.checked; })
    .map(function (cb) { return cb.getAttribute("data-name"); }).sort();
}
function shownNames(dom) {
  return dom.cards.filter(function (c) { return !c.hidden; })
    .map(function (c) { return c.querySelector(".contact-cb").getAttribute("data-name"); }).sort();
}
function pickGroup(dom, value) {
  const chip = dom.document.querySelector('#group-filter .chip[data-value="' + value + '"]');
  require("assert").ok(chip, "그룹 칩을 못 찾았다: " + value);
  chip.fire("click");
}
function pickBucket(dom, value) {
  const chip = dom.document.querySelector('#bucket-filter .chip[data-value="' + value + '"]');
  require("assert").ok(chip, "갈래 칩을 못 찾았다: " + value);
  chip.fire("click");
}
// 보내는 방식 탭을 누른다(딜 소개 · 자료 전달 · 리마인드 …).
function pickMode(dom, mode) {
  const tab = dom.document.querySelector('.mode-tab[data-mode="' + mode + '"]');
  require("assert").ok(tab, "방식 탭을 못 찾았다: " + mode);
  tab.fire("click");
}
function clickSelectAll(dom) { dom.document.getElementById("select-all-contacts").fire("click"); }
function clickClearAll(dom) { dom.document.getElementById("clear-all-contacts").fire("click"); }

module.exports = { EMPTY_GROUP: EMPTY_GROUP, PEOPLE: PEOPLE, SOURCING: SOURCING,
                   COMPANIES: COMPANIES,
                   fakeFetch: fakeFetch, companyBox: companyBox,
                   toggleCompany: toggleCompany, pickNumbers: pickNumbers,
                   buildDom: buildDom, queueRow: queueRow,
                   run: run, boxes: boxes, checkedNames: checkedNames,
                   shownNames: shownNames, pickGroup: pickGroup,
                   pickBucket: pickBucket, pickMode: pickMode,
                   clickSelectAll: clickSelectAll, clickClearAll: clickClearAll };
