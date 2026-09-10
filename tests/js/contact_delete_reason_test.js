// 수정창의 [삭제] — **왜 안 지워지는지 화면이 말하는가.** (node tests/js/contact_delete_reason_test.js)
//
// 여기는 `.then(function () { window.location.reload(); })` 한 줄이었다. 응답을
// 보지 않으니 409 든 500 든 그냥 화면을 다시 그렸고, 사람은 **지워진 줄 알았다가
// 그 줄이 그대로 있는 것을 나중에 발견했다.** 서버가 사유를 잘 만들어 보내도
// 화면이 안 읽으면 아무것도 나아지지 않는다 — 그래서 여기서 잰다.
//
//   1. 막히면 **서버가 준 사유를 그대로** 띄운다(무엇이 몇 건인지 · 다음 걸음).
//   2. 막히면 **화면을 다시 그리지 않는다.** 다시 그리면 지워진 것처럼 보인다.
//   3. 되는 줄은 그대로 지워지고 화면을 다시 그린다(되던 것이 안 깨진다).
//   4. 확인창에서 [취소]를 누르면 한 건도 안 나간다.
//
// 서버 쪽(무엇이 막나 · 사유를 어떻게 짓나 · 로그)은
// `tests/test_contact_delete_reason.py` 가 본다.
//
// 이름·회사는 지어낸 것이다(공개 저장소).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const src = fs.readFileSync(path.join(JS, "contacts.js"), "utf8");
const modalSrc = fs.readFileSync(path.join(JS, "panel_modal.js"), "utf8");

const CONTACT = { id: 7, name: "가상길동", title: "심사역", firm: "가상벤처스" };
// 서버가 실제로 내려보내는 모양 그대로 — 무엇이 몇 건인지, 다음에 뭘 하면 되는지.
const REASON = "발송 기록 12건 · 미팅 1건이 걸려 있어 지울 수 없습니다. " +
  "이력이 사라지면 지난 주간·월간 보고의 수가 바뀝니다. " +
  "대신 [이 줄 감추기] 를 누르면 표에서 빠지고 딜 소개 발송 대상에서도 빠집니다.";

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
  tr.setAttribute("data-id", String(CONTACT.id));
  const table = el("contacts-table");
  table.querySelectorAll = function (sel) {
    return sel.indexOf("tr.data-row") >= 0 ? [tr] : [];
  };
  table.querySelector = function () { return makeEl("tbody"); };

  const document = {
    getElementById(id) { return nodes[id] || (nodes[id] = makeEl(id)); },
    querySelector(sel) {
      return sel && sel.charAt(0) === "#" ? this.getElementById(sel.slice(1)) : null;
    },
    addEventListener() {},
    querySelectorAll() { return []; },
    createElement(tag) { const e = makeEl(tag); e.tagName = tag.toUpperCase(); return e; }
  };
  document.getElementById("detail-panel").hidden = true;
  document.getElementById("detail-backdrop").hidden = true;

  return { document: document, nodes: nodes, el: el };
}

// `reply` 는 삭제 요청에 서버가 어떻게 답할지다.
function run(reply) {
  const dom = makeDom();
  const sent = [];
  const asked = [];
  const told = [];
  let answer = true;
  let reloaded = 0;
  const win = {};
  const ctx = {
    document: dom.document,
    console: console,
    alert(t) { told.push(String(t)); },
    confirm(t) { asked.push(String(t)); return answer; },
    MutationObserver: function (fn) { this.observe = function () {}; this.cb = fn; },
    fetch(url, opts) {
      const method = (opts && opts.method) || "GET";
      sent.push({ url: url, method: method, opts: opts || {} });
      if (method === "DELETE") {
        return Promise.resolve({
          ok: reply.ok,
          status: reply.status,
          json() {
            return reply.body === undefined
              ? Promise.reject(new Error("본문이 JSON 이 아니다"))
              : Promise.resolve(reply.body);
          }
        });
      }
      return Promise.resolve({
        ok: true,
        json() { return Promise.resolve({ contact: CONTACT, timeline: [] }); }
      });
    }
  };
  ctx.window = win;
  Object.assign(win, ctx);
  win.location = { reload() { reloaded += 1; }, pathname: "/contacts", href: "" };
  win.DEALFLOW_OPEN_CONTACT = CONTACT.id;   // 줄 하나를 열어 둔 상태로 시작
  vm.createContext(ctx);
  vm.runInContext(modalSrc, ctx, { filename: "panel_modal.js" });
  vm.runInContext(src, ctx, { filename: "contacts.js" });
  return {
    dom: dom, sent: sent, asked: asked, told: told,
    reloads() { return reloaded; },
    msg() { return dom.nodes["detail-msg"].textContent; },
    setAnswer(v) { answer = v; },
    deletes() { return sent.filter(function (s) { return s.method === "DELETE"; }); },
    click() { dom.nodes["delete-btn"].fire("click", {}); }
  };
}

const flush = () => new Promise(function (r) { setTimeout(r, 0); });

async function main() {
  // --- 막히면 서버가 준 사유를 **그대로** 띄운다 -----------------------------
  {
    const t = run({ ok: false, status: 409, body: { detail: REASON } });
    await flush();
    t.click();
    await flush();
    await flush();

    assert.strictEqual(t.deletes().length, 1, "삭제 요청이 한 번이 아니다");
    assert.strictEqual(t.deletes()[0].url, "/api/contacts/7");

    assert.ok(t.told.indexOf(REASON) >= 0,
      "서버가 준 사유를 안 띄웠다 — 왜 안 되는지 알 길이 없다:\n  뜬 것: " +
      JSON.stringify(t.told));
    assert.strictEqual(t.msg(), REASON,
      "수정창에 사유가 안 남았다 — 확인창은 누르면 사라져서 다시 못 읽는다:\n  " +
      t.msg());

    // 무엇이 몇 건인지 · 다음 걸음이 사람 눈앞까지 왔는가.
    const shown = t.told.join("\n") + "\n" + t.msg();
    assert.ok(shown.indexOf("발송 기록 12건") >= 0 && shown.indexOf("미팅 1건") >= 0,
      "무엇이 몇 건인지가 화면까지 안 왔다:\n  " + shown);
    assert.ok(shown.indexOf("감추기") >= 0,
      "다음에 뭘 하면 되는지가 화면까지 안 왔다 — 막다른 길에 세운다:\n  " + shown);
  }

  // --- 막히면 화면을 다시 그리지 않는다 --------------------------------------
  {
    const t = run({ ok: false, status: 409, body: { detail: REASON } });
    await flush();
    t.click();
    await flush();
    await flush();

    assert.strictEqual(t.reloads(), 0,
      "못 지웠는데 화면을 다시 그렸다 — 그 줄이 그대로 서 있는 것을 사람이 " +
      "나중에야 발견한다(이것이 원래 고장이었다)");
  }

  // --- 사유가 안 왔어도 성공으로 넘어가지 않는다 -----------------------------
  //
  // 502·빈 본문이면 `r.json()` 이 깨진다. 거기서 성공으로 새 나가면 예전과
  // 똑같이 아무 말 없이 새로 그려진다.
  {
    const t = run({ ok: false, status: 500 });   // 본문 없음
    await flush();
    t.click();
    await flush();
    await flush();

    assert.strictEqual(t.reloads(), 0, "사유가 안 왔다고 성공으로 넘어갔다");
    assert.ok(t.told.length + (t.msg() ? 1 : 0) > 0,
      "사유가 안 왔을 때 아무 말도 안 했다 — 눌러도 아무 일이 없는 단추가 된다");
  }

  // --- 되는 줄은 그대로 지워지고 화면을 다시 그린다 --------------------------
  {
    const t = run({ ok: true, status: 200, body: { ok: true } });
    await flush();
    t.click();
    await flush();
    await flush();

    assert.strictEqual(t.deletes().length, 1);
    assert.strictEqual(t.reloads(), 1,
      "지우고 나서 화면을 다시 안 그렸다 — 지운 줄이 표에 그대로 남는다");
    assert.deepStrictEqual(t.told, [], "잘 지웠는데 뭔가 알렸다");
  }

  // --- 확인창에서 취소하면 한 건도 안 나간다 ---------------------------------
  {
    const t = run({ ok: true, status: 200, body: { ok: true } });
    await flush();
    t.setAnswer(false);
    t.click();
    await flush();

    assert.strictEqual(t.asked.length, 1, "확인창 없이 지워 버렸다");
    assert.deepStrictEqual(t.deletes(), [],
      "취소를 눌렀는데 지웠다 — 확인창이 장식이 된다");
    assert.strictEqual(t.reloads(), 0);
  }

  console.log("contact_delete_reason_test: 통과");
}

main().catch(function (e) {
  console.error(e && e.stack || e);
  process.exit(1);
});
