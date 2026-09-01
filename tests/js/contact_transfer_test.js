// 줄 하나를 다른 담당자에게 넘기기 — 확인창과 보내는 것. (node tests/js/contact_transfer_test.js)
//
// 이관은 **되돌리기 번거로운 조작**이라 사람이 마지막에 보는 것이 확인창 한
// 줄이다. 여기서 못 박는 것은 셋이다.
//
//   1. 확인창이 **누구를 누구의 어느 명단으로** 넘기는지 적는다
//      (딜 소싱 삭제 확인창과 같은 결 — `sourcing.html`)
//   2. 확인창이 **월별 기록이 안 보이게 된다**고 말한다. 달마다 늘어나는 칸은
//      명단마다 따로라 넘기면 옛 기록이 새 명단의 수정창에 안 뜬다. 지워지는
//      것은 아니지만 사람 눈에는 사라진 것과 같아서, 말해 주지 않으면 기록이
//      날아간 줄 알고 다시 적는다.
//   3. **취소를 누르면 한 건도 안 나간다.** 확인창을 띄워 놓고 이미 보내 버리면
//      확인창은 장식일 뿐이다.
//
// 화면이 그려지는지만 보는 검사로는 못 잡는다 — 그래서 `contacts.js` 를 실제로
// 실행한다. 이 파일이 쓰는 만큼만 가짜 DOM 을 세워 두고 vm 으로 돌린다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "..", "app", "static", "js", "contacts.js");
const src = fs.readFileSync(SRC, "utf8");

// 가상의 담당자·명단이다 — 저장소가 공개라 실제 이름·번호를 두지 않는다.
const CONTACT = { id: 7, name: "가상길동", title: "심사역", firm: "가상벤처스" };
const TARGET = { label: "나 명단", owner: "가상순신" };

// --- 가짜 DOM (contacts.js 가 만지는 것만) ----------------------------------
function makeEl(id) {
  const attrs = {};
  const el = {
    id: id, value: "", checked: false, textContent: "", innerHTML: "",
    hidden: false, disabled: false, className: "", tagName: "DIV", handlers: {},
    classList: {
      _on: new Set(),
      toggle(c, on) { if (on) this._on.add(c); else this._on.delete(c); },
      contains(c) { return this._on.has(c); },
      add(c) { this._on.add(c); }, remove(c) { this._on.delete(c); }
    },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    setAttribute(k, v) { attrs[k] = v; },
    hasAttribute(k) { return k in attrs; },
    addEventListener(type, fn) { (el.handlers[type] = el.handlers[type] || []).push(fn); },
    fire(type, ev) { (el.handlers[type] || []).forEach(function (fn) { fn(ev); }); },
    querySelector() { return makeEl("*"); },
    querySelectorAll() { return []; },
    closest() { return null; }
  };
  return el;
}

function makeDom() {
  const nodes = {};
  function el(id) { return nodes[id] || (nodes[id] = makeEl(id)); }

  const tr = makeEl("tr");
  tr.setAttribute("data-id", "7");
  const table = el("contacts-table");
  table.querySelectorAll = function (sel) {
    return sel.indexOf("tr.data-row") >= 0 ? [tr] : [];
  };
  table.querySelector = function () { return makeEl("tbody"); };

  // 넘길 곳 고르는 칸. 화면이 그리는 그대로 — 이름표에 담당자를 달아 둔다.
  const pick = el("transfer-target");
  const blank = makeEl("opt-blank");
  const opt = makeEl("opt-target");
  opt.setAttribute("data-owner", TARGET.owner);
  opt.value = TARGET.label;
  pick.options = [blank, opt];
  pick.selectedIndex = 0;
  pick.value = "";

  const document = {
    getElementById(id) { return nodes[id] || (nodes[id] = makeEl(id)); },
    querySelectorAll(sel) { return []; },
    createElement(tag) { const e = makeEl(tag); e.tagName = tag.toUpperCase(); return e; }
  };
  document.getElementById("detail-panel").hidden = true;

  return { document: document, nodes: nodes, el: el, pick: pick };
}

function run() {
  const dom = makeDom();
  const sent = [];        // fetch 로 나간 것 전부
  const asked = [];       // 확인창에 뜬 글
  const told = [];        // alert 로 알린 것
  let answer = true;      // 확인창에서 사람이 누를 답
  let reloaded = 0;
  const win = {};
  const ctx = {
    document: dom.document,
    console: console,
    alert(t) { told.push(String(t)); },
    confirm(t) { asked.push(String(t)); return answer; },
    MutationObserver: function (fn) { this.observe = function () {}; this.cb = fn; },
    fetch(url, opts) {
      sent.push({ url: url, opts: opts || {} });
      return Promise.resolve({
        ok: true,
        json() {
          return Promise.resolve(url.indexOf("/transfer") >= 0
            ? { ok: true, moved: "가 명단 → " + TARGET.label, label: TARGET.label,
                owner: TARGET.owner }
            : { contact: CONTACT, timeline: [] });
        }
      });
    }
  };
  ctx.window = win;
  Object.assign(win, ctx);
  win.location = { reload() { reloaded += 1; }, pathname: "/contacts", href: "" };
  win.DEALFLOW_OPEN_CONTACT = CONTACT.id;   // 줄 하나를 열어 둔 상태로 시작
  vm.runInNewContext(src, ctx, { filename: "contacts.js" });
  return {
    dom: dom, sent: sent, asked: asked, told: told,
    reloads() { return reloaded; },
    setAnswer(v) { answer = v; },
    // 넘길 곳을 고른다 — 화면에서 select 를 바꾸는 것과 같다.
    choose(label) {
      dom.pick.value = label;
      dom.pick.selectedIndex = label ? 1 : 0;
    },
    click() { dom.nodes["transfer-btn"].fire("click", {}); }
  };
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });

async function main() {
  // --- 확인창이 누구를 누구에게 넘기는지, 월별 기록이 어찌 되는지 말한다 -----
  {
    const t = run();
    await flush();                       // 담당자 한 줄을 불러온 뒤
    t.choose(TARGET.label);
    t.click();

    assert.strictEqual(t.asked.length, 1, "확인창 없이 넘겨 버렸다");
    const text = t.asked[0];
    assert.ok(text.indexOf(CONTACT.name) >= 0,
      "확인창에 **누구를** 넘기는지 안 적혔다 — 엉뚱한 줄을 넘겨도 모른다:\n  " + text);
    assert.ok(text.indexOf(TARGET.owner) >= 0,
      "확인창에 **누구에게** 넘기는지 안 적혔다:\n  " + text);
    assert.ok(text.indexOf(TARGET.label) >= 0,
      "확인창에 **어느 명단으로** 넘기는지 안 적혔다:\n  " + text);
    assert.ok(text.indexOf("월별 기록") >= 0,
      "월별 기록이 새 명단 수정창에 안 보이게 된다는 것을 안 말했다 —\n" +
      "  기록이 날아간 줄 알고 다시 적게 된다:\n  " + text);
    assert.ok(text.indexOf("지워지지는 않고") >= 0,
      "안 보일 뿐 지워지지는 않는다는 것을 안 말했다:\n  " + text);
  }

  // --- 확인하면 그 줄만, 고른 명단으로 보낸다 --------------------------------
  {
    const t = run();
    await flush();
    t.choose(TARGET.label);
    t.click();
    await flush();

    const posts = t.sent.filter(function (s) { return s.url.indexOf("/transfer") >= 0; });
    assert.strictEqual(posts.length, 1, "이관 요청이 한 번이 아니다");
    assert.strictEqual(posts[0].url, "/api/contacts/7/transfer",
      "다른 줄을 넘겼다: " + posts[0].url);
    assert.strictEqual(posts[0].opts.method, "POST");
    assert.deepStrictEqual(JSON.parse(posts[0].opts.body), { label: TARGET.label },
      "고른 명단이 아닌 것을 보냈다");

    // 어디서 어디로 갔는지 멈춰 세우고 알린다 — 되돌리려면 옛 명단을 알아야 한다.
    assert.ok(t.told.some(function (m) { return m.indexOf("가 명단 → 나 명단") >= 0; }),
      "어디서 어디로 갔는지 안 알려 줬다 — 잘못 넘겼을 때 되돌릴 근거가 없다");
    // 탭 인원·전체 수·필터의 `N / M명` 은 서버가 그린다 → 다시 그려야 맞는다.
    assert.strictEqual(t.reloads(), 1, "넘기고 나서 화면을 다시 안 그렸다 — 숫자가 옛것으로 남는다");
  }

  // --- 취소하면 한 건도 안 나간다 --------------------------------------------
  {
    const t = run();
    await flush();
    t.setAnswer(false);
    t.choose(TARGET.label);
    t.click();
    await flush();

    assert.deepStrictEqual(
      t.sent.filter(function (s) { return s.url.indexOf("/transfer") >= 0; }), [],
      "취소를 눌렀는데 넘어갔다 — 확인창이 장식이 된다");
    assert.strictEqual(t.reloads(), 0, "취소했는데 화면을 다시 그렸다");
  }

  // --- 명단을 안 고르면 묻지도 보내지도 않는다 -------------------------------
  //
  // 빈 값으로 보내면 서버가 400 으로 받아치지만, 그때는 이미 확인창에
  // `'' 명단으로 넘길까요?` 라는 말이 뜬 뒤다.
  {
    const t = run();
    await flush();
    t.click();                            // 고르지 않은 채로 누른다
    await flush();

    assert.deepStrictEqual(t.asked, [], "고른 명단도 없이 확인창을 띄웠다");
    assert.deepStrictEqual(
      t.sent.filter(function (s) { return s.url.indexOf("/transfer") >= 0; }), [],
      "고른 명단도 없이 보냈다");
    assert.ok(t.dom.nodes["detail-msg"].textContent.indexOf("명단") >= 0,
      "왜 안 되는지 화면에 안 적혔다 — 눌러도 아무 일이 없는 단추가 된다");
  }

  console.log("contact_transfer_test: 통과");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
