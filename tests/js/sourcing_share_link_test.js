// 딜 소싱 화면의 [Series A 딜 소개] — 링크가 **지금 보이는 참여 분**을 싣는가.
// (node tests/js/sourcing_share_link_test.js)
//
// 이 단추는 딜 제안 관리 › 딜 소싱 제안을 [Series A 딜 공유]로 열고, 이 표에서
// 머리글 필터 · 검색으로 거른 **보이는 줄**을 받는 사람으로 미리 골라 둔다
// (`?contacts=…`). 불참여 분은 싣지 않는다. 필터를 바꾸면 링크와 단추의 수가
// 따라와야 한다 — 거른 대로 넘어가지 않으면 담당으로 좁혀 놓고 누른 사람이
// 남의 담당까지 고른 화면을 받는다.
//
// 화면 스크립트는 `sourcing.html` 안에 있다 — 그 글을 그대로 읽어 돌린다(Jinja
// 꺾쇠만 걷는다). 이름 · 번호는 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const el = dom_.el;

const HTML = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "templates", "sourcing.html"), "utf8");
const blocks = HTML.split("{% block scripts %}")[1];
const inline = /<script>([\s\S]*?)<\/script>/.exec(blocks)[1]
  .replace(/\{%[\s\S]*?%\}/g, "").replace(/\{\{[\s\S]*?\}\}/g, "0");

const BASE = "/deals?mode=sourcing&topic=sourcing_deal_share";

function row(id, participation, hidden) {
  const tr = el("tr", { "data-id": String(id), "data-f-participation": participation },
                [el("td", { class: "rowno" })]);
  tr.hidden = !!hidden;
  return tr;
}

function setup(rows) {
  dom_.resetHandlers();
  const root = dom_.makeEl("html");
  const table = el("table", { id: "sourcing-table" }, [el("tbody", {}, rows)]);
  const btn = el("a", { id: "sourcing-share-btn", href: BASE, "data-base": BASE });
  root.appendChild(table);
  root.appendChild(btn);
  root.appendChild(el("input", { id: "sourcing-search", type: "search" }));
  let filterOpts = null;
  const win = {
    DealflowFilters: {
      init: function (opts) {
        filterOpts = opts;
        return { apply: function () { if (opts.onChange) opts.onChange(); } };
      }
    },
    location: { reload: function () {} }
  };
  const ctx = { document: dom_.makeDocument(root), window: win, console: console,
                setTimeout: function () { return 0; }, location: win.location,
                fetch: function () {}, alert: function () {}, confirm: function () { return false; },
                prompt: function () { return ""; } };
  vm.runInNewContext(inline, ctx, { filename: "sourcing.html<script>" });
  return { btn: btn, refilter: function () { filterOpts.onChange(); } };
}

{
  const rows = [row(11, "참여"), row(12, "불참여"), row(13, "참여", true), row(14, "참여")];
  const t = setup(rows);
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11,14",
                     "보이는 참여 분만 실어야 한다(불참여 · 걸러진 줄은 빼고)");
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (2명)");

  // 필터를 바꾸면(걸러진 줄이 다시 보이면) 링크가 따라온다.
  rows[2].hidden = false;
  t.refilter();
  assert.strictEqual(t.btn.getAttribute("href"), BASE + "&contacts=11,13,14");
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (3명)");

  // 아무도 안 보이면 받는 사람 없이 연다(거기서 고른다).
  rows.forEach(function (r) { r.hidden = true; });
  t.refilter();
  assert.strictEqual(t.btn.getAttribute("href"), BASE);
  assert.strictEqual(t.btn.textContent, "Series A 딜 소개 (0명)");
}

console.log("sourcing_share_link_test: ok");
