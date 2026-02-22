// NanoAnalytics beacon — https://github.com/callmefredcom/NanoAnalytics
// Intentionally kept small (< 400 bytes). No cookies. No external calls.
// Session ID lives in sessionStorage only — no GDPR banner needed.
(() => {
  const s = sessionStorage.ab
    || (sessionStorage.ab = Math.random().toString(36).slice(2, 10));

  const origin = new URL(document.currentScript.src).origin;

  function send(path) {
    fetch(
      `${origin}/hit` +
      `?site=${location.hostname}` +
      `&path=${encodeURIComponent(path)}` +
      `&ref=${encodeURIComponent(document.referrer)}` +
      `&lang=${navigator.language}` +
      `&w=${screen.width}` +
      `&s=${s}`,
      { method: 'GET', keepalive: true }
    );
  }

  send(location.pathname);

  // SPA support: intercept history.pushState for client-side navigation
  const _push = history.pushState.bind(history);
  history.pushState = function(state, title, url) {
    _push(state, title, url);
    if (url) send(new URL(url, location.href).pathname);
  };
  window.addEventListener('popstate', () => send(location.pathname));
})();
