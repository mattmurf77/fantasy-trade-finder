// Respond only to an explicit extension verification request, in the top-level
// Sleeper document. No page messages, polling, storage enumeration or logging.
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message?.type !== 'ftf:capture_sleeper_proof' || sender.id !== chrome.runtime.id ||
      window.top !== window || !['https://sleeper.com', 'https://sleeper.app'].includes(location.origin)) return false;
  let token = null;
  try {
    const value = localStorage.getItem('token');
    if (value && value.length <= 16384 && value.split('.').length === 3) token = value;
  } catch { /* Storage is unavailable until the page permits access. */ }
  respond({ token });
  return false;
});
