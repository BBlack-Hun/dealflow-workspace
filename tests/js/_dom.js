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
    value: "", textContent: "", innerHTML: "",
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
    addEventListener(type, fn) { (el.handlers[type] = el.handlers[type] || []).push(fn); },
    querySelector(sel) { return queryAll(el, sel)[0] || null; },
    querySelectorAll(sel) { return queryAll(el, sel); },
    closest(sel) {
      const c = parseCompound(sel.trim());
      let node = el;
      while (node) { if (matchesCompound(node, c)) return node; node = node.parent; }
      return null;
    },
    get childNodes() { return el.children; },
    // 이벤트는 버블링까지 흉내 낸다 — 칩은 줄(`#group-filter`)이 대신 듣는다.
    fire(type, extra) {
      const ev = Object.assign({ target: el, stopPropagation() {}, preventDefault() {} }, extra || {});
      let node = el;
      while (node) {
        (node.handlers[type] || []).forEach(function (fn) { fn(ev); });
        node = node.parent;
      }
      (documentHandlers[type] || []).forEach(function (fn) { fn(ev); });
    }
  };
  return el;
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
