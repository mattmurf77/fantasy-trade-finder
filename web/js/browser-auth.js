// Browser verification requires the installed Fleeced extension and an
// explicit sign-in action. The page receives only a verified FTF session.
(() => {
  const messages = {
    extension_unavailable: 'Install or reload the Fleeced browser extension, then refresh this page and try again.',
    sleeper_tab_required: 'Open sleeper.com in another tab and sign in, then try again.',
    sleeper_login_required: 'Sign in to Sleeper and refresh that tab, then try again.',
    token_user_mismatch: 'Your open Sleeper account does not match this username. Switch accounts in Sleeper and try again.',
    token_rejected: 'Sign in to Sleeper again, then retry verification.',
    token_expired: 'Sign in to Sleeper again, then retry verification.',
    verification_unavailable: 'Sleeper verification is temporarily unavailable. Please try again.',
    verification_busy: 'Another verification is in progress. Please try again.',
  };
  let pending = false;
  window.FTFBrowserAuth = {
    verify(username) {
      if (pending) return Promise.reject(new Error(messages.verification_busy));
      pending = true;
      return new Promise((resolve, reject) => {
        const requestId = crypto.randomUUID();
        let timer;
        function finish(error, session) {
          clearTimeout(timer);
          window.removeEventListener('message', receive);
          pending = false;
          if (error) reject(new Error(messages[error] || 'Could not verify your account. Please sign in to Sleeper and try again.'));
          else resolve(session);
        }
        function receive(event) {
          if (event.source !== window || event.origin !== location.origin || event.data?.requestId !== requestId) return;
          if (event.data.type === 'ftf:web_verifying') {
            clearTimeout(timer);
            timer = setTimeout(() => finish('verification_unavailable'), 60000);
            return;
          }
          if (event.data.type !== 'ftf:web_verified') return;
          const result = event.data.result;
          if (!result?.ok || result.session?.verified !== true || !result.session.token || !result.session.user_id) {
            finish(result?.error || 'verification_incomplete');
            return;
          }
          finish(null, result.session);
        }
        window.addEventListener('message', receive);
        timer = setTimeout(() => finish('extension_unavailable'), 2000);
        window.postMessage({ type: 'ftf:web_verify', requestId, username }, location.origin);
      });
    },
  };
})();
