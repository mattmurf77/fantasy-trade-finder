'use strict';
// Compare React Native 0.81.5's regex URL polyfill (Libraries/Blob/URL.js)
// against the WHATWG parser (node's built-in, ~= what native iOS resolves)
// for the checks the device transport's host allowlist performs.

// --- RN 0.81.5 getters, copied verbatim from the polyfill ---
const rn = {
  hostname: (u) => { const m = u.match(/^https?:\/\/(?:[^@]+@)?([^:/?#]+)/); return m ? m[1] : ''; },
  protocol: (u) => { const m = u.match(/^([a-zA-Z][a-zA-Z\d+\-.]*):/); return m ? m[1] + ':' : ''; },
  username: (u) => { const m = u.match(/^https?:\/\/([^:@]+)(?::[^@]*)?@/); return m ? m[1] : ''; },
  port:     (u) => { const m = u.match(/:(\d+)(?=[/?#]|$)/); return m ? m[1] : ''; },
};

const ALLOWED = new Set(['sleeper.com']);

// The allowlist decision, written the way LLD §4.3 step 3 specifies.
function decide(get, url) {
  try {
    const host = get.hostname(url).toLowerCase();
    const proto = get.protocol(url);
    const user = get.username(url);
    const port = get.port(url);
    if (proto !== 'https:') return 'refuse:proto';
    if (user) return 'refuse:userinfo';
    if (port && port !== '443') return 'refuse:port';
    return ALLOWED.has(host) ? 'ALLOW(' + host + ')' : 'refuse:host(' + host + ')';
  } catch (e) { return 'THROW:' + e.constructor.name; }
}

const whatwg = {
  hostname: (u) => new URL(u).hostname,
  protocol: (u) => new URL(u).protocol,
  username: (u) => new URL(u).username,
  port:     (u) => new URL(u).port,
};

const cases = [
  ['the real URL',                 'https://sleeper.com/graphql'],
  ['userinfo smuggle',             'https://sleeper.com@evil.tld/graphql'],
  ['double userinfo',              'https://a@b@sleeper.com/graphql'],
  ['backslash (WHATWG: /)',        'https://sleeper.com\\@evil.tld/graphql'],
  ['fragment before @',            'https://sleeper.com#@evil.tld/'],
  ['tab inside host',              'https://sleep\ter.com/graphql'],
  ['CR/LF inside host',            'https://sleeper.com\r\n.evil.tld/'],
  ['uppercase host',               'https://SLEEPER.COM/graphql'],
  ['trailing dot FQDN',            'https://sleeper.com./graphql'],
  ['explicit :443',                'https://sleeper.com:443/graphql'],
  ['port 8443',                    'https://sleeper.com:8443/graphql'],
  ['colon-at in path',             'https://sleeper.com/a:b@c'],
  ['http not https',               'http://sleeper.com/graphql'],
  ['garbage',                      'not-a-url-at-all'],
  ['scheme-relative',              '//sleeper.com/graphql'],
  ['unicode lookalike',            'https://sleeper.coх/graphql'],
];

let bypass = 0, falseRefuse = 0;
console.log('case                       | RN polyfill              | WHATWG                   | verdict');
console.log('-'.repeat(104));
for (const [name, url] of cases) {
  const r = decide(rn, url);
  let w; try { w = decide(whatwg, url); } catch (e) { w = 'THROW:' + e.constructor.name; }
  let verdict = 'agree';
  if (r !== w) {
    const rAllow = r.startsWith('ALLOW'), wAllow = w.startsWith('ALLOW');
    if (rAllow && !wAllow) { verdict = '*** BYPASS RISK ***'; bypass++; }
    else if (!rAllow && wAllow) { verdict = 'false refusal (M4 page)'; falseRefuse++; }
    else verdict = 'differ (both refuse)';
  }
  console.log(name.padEnd(26) + ' | ' + r.padEnd(24) + ' | ' + w.padEnd(24) + ' | ' + verdict);
}
console.log('\nBYPASS RISK cases: ' + bypass + '   |   false refusals: ' + falseRefuse);
