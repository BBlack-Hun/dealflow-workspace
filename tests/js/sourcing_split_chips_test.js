// 딜 소싱 시리즈 A 탭 위 칩 수(i133) — `참여` · `담당자` 를 고치면 새로고침 없이 다시 센다.
// (node tests/js/sourcing_split_chips_test.js)
//
// 사용자: "참여로 바꾸면 검토가능 묶음에서 자동으로 빠지고 참여 묶음에 자동으로 들어가게"
//   ① `참여` 저장 → 검토가능 칩 -1 · 참여 칩 +1, 그 담당의 작은 링크도 같이
//   ② `담당자` 저장 → 담당별 칩이 옮겨 간다
// 세는 값은 머리글 필터가 거르는 행의 `data-f-*` 다(칩 수 = 눌렀을 때 뜨는 줄 수).
//
// 화면 스크립트는 `sourcing.html` 안에 있다 — 그 글을 그대로 읽어 돌린다(Jinja
// 꺾쇠만 걷는다). 이름은 가상값이다(공개 저장소).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dom_ = require("./_dom.js");
const el = dom_.el;

const HTML = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "templates", "sourcing.html"), "utf8");
const inline = /<script>([\s\S]*?)<\/script>/.exec(HTML.split("{% block scripts %}")[1])[1]
  .replace(/\{%[\s\S]*?%\}/g, "").replace(/\{\{[\s\S]*?\}\}/g, "0");

const OFFER = "딜 소싱 참여 제안 대기중";
const ASKING = "참여 의사를 물어보는 중";
const INVITE = OFFER + "|" + ASKING;

function row(id, participation, who) {
  const cell = el("td", { "data-field": "participation" });
  const whoCell = el("td", { "data-field": "assignee_name" });
  return el("tr", { "data-id": String(id), "data-f-participation": participation,
                    "data-f-assignee_name": who }, [cell, whoCell]);
}

// 서버가 그린 모양(`split_chips`) — 처음 수는 서버가 센 그대로.
function chip(label, part, who, n) {
  return el("a", { "data-part": part, "data-who": who, "data-label": label },
            [Object.assign(el("b", {}), { textContent: String(n) })]);
}

const rows = [row(1, OFFER, "가담당"), row(2, ASKING, "가담당"), row(3, "참여", "나담당"),
              row(4, "불참여", "나담당")];
const chips = [chip("검토가능", INVITE, "", 2), chip("참여", "참여", "", 1),
               chip("불참여", "불참여", "", 1), chip("가담당", "", "가담당", 2),
               chip("가담당 검토가능", INVITE, "가담당", 2), chip("가담당 참여", "참여", "가담당", 0),
               chip("나담당", "", "나담당", 2), chip("나담당 검토가능", INVITE, "나담당", 0),
               chip("나담당 참여", "참여", "나담당", 1)];

dom_.resetHandlers();
const root = dom_.makeEl("html");
const table = el("table", { id: "sourcing-table" }, [el("tbody", {}, rows)]);
root.appendChild(el("div", { id: "sourcing-split" }, chips));
root.appendChild(table);
const win = {
  DealflowFilters: { init: function () { return { apply: function () {} }; } },
  location: { reload: function () {} }
};
vm.runInNewContext(inline, {
  document: dom_.makeDocument(root), window: win, console: console,
  setTimeout: function () { return 0; }, location: win.location, fetch: function () {},
  alert: function () {}, confirm: function () { return false; }, prompt: function () { return ""; }
}, { filename: "sourcing.html<script>" });

function counts() {
  const out = {};
  chips.forEach(function (c) { out[c.getAttribute("data-label")] = Number(c.querySelector("b").textContent); });
  return out;
}
function save(tr, field, data) {
  table.fire("inline-saved", { detail: {
    row: tr, cell: tr.querySelector('[data-field="' + field + '"]'), data: data } });
}

// --- ① 제안 대기중 → 참여 ------------------------------------------------------
save(rows[0], "participation", { participation: "참여", participation_kind: "joined" });
assert.deepStrictEqual(counts(), {
  "검토가능": 1, "참여": 2, "불참여": 1, "가담당": 2, "가담당 검토가능": 1, "가담당 참여": 1,
  "나담당": 2, "나담당 검토가능": 0, "나담당 참여": 1
}, "참여로 바꿨는데 검토가능 · 참여 칩이 그대로다");
assert.strictEqual(rows[0].getAttribute("data-f-participation"), "참여");

// --- ② 담당 바꾸기 — 줄이 다른 담당 묶음으로 옮겨 간다 ---------------------------
save(rows[1], "assignee_name", { assignee: "나담당" });
assert.deepStrictEqual(counts(), {
  "검토가능": 1, "참여": 2, "불참여": 1, "가담당": 1, "가담당 검토가능": 0, "가담당 참여": 1,
  "나담당": 3, "나담당 검토가능": 1, "나담당 참여": 1
}, "담당을 바꿨는데 담당별 칩이 안 옮겨 갔다");

console.log("sourcing_split_chips_test: ok");
