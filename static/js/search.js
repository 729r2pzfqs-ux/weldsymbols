/* weldsymbols.org — client-side search over a prebuilt index.
   No dependencies. The index is fetched once, on first interaction. */
(function () {
  "use strict";

  var boxes = document.querySelectorAll("[data-search]");
  if (!boxes.length) return;

  var index = null;
  var loading = null;

  function load(base) {
    if (index) return Promise.resolve(index);
    if (loading) return loading;
    loading = fetch(base + "search-index.json")
      .then(function (r) { return r.json(); })
      .then(function (d) { index = d; return d; })
      .catch(function () { index = []; return index; });
    return loading;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function highlight(text, q) {
    var i = text.toLowerCase().indexOf(q);
    if (i < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, i)) + "<mark>" +
           escapeHtml(text.slice(i, i + q.length)) + "</mark>" +
           escapeHtml(text.slice(i + q.length));
  }

  /* Rank: exact title, title prefix, title substring, keyword hit, description hit. */
  function score(item, q) {
    var t = item.t.toLowerCase();
    if (t === q) return 0;
    if (t.indexOf(q) === 0) return 1;
    if (t.indexOf(q) > -1) return 2;
    if (item.k && item.k.indexOf(q) > -1) return 3;
    if (item.d && item.d.toLowerCase().indexOf(q) > -1) return 4;
    return -1;
  }

  function search(q) {
    q = q.trim().toLowerCase();
    if (q.length < 2) return [];
    var hits = [];
    for (var i = 0; i < index.length; i++) {
      var s = score(index[i], q);
      if (s >= 0) hits.push([s, i, index[i]]);
    }
    hits.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
    return hits.slice(0, 12).map(function (h) { return h[2]; });
  }

  boxes.forEach(function (box) {
    var input = box.querySelector("input");
    var out = box.querySelector("[data-results]");
    var base = box.getAttribute("data-base") || "/";
    var items = [];
    var sel = -1;

    function render(q) {
      if (!items.length) {
        out.innerHTML = q.length >= 2
          ? '<p class="r-none">No matches for “' + escapeHtml(q) + '”</p>' : "";
        out.hidden = !q.length || q.length < 2;
        return;
      }
      out.innerHTML = items.map(function (it, i) {
        return '<a href="' + base + it.u + '" data-i="' + i + '">' +
               '<span class="r-t">' + highlight(it.t, q.toLowerCase()) + "</span>" +
               '<span class="r-k">' + escapeHtml(it.c) + "</span>" +
               '<span class="r-d">' + escapeHtml(it.d) + "</span></a>";
      }).join("");
      out.hidden = false;
    }

    function update() {
      var q = input.value;
      if (q.trim().length < 2) { items = []; sel = -1; render(q); return; }
      load(base).then(function () {
        items = search(q);
        sel = -1;
        render(q);
      });
    }

    function move(d) {
      var links = out.querySelectorAll("a");
      if (!links.length) return;
      if (sel > -1) links[sel].classList.remove("sel");
      sel = (sel + d + links.length) % links.length;
      links[sel].classList.add("sel");
      links[sel].scrollIntoView({ block: "nearest" });
    }

    input.addEventListener("input", update);
    input.addEventListener("focus", function () {
      box.classList.add("has-focus");
      load(base);
      if (input.value.trim().length >= 2) update();
    });
    input.addEventListener("blur", function () {
      if (!input.value) box.classList.remove("has-focus");
      setTimeout(function () { out.hidden = true; }, 160);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") {
        var links = out.querySelectorAll("a");
        if (sel > -1 && links[sel]) { e.preventDefault(); window.location = links[sel].href; }
        else if (links.length) { e.preventDefault(); window.location = links[0].href; }
      } else if (e.key === "Escape") { input.blur(); out.hidden = true; }
    });
  });

  /* "/" focuses the first search box, the way most reference sites behave. */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
    var tag = (document.activeElement.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") return;
    var first = document.querySelector("[data-search] input");
    if (first) { e.preventDefault(); first.focus(); }
  });

  /* Mobile nav */
  var toggle = document.querySelector(".nav-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var nav = document.getElementById("nav");
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
})();
