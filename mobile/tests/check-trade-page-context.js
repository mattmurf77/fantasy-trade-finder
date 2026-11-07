#!/usr/bin/env node
// Synthetic delayed-storage, request identity and transition regressions.
'use strict';
let finished = false;
process.on('exit', () => {
    if (!finished) {
        console.error('trade page context did not finish');
        process.exitCode = 1;
    }
});
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const root = require('path').join(__dirname, '../..');
const ts = require('typescript');
const source = p => fs.readFileSync(root + '/mobile/src/' + p, 'utf8');
function compile(s, imports, extra = {}) {
    const m = {
        exports: {}
    };
    vm.runInNewContext(ts.transpileModule(s, {
        compilerOptions: {
            target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS
        }
    }).outputText, {
        module: m, exports: m.exports, require: n => {
            if (!(n in imports))
                throw Error('unexpected ' + n);
            return imports[n];
        }, Map, Set, Date, Promise, JSON, Math, ...extra
    });
    return m.exports;
}
const P = compile(source('utils/tradePages.ts'), {}), D = compile(source('utils/devicePage.ts'), {
    './tradePages': P
});
const deferred = () => {
    let resolve, reject;
    const promise = new Promise((a, b) => {
        resolve = a;
        reject = b;
    });
    return {
        promise, resolve, reject
    };
}, flush = () => new Promise(r => setImmediate(r));
const key = D.devicePageKey('synthetic-user', 'synthetic-league', '1qb_ppr'), scope = 'organic:f=0.50';
function response(id = 'old') {
    return {
        job_id: id, status: 'complete', current_validated: true, deck_id: id, cursor: 1, cards: [{
                trade_id: id
            }]
    };
}
function env() {
    const e = {
        disk: new Map(), timers: new Map(), timerId: 0, now: 1800000000000, revision: 1, active: 'active', online: true, calls: [], polls: [], handoffs: 0
    };
    e.storage = {
        getAllKeys: async () => [...e.disk.keys()], multiGet: async (ks) => ks.map(k => [k, e.disk.get(k) || null]), setItem: async (k, v) => {
            e.disk.set(k, v);
        }, removeItem: async (k) => {
            e.disk.delete(k);
        }, multiRemove: async (ks) => {
            ks.forEach(k => e.disk.delete(k));
        }
    };
    e.respond = async () => response();
    e.status = async () => response();
    e.runTimers = () => {
        const list = [...e.timers.values()];
        e.timers.clear();
        list.forEach(fn => fn());
    };
    return e;
}
function store(e) {
    return compile(source('state/devicePageStore.ts'), {
        '@react-native-async-storage/async-storage': {
            default: e.storage
        }, 'react-native': {
            AppState: {
                get currentState() {
                    return e.active;
                }
            }
        }, '@tanstack/react-query': {
            onlineManager: {
                isOnline: () => e.online
            }
        }, '../api/client': {
            setOnWriteRequest: fn => {
                e.onWrite = fn;
            }, getSessionRevision: () => e.revision
        }, './tradeSearchHandoff': {
            invalidateTradeSearchHandoffs: () => e.handoffs++
        }, '../api/trades': {
            generateTrades: (...a) => {
                e.calls.push(a);
                return e.respond(...a);
            }, getTradeStatus: (...a) => {
                e.polls.push(a);
                return e.status(...a);
            }
        }, '../utils/devicePage': D
    }, {
        Date: {
            now: () => e.now
        }, setTimeout: fn => {
            const id = ++e.timerId;
            e.timers.set(id, fn);
            return id;
        }, clearTimeout: id => e.timers.delete(id)
    });
}
function page(e, id = 'old') {
    return D.devicePageFrom(response(id), {
        scope, validatedAt: e.now
    });
}
function target() {
    return {
        key, scope, format: '1qb_ppr', request: {
            league_id: 'synthetic-league', fairness_threshold: .5
        }
    };
}
const tests = [];
function test(name, fn) {
    tests.push([name, fn]);
}
test('per-key discard wins delayed hydration and disk', async () => {
    const e = env();
    e.disk.set(key, JSON.stringify(page(e)));
    const read = deferred();
    e.storage.multiGet = () => read.promise;
    const s = store(e);
    const pending = s.hydrateDevicePages();
    await flush();
    s.discardDevicePage(key);
    read.resolve([[key, JSON.stringify(page(e))]]);
    await pending;
    e.runTimers();
    await flush();
    assert.equal(s.readDevicePage(key), null);
    assert.equal(e.disk.has(key), false);
});
test('global mutation removes disk-only page across restart', async () => {
    const e = env();
    e.disk.set(key, JSON.stringify(page(e)));
    const read = deferred();
    e.storage.multiGet = () => read.promise;
    const s = store(e);
    const pending = s.hydrateDevicePages();
    await flush();
    e.onWrite('/api/rank3', 'start');
    read.resolve([[key, JSON.stringify(page(e))]]);
    await pending;
    e.onWrite('/api/rank3', 'settled');
    e.runTimers();
    await flush();
    assert.equal(s.readDevicePage(key), null);
    assert.equal(e.disk.has(key), false, 'disk-only page must not resurrect on next process');
});
test('old dispatched write then clear then same-account new page preserves newest', async () => {
    const e = env(), s = store(e), write = deferred();
    let first = true;
    e.storage.setItem = async (k, v) => {
        if (first) {
            first = false;
            await write.promise;
        }
        e.disk.set(k, v);
    };
    s.saveDevicePage(key, page(e, 'old'));
    e.runTimers();
    await flush();
    const clearing = s.clearDevicePages();
    e.now++;
    s.saveDevicePage(key, page(e, 'new'));
    e.runTimers();
    write.resolve();
    await clearing;
    await flush();
    assert.equal(s.readDevicePage(key).cards[0].trade_id, 'new');
    assert.equal(JSON.parse(e.disk.get(key)).cards[0].trade_id, 'new');
});
test('old token response cannot overwrite new same-key attempt', async () => {
    const e = env(), s = store(e), old = deferred(), fresh = deferred();
    let n = 0;
    e.respond = () => ++n === 1 ? old.promise : fresh.promise;
    const a = s.refreshDevicePage(target(), e.now);
    e.revision++;
    const b = s.refreshDevicePage(target(), e.now + 1);
    assert.equal(e.calls.length, 2);
    fresh.resolve(response('new'));
    await b;
    old.resolve(response('old'));
    await a;
    assert.equal(s.readDevicePage(key).cards[0].trade_id, 'new');
    await s.refreshDevicePage(target(), e.now + 2);
    assert.equal(e.calls.length, 2, 'old finally must not clear new throttle');
});
test('cancelled old token attempt frees own throttle for focus retry', async () => {
    const e = env(), s = store(e), old = deferred();
    e.respond = () => old.promise;
    const pending = s.refreshDevicePage(target(), e.now);
    e.revision++;
    old.resolve(response());
    await pending;
    assert.equal(s.readDevicePage(key), null);
    e.respond = async () => response('new');
    await s.refreshDevicePage(target(), e.now + 1);
    assert.equal(e.calls.length, 2);
    assert.equal(s.readDevicePage(key).cards[0].trade_id, 'new');
});
test('all passive requests including polls bind exact captured format', async () => {
    const e = env(), s = store(e);
    e.respond = async () => ({
        ...response(), status: 'running', cards: []
    });
    const pending = s.refreshDevicePage(target(), e.now);
    await flush();
    e.runTimers();
    await pending;
    assert.equal(e.calls[0][2].headers['X-Scoring-Format'], '1qb_ppr');
    assert.equal(e.polls[0][2].headers['X-Scoring-Format'], '1qb_ppr');
    assert.equal(e.polls[0][2].headers['X-FTF-Prewarm'], '1');
    assert.equal(e.calls[0][2].background, true);
});
test('unsupported format and mismatched scope cannot dispatch', async () => {
    const e = env(), s = store(e);
    await s.refreshDevicePage({
        ...target(), format: 'unknown'
    });
    await s.refreshDevicePage({
        ...target(), scope: 'organic:f=0.75'
    });
    assert.equal(e.calls.length, 0);
});
test('transition extends API settlement and finish is idempotent', async () => {
    const e = env(), s = store(e);
    const finish = s.beginTradePageInputTransition();
    e.onWrite('/api/scoring/switch', 'start');
    e.onWrite('/api/scoring/switch', 'settled');
    await s.refreshDevicePage(target());
    assert.equal(e.calls.length, 0);
    finish();
    finish();
    await s.refreshDevicePage(target());
    assert.equal(e.calls.length, 1);
});
test('overlapping real input writes remain blocked until all settle', async () => {
    const e = env(), s = store(e);
    e.onWrite('/api/rank3', 'start');
    e.onWrite('/api/league/preferences', 'start');
    e.onWrite('/api/rank3', 'settled');
    await s.refreshDevicePage(target());
    assert.equal(e.calls.length, 0);
    e.onWrite('/api/league/preferences', 'settled');
    await s.refreshDevicePage(target());
    assert.equal(e.calls.length, 1);
});
test('request target mutation cannot change response storage scope', async () => {
    const e = env(), s = store(e), d = deferred();
    e.respond = () => d.promise;
    const t = target(), pending = s.refreshDevicePage(t);
    t.key = key + 'other';
    t.scope = 'organic:f=0.75';
    t.format = 'sf_tep';
    t.request.fairness_threshold = .75;
    d.resolve(response());
    await pending;
    assert.equal(s.readDevicePage(key + 'other'), null);
    const held = s.readDevicePage(key);
    assert(held === null || held.scope === scope);
});
(async () => {
    let failed = 0;
    for (const [name, fn] of tests) {
        try {
            await fn();
            console.log('PASS ' + name);
        }
        catch (e) {
            failed++;
            console.log('FAIL ' + name + ': ' + e.message);
        }
    }
    finished = true;
    console.log(JSON.stringify({
        passed: tests.length - failed, failed
    }));
    process.exitCode = failed ? 1 : 0;
})().catch(e => {
    console.error(e);
    process.exitCode = 1;
});
