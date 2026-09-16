// Loaded synchronously in <head> so the saved theme is applied before first
// paint. It lives in a file rather than an inline <script> because the page's
// Content-Security-Policy forbids inline script.
(function () {
  try {
    var saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  } catch (_) { /* storage blocked: follow the system setting */ }
})();
