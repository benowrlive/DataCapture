/* DataCapture client-side helpers: live branching logic on entry/survey forms. */
(function () {
  "use strict";

  // ---------- theme toggle ----------
  var THEME_KEY = "datacapture-theme";
  var THEMES = ["light", "dark", "glass"];
  var THEME_META = { light: "#2563eb", dark: "#0b1120", glass: "#dfe7ff" };
  var THEME_LABEL = { light: "Light", dark: "Dark", glass: "Glass" };
  function getPreferredTheme() {
    var saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) { saved = null; }
    if (THEMES.indexOf(saved) >= 0) return saved;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }
  function applyTheme(theme, persist) {
    if (THEMES.indexOf(theme) < 0) theme = "light";
    document.documentElement.dataset.theme = theme;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", THEME_META[theme]);
    try { if (persist) localStorage.setItem(THEME_KEY, theme); } catch (e) { return; }
    Array.prototype.forEach.call(document.querySelectorAll("[data-theme-toggle]"), function (btn) {
      var label = btn.querySelector("[data-theme-label]");
      if (label) label.textContent = THEME_LABEL[theme];
      btn.setAttribute("title", "Theme: " + THEME_LABEL[theme] + " (click to change)");
    });
  }
  function initThemeControls() {
    applyTheme(document.documentElement.dataset.theme || getPreferredTheme(), false);
    Array.prototype.forEach.call(document.querySelectorAll("[data-theme-toggle]"), function (btn) {
      btn.addEventListener("click", function () {
        var cur = THEMES.indexOf(document.documentElement.dataset.theme);
        applyTheme(THEMES[(cur + 1) % THEMES.length], true);
      });
    });
  }

  // ---------- branching logic evaluator (mirrors validators.py) ----------
  var TOKEN_RE = /\s*(\[[a-z0-9_]+(?:\(\d+\))?\]|<>|>=|<=|=|>|<|\(|\)|and\b|or\b|'[^']*'|"[^"]*"|-?\d+(?:\.\d+)?)/iy;

  function tokenize(logic) {
    var tokens = [], pos = 0;
    while (pos < logic.length) {
      TOKEN_RE.lastIndex = pos;
      var m = TOKEN_RE.exec(logic);
      if (!m) {
        if (logic.slice(pos).trim() === "") break;
        throw new Error("bad token");
      }
      tokens.push(m[1]);
      pos = TOKEN_RE.lastIndex;
    }
    return tokens;
  }

  function evalLogic(logic, values) {
    logic = (logic || "").trim();
    if (!logic) return true;
    try {
      var t = tokenize(logic);
      var r = parseOr(t, values);
      if (r.rest.length) throw new Error("trailing");
      return r.val;
    } catch (e) { return true; }
  }

  function parseOr(tokens, values) {
    var r = parseAnd(tokens, values);
    while (r.rest.length && r.rest[0].toLowerCase() === "or") {
      var right = parseAnd(r.rest.slice(1), values);
      r = { val: r.val || right.val, rest: right.rest };
    }
    return r;
  }
  function parseAnd(tokens, values) {
    var r = parseCmp(tokens, values);
    while (r.rest.length && r.rest[0].toLowerCase() === "and") {
      var right = parseCmp(r.rest.slice(1), values);
      r = { val: r.val && right.val, rest: right.rest };
    }
    return r;
  }
  function parseCmp(tokens, values) {
    if (!tokens.length) throw new Error("eof");
    if (tokens[0] === "(") {
      var inner = parseOr(tokens.slice(1), values);
      if (!inner.rest.length || inner.rest[0] !== ")") throw new Error(")");
      return { val: inner.val, rest: inner.rest.slice(1) };
    }
    var l = operand(tokens, values);
    if (!l.rest.length) throw new Error("op");
    var op = l.rest[0];
    var r = operand(l.rest.slice(1), values);
    return { val: compare(l.val, op, r.val), rest: r.rest };
  }
  function operand(tokens, values) {
    if (!tokens.length) throw new Error("operand");
    var tok = tokens[0];
    if (tok[0] === "[") {
      var inner = tok.slice(1, -1);
      var m = inner.match(/^([a-z0-9_]+)\((\d+)\)$/);
      if (m) {
        var raw = values[m[1]] || "";
        var checked = raw.split(",").map(function (s) { return s.trim(); })
          .indexOf(m[2]) >= 0;
        return { val: checked ? "1" : "0", rest: tokens.slice(1) };
      }
      return { val: values[inner] || "", rest: tokens.slice(1) };
    }
    if (tok[0] === "'" || tok[0] === '"')
      return { val: tok.slice(1, -1), rest: tokens.slice(1) };
    return { val: tok, rest: tokens.slice(1) };
  }
  function compare(l, op, r) {
    var ln = parseFloat(l), rn = parseFloat(r);
    var numeric = !isNaN(ln) && !isNaN(rn) && String(ln) !== "NaN";
    if (numeric && l !== "" && r !== "") { l = ln; r = rn; }
    switch (op) {
      case "=": return l == r;          // eslint-disable-line eqeqeq
      case "<>": return l != r;          // eslint-disable-line eqeqeq
      case ">": return l > r;
      case ">=": return l >= r;
      case "<": return l < r;
      case "<=": return l <= r;
    }
    return true;
  }

  // ---------------- wire up entry / survey forms ----------------
  function collectValues(form) {
    var values = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.name.indexOf("f_") !== 0) return;
      var name = el.name.slice(2);
      if (el.type === "checkbox") {
        if (!(name in values)) values[name] = "";
        if (el.checked) values[name] = values[name] ? values[name] + "," + el.value : el.value;
      } else if (el.type === "radio") {
        if (el.checked) values[name] = el.value;
        else if (!(name in values)) values[name] = values[name] || "";
      } else {
        values[name] = el.value;
      }
    });
    return values;
  }

  function applyBranching(form, logicMap) {
    var values = collectValues(form);
    Object.keys(logicMap).forEach(function (fname) {
      var block = form.querySelector('[data-field="' + fname + '"]');
      if (!block) return;
      var show = evalLogic(logicMap[fname], values);
      block.classList.toggle("hidden-by-logic", !show);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initThemeControls();
    var form = document.getElementById("entry-form");
    if (!form) return;
    var el = document.getElementById("branching-data");
    var logicMap = el ? JSON.parse(el.textContent || "{}") : {};
    if (Object.keys(logicMap).length) {
      applyBranching(form, logicMap);
      form.addEventListener("input", function () { applyBranching(form, logicMap); });
      form.addEventListener("change", function () { applyBranching(form, logicMap); });
    }
  });

  // choice-type helper on the designer page
  document.addEventListener("DOMContentLoaded", function () {
    var sel = document.getElementById("field_type_select");
    if (!sel) return;
    function toggle() {
      var t = sel.value;
      var choiceRow = document.getElementById("choices_row");
      var valRow = document.getElementById("validation_row");
      if (choiceRow)
        choiceRow.style.display =
          (t === "dropdown" || t === "radio" || t === "checkbox") ? "" : "none";
      if (valRow)
        valRow.style.display = (t === "text") ? "" : "none";
    }
    sel.addEventListener("change", toggle);
    toggle();
  });
})();
