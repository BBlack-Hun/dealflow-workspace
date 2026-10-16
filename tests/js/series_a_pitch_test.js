// `Series A 이상 딜 소싱` 탭의 [딜소개 문구 올리기] — 브라우저 쪽.
// (node tests/js/series_a_pitch_test.js)
//
// 규칙을 여기 옮겨 적으면 두 벌이 되어 어긋나도 모르므로 **파일을 그대로 돌린다**
// (`app/static/js/series_a_pitch.js`). 어느 줄에 맞는지는 서버가 세므로 여기서는
// 보내는 것과 그리는 것만 본다.
//
//   ① 단추로 창을 열고 닫는다. 파일이 없으면 보내지 않는다.
//   ② [미리보기] 는 `dry_run=true` 로 보내고, 수와 목록을 그린다(글자는 이스케이프).
//   ③ 파일 · 탭 · 덮어쓰기를 바꾸면 미리보기가 낡는다 — [반영] 이 다시 잠긴다.
//   ④ [반영] 은 묻고, 같은 파일을 `dry_run=false` 로 보낸 뒤 보던 주소에 알림을 얹어 다시 연다.
//   ⑤ 바뀔 것이 없으면 [반영] 이 잠긴 채다.
//   ⑥ 탭을 못 고르면(400) 서버가 준 탭으로 고르개를 세우고, 고른 탭을 보낸다.
//
// 기업명은 전부 지어낸 것이다 — 저장소가 공개다.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const D = require("./_dom.js");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "static", "js", "series_a_pitch.js"), "utf8");

// 화면(`app/templates/companies_series_a.html`)이 관리자에게 그리는 만큼만 세운다.
function build() {
  const ids = {};
  function mk(tag, id, attrs, kids) {
    const node = D.el(tag, Object.assign({ id: id }, attrs || {}), kids || []);
    ids[id] = node;
    return node;
  }
  const auto = D.el("option", { value: "" });
  auto.textContent = "알아서 고르기";
  const sheetBox = mk("label", "sa-pitch-sheet-box", { class: "field inline-field" },
                      [mk("select", "sa-pitch-sheet", {}, [auto])]);
  sheetBox.hidden = true;
  const panel = mk("section", "sa-pitch-panel", { class: "panel import-panel" }, [
    mk("button", "sa-pitch-close"),
    mk("input", "sa-pitch-file", { type: "file" }),
    sheetBox,
    mk("input", "sa-pitch-overwrite", { type: "checkbox" }),
    mk("button", "sa-pitch-preview"),
    mk("button", "sa-pitch-apply"),
    mk("div", "sa-pitch-result", { class: "import-result" })
  ]);
  panel.hidden = true;
  ids["sa-pitch-apply"].disabled = true;
  const root = D.el("div", {}, [mk("button", "sa-pitch-btn"), panel]);
  return { root: root, $: ids };
}

function FormDataStub() { this.entries = []; }
FormDataStub.prototype.append = function (k, v) { this.entries.push([k, v]); };
FormDataStub.prototype.get = function (k) {
  const hit = this.entries.find(function (e) { return e[0] === k; });
  return hit ? hit[1] : null;
};

function run(dom, opts) {
  opts = opts || {};
  D.resetHandlers();
  const document = D.makeDocument(dom.root);
  const calls = [];
  const asked = [];
  const answers = (opts.answers || []).slice();
  const win = {
    location: { pathname: "/companies", search: opts.search || "?tab=series-a", href: "" }
  };
  const sandbox = {
    document: document, console: console,
    alert: function () {},
    confirm: function (text) { asked.push(text); return opts.confirm !== false; },
    encodeURIComponent: encodeURIComponent,
    FormData: FormDataStub,
    fetch: function (url, init) {
      calls.push({ url: url, method: init && init.method, body: init && init.body });
      const next = answers.shift() || { ok: true, data: {} };
      return Promise.resolve({ ok: next.ok, json: function () { return Promise.resolve(next.data); } });
    }
  };
  sandbox.window = win;
  Object.assign(win, sandbox);
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "series_a_pitch.js" });
  return { calls: calls, asked: asked, win: win, answers: answers };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

function preview(over) {
  return Object.assign({
    dry_run: true, overwrite: false, sheets: [], sheet_used: "",
    file_rows: 9, no_name: 1, matched: 6, unmatched: 1, unmatched_with_pitch: 1,
    ambiguous: 1, duplicates: 1, changed: 2, filled: 2, overwritten: 0,
    same: 1, kept: 1, blank: 1,
    changes: [
      { id: 1, name: "샘플<b>애그", received_at: "2026-07-01", shared_by: "박영희 이사",
        source_firm: "가나벤처스", how: "fill", before: "", after: "애그 새 문구" },
      { id: 4, name: "샘플페이", received_at: "2026-07-04", shared_by: "박영희 이사",
        source_firm: "마바벤처스", how: "fill", before: "", after: "페이 새 문구" }
    ],
    unmatched_rows: [{ name: "샘플없음", received_at: "2026-07-08", shared_by: "박영희 이사",
                       source_firm: "가나벤처스", has_pitch: true }],
    ambiguous_rows: [{ name: "샘플푸드", received_at: "2026-07-06", shared_by: "김서연 이사",
                       source_firm: "가나벤처스", has_pitch: true }],
    summary: "바뀔 줄 2(빈 칸 채움 2 · 덮어씀 0) · 못 맞춘 줄 1 · 애매해서 건너뛴 줄 1"
  }, over || {});
}

const FILE = { name: "sheet.csv" };

(async function main() {
  // --- ① 열고 닫기 · 파일 없음 ---------------------------------------------
  {
    const dom = build();
    const t = run(dom);
    dom.$["sa-pitch-btn"].fire("click");
    assert.strictEqual(dom.$["sa-pitch-panel"].hidden, false, "단추를 눌러도 창이 안 열린다");
    dom.$["sa-pitch-close"].fire("click");
    assert.strictEqual(dom.$["sa-pitch-panel"].hidden, true, "[닫기] 가 창을 안 닫는다");

    dom.$["sa-pitch-preview"].fire("click");
    await settle();
    assert.strictEqual(t.calls.length, 0, "파일이 없는데 보냈다");
    assert.ok(dom.$["sa-pitch-result"].innerHTML.indexOf("파일을 먼저 고르세요") >= 0);
  }

  // --- ② 미리보기 · ③ 바꾸면 낡는다 -----------------------------------------
  {
    const dom = build();
    const t = run(dom, { answers: [{ ok: true, data: preview() }] });
    dom.$["sa-pitch-file"].files = [FILE];
    dom.$["sa-pitch-preview"].fire("click");
    await settle();
    assert.strictEqual(t.calls.length, 1);
    assert.strictEqual(t.calls[0].url, "/api/import/series-a-pitch");
    assert.strictEqual(t.calls[0].method, "POST");
    const body = t.calls[0].body;
    assert.strictEqual(body.get("file"), FILE, "파일을 안 실었다");
    assert.strictEqual(body.get("dry_run"), "true", "미리보기가 dry_run 이 아니다");
    assert.strictEqual(body.get("overwrite"), "false");
    assert.strictEqual(body.get("sheet"), "");

    const html = dom.$["sa-pitch-result"].innerHTML;
    assert.ok(html.indexOf("미리보기 — 아직 반영되지 않았습니다") >= 0, html);
    ["맞은 줄", "못 맞춘 줄", "애매해서 건너뛴 줄", "시트 안 중복", "바뀔 줄"].forEach(function (w) {
      assert.ok(html.indexOf(w) >= 0, "미리보기에 '" + w + "' 가 없다");
    });
    assert.ok(html.indexOf("2줄 (채움 2 · 덮어씀 0)") >= 0, html);
    assert.ok(html.indexOf("샘플&lt;b&gt;애그") >= 0 && html.indexOf("샘플<b>애그") < 0,
              "기업명을 이스케이프하지 않았다");
    assert.ok(html.indexOf("샘플없음") >= 0 && html.indexOf("샘플푸드") >= 0,
              "못 맞춘 줄 · 애매한 줄 목록이 없다");
    assert.ok(html.indexOf("이미 적힌 문구도 덮어쓰기") >= 0, "안 덮은 줄 안내가 없다");
    assert.strictEqual(dom.$["sa-pitch-apply"].disabled, false, "미리본 뒤에도 [반영] 이 잠겨 있다");
    // 탭이 없는 파일(CSV)에는 고르개를 안 세운다.
    assert.strictEqual(dom.$["sa-pitch-sheet-box"].hidden, true);

    dom.$["sa-pitch-overwrite"].checked = true;
    dom.$["sa-pitch-overwrite"].fire("change");
    assert.strictEqual(dom.$["sa-pitch-apply"].disabled, true, "덮어쓰기를 바꿨는데 [반영] 이 열려 있다");
    assert.strictEqual(dom.$["sa-pitch-result"].innerHTML, "");
    dom.$["sa-pitch-apply"].fire("click");
    await settle();
    assert.strictEqual(t.calls.length, 1, "낡은 미리보기로 반영했다");
  }

  // --- ④ 반영 ------------------------------------------------------------------
  {
    const dom = build();
    const applied = preview({ dry_run: false, overwrite: true, changed: 3, overwritten: 1,
                              summary: "딜소개 문구 3줄을 바꿨습니다(빈 칸 채움 2 · 덮어씀 1)" });
    const t = run(dom, { search: "?tab=series-a&type=%ED%9B%84%EC%86%8D&msg=old",
                         answers: [{ ok: true, data: preview({ overwrite: true, changed: 3,
                                                               overwritten: 1 }) },
                                   { ok: true, data: applied }] });
    dom.$["sa-pitch-file"].files = [FILE];
    dom.$["sa-pitch-overwrite"].checked = true;
    dom.$["sa-pitch-preview"].fire("click");
    await settle();
    assert.strictEqual(t.calls[0].body.get("overwrite"), "true");
    dom.$["sa-pitch-apply"].fire("click");
    await settle();
    assert.strictEqual(t.asked.length, 1, "반영 전에 묻지 않았다");
    assert.ok(t.asked[0].indexOf("3줄") >= 0 && t.asked[0].indexOf("덮어") >= 0, t.asked[0]);
    assert.strictEqual(t.calls.length, 2);
    assert.strictEqual(t.calls[1].body.get("dry_run"), "false", "반영이 dry_run=false 가 아니다");
    assert.strictEqual(t.calls[1].body.get("file"), FILE, "반영에 같은 파일을 안 실었다");
    assert.strictEqual(t.calls[1].body.get("overwrite"), "true");
    assert.strictEqual(t.win.location.href,
      "/companies?tab=series-a&type=%ED%9B%84%EC%86%8D&msg=" +
      encodeURIComponent(applied.summary),
      "보던 탭 · 필터를 지키고 알림 한 줄만 얹어 다시 열어야 한다");
  }

  // 묻는 창에서 [취소] — 보내지 않는다.
  {
    const dom = build();
    const t = run(dom, { confirm: false, answers: [{ ok: true, data: preview() }] });
    dom.$["sa-pitch-file"].files = [FILE];
    dom.$["sa-pitch-preview"].fire("click");
    await settle();
    dom.$["sa-pitch-apply"].fire("click");
    await settle();
    assert.strictEqual(t.calls.length, 1, "[취소] 했는데 보냈다");
    assert.strictEqual(t.win.location.href, "");
  }

  // --- ⑤ 바뀔 것이 없으면 ------------------------------------------------------
  {
    const dom = build();
    run(dom, { answers: [{ ok: true, data: preview({ changed: 0, filled: 0, changes: [] }) }] });
    dom.$["sa-pitch-file"].files = [FILE];
    dom.$["sa-pitch-preview"].fire("click");
    await settle();
    assert.strictEqual(dom.$["sa-pitch-apply"].disabled, true, "바뀔 것이 없는데 [반영] 이 열렸다");
    assert.ok(dom.$["sa-pitch-result"].innerHTML.indexOf("바꿀 줄이 없습니다") >= 0);
  }

  // --- ⑥ 탭 고르기 ---------------------------------------------------------------
  {
    const dom = build();
    const t = run(dom, { answers: [
      { ok: false, data: { detail: "이 시트로 보이는 탭이 하나가 아닙니다 <탭>", sheets: ["사본", "본문"] } },
      { ok: true, data: preview({ sheets: ["사본", "본문"], sheet_used: "본문" }) }
    ] });
    dom.$["sa-pitch-file"].files = [{ name: "book.xlsx" }];
    dom.$["sa-pitch-preview"].fire("click");
    await settle();
    const html = dom.$["sa-pitch-result"].innerHTML;
    assert.ok(html.indexOf('class="err"') >= 0 && html.indexOf("&lt;탭&gt;") >= 0, html);
    assert.strictEqual(dom.$["sa-pitch-apply"].disabled, true);
    const sel = dom.$["sa-pitch-sheet"];
    assert.strictEqual(dom.$["sa-pitch-sheet-box"].hidden, false, "탭 고르개가 안 섰다");
    assert.deepStrictEqual(sel.children.map((o) => o.value), ["", "사본", "본문"]);

    sel.value = "본문";
    sel.fire("change");
    dom.$["sa-pitch-preview"].fire("click");
    await settle();
    assert.strictEqual(t.calls[1].body.get("sheet"), "본문", "고른 탭을 안 보냈다");
    assert.strictEqual(sel.value, "본문", "다시 그리며 고른 탭을 잃었다");
    assert.strictEqual(sel.children.length, 3, "고르개에 탭이 겹쳐 쌓였다");
    assert.ok(dom.$["sa-pitch-result"].innerHTML.indexOf("읽은 탭") >= 0);

    // 파일을 바꾸면 고르개는 처음으로.
    dom.$["sa-pitch-file"].files = [FILE];
    dom.$["sa-pitch-file"].fire("change");
    assert.strictEqual(dom.$["sa-pitch-sheet-box"].hidden, true);
    assert.strictEqual(sel.value, "");
    assert.strictEqual(dom.$["sa-pitch-apply"].disabled, true);
  }

  console.log("series_a_pitch_test: ok");
})().catch(function (err) {
  console.error(err);
  process.exit(1);
});
