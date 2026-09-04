// 브라우저 검사가 쓰는 **아주 작은 DOM**. (node tests/js/_dom.js — 혼자 돌면 아무 일도 안 한다)
//
// 화면 코드는 DOM 에 매여 있어서, 규칙을 옮겨 적어 검사하면 두 벌이 되어 어긋나도
// 모른다. 그래서 실제 파일을 `vm` 으로 그대로 돌리고 이 파일이 그 밑을 받쳐 준다.
// 선택자는 화면들이 실제로 쓰는 만큼만 푼다: `태그`, `.클래스`, `#아이디`,
// `[속성]`, `[속성="값"]`, `:checked`, 그리고 사이의 공백(자손).
//
// **두 검사가 같은 것을 쓴다.** 각자 한 벌씩 들고 있으면 한쪽만 고쳐진다.
"use strict";

function parseCompound(text) {
  const out = { tag: "", id: "", classes: [], attrs: [], checked: false };
  const re = /(^[a-zA-Z][\w-]*)|\.([\w-]+)|#([\w-]+)|\[([\w-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]*)))?\]|(:checked)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m[1]) out.tag = m[1].toLowerCase();
    else if (m[2]) out.classes.push(m[2]);
    else if (m[3]) out.id = m[3];
    else if (m[4]) {
      const value = m[5] !== undefined ? m[5]
        : m[6] !== undefined ? m[6]
        : m[7] !== undefined ? m[7] : undefined;
      out.attrs.push([m[4], value]);
    } else if (m[8]) out.checked = true;
  }
  return out;
}

function matchesCompound(el, c) {
  if (c.tag && el.tag !== c.tag) return false;
  if (c.id && el.getAttribute("id") !== c.id) return false;
  for (const cls of c.classes) if (!el.classList.contains(cls)) return false;
  for (const [k, v] of c.attrs) {
    const have = el.getAttribute(k);
    if (have === null) return false;
    if (v !== undefined && v !== null && have !== v) return false;
  }
  if (c.checked && !el.checked) return false;
  return true;
}

function descendants(root, out) {
  out = out || [];
  for (const kid of root.children) { out.push(kid); descendants(kid, out); }
  return out;
}

// 공백으로 자르되 `[...]` 와 따옴표 안은 건드리지 않는다 —
// `[data-value="(비어 있음)"]` 처럼 값에 띄어쓰기가 든 선택자가 있다.
function splitSteps(one) {
  const out = [];
  let buf = "", depth = 0, quote = "";
  for (const ch of one.trim()) {
    if (quote) { buf += ch; if (ch === quote) quote = ""; continue; }
    if (ch === '"' || ch === "'") { quote = ch; buf += ch; continue; }
    if (ch === "[") depth += 1;
    if (ch === "]") depth -= 1;
    if (/\s/.test(ch) && depth === 0) { if (buf) { out.push(buf); buf = ""; } continue; }
    buf += ch;
  }
  if (buf) out.push(buf);
  return out;
}

function queryAll(root, selector) {
  const hits = [];
  const seen = new Set();
  for (const one of String(selector).split(",")) {
    const steps = splitSteps(one).map(parseCompound);
    if (!steps.length) continue;
    const last = steps[steps.length - 1];
    for (const el of descendants(root)) {
      if (!matchesCompound(el, last)) continue;
      // 앞 단계들이 조상 사슬에 순서대로 있어야 한다.
      let ok = true;
      let node = el.parent;
      for (let i = steps.length - 2; i >= 0; i -= 1) {
        while (node && !matchesCompound(node, steps[i])) node = node.parent;
        if (!node) { ok = false; break; }
        node = node.parent;
      }
      if (ok && !seen.has(el)) { seen.add(el); hits.push(el); }
    }
  }
  return hits;
}

function makeEl(tag) {
  const attrs = {};
  const el = {
    tag: String(tag).toLowerCase(),
    // 이 DOM 에는 **글자 노드가 없다** — 글자는 `textContent` 한 칸에 담긴다.
    // 그래서 `childNodes` 는 자식 요소만 돌려준다(전부 nodeType 1). 글자 노드를
    // 골라 지우는 코드(filters.js 가 머리글 이름을 지우는 자리)는 여기서
    // 아무 일도 하지 않는데, 그 편이 낫다 — 없는 것을 있는 척하면 검사가
    // 브라우저와 다른 것을 보증하게 된다.
    nodeType: 1,
    children: [], parent: null, handlers: {},
    hidden: false, checked: false, disabled: false,
    value: "", textContent: "",
    classList: {
      _on: new Set(),
      add(c) { this._on.add(c); },
      remove(c) { this._on.delete(c); },
      contains(c) { return this._on.has(c); },
      toggle(c, on) { if (on === undefined) on = !this._on.has(c); if (on) this._on.add(c); else this._on.delete(c); }
    },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    setAttribute(k, v) { attrs[k] = String(v); },
    hasAttribute(k) { return k in attrs; },
    removeAttribute(k) { delete attrs[k]; },
    appendChild(kid) { kid.parent = el; el.children.push(kid); return kid; },
    // 브라우저는 `textContent = ""` 로도 자식을 지우는데, 이 DOM 에는 글자
    // 노드가 없어서 그것만으로는 자식이 그대로 남는다. 다시 그리는 화면 코드는
    // 표준대로 `removeChild` 를 쓰므로 여기서도 받아 준다 — 안 그러면 두 번째로
    // 그릴 때 줄이 쌓이는 고장을 검사가 못 본다.
    removeChild(kid) {
      const at = el.children.indexOf(kid);
      if (at >= 0) { el.children.splice(at, 1); kid.parent = null; }
      return kid;
    },
    addEventListener(type, fn) { (el.handlers[type] = el.handlers[type] || []).push(fn); },
    // 글자 칸을 골라 두는 자리(복사 단추의 마지막 수단). 여기서 할 일은 없지만
    // **있어야 한다** — 없으면 화면 코드가 검사에서만 죽어, 클립보드가 없는
    // 브라우저에서 무슨 일이 나는지 아무도 못 본다.
    focus() {}, select() {},
    querySelector(sel) { return queryAll(el, sel)[0] || null; },
    querySelectorAll(sel) { return queryAll(el, sel); },
    closest(sel) {
      const c = parseCompound(sel.trim());
      let node = el;
      while (node) { if (matchesCompound(node, c)) return node; node = node.parent; }
      return null;
    },
    get childNodes() { return el.children; },
    // 브라우저가 부르는 이름. 화면 코드는 `parentNode` 를 쓰는데 여기 없으면
    // 검사에서만 `undefined` 를 만나 죽는다 — 그 자리를 아무도 못 보게 된다.
    get parentNode() { return el.parent; },
    // 이벤트는 버블링까지 흉내 낸다 — 칩은 줄(`#group-filter`)이 대신 듣는다.
    fire(type, extra) {
      const ev = Object.assign({ target: el, stopPropagation() {}, preventDefault() {} }, extra || {});
      let node = el;
      while (node) {
        // 브라우저는 `onclick = …` 도 함께 부른다. 안 부르면 그렇게 맨 화면
        // 코드가 검사에서만 조용히 죽은 채로 있다 — 미리보기 탭이 그렇다.
        const direct = node["on" + type];
        if (typeof direct === "function") direct.call(node, ev);
        (node.handlers[type] || []).forEach(function (fn) { fn(ev); });
        node = node.parent;
      }
      (documentHandlers[type] || []).forEach(function (fn) { fn(ev); });
    }
  };
  // 브라우저는 `innerHTML` 을 넣으면 **있던 자식을 먼저 버린다.** 이 DOM 은
  // 글자를 파싱하지 않아 새 자식이 생기지는 않지만, 버리는 것까지 안 하면
  // "비우고 다시 그린다" 는 화면 코드가 여기서만 **줄을 쌓는다** — 그러면
  // 두 번째로 그릴 때 목록이 두 벌이 되는 고장을 검사가 못 본다
  // (`removeChild` 를 받아 주는 것과 같은 뜻이다).
  // `class="…"` 를 통째로 갈아 끼우는 자리. 브라우저에서는 `classList` 와 같은
  // 것을 가리키는데, 여기서 안 이어 두면 `className = "…"` 은 아무 데도 안
  // 닿는 성질 하나가 되어 — 그렇게 붙인 이름은 선택자로 영영 안 잡힌다.
  Object.defineProperty(el, "className", {
    enumerable: true,
    get() { return Array.from(el.classList._on).join(" "); },
    set(value) {
      el.classList._on.clear();
      String(value).split(/\s+/).filter(Boolean)
        .forEach(function (c) { el.classList._on.add(c); });
    }
  });
  // 링크 주소. 브라우저는 성질과 속성을 서로 비춰 준다 — 안 이어 두면
  // `a.href = "…"` 로 건 주소를 `getAttribute("href")` 가 못 보고, 검사는
  // 서버가 그려 둔 옛 주소를 보며 통과한다.
  Object.defineProperty(el, "href", {
    enumerable: true,
    get() { return el.getAttribute("href") || ""; },
    set(value) { el.setAttribute("href", value); }
  });
  let html = "";
  Object.defineProperty(el, "innerHTML", {
    enumerable: true,
    get() { return html; },
    set(value) {
      html = String(value);
      el.children.forEach(function (kid) { kid.parent = null; });
      el.children.length = 0;
      // 브라우저는 여기서 **새 자식을 만든다.** 아이디가 붙은 것만 만든다 —
      // 그려 놓고 곧바로 다시 찾아 매는 자리가 그것들이기 때문이다
      // (`getElementById` — 미리보기의 문구 칸 · 복사 단추 · 되돌리기).
      // 안 만들면 그 코드가 검사에서만 `null` 을 받아 죽고, 그러면 그 자리를
      // 아무도 못 본다. 나머지(`<br>` · `<b>` …)까지 흉내 내려면 진짜 파서가
      // 필요하고, 그건 이 파일이 하려는 일이 아니다.
      idTags(html).forEach(function (kid) { el.appendChild(kid); });
    }
  });
  return el;
}

// `innerHTML` 글자에서 **아이디가 붙은 여는 태그**만 골라 요소로 세운다.
// 중첩은 펴서 담는다 — 찾는 쪽이 `getElementById` 라 조상 사슬을 안 본다.
function idTags(html) {
  const out = [];
  const re = /<([a-zA-Z][\w-]*)([^>]*)>/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const attrs = m[2] || "";
    const id = /\bid="([^"]*)"/.exec(attrs);
    if (!id) continue;
    const node = makeEl(m[1]);
    node.setAttribute("id", id[1]);
    const cls = /\bclass="([^"]*)"/.exec(attrs);
    if (cls) cls[1].split(/\s+/).filter(Boolean).forEach(function (c) { node.classList.add(c); });
    // 값이 없는 속성(`hidden`)은 따옴표 안을 걷어낸 뒤에 본다 — 안 그러면
    // `class="… hidden …"` 같은 글자에 걸린다.
    if (/\bhidden\b/.test(attrs.replace(/"[^"]*"/g, ""))) node.hidden = true;
    // 여는 태그 바로 뒤의 글자(`<button …>복사</button>` 의 '복사').
    node.textContent = /^([^<]*)/.exec(html.slice(re.lastIndex))[1];
    out.push(node);
  }
  return out;
}

let documentHandlers = {};

function el(tag, attrs, kids) {
  const node = makeEl(tag);
  Object.keys(attrs || {}).forEach(function (k) {
    if (k === "class") String(attrs[k]).split(/\s+/).filter(Boolean).forEach(function (c) { node.classList.add(c); });
    else {
      node.setAttribute(k, attrs[k]);
      // 브라우저는 `value` 속성을 **칸의 값**으로도 비춰 준다. 여기서 안 비추면
      // 화면 코드가 읽는 `input.value` 가 늘 빈 글자라, 번호를 실어 보내는
      // 자리(`parseInt(c.value)`)가 검사에서만 조용히 `NaN` 이 된다.
      if (k === "value") node.value = String(attrs[k]);
    }
  });
  (kids || []).forEach(function (kid) { node.appendChild(kid); });
  return node;
}


function resetHandlers() { documentHandlers = {}; }

function makeDocument(root) {
  return {
    getElementById(id) { return queryAll(root, "#" + id)[0] || null; },
    querySelector(sel) { return queryAll(root, sel)[0] || null; },
    querySelectorAll(sel) { return queryAll(root, sel); },
    createElement(tag) { return makeEl(tag); },
    addEventListener(type, fn) { (documentHandlers[type] = documentHandlers[type] || []).push(fn); },
    body: root
  };
}

module.exports = { makeEl: makeEl, el: el, queryAll: queryAll,
                   parseCompound: parseCompound, resetHandlers: resetHandlers,
                   makeDocument: makeDocument };
