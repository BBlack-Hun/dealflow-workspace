// 문구 관리 화면의 **문구 검색** — 단어·문장으로 문구가 찾아지는가.
// (node tests/js/templates_search_test.js)
//
// 실제로 나가는 `app/static/js/templates_search.js` 를 그대로 돌린다. 화면 틀이
// 거르는 단위(구간 › 갈래 › 문구)를 정말 싣고 있는지도 `templates.html` 에서
// 읽어 본다 — 한쪽만 바뀌면 검색칸이 아무 일도 안 하는 칸이 된다.
//
// 잠그는 것:
//   · 문구 이름 · 본문 · 구간 제목줄(종류 · 설명)로 찾아진다.
//   · 대소문자 · 띄어쓰기를 안 따진다. 여러 낱말은 **모두** 들어야 걸린다.
//   · 남은 문구가 없는 갈래 · 구간은 제목째 숨는다. 하나도 없으면 `검색 결과 없음`.
//   · **고치던 칸이 안 날아간다** — 고친 글자로 찾아지고, 걸러도 값이 그대로다.
//   · 접힌 `그 밖의 문구` 는 걸리면 펴지고, 지우면 원래 접힘으로 돌아간다.
//   · 검색어를 지우면 전부 되돌아온다.
//
// 문구는 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(
  path.join(ROOT, "app", "static", "js", "templates_search.js"), "utf8");
const PAGE = fs.readFileSync(
  path.join(ROOT, "app", "templates", "templates.html"), "utf8");

// ── 화면 틀이 거르는 단위를 싣는가 ─────────────────────────────────────────
{
  assert.ok(/<input type="search" id="tpl-search"/.test(PAGE), "검색칸이 없다");
  const ph = PAGE.match(/id="tpl-search" placeholder="([^"]*)"/);
  assert.ok(ph && /\(\{\{ tpl_count\.n \}\}개\)/.test(ph[1]),
    "placeholder 에 문구 개수가 없다");
  assert.ok(/id="tpl-search-empty" hidden>검색 결과 없음</.test(PAGE),
    "`검색 결과 없음` 줄이 없다");
  assert.ok(/<div class="panel" id="\{\{ g\.kind \}\}">\s*<h2 class="panel-title tpl-kind-title">/.test(PAGE),
    "구간 제목줄(tpl-kind-title)이 구간(.panel) 바로 안에 없다");
  assert.ok(/<div class="tpl-slot">/.test(PAGE), "갈래를 tpl-slot 으로 안 묶는다");
  assert.ok(/\/edit" class="tpl-item" data-tpl-row>/.test(PAGE),
    "문구 줄에 data-tpl-row 가 없다");
  assert.ok(/class="panel-title tpl-kind-title"/.test(PAGE), "구간 제목줄 이름이 바뀌었다");
  assert.ok(/<textarea name="body"/.test(PAGE) && /<input type="text" name="name"/.test(PAGE),
    "문구 칸(이름 · 본문) 모양이 바뀌었다");
  assert.ok(/js\/templates_search\.js/.test(PAGE), "templates_search.js 를 안 싣는다");
}

// ── 화면 한 벌 ───────────────────────────────────────────────────────────
//
// 브라우저의 `textContent` 는 자식 글자까지 모은다 — 이 작은 DOM 은 안 모으므로
// 제목줄은 화면에 보이는 글자를 통째로 적어 둔다.
function row(name, body, tags) {
  const tagEls = (tags || ["팀 기본"]).map(function (t) {
    const s = D.el("span", { class: "tag" });
    s.textContent = t;
    return s;
  });
  const input = D.el("input", { type: "text", name: "name", value: name });
  const area = D.el("textarea", { name: "body", rows: "3" });
  area.value = body;
  return D.el("form", { method: "post", class: "tpl-item", "data-tpl-row": "" }, [
    D.el("div", { class: "tpl-head" }, [input].concat(tagEls)),
    area
  ]);
}

function slot(rows, bucket) {
  const kids = [];
  if (bucket) {
    const h3 = D.el("h3", { class: "panel-title" });
    h3.textContent = bucket;
    kids.push(h3);
  }
  return D.el("div", { class: "tpl-slot" }, kids.concat(rows));
}

function section(kind, head, slots) {
  const h2 = D.el("h2", { class: "panel-title tpl-kind-title" });
  h2.textContent = head;
  // 새 문구 만들기 칸 — 문구가 아니라 안 걸러야 한다.
  const draft = D.el("details", { class: "tpl-new" }, [
    D.el("form", {}, [D.el("input", { type: "text", name: "name", value: "" }),
                      D.el("textarea", { name: "body" })])
  ]);
  return D.el("div", { class: "panel", id: kind },
              [h2].concat(slots, [draft]));
}

function build() {
  D.resetHandlers();
  const r = {
    deal: row("기본 안내", "아래 기업들을 소개드립니다.\n검토 부탁드립니다."),
    dealMine: row("짧은 안내", "IR 자료가 필요하시면 말씀해 주세요.",
                  ["내 문구", "꺼진 문구 — 발송에 쓰이지 않습니다"]),
    remind: row("리마인드 기본", "지난주 보내 드린 기업 중 관심 있으신 곳이 있을까요?"),
    srcA: row("시리즈 A 이상", "대표님, 딜 소싱에 함께해 주실 수 있을까요?"),
    srcB: row("개인 참여", "개인 투자자분께 드리는 안내입니다."),
    greet: row("첫 인사", "안녕하세요, 처음 인사드립니다.")
  };
  const deal = section("closing_day1",
    "안내문 — 딜소개 딜 제안 관리 · 딜 소개 탭 기업 목록 위에 오는 안내 문구",
    [slot([r.deal, r.dealMine])]);
  const remind = section("closing_remind",
    "안내문 — 리마인드 딜 제안 관리 · 리마인드 탭 딜소개 발송 6~7일 뒤에 보냅니다",
    [slot([r.remind])]);
  const sourcing = section("sourcing_intro",
    "딜 소싱 제안 딜 제안 관리 · 딜 소싱 제안 탭 갈래마다 하나씩",
    [slot([r.srcA], "시리즈 A 이상"), slot([r.srcB], "개인 참여")]);
  // 문구가 하나도 없는 종류 — 제목이 걸리면 구간이 남아야 거기서 새로 만든다.
  const call = section("connect_call", "연결 — 전화 응대 카톡방 연결 전 첫 통화",
    [slot([])]);
  const opening = section("opening_first", "인사말 — 첫 연락 처음 딜소개를 보내는 담당자에게",
    [slot([r.greet])]);

  const others = D.el("details", { id: "others" }, [D.el("summary", {}), opening, call]);
  others.open = false;

  const box = D.el("input", { type: "search", id: "tpl-search" });
  const note = D.el("span", { class: "hint", id: "tpl-search-note" });
  note.hidden = true;
  const empty = D.el("p", { class: "muted", id: "tpl-search-empty" });
  empty.hidden = true;
  empty.textContent = "검색 결과 없음";

  const root = D.el("main", {}, [
    D.el("div", { class: "panel" }, [D.el("div", { class: "picker-search" }, [box, note]), empty]),
    deal, remind, sourcing, others
  ]);
  const document = D.makeDocument(root);
  const sandbox = { document: document, console: console };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "templates_search.js" });
  return { box: box, note: note, empty: empty, others: others, rows: r,
           secs: { deal: deal, remind: remind, sourcing: sourcing, call: call,
                   opening: opening } };
}

function type(dom, value) { dom.box.value = value; dom.box.fire("input"); }

// 지금 보이는 문구 이름들(조상 중 하나라도 숨었으면 안 보이는 것이다).
function visibleNames(dom) {
  return Object.keys(dom.rows).filter(function (k) {
    let node = dom.rows[k];
    while (node) {
      if (node.hidden) return false;
      if (node.tag === "details" && node.getAttribute("id") === "others" && !node.open) {
        return false;
      }
      node = node.parent;
    }
    return true;
  }).sort();
}

const ALL = ["deal", "dealMine", "greet", "remind", "srcA", "srcB"];

function main() {
  // ── 1. 문구 이름으로 ────────────────────────────────────────────────
  {
    const dom = build();
    type(dom, "짧은 안내");
    assert.deepStrictEqual(visibleNames(dom), ["dealMine"], "이름으로 안 좁혀진다");
    assert.strictEqual(dom.secs.deal.hidden, false);
    assert.strictEqual(dom.rows.deal.hidden, true, "같은 구간의 다른 문구가 남았다");
    assert.strictEqual(dom.note.hidden, false);
    assert.strictEqual(dom.note.textContent, "1 / 6개 표시 중");
    assert.strictEqual(dom.empty.hidden, true);
  }

  // ── 2. 본문으로 — 대소문자 · 띄어쓰기 · 줄바꿈을 안 따진다 ──────────
  {
    const dom = build();
    type(dom, "관심 있으신");
    assert.deepStrictEqual(visibleNames(dom), ["remind"], "본문 낱말로 안 찾아진다");
    type(dom, "ir 자료");
    assert.deepStrictEqual(visibleNames(dom), ["dealMine"], "대문자 본문이 소문자로 안 걸린다");
    // 본문의 줄바꿈을 건너 붙여 쳐도 걸린다.
    type(dom, "소개드립니다.검토");
    assert.deepStrictEqual(visibleNames(dom), ["deal"], "줄바꿈을 건너면 안 걸린다");
    // `딜 소싱` 을 붙여 써도 걸린다.
    type(dom, "딜소싱에");
    assert.deepStrictEqual(visibleNames(dom), ["srcA"], "띄어쓰기를 따진다");
  }

  // ── 3. 여러 낱말은 모두 들어야 걸린다 ────────────────────────────────
  {
    const dom = build();
    type(dom, "기업 관심");
    assert.deepStrictEqual(visibleNames(dom), ["remind"],
      "한 낱말만 든 문구까지 걸린다 ★ 여러 낱말은 모두 들어야 한다");
    type(dom, "  검토   부탁드립니다  ");
    assert.deepStrictEqual(visibleNames(dom), ["deal"], "앞뒤 · 겹친 띄어쓰기에 흔들린다");
    // 구간 제목줄 + 본문을 함께 — `리마인드` 는 제목에만, `지난주` 는 본문에만 있다.
    type(dom, "리마인드 지난주");
    assert.deepStrictEqual(visibleNames(dom), ["remind"], "제목줄과 본문을 함께 못 본다");
  }

  // ── 4. 종류 이름 · 설명 · 꼬리표로 ────────────────────────────────────
  {
    const dom = build();
    type(dom, "6~7일 뒤");
    assert.deepStrictEqual(visibleNames(dom), ["remind"], "구간 설명으로 안 찾아진다");
    type(dom, "리마인드 탭");
    assert.deepStrictEqual(visibleNames(dom), ["remind"], "탭 이름으로 안 찾아진다");
    // 설명이 걸리면 그 구간 문구가 전부 남는다 — 본문에 그 말이 없어도.
    type(dom, "기업 목록 위");
    assert.deepStrictEqual(visibleNames(dom), ["deal", "dealMine"],
      "구간 설명이 걸렸는데 그 구간 문구가 다 안 남는다");
    type(dom, "꺼진");
    assert.deepStrictEqual(visibleNames(dom), ["dealMine"], "꼬리표로 안 찾아진다");
  }

  // ── 5. 남은 것이 없는 갈래 · 구간은 제목째 숨는다 ─────────────────────
  {
    const dom = build();
    type(dom, "개인 투자자");
    assert.deepStrictEqual(visibleNames(dom), ["srcB"]);
    const slots = dom.secs.sourcing.querySelectorAll(".tpl-slot");
    assert.strictEqual(slots[0].hidden, true, "남은 문구가 없는 갈래 제목이 남았다");
    assert.strictEqual(slots[1].hidden, false);
    assert.strictEqual(dom.secs.deal.hidden, true, "남은 문구가 없는 구간 제목이 남았다");
    assert.strictEqual(dom.secs.remind.hidden, true);
    assert.strictEqual(dom.others.hidden, true, "안에 걸린 것이 없는데 `그 밖의 문구` 가 남았다");
    // 갈래 이름으로 찾으면 그 갈래가 통째로 남는다.
    type(dom, "시리즈 a 이상");
    assert.strictEqual(slots[0].hidden, false);
    assert.strictEqual(slots[1].hidden, true);
  }

  // ── 6. 문구가 없는 종류도 제목이 걸리면 남는다 · `그 밖의 문구` 는 펴진다 ─
  {
    const dom = build();
    type(dom, "전화 응대");
    assert.strictEqual(dom.secs.call.hidden, false, "문구 없는 종류가 제목으로 안 찾아진다");
    assert.strictEqual(dom.others.hidden, false);
    assert.strictEqual(dom.others.open, true, "걸린 것이 접힌 칸 안에 있는데 안 펴진다");
    assert.strictEqual(dom.secs.opening.hidden, true);
    assert.strictEqual(dom.empty.hidden, true);
  }

  // ── 7. 하나도 없으면 `검색 결과 없음` ──────────────────────────────────
  {
    const dom = build();
    type(dom, "없는낱말");
    assert.deepStrictEqual(visibleNames(dom), []);
    assert.strictEqual(dom.empty.hidden, false, "`검색 결과 없음` 이 안 뜬다");
    assert.strictEqual(dom.note.textContent, "0 / 6개 표시 중");
    Object.keys(dom.secs).forEach(function (k) {
      assert.strictEqual(dom.secs[k].hidden, true, k + " 구간이 남았다");
    });
  }

  // ── 8. 지우면 전부 되돌아온다 — 접힘도 검색 전 그대로 ──────────────────
  {
    const dom = build();
    type(dom, "첫 인사");
    assert.deepStrictEqual(visibleNames(dom), ["greet"]);
    assert.strictEqual(dom.others.open, true);
    type(dom, "없는낱말");
    type(dom, "   ");
    assert.deepStrictEqual(visibleNames(dom), ALL.filter(function (k) { return k !== "greet"; }),
      "지웠는데 다 안 돌아온다(그 밖의 문구는 원래 접혀 있다)");
    assert.strictEqual(dom.others.open, false, "지웠는데 `그 밖의 문구` 가 펴진 채다");
    assert.strictEqual(dom.others.hidden, false);
    assert.strictEqual(dom.empty.hidden, true);
    assert.strictEqual(dom.note.hidden, true);
    Object.keys(dom.secs).forEach(function (k) {
      assert.strictEqual(dom.secs[k].hidden, false, k + " 구간이 숨은 채다");
      dom.secs[k].querySelectorAll(".tpl-slot").forEach(function (s) {
        assert.strictEqual(s.hidden, false, k + " 갈래가 숨은 채다");
      });
    });
    // 펴 둔 채로 검색했다 지우면 펴진 채로 돌아온다.
    const dom2 = build();
    dom2.others.open = true;
    type(dom2, "리마인드");
    assert.strictEqual(dom2.others.hidden, true);
    type(dom2, "");
    assert.strictEqual(dom2.others.open, true, "펴 둔 `그 밖의 문구` 가 접혔다");
    assert.deepStrictEqual(visibleNames(dom2), ALL);
  }

  // ── 9. 고치던 칸 — 고친 글자로 찾고, 걸러도 값이 그대로다 ───────────────
  {
    const dom = build();
    const area = dom.rows.remind.querySelector("textarea");
    area.value = "이번 주에 새로 고친 문장입니다";   // 저장 전
    type(dom, "새로 고친");
    assert.deepStrictEqual(visibleNames(dom), ["remind"], "고친 글자로 안 찾아진다");
    type(dom, "관심 있으신");                     // 저장 전 옛 글자
    assert.deepStrictEqual(visibleNames(dom), [], "화면에 없는 옛 글자로 걸린다");
    type(dom, "");
    assert.strictEqual(area.value, "이번 주에 새로 고친 문장입니다",
      "거르다가 고치던 칸이 되돌아갔다 ★ 저장 안 한 글자가 날아간다");
    // 이름 칸도 지금 값으로 본다.
    dom.rows.deal.querySelector("input").value = "연말 안내";
    type(dom, "연말");
    assert.deepStrictEqual(visibleNames(dom), ["deal"], "고친 이름으로 안 찾아진다");
    // 새 문구 만들기 칸은 문구가 아니다 — 거기 쓴 글자로 구간이 걸리면 안 된다.
    type(dom, "");
    dom.secs.remind.querySelector(".tpl-new textarea").value = "초안낱말";
    type(dom, "초안낱말");
    assert.deepStrictEqual(visibleNames(dom), [], "새 문구 초안으로 걸린다");
    assert.strictEqual(dom.secs.remind.querySelector(".tpl-new textarea").value, "초안낱말");
  }

  console.log("templates_search_test OK");
}

main();
