// 딜 소싱 카톡방 [방 후보 찾기] · [이 방으로 확정] — **새로고침 없이**(`sourcing_rooms.js`).
// (node tests/js/sourcing_rooms_async_test.js)
//
// 사용자: "딜 소싱에서 방 후보 누를때 비동기로 해줘… 계속 새로고침이 되서… 연속해서
// 클릭을 못함".
//   ① [이 방으로 확정] — 폼 제출을 가로채 같은 주소로 보내고(JSON 답), 그 줄만 고친다:
//      방 이름 칸에 제목 · `방 없음` · 후보 걷기 · `data-no-room` 떼기. 다른 줄은 그대로
//   ② 보내는 중에는 그 줄의 후보 단추가 잠기고 두 번 눌러도 한 번만 간다. 서버가 잠근
//      단추(같은 제목 여럿)는 끝나도 잠긴 채
//   ③ 실패(400 · 세션이 끊겨 로그인 화면 · 연결 오류)는 그 자리에 문구, 줄은 그대로
//   ④ 줄의 [방 후보 찾기] — 실린 줄마다 `찾기 요청됨(회차 #N)`
//   ⑤ 툴바 [방 후보 찾기] — 화면 스크립트(확인창 · 고른 줄 번호)를 지난 뒤에만 보낸다.
//      확정한 줄은 툴바 셈에서 빠진다
//   ⑥ 다른 폼(딜 받음 등)은 건드리지 않는다
//
// 이름 · 방 제목은 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const el = dom_.el;

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "app", "static", "js", "sourcing_rooms.js"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "app", "templates", "sourcing.html"), "utf8");
const INLINE = /<script>([\s\S]*?)<\/script>/.exec(HTML.split("{% block scripts %}")[1])[1]
  .replace(/\{%[\s\S]*?%\}/g, "").replace(/\{\{[\s\S]*?\}\}/g, "0");

function button(text, disabled) {
  const b = el("button", { type: "submit", class: "linkbtn" });
  b.textContent = text;
  b.disabled = !!disabled;
  return b;
}

function hidden(name, value) { return el("input", { type: "hidden", name: name, value: value }); }

// 서버가 그리는 `방 없음` 줄(`sourcing.html` 의 카톡방 칸) — 후보는 `rooms`.
function row(id, name, rooms) {
  const kids = [el("div", { class: "cell", "data-field": "kakao_room_name" })];
  kids.push(el("div", { class: "cell-sub sourcing-room", "data-testid": "sourcing-no-room" }, [
    el("form", { class: "inline-form js-room-search", method: "post",
                 action: "/sourcing/rooms/search" },
       [hidden("tab", "all"), hidden("ids", String(id)), button("방 후보 찾기")])]));
  if (rooms && rooms.length) {
    kids.push(el("div", { class: "cell-sub sourcing-room", "data-testid": "sourcing-room-picks" },
      rooms.map(function (r) {
        return el("form", { class: "inline-form js-room-confirm", method: "post",
                            action: "/sourcing/" + id + "/room-confirm" },
                  [hidden("tab", "all"), hidden("room", r.room),
                   button("💬 " + r.room + " — 이 방으로 확정", r.same)]);
      })));
  }
  const nameCell = el("b", { class: "cell", "data-field": "name" });
  nameCell.textContent = name;
  return el("tr", { "data-id": String(id), "data-no-room": "", "data-part-kind": "joined" }, [
    el("td", { class: "pick-col" }, [el("input", { type: "checkbox", class: "js-sourcing-pick",
                                                   value: String(id) })]),
    el("td", { class: "rowno" }), el("td", {}, [nameCell]),
    el("td", { title: "카톡방 제목을 그대로 적어주세요", class: "room-td" }, kids)]);
}

function setup(rows, opts) {
  opts = opts || {};
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const all = el("input", { type: "checkbox", id: "sourcing-check-all" });
  const table = el("table", { id: "sourcing-table" }, [
    el("thead", {}, [el("tr", {}, [el("th", {}, [all])])]), el("tbody", {}, rows)]);
  const toolBtn = el("button", { type: "submit", id: "sourcing-room-btn" });
  toolBtn.disabled = true;
  const tool = el("form", { id: "sourcing-room-search", class: "inline-form js-room-search",
                            method: "post", action: "/sourcing/rooms/search" },
                  [hidden("tab", "all"), hidden("ids", ""), toolBtn]);
  // 딜 받음 — 이 스크립트가 손대지 않는 폼.
  const other = el("form", { class: "inline-form", method: "post", action: "/sourcing/11/received" },
                   [hidden("on", "1"), button("딜 받음")]);
  root.appendChild(tool);
  root.appendChild(el("span", { id: "sourcing-room-hint" }));
  root.appendChild(table);
  root.appendChild(other);
  root.appendChild(el("input", { id: "sourcing-search", type: "search" }));

  const calls = [];
  const asked = [];
  const t = { answer: true, reloads: 0 };
  function FakeFormData(form) {
    this.pairs = form.querySelectorAll("input")
      .filter(function (i) { return i.getAttribute("name"); })
      .map(function (i) { return [i.getAttribute("name"), i.value]; });
  }
  FakeFormData.prototype.get = function (k) {
    const hit = this.pairs.find(function (p) { return p[0] === k; });
    return hit ? hit[1] : null;
  };
  function FakeEvent(type, init) { this.type = type; this.bubbles = !!(init && init.bubbles); }
  const win = {
    DealflowFilters: { init: function (o) { return { apply: function () { o.onChange && o.onChange(); } }; } },
    location: { reload: function () { t.reloads += 1; } }
  };
  const ctx = {
    document: dom_.makeDocument(root), window: win, console: console, location: win.location,
    setTimeout: function () { return 0; }, alert: function () {}, prompt: function () { return ""; },
    confirm: function (m) { asked.push(m); return t.answer; },
    FormData: FakeFormData, Event: FakeEvent,
    fetch: function (url, init) {
      let resolve, reject;
      const p = new Promise(function (res, rej) { resolve = res; reject = rej; });
      calls.push({ url: url, init: init, resolve: resolve, reject: reject });
      return p;
    }
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx, { filename: "sourcing_rooms.js" });
  // 화면에 실린 차례대로 — 툴바 확인창 · 고른 줄 번호를 싣는 손은 그 페이지 스크립트다.
  if (opts.inline) vm.runInContext(INLINE, ctx, { filename: "sourcing.html<script>" });
  return Object.assign(t, {
    root: root, table: table, tool: tool, toolBtn: toolBtn, other: other, calls: calls, asked: asked,
    // 폼이 보내지려 한다. `defaultPrevented` — 누가 막았나(막았으면 새로고침도 없다).
    // `_dom.js` 는 넘긴 값을 새 이벤트에 덧붙이므로 막은 것을 양쪽에 적는다.
    submit: function (form) {
      const seen = { defaultPrevented: false };
      form.fire("submit", { defaultPrevented: false, preventDefault: function () {
        this.defaultPrevented = true;
        seen.defaultPrevented = true;
      } });
      return seen;
    }
  });
}

// 서버 답. `body` 가 없으면 JSON 이 아닌 답(로그인 화면으로 넘어간 HTML).
function reply(call, status, body) {
  call.resolve({ ok: status >= 200 && status < 300, status: status,
                 json: function () { return body === undefined ? Promise.reject(new Error("html")) : Promise.resolve(body); } });
}
function flush() { return new Promise(function (r) { setImmediate(r); }); }

function td(tr) { return tr.querySelector(".room-td"); }
function noteOf(node) { const n = node.querySelector(".js-room-note"); return n ? n.textContent : ""; }

async function main() {
  // --- ① · ② 확정 — 그 줄만 고치고, 보내는 중에는 잠긴다 ------------------------
  {
    const a = row(11, "홍길동", [{ room: "홍길동 딜소싱" }, { room: "같은 방", same: true },
                                 { room: "홍길동 다른 방" }]);
    const b = row(12, "김철수", [{ room: "김철수 딜소싱" }]);
    const t = setup([a, b]);
    const forms = a.querySelectorAll(".js-room-confirm");
    const ev = t.submit(forms[0]);
    assert.strictEqual(ev.defaultPrevented, true, "폼이 그대로 보내져 화면이 새로 그려진다");
    assert.strictEqual(t.calls.length, 1);
    const call = t.calls[0];
    assert.strictEqual(call.url, "/sourcing/11/room-confirm");
    assert.strictEqual(call.init.method, "POST");
    assert.strictEqual(call.init.headers.Accept, "application/json", "JSON 으로 답해 달라고 안 했다");
    assert.strictEqual(call.init.body.get("room"), "홍길동 딜소싱");
    assert.strictEqual(call.init.body.get("tab"), "all");

    const btns = forms.map(function (f) { return f.querySelector("button"); });
    assert.deepStrictEqual(btns.map(function (x) { return x.disabled; }), [true, true, true],
                           "보내는 중인데 그 줄의 후보 단추가 눌린다");
    assert.strictEqual(noteOf(forms[0]), "확정 중…");
    t.submit(forms[0]);
    t.submit(forms[2]);
    assert.strictEqual(t.calls.length, 1, "보내는 중에 또 누르면 두 번 간다");
    assert.strictEqual(b.querySelector(".js-room-confirm button").disabled, false,
                       "다른 줄까지 잠갔다 — 연달아 누를 수 없다");

    reply(call, 200, { ok: true, msg: "홍길동 — 방을 확정했습니다: 홍길동 딜소싱",
                       room: "홍길동 딜소싱" });
    await flush();
    assert.strictEqual(td(a).querySelector('[data-field="kakao_room_name"]').textContent, "홍길동 딜소싱");
    assert.strictEqual(td(a).getAttribute("title"), "홍길동 딜소싱");
    assert.strictEqual(td(a).querySelector('[data-testid="sourcing-no-room"]'), null, "`방 없음` 이 남았다");
    assert.strictEqual(td(a).querySelector('[data-testid="sourcing-room-picks"]'), null, "후보가 남았다");
    assert.strictEqual(a.hasAttribute("data-no-room"), false, "툴바 찾기에 아직 실린다");
    assert.ok(/확정했습니다/.test(noteOf(td(a))), noteOf(td(a)));
    // 다른 줄은 그대로 — 곧바로 이어서 누른다.
    assert.ok(b.hasAttribute("data-no-room"));
    assert.ok(td(b).querySelector('[data-testid="sourcing-room-picks"]'));
    t.submit(b.querySelector(".js-room-confirm"));
    assert.strictEqual(t.calls.length, 2, "다음 줄을 이어서 못 누른다");
    assert.strictEqual(t.calls[1].url, "/sourcing/12/room-confirm");
    assert.strictEqual(t.reloads, 0, "화면을 새로 그렸다");
  }

  // --- ③ 실패 — 그 자리에 문구 · 줄은 그대로 · 서버가 잠근 단추는 잠긴 채 -----------
  {
    const a = row(11, "홍길동", [{ room: "아무 방" }, { room: "같은 방", same: true }]);
    const t = setup([a]);
    const forms = a.querySelectorAll(".js-room-confirm");
    t.submit(forms[0]);
    reply(t.calls[0], 400, { detail: "카톡에서 찾은 후보가 아닙니다 — 화면을 새로 열어 보세요" });
    await flush();
    const n = forms[0].querySelector(".js-room-note");
    assert.strictEqual(n.textContent, "카톡에서 찾은 후보가 아닙니다 — 화면을 새로 열어 보세요");
    assert.ok(n.classList.contains("warn-text"), "오류가 오류로 안 보인다");
    assert.strictEqual(forms[0].querySelector("button").disabled, false, "실패 뒤 다시 못 누른다");
    assert.strictEqual(forms[1].querySelector("button").disabled, true, "서버가 잠근 단추를 풀었다");
    assert.ok(a.hasAttribute("data-no-room"));
    assert.ok(td(a).querySelector('[data-testid="sourcing-room-picks"]'));

    // 세션이 끊겨 로그인 화면(200 · HTML)으로 넘어갔다 — 성공으로 읽으면 안 된다.
    t.submit(forms[0]);
    reply(t.calls[1], 200);
    await flush();
    assert.ok(/처리하지 못했습니다/.test(noteOf(forms[0])), noteOf(forms[0]));
    assert.ok(a.hasAttribute("data-no-room"), "로그인 화면을 확정 성공으로 읽었다");

    // 연결 오류
    t.submit(forms[0]);
    t.calls[2].reject(new Error("offline"));
    await flush();
    assert.strictEqual(noteOf(forms[0]), "요청 오류 — 다시 눌러 보세요");
    assert.strictEqual(forms[0].querySelector("button").disabled, false);
  }

  // --- ④ 줄의 [방 후보 찾기] — 처리 중 · 찾기 요청됨 -------------------------------
  {
    const a = row(11, "홍길동");
    const t = setup([a, row(12, "김철수")]);
    const form = a.querySelector(".js-room-search");
    t.submit(form);
    assert.strictEqual(t.calls[0].url, "/sourcing/rooms/search");
    assert.strictEqual(t.calls[0].init.body.get("ids"), "11");
    assert.strictEqual(form.querySelector("button").disabled, true);
    assert.strictEqual(noteOf(form), "찾기 요청 중…");
    reply(t.calls[0], 200, { ok: true, msg: "…", job_id: 7, ids: [11] });
    await flush();
    assert.strictEqual(noteOf(form), "찾기 요청됨(회차 #7) — 끝나면 새로고침해 후보를 고르세요");
    assert.strictEqual(form.querySelector("button").disabled, false);
    assert.ok(a.hasAttribute("data-no-room"), "찾기만 했는데 방이 생긴 줄로 그렸다");
  }

  // --- ⑤ 툴바 [방 후보 찾기] — 화면 스크립트를 지난 뒤에만 · 확정하면 셈에서 빠진다 ----
  {
    const a = row(11, "홍길동", [{ room: "홍길동 딜소싱" }]);
    const b = row(12, "김철수");
    const c = row(13, "박영희");
    const t = setup([a, b, c], { inline: true });
    [a, c].forEach(function (tr) {
      const cb = tr.querySelector(".js-sourcing-pick");
      cb.checked = true;
      cb.fire("change");
    });
    assert.strictEqual(t.toolBtn.textContent, "방 후보 찾기 (선택 2명)");

    t.answer = false;                                    // 확인창 취소
    t.submit(t.tool);
    assert.strictEqual(t.calls.length, 0, "확인창에서 취소했는데 보냈다");

    t.answer = true;
    t.submit(t.tool);
    assert.strictEqual(t.calls.length, 1);
    assert.strictEqual(t.calls[0].init.body.get("ids"), "11,13", "고른 줄 번호가 안 실렸다");
    reply(t.calls[0], 200, { ok: true, job_id: 9, ids: [11, 13],
                             msg: "가상 님 PC 의 카톡에서 2명의 방을 찾습니다(회차 #9)" });
    await flush();
    assert.strictEqual(noteOf(t.tool), "가상 님 PC 의 카톡에서 2명의 방을 찾습니다(회차 #9)");
    assert.ok(/회차 #9/.test(noteOf(a.querySelector(".js-room-search"))));
    assert.ok(/회차 #9/.test(noteOf(c.querySelector(".js-room-search"))));
    assert.strictEqual(noteOf(b.querySelector(".js-room-search")), "", "안 실린 줄에 적었다");
    assert.strictEqual(a.querySelector(".js-sourcing-pick").checked, true, "체크가 풀렸다");

    // 고른 줄 하나를 확정하면 툴바 셈에서 빠진다(그 줄은 이제 방이 있다).
    t.submit(a.querySelector(".js-room-confirm"));
    reply(t.calls[1], 200, { ok: true, msg: "확정", room: "홍길동 딜소싱" });
    await flush();
    assert.strictEqual(t.toolBtn.textContent, "방 후보 찾기 (선택 1명)");
  }

  // 아무도 안 골랐으면 화면 스크립트가 막는다 — 여기서도 안 보낸다.
  {
    const t = setup([row(11, "홍길동")], { inline: true });
    t.submit(t.tool);
    assert.strictEqual(t.calls.length, 0, "안 골랐는데 보냈다");
  }

  // --- ⑥ 다른 폼은 그대로 — 예전처럼 보내진다 ---------------------------------------
  {
    const t = setup([row(11, "홍길동")]);
    const ev = t.submit(t.other);
    assert.strictEqual(ev.defaultPrevented, false, "딜 받음 폼까지 가로챘다");
    assert.strictEqual(t.calls.length, 0);
  }

  console.log("sourcing_rooms_async_test: ok");
}

main().catch(function (e) { console.error(e); process.exit(1); });
