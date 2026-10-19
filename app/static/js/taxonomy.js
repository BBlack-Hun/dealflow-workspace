// 분야 기준 목록(관리자) — 목록 고치기 · IR 기업현황 정리.
//
// **값이 바뀌는 고침은 먼저 몇 줄이 바뀌는지 묻는다.** 이름 바꾸기 · 합치기 ·
// 옮기기는 미리보기(`…/preview/<고침>`)로 IR 기업 수 · 투자사 수를 받아 확인을
// 받은 뒤에야 보낸다. 정리는 미리보기 표에서 고른 것만 보낸다 — 서버는
// 계획을 다시 세워 그 안에 있는 것만 바꾼다(`routers/taxonomy.py`).
(function () {
  "use strict";

  var msg = document.getElementById("tx-msg");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  function say(text, isError) {
    if (!msg) return;
    msg.hidden = !text;
    msg.textContent = text || "";
    msg.classList.toggle("err", !!isError);
  }

  function call(method, url, body) {
    var opts = { method: method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.detail || "처리하지 못했습니다");
        return d;
      });
    });
  }

  function fail(err) { say(err && err.message ? err.message : String(err), true); }

  // ── 기준 목록 ──────────────────────────────────────────────────────────
  var treeEl = document.getElementById("tx-tree");
  var tree = [];

  function tags(term) {
    var out = "";
    if (term.merged_into) out += ' <span class="tag soft">→ ' + esc(term.merged_into) + "</span>";
    else if (term.hidden) out += ' <span class="tag soft">숨김</span>';
    return out;
  }

  function actions(term, isMajor) {
    if (term.merged_into) return "";
    var b = function (act, label, title) {
      return '<button type="button" class="linkbtn" data-act="' + act + '" data-id="' +
        term.id + '"' + (title ? ' title="' + esc(title) + '"' : "") + ">" + label + "</button>";
    };
    return '<span class="tx-acts">' +
      b("up", "▲", "위로") + b("down", "▼", "아래로") +
      b("rename", "이름 바꾸기") +
      (isMajor ? "" : b("move", "옮기기", "다른 대분류 아래로")) +
      b("merge", "합치기", "같은 단계의 다른 이름으로 합칩니다") +
      b(term.hidden ? "show" : "hide", term.hidden ? "다시 보이기" : "숨기기") +
      (isMajor ? b("add", "소분류 추가") : "") +
      "</span>";
  }

  function render() {
    if (!treeEl) return;
    treeEl.innerHTML = tree.map(function (major) {
      var cls = "tx-major" + (major.hidden || major.merged_into ? " tx-off" : "");
      return '<div class="' + cls + '" data-id="' + major.id + '">' +
        '<div class="tx-row"><b class="tx-name">' + esc(major.name) + "</b>" + tags(major) +
        actions(major, true) + "</div>" +
        '<ul class="tx-minors">' + (major.minors || []).map(function (minor) {
          return '<li class="tx-row' + (minor.hidden || minor.merged_into ? " tx-off" : "") +
            '" data-id="' + minor.id + '"><span class="tx-name">' + esc(minor.name) + "</span>" +
            tags(minor) + actions(minor, false) + "</li>";
        }).join("") + "</ul>" +
        '<div class="tx-pick" hidden></div></div>';
    }).join("");
  }

  function find(id) {
    for (var i = 0; i < tree.length; i += 1) {
      if (tree[i].id === id) return { term: tree[i], major: tree[i], isMajor: true };
      var minors = tree[i].minors || [];
      for (var j = 0; j < minors.length; j += 1) {
        if (minors[j].id === id) return { term: minors[j], major: tree[i], isMajor: false };
      }
    }
    return null;
  }

  function live(term) { return !term.hidden && !term.merged_into; }

  function refresh(res, text) {
    if (res && res.tree) { tree = res.tree; render(); }
    say(text || "");
  }

  // 값이 바뀌는 고침 — 미리보기로 몇 줄인지 묻고 나서 보낸다.
  function changeWithPreview(op, id, body, what) {
    call("POST", "/api/taxonomy/terms/" + id + "/preview/" + op, body)
      .then(function (p) {
        var text = what + "\n\n함께 바뀌는 값: IR 기업 " + p.ir + "곳 · 투자사 " + p.vc + "명";
        if (p.samples && p.samples.length) {
          text += "\n\n예)\n" + p.samples.slice(0, 5).map(function (s) {
            return "· " + s.name + ": " + (s.old || "(빈 칸)") + " → " + s.new;
          }).join("\n");
        }
        if (!window.confirm(text + "\n\n한 번에 바꿉니다. 진행할까요?")) return null;
        return call("POST", "/api/taxonomy/terms/" + id + "/" + op, body).then(function (res) {
          refresh(res, what + " — IR 기업 " + (res.ir || 0) + "곳 · 투자사 " +
            (res.vc || 0) + "명의 값을 함께 바꿨습니다.");
        });
      })
      .catch(fail);
  }

  // 같은 줄 아래에 고르는 칸을 편다(합칠 곳 · 옮길 대분류).
  function pick(id, label, options, onGo) {
    var box = treeEl.querySelector('.tx-major[data-id="' + find(id).major.id + '"] .tx-pick');
    if (!box) return;
    if (!options.length) { say("고를 곳이 없습니다", true); return; }
    box.innerHTML = "<span>" + esc(label) + "</span> " +
      '<select class="tx-select">' + options.map(function (o) {
        return '<option value="' + o.id + '">' + esc(o.name) + "</option>";
      }).join("") + "</select> " +
      '<button type="button" class="secondary-btn tx-go">확인</button> ' +
      '<button type="button" class="linkbtn tx-cancel">취소</button>';
    box.hidden = false;
    box.querySelector(".tx-go").addEventListener("click", function () {
      var value = Number(box.querySelector(".tx-select").value);
      box.hidden = true;
      onGo(value, (options.filter(function (o) { return o.id === value; })[0] || {}).name);
    });
    box.querySelector(".tx-cancel").addEventListener("click", function () { box.hidden = true; });
  }

  function onTreeClick(e) {
    var btn = e.target.closest("button[data-act]");
    if (!btn) return;
    var id = Number(btn.getAttribute("data-id"));
    var act = btn.getAttribute("data-act");
    var hit = find(id);
    if (!hit) return;
    var term = hit.term;
    if (act === "up" || act === "down") {
      call("POST", "/api/taxonomy/terms/" + id + "/order", { step: act === "up" ? -1 : 1 })
        .then(function (res) { refresh(res); }).catch(fail);
    } else if (act === "hide" || act === "show") {
      call("POST", "/api/taxonomy/terms/" + id + "/hide", { hidden: act === "hide" })
        .then(function (res) {
          refresh(res, act === "hide"
            ? "`" + term.name + "` 을 숨겼습니다 — 고르는 목록에서 빠지고, 쓰던 값은 그대로입니다."
            : "`" + term.name + "` 을 다시 보이게 했습니다.");
        }).catch(fail);
    } else if (act === "add") {
      add(id);
    } else if (act === "rename") {
      var name = window.prompt("새 이름 (`" + term.name + "`)", term.name);
      if (!name || name.trim() === term.name) return;
      changeWithPreview("rename", id, { name: name.trim() },
        "이름 바꾸기: " + term.name + " → " + name.trim());
    } else if (act === "merge") {
      var same = [];
      tree.forEach(function (major) {
        if (hit.isMajor) {
          if (major.id !== id && live(major)) same.push({ id: major.id, name: major.name });
        } else {
          (major.minors || []).forEach(function (minor) {
            if (minor.id !== id && live(minor)) {
              same.push({ id: minor.id, name: minor.name + "  (" + major.name + ")" });
            }
          });
        }
      });
      pick(id, "`" + term.name + "` 을 이리로 합칩니다:", same, function (target, label) {
        changeWithPreview("merge", id, { target_id: target },
          "합치기: " + term.name + " → " + label);
      });
    } else if (act === "move") {
      var majors = tree.filter(function (m) { return m.id !== hit.major.id && live(m); })
        .map(function (m) { return { id: m.id, name: m.name }; });
      pick(id, "`" + term.name + "` 을 이 대분류 아래로:", majors, function (target, label) {
        changeWithPreview("move", id, { parent_id: target },
          "옮기기: " + term.name + " → " + label + " 아래");
      });
    }
  }

  function add(parentId) {
    var where = parentId ? find(parentId).term.name + " 아래 소분류" : "대분류";
    var name = window.prompt("새 " + where + " 이름");
    if (!name || !name.trim()) return;
    call("POST", "/api/taxonomy/terms", { name: name.trim(), parent_id: parentId })
      .then(function (res) { refresh(res, "`" + name.trim() + "` 을 더했습니다."); })
      .catch(fail);
  }

  if (treeEl) {
    try { tree = JSON.parse(treeEl.getAttribute("data-tree") || "[]"); } catch (err) { tree = []; }
    render();
    treeEl.addEventListener("click", onTreeClick);
    var addMajor = document.getElementById("tx-add-major");
    if (addMajor) addMajor.addEventListener("click", function () { add(null); });
  }

  // 미리보기 표의 체크상자를 한꺼번에.
  function checkAll(scope, selector, on) {
    scope.querySelectorAll(selector).forEach(function (cb) { cb.checked = on; });
  }

  function list(items) {
    return items.length ? items.map(esc).join("<br>") : '<span class="muted">—</span>';
  }

  // ── IR 기업현황 정리 ───────────────────────────────────────────────────
  var irResult = document.getElementById("ir-result");
  var irApply = document.getElementById("ir-apply");

  function both(major, minor) {
    return esc(major || "(빈 칸)") + ' <span class="muted">/</span> ' + esc(minor || "—");
  }

  function renderIr(d) {
    var c = d.counts || {};
    var html = '<ul class="import-stats">' +
      "<li><span>규칙대로 바뀌는 기업</span><b>" + (c.fix || 0) + "곳</b></li>" +
      "<li><span>빈 대분류 제안</span><b>" + (c.suggest || 0) + "곳</b></li>" +
      "<li><span>정리 대상(바꾸지 않음)</span><b>" + (c.flagged || 0) + "곳</b></li>" +
      "<li><span>대분류가 비었는데 제안 없음</span><b>" + (c.no_suggestion || 0) + "곳</b></li>" +
      "<li><span>IR 기업 전체</span><b>" + (c.total || 0) + "곳</b></li></ul>";
    var rows = d.rows || [];
    if (rows.length) {
      html += '<div class="table-wrap"><table class="grid-table compact tx-table"><thead><tr>' +
        "<th>고름</th><th>기업</th><th>지금 (대분류 / 소분류)</th>" +
        "<th>바뀔 값 (대분류 / 소분류)</th><th>까닭</th></tr></thead><tbody>" +
        rows.map(function (r) {
          var target = r.kind === "suggest"
            ? '<select class="ir-major">' + (d.majors || []).map(function (m) {
                return '<option value="' + esc(m) + '"' + (m === r.new_major ? " selected" : "") +
                  ">" + esc(m) + "</option>";
              }).join("") + "</select>" + ' <span class="muted">/</span> ' + esc(r.new_minor || "—")
            : "<b>" + both(r.new_major, r.new_minor) + "</b>";
          return '<tr data-id="' + r.id + '"' + (r.kind === "suggest" ? ' class="tx-suggest"' : "") +
            '><td><input type="checkbox" class="ir-cb"' + (r.checked ? " checked" : "") +
            "></td><td>" + esc(r.name) + (r.kind === "suggest" ? ' <span class="tag">제안</span>' : "") +
            "</td><td>" + both(r.major, r.minor) + "</td><td>" + target + "</td><td>" +
            list(r.reasons || []) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    } else {
      html += '<p class="hint ok">목록대로 바꿀 기업이 없습니다.</p>';
    }
    if ((d.flagged || []).length) {
      html += '<h3 class="tx-sub">정리 대상 — 바꾸지 않습니다</h3><p class="hint">' +
        d.flagged.map(function (f) { return esc(f.name) + " (" + both(f.major, f.minor) + ")"; })
          .join(", ") + "</p>";
    }
    if ((d.unknown_majors || []).length || (d.unknown_minors || []).length) {
      html += '<h3 class="tx-sub">목록에 없는 값 — 그대로 둡니다</h3><p class="hint">' +
        (d.unknown_majors || []).map(function (u) { return "대분류 `" + esc(u[0]) + "` " + u[1] + "곳"; })
          .concat((d.unknown_minors || []).map(function (u) {
            return "소분류 `" + esc(u[0]) + "` " + u[1] + "곳";
          })).join(" · ") +
        "<br>목록에 더하거나(옛 이름이면 합치기) 손으로 고친 뒤 다시 미리보기를 여세요.</p>";
    }
    if ((d.no_suggestion || []).length) {
      html += '<details class="tx-sub"><summary>대분류가 비었는데 제안을 못 만든 기업 ' +
        d.no_suggestion.length + "곳</summary><p class=\"hint\">" +
        d.no_suggestion.map(function (n) { return esc(n.name); }).join(", ") +
        "</p></details>";
    }
    irResult.innerHTML = html;
    var any = rows.length > 0;
    irApply.disabled = !any;
    document.getElementById("ir-all").hidden = !any;
    document.getElementById("ir-none").hidden = !any;
  }

  function loadIr() {
    irResult.innerHTML = '<p class="muted">세는 중…</p>';
    call("GET", "/api/taxonomy/ir-cleanup").then(renderIr).catch(fail);
  }

  if (irResult) {
    document.getElementById("ir-preview").addEventListener("click", loadIr);
    document.getElementById("ir-all").addEventListener("click", function () {
      checkAll(irResult, ".ir-cb", true);
    });
    document.getElementById("ir-none").addEventListener("click", function () {
      checkAll(irResult, ".ir-cb", false);
    });
    irApply.addEventListener("click", function () {
      var items = [];
      irResult.querySelectorAll("tr[data-id]").forEach(function (tr) {
        var cb = tr.querySelector(".ir-cb");
        if (!cb || !cb.checked) return;
        var sel = tr.querySelector(".ir-major");
        items.push({ id: Number(tr.getAttribute("data-id")), major: sel ? sel.value : null });
      });
      if (!items.length) { say("반영할 기업을 고르세요", true); return; }
      if (!window.confirm("고른 " + items.length + "곳의 대분류·소분류를 바꿉니다.\n" +
                          "원래 값은 백업 칸에 처음 한 번만 남습니다. 진행할까요?")) return;
      irApply.disabled = true;
      call("POST", "/api/taxonomy/ir-cleanup", { items: items })
        .then(function (res) {
          renderIr(res);
          say(res.applied + "곳을 반영했습니다" +
              (res.skipped ? " (그 사이 바뀐 " + res.skipped + "곳은 건너뜀)" : "") + ".");
        })
        .catch(function (err) { irApply.disabled = false; fail(err); });
    });
  }
})();
