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

// 연결이 안 끝나 **발송 목록에 없는** 사람(`sheet_owner.blocked_stages`).
// 화면은 이 자리에 입력칸을 두지 않지만, 여기서는 **일부러 체크박스를 붙인다.**
// 검사가 지키려는 것은 "화면이 체크박스를 안 그린다" 가 아니라 **"목록 밖의
// 체크박스는 어떤 조작에도 안 딸려 온다"** 이기 때문이다 — deals.js 가 고르는
// 상자를 `#contact-list` 안으로 좁혀 둔(`contactCbs`) 덕이고, 그 좁힘이 풀리면
// 연결도 안 된 사람에게 문구가 나간다. 되돌릴 수 없는 일이라 여기서 못박는다.
function blockedBlock() {
  const cb = el("input", {
    id: "cb-99", class: "contact-cb", value: "99",
    "data-name": "못보낼담당", "data-noreact": "1"
  });
  return el("details", { id: "blocked-contacts", class: "miss-box" }, [
    el("summary", {}, []),
    el("p", { class: "miss-people name-line" }, [cb])
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

function buildDom(people) {
  dom_.resetHandlers();
  const root = makeEl("html");
  const roster = people || PEOPLE;

  const cards = roster.map(function (p) { return contactCard(p[0], p[1], p[2], p[3]); });
  const contactList = el("div", { id: "contact-list", class: "card-list" }, cards);
  const blocked = blockedBlock();
  const sourcingCards = SOURCING.map(function (s) { return sourcingCard(s[0], s[1], s[2]); });
  const sourcingList = el("div", { id: "sourcing-list", class: "card-list" }, sourcingCards);
  const companyList = el("div", { id: "company-list", class: "card-list" }, []);
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

  const simple = ["company-pill", "contact-pill", "contact-summary", "ss-companies",
                  "ss-contacts", "ss-note", "preview-tabs", "preview-area",
                  "send-warnings", "send-btn", "refresh-preview", "contact-search",
                  "only-picked-contacts", "company-search", "only-picked",
                  "company-filter-note", "contact-filter-note", "bucket-mix-note",
                  "select-all-contacts", "clear-all-contacts", "select-noreact",
                  "sourcing-filters",
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

  [companyPanel, contactList, blocked, sourcingList, groupBox, arrow, channel]
    .concat(simple).concat(modeTabs)
    .forEach(function (node) { root.appendChild(node); });

  return { root: root, document: dom_.makeDocument(root), cards: cards,
           sourcingCards: sourcingCards,
           blocked: blocked, blockedCb: blocked.querySelector(".contact-cb") };
}

// deals.js 를 이 화면 위에서 그대로 돌린다.
function run(people) {
  const fs = require("fs");
  const path = require("path");
  const vm = require("vm");
  const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "deals.js");
  const src = fs.readFileSync(SRC, "utf8");

  const dom = buildDom(people);
  const win = { location: { search: "", href: "" } };
  const ctx = {
    document: dom.document, console: console, window: win,
    setTimeout: function () { return 0; }, clearTimeout: function () {},
    URLSearchParams: URLSearchParams,
    alert: function () {}, confirm: function () { return false; },
    fetch: function () {
      // 문구 목록·미리보기는 이 검사들과 무관하다. 절대 안 풀리는 약속을 준다.
      return { then: function () { return this; }, catch: function () { return this; } };
    }
  };
  ctx.window = win;
  Object.assign(win, { location: win.location, document: dom.document });
  vm.runInNewContext(src, ctx, { filename: "deals.js" });
  return dom;
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
function clickSelectAll(dom) { dom.document.getElementById("select-all-contacts").fire("click"); }
function clickClearAll(dom) { dom.document.getElementById("clear-all-contacts").fire("click"); }

module.exports = { EMPTY_GROUP: EMPTY_GROUP, PEOPLE: PEOPLE, SOURCING: SOURCING,
                   buildDom: buildDom,
                   run: run, boxes: boxes, checkedNames: checkedNames,
                   shownNames: shownNames, pickGroup: pickGroup,
                   clickSelectAll: clickSelectAll, clickClearAll: clickClearAll };
