// First-party bridge: only a real click/Enter on the visible sign-in control
// permits one proof request. The Sleeper credential never crosses this bridge.
(() => {
  const origins = ['https://fantasy-trade-finder.onrender.com'];
  if (window.top !== window || !origins.includes(location.origin)) return;
  let allowedUntil = 0;
  document.addEventListener('click', event => {
    if (event.isTrusted && event.target.closest?.('#auth-btn')) allowedUntil = Date.now() + 1500;
  }, true);
  document.addEventListener('keydown', event => {
    if (event.isTrusted && event.key === 'Enter' && event.target.id === 'username-input') allowedUntil = Date.now() + 1500;
  }, true);
  window.addEventListener('message', event => {
    const request = event.data;
    if (event.source !== window || event.origin !== location.origin ||
        request?.type !== 'ftf:web_verify' || typeof request.requestId !== 'string' ||
        request.requestId.length > 100 || Date.now() > allowedUntil || !document.hasFocus()) return;
    allowedUntil = 0;
    window.postMessage({ type: 'ftf:web_verifying', requestId: request.requestId }, location.origin);
    chrome.runtime.sendMessage({ type: 'ftf:verify_sleeper', username: request.username }, response => {
      const result = chrome.runtime.lastError ? { ok: false, error: 'extension_unavailable' } : response;
      window.postMessage({ type: 'ftf:web_verified', requestId: request.requestId, result }, location.origin);
    });
  });
})();
