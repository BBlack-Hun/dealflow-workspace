// 담당자 고르기의 **검색** — 133명 중에서 이름으로 찾아지는가.
// (node tests/js/ir_contact_search_test.js)
//
// ── 여기서 잠그는 것 ─────────────────────────────────────────────────────
//
// 이 칸이 보내는 값은 **번호**(`contact_id`)라, 검색을 얹다가 그 값이 흔들리면
// 요청이 **엉뚱한 담당자에게** 적힌다. 그래서 잠그는 것이 "좁혀지는가" 만이
// 아니다.
//
//   · 이름·투자사 가운데 글자로도 좁혀진다.
//   · **검색은 거르기만 한다** — 좁혀졌다고 대신 골라 주지 않는다.
//   · 하나로 좁혀졌을 때의 Enter 는 고르고, 그 Enter 가 **폼을 안 보낸다.**
//   · 골랐다고 **알린다** — 지난 회차 번호가 그 알림을 듣는다(`ir_numbers.js`).
//   · 고른 사람은 검색어와 무관하게 남는다(딜 제안 관리와 같은 규칙).
//   · 아무도 안 맞으면 **빈 보기만 남는다** — `required` 가 막을 수 있어야 한다.
//   · 검색어를 지우면 전부 되돌아온다.
//   · 폼 **둘 다**(요청 적기 · 미팅 등록) 붙는다 — 한쪽만 달리면 그게 원래 문제다.
//   · [미팅 잡기] 로 사람을 넣는 길이 걸러 둔 목록에 막히지 않는다.
//   · **상태 꼬리표(`[방 나감]`)로도 좁혀진다** — 화면에 적어 놓고 그 말로
//     못 찾으면 꼬리표는 훑어야 보이는 글자일 뿐이다.
//
// 이름·투자사는 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js");
const SEARCH = fs.readFileSync(path.join(SRC, "ir_contact_search.js"), "utf8");
const NUMBERS = fs.readFileSync(path.join(SRC, "ir_numbers.js"), "utf8");

//: 화면이 그리는 담당자들. `data-search` 는 서버가 소문자로 만들어 싣는다.
//: `note` 는 **상태 꼬리표**(`sheet_owner.pick_note`) — 딜 제안 관리에서는
//: 빠지는데 이 고르기에는 남는 사람에게만 붙는다. 대부분은 안 붙는다.
const PEOPLE = [
  { id: 11, name: "가담당", title: "심사역", firm: "가나벤처스" },
  { id: 12, name: "나담당", title: "팀장", firm: "가나벤처스" },
  { id: 13, name: "다담당", title: "대표", firm: "다라인베스트" },
  { id: 14, name: "라담당", title: "수석", firm: "마바캐피탈" },
  { id: 15, name: "마담당", title: "이사", firm: "사아파트너스", note: "방 나감" }
];

function option(person) {
  // 서버가 그리는 그대로다(`ir.html` 의 `contact_pick`) — 보이는 글자 끝에
  // 대괄호 꼬리표가 붙고, **거르는 값에도 같은 말이 들어간다.**
  const tag = person.note ? " [" + person.note + "]" : "";
  const node = D.el("option", {
    value: String(person.id),
    "data-search": (person.name + " " + person.title + " " + person.firm
                    + " " + (person.note || "")).toLowerCase()
  });
  node.textContent = person.name + " " + person.title + " · " + person.firm + tag;
  return node;
}

// 서버가 그리는 한 벌(`ir.html` 의 `contact_pick` 매크로). **빈 보기가 맨 앞**이다.
function pick(pickId) {
  const box = D.el("input", {
    type: "search", class: "pick-filter", "data-contact-pick": pickId
  });
  const empty = D.el("option", { value: "" });
  empty.textContent = "담당자를 고르세요";
  const select = D.el("select", { id: pickId, name: "contact_id", required: "" },
                      [empty].concat(PEOPLE.map(option)));
  select.value = "";                       // 빈 보기가 골라진 채로 시작한다
  const note = D.el("p", { class: "hint pick-note",
                           "data-contact-pick-note": pickId });
  note.hidden = true;
  return { wrap: D.el("div", { class: "field inline-field contact-pick" },
                      [box, select, note]),
           box: box, select: select, note: note };
}

function build() {
  D.resetHandlers();
  const request = pick("request-contact");
  const meeting = pick("meeting-contact");

  const textarea = D.el("textarea", { id: "request-companies", name: "company_name" });
  const lastBatch = D.el("div", { class: "field inline-field wide", id: "last-batch" },
                         [D.el("em", { id: "last-batch-title" }),
                          D.el("div", { class: "num-pick", id: "num-pick" })]);
  lastBatch.hidden = true;

  const newRequest = D.el("div", { class: "member-form", id: "new-request" }, [
    D.el("form", { method: "post", action: "/ir/requests" },
         [request.wrap, lastBatch, textarea])
  ]);
  const newMeeting = D.el("div", { class: "member-form", id: "new-meeting" }, [
    D.el("form", { method: "post", action: "/ir/meetings" },
         [meeting.wrap, D.el("input", { type: "text", name: "company_name" }),
          D.el("select", { name: "kind" })])
  ]);
  newMeeting.hidden = true;

  // 전달한 자료 줄의 [미팅 잡기] — 담당자를 **밖에서 넣는** 길.
  const bookBtn = D.el("button", {
    type: "button", class: "linkbtn js-book-meeting",
    "data-contact": "13", "data-company": "샘플애그", "data-kind": "second"
  });

  const root = D.el("div", { class: "layout" }, [newRequest, newMeeting, bookBtn]);
  return { root: root, request: request, meeting: meeting,
           textarea: textarea, lastBatch: lastBatch, bookBtn: bookBtn };
}

function run(dom) {
  const asked = [];
  const document = D.makeDocument(dom.root);
  const win = { innerWidth: 1440, innerHeight: 900,
                addEventListener: function () {}, removeEventListener: function () {} };
  const sandbox = {
    document: document, console: console, setTimeout: setTimeout,
    // 브라우저의 `new Event("change")` 와 같은 자리. 없으면 알리는 길이
    // 검사에서만 다른 길로 새서, 정작 봐야 할 것(번호가 불리는가)을 못 본다.
    Event: function (type) { this.type = type; },
    fetch: function (url) {
      asked.push(url);
      return {
        then: function () { return this; }, catch: function () { return this; }
      };
    }
  };
  sandbox.window = win;
  win.document = document;
  // 브라우저는 `window.Event` 로 알린다 — 여기에도 두어야 검사가 그 길을
  // 지난다(안 두면 다른 길로 새고, 브라우저에서만 나는 고장을 못 본다).
  win.Event = sandbox.Event;
  vm.createContext(sandbox);
  // 화면이 싣는 차례 그대로 — 번호 쪽이 먼저다.
  vm.runInContext(NUMBERS, sandbox, { filename: "ir_numbers.js" });
  vm.runInContext(SEARCH, sandbox, { filename: "ir_contact_search.js" });
  return { asked: asked, win: win, sandbox: sandbox };
}

// 지금 고를 수 있게 서 있는 사람들(빈 보기는 뺀다).
function listed(select) {
  return select.querySelectorAll("option")
    .filter((o) => o.getAttribute("value") !== "")
    .map((o) => o.textContent);
}

function type(box, value) { box.value = value; box.fire("input"); }

function enter(box) {
  let prevented = 0;
  box.fire("keydown", { key: "Enter", preventDefault: function () { prevented += 1; } });
  return prevented;
}

function main() {
  // ── 1. 이름·투자사 **가운데 글자**로도 좁혀진다 ───────────────────────
  //
  // 브라우저 `<datalist>` 는 앞에서부터만 맞춘다 — 그 길로 갔으면 `벤처스`
  // 로는 아무도 못 찾는다. 여기서는 찾아져야 한다.
  {
    const dom = build();
    run(dom);
    type(dom.request.box, "벤처스");
    assert.deepStrictEqual(listed(dom.request.select).length, 2,
      "투자사 가운데 글자로 안 좁혀진다 ★ 이름을 알아도 목록을 훑어야 한다");
    type(dom.request.box, "다담당");
    assert.deepStrictEqual(listed(dom.request.select),
      ["다담당 대표 · 다라인베스트"], "이름으로 안 좁혀진다");
  }

  // ── 2. **검색은 거르기만 한다** ───────────────────────────────────────
  //
  // 좁혀졌다고 대신 골라 주면, 친 것과 저장되는 것이 달라진다. 요청이
  // 엉뚱한 담당자에게 적히는 자리라 여기서 못 박는다.
  {
    const dom = build();
    run(dom);
    type(dom.request.box, "벤처스");
    assert.strictEqual(dom.request.select.value, "",
      "검색만 했는데 누군가 골라졌다 ★ 친 것과 저장되는 것이 달라진다");
  }

  // ── 3. 하나로 좁혀졌을 때의 Enter 는 고르고, **폼을 안 보낸다** ───────
  {
    const dom = build();
    const t = run(dom);
    type(dom.request.box, "라담당");
    const prevented = enter(dom.request.box);
    assert.strictEqual(dom.request.select.value, "14", "Enter 로 안 골라진다");
    assert.ok(prevented >= 1,
      "검색칸의 Enter 가 폼을 그대로 보낸다 ★ 좁히려던 Enter 로 요청이 기록된다");
    // 골랐다고 **알렸는가** — 지난 회차 번호가 그 알림을 듣는다.
    assert.deepStrictEqual(t.asked, ["/api/ir/last-batch/14"],
      "골랐는데 지난 회차 번호를 안 부른다 ★ 번호로 적는 길이 막힌다");
  }

  // ── 4. 둘 이상 남아 있으면 Enter 가 **아무도 안 고른다** ──────────────
  {
    const dom = build();
    const t = run(dom);
    type(dom.request.box, "벤처스");
    enter(dom.request.box);
    assert.strictEqual(dom.request.select.value, "",
      "둘 중 하나를 대신 골라 줬다 ★ 무엇이 골라졌는지 사람이 모른다");
    assert.deepStrictEqual(t.asked, [], "안 골랐는데 번호를 불렀다");
  }

  // ── 5. 아무도 안 맞으면 **빈 보기만 남는다** ─────────────────────────
  //
  // 그래야 `required` 가 막는다. 그리고 왜 막히는지 말해 준다 — 말 안 하면
  // 막다른 길이 된다.
  {
    const dom = build();
    run(dom);
    type(dom.request.box, "없는사람");
    assert.deepStrictEqual(listed(dom.request.select), [],
      "안 맞는 사람이 남아 있다");
    assert.strictEqual(dom.request.select.value, "",
      "아무도 안 맞는데 누군가 골라져 있다 ★ required 가 아무 일도 안 한다");
    assert.strictEqual(dom.request.note.hidden, false, "왜 막히는지 말이 없다");
    assert.ok(/없습니다/.test(dom.request.note.textContent),
      "안내줄이 '없다' 고 말하지 않는다: " + dom.request.note.textContent);
  }

  // ── 6. 검색어를 지우면 **전부 되돌아온다** ───────────────────────────
  {
    const dom = build();
    run(dom);
    type(dom.request.box, "다담당");
    type(dom.request.box, "");
    assert.strictEqual(listed(dom.request.select).length, PEOPLE.length,
      "검색어를 지웠는데 사람이 안 돌아온다 ★ 지운 보기를 잃어버렸다");
    assert.strictEqual(dom.request.note.hidden, true,
      "검색어가 없는데 안내줄이 떠 있다");
  }

  // ── 7. **고른 사람은 검색어와 무관하게 남는다** ──────────────────────
  //
  // 딜 제안 관리가 정한 그 규칙이다 — 검색어를 바꾸다 고른 사람이 사라지면
  // 누구를 골라 뒀는지 알 수 없다.
  {
    const dom = build();
    run(dom);
    type(dom.request.box, "라담당");
    enter(dom.request.box);
    type(dom.request.box, "다담당");
    assert.strictEqual(dom.request.select.value, "14",
      "검색어를 바꿨다고 골라 둔 사람이 풀렸다");
    assert.ok(listed(dom.request.select).indexOf("라담당 수석 · 마바캐피탈") >= 0,
      "골라 둔 사람이 목록에서 사라졌다 ★ 누구를 골랐는지 화면에서 확인할 수 없다");
  }

  // ── 8. 폼 **둘 다** 붙는다 ───────────────────────────────────────────
  //
  // 한쪽에만 달리는 것이 바로 고치려던 문제다.
  {
    const dom = build();
    run(dom);
    type(dom.meeting.box, "다담당");
    assert.deepStrictEqual(listed(dom.meeting.select),
      ["다담당 대표 · 다라인베스트"],
      "미팅 등록 폼에는 검색이 안 붙었다 ★ 같은 모양이 두 벌로 갈렸다");
  }

  // ── 9. [미팅 잡기] 가 **걸러 둔 목록에 막히지 않는다** ───────────────
  //
  // 검색으로 좁혀 둔 채로 값을 넣으면 그 보기가 목록에 없어 값이 안 들어간다 —
  // 화면은 엉뚱한 사람을 가리킨 채로 미팅이 등록된다.
  {
    const dom = build();
    run(dom);
    type(dom.meeting.box, "가담당");           // 13번이 목록에서 빠진 상태
    dom.bookBtn.fire("click");
    assert.strictEqual(dom.meeting.select.value, "13",
      "걸러 둔 채로 넣은 담당자가 안 들어갔다 ★ 엉뚱한 사람에게 미팅이 잡힌다");
    assert.strictEqual(dom.meeting.box.value, "",
      "검색어가 그대로 남아 목록이 좁혀진 채다");
  }

  // ── 10. 검색칸이 없어도 **고르기는 그대로 산다** ─────────────────────
  //
  // 자산이 안 실리거나 화면이 옛 모양이어도 폼은 폼대로 가야 한다.
  {
    D.resetHandlers();
    const select = D.el("select", { id: "solo", name: "contact_id" },
                        PEOPLE.map(option));
    const root = D.el("div", {}, [select]);
    const document = D.makeDocument(root);
    const win = { addEventListener: function () {} };
    const sandbox = { document: document, console: console, window: win,
                      Event: function (t) { this.type = t; } };
    win.document = document;
    vm.createContext(sandbox);
    vm.runInContext(SEARCH, sandbox, { filename: "ir_contact_search.js" });
    assert.strictEqual(select.querySelectorAll("option").length, PEOPLE.length,
      "검색칸이 없는 화면에서 보기가 사라졌다");
  }

  // ── 11. 거르는 재료를 읽는 자리가 **한 곳**이다 ──────────────────────
  //
  // 두 벌이 되는 날 두 화면이 서로 다른 사람을 찾아 준다.
  {
    const readers = fs.readdirSync(SRC)
      .filter((f) => f.endsWith(".js"))
      .filter((f) => /data-contact-pick/.test(
        fs.readFileSync(path.join(SRC, f), "utf8")));
    assert.deepStrictEqual(readers, ["ir_contact_search.js"],
      "담당자 검색을 거르는 자리가 둘 이상이다 ★ 화면마다 다른 사람이 나온다");
  }

  // ── 12. **상태로도 좁혀진다** ────────────────────────────────────────
  //
  // 꼬리표를 적어 놓고 그 말로 못 찾으면, 꼬리표는 훑어 내려가야 보이는
  // 글자일 뿐이다. `방 나감` 을 쳐서 **그 사람들만** 볼 수 있어야 한다.
  {
    const dom = build();
    run(dom);
    type(dom.request.box, "방 나감");
    assert.deepStrictEqual(listed(dom.request.select),
      ["마담당 이사 · 사아파트너스 [방 나감]"],
      "상태로 안 좁혀진다 ★ 꼬리표를 보고 친 말로 아무도 안 나온다");
    // 미팅 등록 폼도 같은 한 벌이다.
    type(dom.meeting.box, "방 나감");
    assert.strictEqual(listed(dom.meeting.select).length, 1,
      "미팅 등록 폼에서는 상태로 안 좁혀진다");
  }

  // ── 13. 꼬리표가 **고르는 값을 흔들지 않는다** ───────────────────────
  //
  // 이 칸이 보내는 것은 번호다. 꼬리표는 보이는 글자일 뿐이라, 골라 보낸
  // 값은 여전히 `15` 여야 한다.
  {
    const dom = build();
    run(dom);
    type(dom.request.box, "방 나감");
    enter(dom.request.box);
    assert.strictEqual(dom.request.select.value, "15",
      "꼬리표가 붙은 사람을 고르니 번호가 안 실린다 ★ 엉뚱한 사람에게 적힌다");
  }

  console.log("ir_contact_search_test OK");
}

main();
