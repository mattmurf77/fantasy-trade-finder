// inject.js — Maestro runScript helper that drives the backend's test-support
// injection endpoints (backend/test_support.py) from inside a capture flow.
//
// Usage from a flow (paths are relative to the flow file):
//
//   - runScript:
//       file: helpers/inject.js
//       env:
//         INJECT_KIND: fail_next        # fail_next | latency | reset
//         INJECT_PATH: "/api/trades/generate"
//         INJECT_STATUS: "503"
//         INJECT_COUNT: "1"
//         INJECT_MS: "2500"             # latency only
//         API: "http://localhost:5001"  # optional; this is the default
//
// After the step, `output.inject` carries {kind, url, ok, status, body} so the
// flow can assert the injection actually armed:
//
//   - assertTrue: ${output.inject.ok}
//
// WARNING: INJECT_KIND=reset also clears the backend's in-memory sessions
// (test_support.reset), i.e. it signs the app out. Never use it mid-flow after
// sign-in — sim-run.sh already resets once at the end of the cell.

// Maestro exposes `env:` entries as GraalJS globals. Reading an undefined
// global throws, so probe with typeof and fall back to process.env if this
// ever runs under a different JS host.
var _procEnv = (typeof process !== 'undefined' && process && process.env) ? process.env : {};

function param(name, dflt) {
  var v;
  try {
    // eslint-disable-next-line no-eval
    v = eval('typeof ' + name + " !== 'undefined' ? " + name + ' : undefined');
  } catch (e) {
    v = undefined;
  }
  if (v === undefined || v === null || v === '') v = _procEnv[name];
  if (v === undefined || v === null || v === '') return dflt;
  return String(v);
}

var API = param('API', 'http://localhost:5001');
var KIND = param('INJECT_KIND', 'reset');
var PATH = param('INJECT_PATH', '');
var STATUS = parseInt(param('INJECT_STATUS', '503'), 10);
var COUNT = parseInt(param('INJECT_COUNT', '1'), 10);
var MS = parseInt(param('INJECT_MS', '2000'), 10);
// Fidelity: pass the REAL endpoint's error body (JSON string) so screens that
// render err.message show production copy, not the harness default.
var BODY = param('INJECT_BODY', '');

var url = API + '/__test__/reset';
var payload = {};

if (KIND === 'fail_next') {
  url = API + '/__test__/fail_next';
  payload = { path: PATH, status: STATUS, count: COUNT };
  if (BODY) {
    try { payload.body = JSON.parse(BODY); } catch (e) { payload.body = BODY; }
  }
} else if (KIND === 'latency') {
  url = API + '/__test__/latency';
  payload = { path: PATH, ms: MS };
}

var res;
var err = null;
try {
  res = http.post(url, {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
} catch (e) {
  err = String(e);
  res = null;
}

output.inject = {
  kind: KIND,
  url: url,
  payload: payload,
  ok: !!(res && res.ok),
  status: res ? res.status : 0,
  body: res ? res.body : '',
  error: err,
};
