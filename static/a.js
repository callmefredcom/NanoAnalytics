// NanoAnalytics beacon — https://github.com/callmefredcom/NanoAnalytics
// Intentionally kept small (< 400 bytes). No cookies. No external calls.
// Session ID lives in sessionStorage only — no GDPR banner needed.
(() => {
  const s = sessionStorage.ab
    || (sessionStorage.ab = Math.random().toString(36).slice(2, 10));

  fetch(
    `${new URL(document.currentScript.src).origin}/hit` +
    `?site=${location.hostname}` +
    `&path=${encodeURIComponent(location.pathname)}` +
    `&ref=${encodeURIComponent(document.referrer)}` +
    `&lang=${navigator.language}` +
    `&w=${screen.width}` +
    `&s=${s}`,
    { method: 'GET', keepalive: true }
  );
})();
