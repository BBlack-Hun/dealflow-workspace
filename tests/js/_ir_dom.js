// IR 진행 관리(`app/templates/ir.html`)의 [자료 보내기] 자리를 세운다.
// (node tests/js/_ir_dom.js — 혼자 돌면 아무 일도 안 한다)
//
// 규칙을 옮겨 적어 검사하면 두 벌이 되어 어긋나도 모른다. 그래서 검사는
// **ir_send.js 를 그대로 실행**하고, 이 파일이 그 밑에 화면을 세워 준다
// (`_deals_dom.js` 와 같은 뜻).
//
// 여기 세운 아이디가 **실제로 그려진 화면과 같은지**는 파이썬 쪽이 따로 본다
// (`tests/test_ir_send_inline.py`) — 화면에서 아이디 하나가 바뀌면 이 가짜
// 화면 위에서는 검사가 그대로 통과하기 때문이다.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const dom_ = require("./_dom.js");
const el = dom_.el;

//: 화면의 [자료 보내기] 폼이 싣는 값. 가상의 사람·기업이다.
const CONTACT_ID = 7;
const COMPANY_IDS = [11, 12];
const NAME = "가담당";

function deliverForm(name, contactId, companyIds) {
  return el("form", {
    class: "deliver-form", method: "post", action: "/ir/deliver-guide",
    "data-name": name
  }, [
    el("input", { type: "hidden", name: "contact_id", value: String(contactId) }),
    el("input", { type: "hidden", name: "company_ids", value: companyIds.join(",") }),
    el("button", { class: "primary-btn inline", type: "submit" })
  ]);
}

// 창은 서버가 그려 둔 자리다(`ir.html`) — 스크립트는 채우기만 한다.
// `hidden` 으로 시작하고, 자동 첨부 여부에 따라 머리말이 갈린다(그 갈림은
// 서버가 정한다 — 여기서는 그 자리가 있다는 것만 세운다).
function sendModal() {
  return el("div", { class: "send-modal", id: "ir-send-modal" }, [
    el("h2", { class: "send-modal-title", id: "ir-send-title" }),
    // 설명 글귀는 한 줄만 남기고 뺐다(`ir.html`) — 여기서도 세우지 않는다.
    // 가짜 화면이 없는 자리를 세우고 있으면, 그 자리를 쓰는 코드가 되살아나도
    // 검사가 잡지 못한다.
    el("div", { class: "ir-attach", id: "ir-attach" }, [
      el("ul", { id: "ir-links" })
    ]),
    el("textarea", { class: "bubble-edit", id: "ir-send-message", readonly: "" }),
    el("p", { class: "hint muted", id: "ir-send-state" }),
    el("div", { class: "warn-box", id: "ir-send-warnings" }),
    el("div", { class: "send-modal-acts" }, [
      el("button", { type: "button", class: "linkbtn", id: "ir-send-copy" }),
      el("a", { class: "linkbtn", id: "ir-send-open-deals", href: "/deals" }),
      el("a", { class: "linkbtn", id: "ir-send-job", href: "/jobs" }),
      el("button", { type: "button", class: "secondary-btn", id: "ir-send-close" }),
      el("button", { type: "button", class: "primary-btn", id: "ir-send-go" })
    ])
  ]);
}

function buildDom() {
  dom_.resetHandlers();
  const form = deliverForm(NAME, CONTACT_ID, COMPANY_IDS);
  const head = el("div", { class: "due-head" }, [form]);
  const modal = sendModal();
  const root = el("div", { class: "layout" }, [
    el("div", { class: "send-groups" }, [el("div", { class: "due-group" }, [head])]),
    modal
  ]);
  // 단추 글자는 화면이 정한다 — 스크립트가 "보내는 중…" 뒤에 되돌릴 글자를
  // 여기서 읽는다. 비워 두면 되돌린 뒤 단추에 글자가 없어진다.
  modal.querySelector("#ir-send-go").textContent = "보내기";
  modal.querySelector("#ir-send-copy").textContent = "문구 복사";
  // 서버가 그려 주는 **처음 모습**. 창은 닫혀 있고, 무엇이 나갈지 보기 전에는
  // 아무 단추도 못 누른다 — 이 검사가 "창이 열렸다" 를 볼 수 있으려면 시작이
  // 닫힌 상태여야 한다(`el()` 은 속성만 달고 `hidden` 성질은 안 켠다).
  [modal, modal.querySelector("#ir-send-state"),
   modal.querySelector("#ir-send-warnings"), modal.querySelector("#ir-send-job")]
    .forEach(function (node) { node.hidden = true; });
  modal.querySelector("#ir-send-go").disabled = true;
  modal.querySelector("#ir-send-copy").disabled = true;
  const document = dom_.makeDocument(root);
  return { document: document, root: root, form: form, head: head, modal: modal };
}

// ir_send.js 를 이 화면 위에서 그대로 돌린다. 목록을 그리는 공용 한 벌
// (`ir_attach_list.js`)이 화면에서 먼저 실리므로 여기서도 같은 차례로 돌린다.
function run(opts) {
  opts = opts || {};
  const dom = buildDom();
  const JS = path.join(__dirname, "..", "..", "app", "static", "js");
  const win = { location: { search: "", href: "" } };
  const ctx = {
    document: dom.document, console: console, window: win,
    // 클립보드는 https·localhost 에서만 있다. 기본값은 **없는 쪽**이다 —
    // 사내에서 http 로 여는 화면이 그렇고, 거기서 복사가 죽으면 안 된다.
    navigator: opts.navigator || {},
    setTimeout: opts.setTimeout || function () { return 0; },
    clearTimeout: function () {},
    alert: opts.alert || function () {},
    // 발송은 되돌릴 수 없다 — 기본값은 **아니오**다.
    confirm: opts.confirm || function () { return false; },
    fetch: opts.fetch || function () {
      return { then: function () { return this; }, catch: function () { return this; } };
    }
  };
  ctx.window = win;
  win.document = dom.document;
  win.confirm = ctx.confirm;
  vm.runInNewContext(fs.readFileSync(path.join(JS, "ir_attach_list.js"), "utf8"),
                     ctx, { filename: "ir_attach_list.js" });
  vm.runInNewContext(fs.readFileSync(path.join(JS, "ir_send.js"), "utf8"),
                     ctx, { filename: "ir_send.js" });
  dom.window = win;
  return dom;
}

// [자료 보내기] 를 누른다. **화면이 넘어갔는지 알아야 하므로** 폼의 기본
// 동작이 막혔는지를 세어 돌려준다 — 안 막히면 브라우저는 그대로 폼을 보낸다.
function pressDeliver(dom) {
  let prevented = 0;
  dom.form.fire("submit", { preventDefault: function () { prevented += 1; } });
  return prevented;
}

// 창에 뜬 [보낼 자료] 목록의 줄들(그린 그대로의 HTML).
function attachRows(dom) {
  return dom.document.getElementById("ir-links").children
    .map(function (li) { return li.innerHTML; });
}

// 목록에 **보이는** 번호 — `{기업명: 번호}`.
function attachNumbers(dom, names) {
  const out = {};
  attachRows(dom).forEach(function (row) {
    const name = names.filter(function (n) { return row.indexOf(n) >= 0; })[0];
    const m = /(\d+)번/.exec(row);
    if (name && m) out[name] = parseInt(m[1], 10);
  });
  return out;
}

module.exports = {
  CONTACT_ID: CONTACT_ID, COMPANY_IDS: COMPANY_IDS, NAME: NAME,
  buildDom: buildDom, run: run, pressDeliver: pressDeliver,
  attachRows: attachRows, attachNumbers: attachNumbers,
  fakeFetch: require("./_deals_dom.js").fakeFetch
};
