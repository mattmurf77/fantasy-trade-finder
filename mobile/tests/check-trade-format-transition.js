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
function load() {
    const calls = [], http = deferred(), disk = deferred();
    let pending = 0;
    const state = {
        formatExplicit: false, activeFormat: '1qb_ppr', setActiveFormat: (f, o) => {
            calls.push('local:' + f);
            state.activeFormat = f;
            state.formatExplicit = o.explicit;
        }
    };
    const imports = {
        'react': {}, '@tanstack/react-query': {}, '../state/useSession': {
            useSession: {
                getState: () => state
            }
        }, '../state/devicePageStore': {
            beginTradePageInputTransition: () => {
                pending++;
                calls.push('begin');
                return () => {
                    pending--;
                    calls.push('finish');
                };
            }
        }, '../api/rankings': {
            switchScoringFormat: async (f) => {
                calls.push('post:' + f);
                await http.promise;
            }, setActiveScoringFormat: async (f) => {
                calls.push('disk:' + f);
                await disk.promise;
            }
        }, '../api/league': {}
    };
    const m = {
        exports: {}
    };
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(root + '/mobile/src/hooks/useScoringFormat.ts', 'utf8') + '\nexport { applyFormat as __reviewApply };', {
        compilerOptions: {
            target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS
        }
    }).outputText, {
        module: m, exports: m.exports, require: n => {
            if (!(n in imports))
                throw Error(n);
            return imports[n];
        }, Promise
    });
    return {
        calls, http, disk, state, get pending() {
            return pending;
        }, apply: () => m.exports.__reviewApply({
            invalidateQueries: () => calls.push('query')
        }, 'sf_tep', true)
    };
}
(async () => {
    let e = load(), p = e.apply();
    await flush();
    assert.equal(e.pending, 1);
    e.http.resolve();
    await flush();
    assert.equal(e.pending, 1);
    assert.equal(e.state.activeFormat, '1qb_ppr');
    e.disk.resolve();
    await p;
    assert.equal(e.pending, 0);
    assert.equal(e.state.activeFormat, 'sf_tep');
    assert.equal(e.calls.at(-1), 'finish');
    console.log('PASS transition covers delayed local format mirror');
    e = load();
    p = e.apply();
    const handled = p.catch(x => x);
    await flush();
    e.http.reject(new Error('ambiguous switch'));
    await handled;
    assert.equal(e.pending, 0);
    assert.equal(e.state.activeFormat, '1qb_ppr');
    assert(!e.calls.some(x => x.startsWith('disk:')));
    console.log('PASS rejected server switch releases fence without local adoption');
    e = load();
    p = e.apply();
    const handled2 = p.catch(x => x);
    await flush();
    e.http.resolve();
    await flush();
    e.disk.reject(new Error('mirror error'));
    await handled2;
    assert.equal(e.pending, 0);
    assert.equal(e.state.activeFormat, '1qb_ppr');
    console.log('PASS mirror failure releases fence without state adoption');
    finished = true;
    console.log(JSON.stringify({
        passed: 3, failed: 0
    }));
})().catch(e => {
    console.error(e);
    process.exitCode = 1;
});
