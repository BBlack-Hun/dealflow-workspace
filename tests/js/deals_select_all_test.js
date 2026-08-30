// 그룹으로 추린 뒤 [전체선택]이 **걸러진 사람에게만** 걸리는가.
// (node tests/js/deals_select_all_test.js)
//
// 이 화면에서 가장 위험한 자리다. 목록에서 안 보이는 사람까지 체크되면 그대로
// **실제 투자사 카톡방으로 문구가 나간다** — 되돌릴 수가 없다.
//
// 눈에 안 띄는 함정이 하나 있다. 이 화면은 **고른 사람을 조건에서 벗어나도
// 계속 보여 준다**(몇 명 골랐는지 알아야 하므로). 그래서 `안 숨겨졌다 = 조건에
// 맞다` 로 읽으면, 그룹 A 에서 몇 명 고른 뒤 그룹 B 로 추리고 [전체선택]을
// 누르는 순간 A 의 그 사람들까지 함께 켜진다. 화면은 "그룹 B" 라고 적혀 있는데
// 발송 대상에는 A 가 섞여 있다.
//
// 규칙을 옮겨 적어 검사하면 두 벌이 되어 어긋나도 모른다. 그래서 **deals.js 를
// 그대로 실행**한다 — 이 파일이 쓰는 만큼만 가짜 DOM 을 세우고 vm 으로 돌린다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "deals.js");
const src = fs.readFileSync(SRC, "utf8");

// 서버가 `sheet_owner.EMPTY_GROUP` 으로 실어 보내는 말. 표 필터(filters.js)의
// `EMPTY` 와 같은 글자여야 한다 — 그 짝은 파이썬 쪽 검사가 지킨다.
const EMPTY_GROUP = "(비어 있음)";

const dom_ = require("./_dom.js");
const makeEl = dom_.makeEl;
const el = dom_.el;
const queryAll = dom_.queryAll;

// ── 화면 세우기 ─────────────────────────────────────────────────────────────
// deals.html 의 `② 대상 담당자` 칸을 그대로 옮긴다. 이 짝(아이디·속성)이
// 템플릿과 어긋나면 여기 검사가 헛돌므로, **실제로 그려진 화면에 같은 아이디와
// 속성이 있는지**는 파이썬 쪽(tests/test_deals_recipients.py)이 따로 본다.

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

const PEOPLE = [
  // id, 이름(가상), 그룹, 반응 없음
  [1, "가담당", "1군", true],
  [2, "나담당", "1군", false],
  [3, "다담당", "2군", true],
  [4, "라담당", "2군", false],
  [5, "마담당", "", false]      // 그룹을 안 정해 둔 사람
];

function buildDom() {
  dom_.resetHandlers();
  const root = makeEl("html");

  const cards = PEOPLE.map(function (p) { return contactCard(p[0], p[1], p[2], p[3]); });
  const contactList = el("div", { id: "contact-list", class: "card-list" }, cards);
  const sourcingList = el("div", { id: "sourcing-list", class: "card-list" }, []);
  const companyList = el("div", { id: "company-list", class: "card-list" }, []);
  const companyPanel = el("section", { class: "panel" }, [companyList]);

  const chips = [el("button", { class: "chip active", "data-value": "" })]
    .concat(["1군", "2군"].map(function (g) {
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
                  "select-all-contacts", "select-noreact", "sourcing-filters",
                  "batch-title", "include-opening", "tpl-opening", "tpl-closing",
                  "tpl-opening-wrap", "tpl-closing-wrap", "ir-attach", "ir-links",
                  "mail-fields", "mail-subject", "company-hint", "mode-help"]
    .map(function (id) { return el("div", { id: id }); });

  const arrow = el("span", { class: "ss-arrow" });
  const modeTabs = ["deal", "ir", "remind", "meeting", "review", "ask", "sourcing"]
    .map(function (m, i) {
      return el("button", { class: i === 0 ? "mode-tab active" : "mode-tab", "data-mode": m });
    });
  const channel = el("input", { name: "channel", value: "kakao" });
  channel.checked = true;

  [companyPanel, contactList, sourcingList, groupBox, arrow, channel]
    .concat(simple).concat(modeTabs)
    .forEach(function (node) { root.appendChild(node); });

  return { root: root, document: dom_.makeDocument(root), cards: cards };
}

function run() {
  const dom = buildDom();
  const win = { location: { search: "", href: "" } };
  const ctx = {
    document: dom.document, console: console, window: win,
    setTimeout: function () { return 0; }, clearTimeout: function () {},
    URLSearchParams: URLSearchParams,
    alert: function () {}, confirm: function () { return false; },
    fetch: function () {
      // 문구 목록·미리보기는 이 검사와 무관하다. 절대 안 풀리는 약속을 준다.
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
  assert.ok(chip, "그룹 칩을 못 찾았다: " + value);
  chip.fire("click");
}
function clickSelectAll(dom) { dom.document.getElementById("select-all-contacts").fire("click"); }

// ── 1) 그룹 필터가 실제로 줄을 거른다 ───────────────────────────────────────
{
  const dom = run();
  assert.deepStrictEqual(shownNames(dom),
    ["가담당", "나담당", "다담당", "라담당", "마담당"],
    "아무 것도 안 골랐는데 누가 숨겨져 있다");

  pickGroup(dom, "1군");
  assert.deepStrictEqual(shownNames(dom), ["가담당", "나담당"],
    "그룹으로 추렸는데 다른 그룹이 그대로 보인다");

  pickGroup(dom, EMPTY_GROUP);
  assert.deepStrictEqual(shownNames(dom), ["마담당"],
    "`(비어 있음)` 은 그룹을 안 정해 둔 사람만이어야 한다");

  pickGroup(dom, "");
  assert.deepStrictEqual(shownNames(dom).length, 5, "[전체] 로 돌아오지 않는다");
}

// ── 2) [전체선택]은 걸러진 사람에게만 걸린다 ────────────────────────────────
{
  const dom = run();
  pickGroup(dom, "2군");
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["다담당", "라담당"],
    "그룹으로 추려 놓고 [전체선택]을 눌렀는데 다른 그룹까지 켜졌다 — " +
    "그대로 실제 투자사 방으로 문구가 나간다");
}

// ── 3) ★ 이미 고른 사람이 있어도 마찬가지다 ─────────────────────────────────
//
// 여기가 진짜 함정이다. 고른 사람은 조건에서 벗어나도 계속 **보인다** —
// `보인다 = 조건에 맞다` 로 읽으면 아까 고른 1군이 2군 전체선택에 딸려 온다.
{
  const dom = run();
  pickGroup(dom, "1군");
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "나담당"]);

  pickGroup(dom, "2군");
  // 고른 1군은 계속 보인다(몇 명 골랐는지 알아야 한다) — 그건 그대로 둔다.
  assert.ok(shownNames(dom).indexOf("가담당") >= 0,
    "고른 사람이 사라지면 몇 명 골랐는지 알 수 없다");

  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "나담당", "다담당", "라담당"],
    "2군을 켜는 조작이 1군을 건드렸거나, 2군이 안 켜졌다");

  // 한 번 더 누르면 **2군만** 꺼진다. 1군은 이 조작의 대상이 아니다.
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당", "나담당"],
    "[전체선택]을 되돌리는데 조건 밖 사람까지 껐다");
}

// ── 4) 검색으로 좁혀도 같은 규칙 ────────────────────────────────────────────
{
  const dom = run();
  const search = dom.document.getElementById("contact-search");
  search.value = "가담당";
  search.fire("input");
  clickSelectAll(dom);
  assert.deepStrictEqual(checkedNames(dom), ["가담당"],
    "검색으로 좁혀 놓고 누른 [전체선택]에 안 보이는 사람이 딸려 왔다");
}

// ── 5) [반응 없는 담당자만] 도 추린 안에서만 ────────────────────────────────
{
  const dom = run();
  pickGroup(dom, "2군");
  dom.document.getElementById("select-noreact").fire("click");
  assert.deepStrictEqual(checkedNames(dom), ["다담당"],
    "그룹으로 추려 놓았는데 다른 그룹의 '반응 없음' 까지 켜졌다");
}

// ── 6) 조건 밖에서 고른 사람이 있으면 화면이 말해 준다 ──────────────────────
//
// 그 사람들도 그대로 발송에 들어간다. 숫자만 줄어든 줄 알고 보내면 안 된다.
{
  const dom = run();
  pickGroup(dom, "1군");
  clickSelectAll(dom);
  pickGroup(dom, "2군");
  const note = dom.document.getElementById("contact-filter-note");
  assert.ok(/조건 밖에서 고른 2명/.test(note.textContent),
    "조건 밖에서 고른 사람이 발송에 남아 있는데 화면이 말하지 않는다: " + note.textContent);
}

console.log("deals_select_all_test: 통과");
