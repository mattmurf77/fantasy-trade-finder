#!/usr/bin/env node
'use strict';
let finished = false;
process.on('exit', () => {
    if (!finished) {
        console.error('trade preparation regression did not finish');
        process.exitCode = 1;
    }
});
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const root = require('path').join(__dirname, '../..');
const ts = require('typescript');
const compile = (src, imports = {}, extra = {}) => {
    const m = {
        exports: {}
    };
    vm.runInNewContext(ts.transpileModule(src, {
        compilerOptions: {
            target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS
        }
    }).outputText, {
        module: m, exports: m.exports, require: n => {
            if (!(n in imports))
                throw Error(n);
            return imports[n];
        }, Date, Promise, ...extra
    });
    return m.exports;
};
const deferred = () => {
    let resolve;
    const promise = new Promise(r => resolve = r);
    return {
        promise, resolve
    };
}, flush = () => new Promise(r => setImmediate(r));
const key = 'u:L:1qb_ppr', target = {
    key, format: '1qb_ppr', scope: 'organic:f=0.50', request: {
        league_id: 'L', fairness_threshold: .5
    }
};
function setup() {
    const disk = deferred(), ready = deferred(), pref = deferred(), calls = [];
    const e = {
        disk, ready, pref, calls, revision: 1, active: 'active', flag: true, continues: true, state: {
            user: {
                user_id: 'u'
            }, league: {
                league_id: 'L'
            }, activeFormat: '1qb_ppr', hasToken: true, switching: false, isDemo: false
        }
    };
    e.state.revalidateSession = () => {
        calls.push('ready');
        return ready.promise;
    };
    e.prepare = compile(fs.readFileSync(root + '/mobile/src/state/tradePagePreparation.ts', 'utf8'), {
        'react-native': {
            AppState: {
                get currentState() {
                    return e.active;
                }
            }
        }, '../api/client': {
            getSessionRevision: () => e.revision
        }, './devicePageStore': {
            hydrateDevicePages: () => {
                calls.push('disk');
                return disk.promise;
            }, refreshDevicePage: async (t, now, g) => {
                calls.push('refresh');
                e.guard = g;
            }
        }, './useSession': {
            useSession: {
                getState: () => e.state
            }
        }, './useFeatureFlags': {
            useFeatureFlags: {
                getState: () => ({
                    flags: {
                        'trade.first_page_store': e.flag
                    }
                })
            }
        }, '../utils/devicePage': {
            devicePageKey: (u, l, f) => [u, l, f].join(':')
        }
    }).prepareTradePage;
    return e;
}
let passed = 0;
const ok = name => {
    passed++;
    console.log('PASS ' + name);
};
(async () => {
    let e = setup();
    let pending = e.prepare(key, () => {
        e.calls.push('pref');
        return e.pref.promise;
    }, () => e.continues);
    assert.deepEqual(e.calls, ['disk', 'pref', 'ready']);
    e.revision = 2;
    e.ready.resolve();
    e.pref.resolve(target);
    await pending;
    assert.equal(e.calls.at(-1), 'refresh');
    assert(e.guard());
    e.revision = 3;
    assert(!e.guard());
    ok('parallel readiness/preferences, no disk barrier, post-readiness token binding');
    for (const change of ['account', 'league', 'format', 'token_missing', 'switching', 'demo', 'flag', 'inactive', 'cleanup']) {
        e = setup();
        pending = e.prepare(key, () => e.pref.promise, () => e.continues);
        if (change === 'account')
            e.state.user = {
                user_id: 'other'
            };
        if (change === 'league')
            e.state.league = {
                league_id: 'other'
            };
        if (change === 'format')
            e.state.activeFormat = 'sf_tep';
        if (change === 'token_missing')
            e.state.hasToken = false;
        if (change === 'switching')
            e.state.switching = true;
        if (change === 'demo')
            e.state.isDemo = true;
        if (change === 'flag')
            e.flag = false;
        if (change === 'inactive')
            e.active = 'background';
        if (change === 'cleanup')
            e.continues = false;
        e.ready.resolve();
        e.pref.resolve(target);
        await pending;
        assert(!e.calls.includes('refresh'));
        ok('pending preparation refuses ' + change);
    }
    e = setup();
    e.ready.resolve();
    e.pref.resolve({
        ...target, format: 'sf_tep'
    });
    await e.prepare(key, () => e.pref.promise, () => true);
    assert(!e.calls.includes('refresh'));
    ok('wrong target format refused');
    const src = fs.readFileSync(root + '/mobile/src/screens/TradesScreen.tsx', 'utf8'), ast = ts.createSourceFile('Trades.tsx', src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX), bodies = [];
    function visit(n) {
        if (ts.isCallExpression(n) && n.expression.getText(ast) === 'useEffect' && n.arguments[0] && ts.isArrowFunction(n.arguments[0])) {
            const b = n.arguments[0].body.getText(ast);
            if (b.includes('prepareTradePage(devicePageTarget.key'))
                bodies.push(b);
        }
        ts.forEachChild(n, visit);
    }
    visit(ast);
    assert.equal(bodies.length, 2);
    const effect = b => compile('module.exports=(env)=>{const {isResultsPushed,navFocused,devicePageTarget,prepareTradePage,AppState}=env;' + b + '}');
    const focus = effect(bodies.find(b => b.includes('navFocused')));
    let calls = [];
    let cleanup = focus({
        isResultsPushed: false, navFocused: true, devicePageTarget: target, prepareTradePage: (k, load, g) => calls.push({
            k, load, g
        })
    });
    assert.equal(calls.length, 1);
    assert(calls[0].g());
    cleanup();
    assert(!calls[0].g());
    ok('actual focus effect cleanup revokes old preparation');
    const fg = effect(bodies.find(b => b.includes('addEventListener')));
    let callback, removed = false;
    calls = [];
    cleanup = fg({
        isResultsPushed: false, devicePageTarget: target, prepareTradePage: (k, load, g) => calls.push({
            g
        }), AppState: {
            addEventListener: (name, cb) => {
                callback = cb;
                return {
                    remove: () => removed = true
                };
            }
        }
    });
    callback('active');
    assert(calls[0].g());
    callback('inactive');
    assert(!calls[0].g());
    callback('active');
    assert(calls[1].g());
    assert(!calls[0].g());
    cleanup();
    assert(!calls[1].g() && removed);
    ok('actual foreground effect fences reactivation and cleanup');
    finished = true;
    console.log(JSON.stringify({
        passed, failed: 0
    }));
})().catch(e => {
    console.error(e);
    process.exitCode = 1;
});
