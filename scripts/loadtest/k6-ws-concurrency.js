import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const TARGET = Number(__ENV.TARGET || 100);
const HOLD_SECONDS = Number(__ENV.HOLD_SECONDS || 45);
const RAMP_SECONDS = Number(__ENV.RAMP_SECONDS || 30);
const STEADY_SECONDS = Number(__ENV.STEADY_SECONDS || 120);
const RAMP_DOWN_SECONDS = Number(__ENV.RAMP_DOWN_SECONDS || 20);
const FAIL_SLEEP_SECONDS = Number(__ENV.FAIL_SLEEP_SECONDS || 1);
const BASE_URL = String(__ENV.BASE_URL || 'http://127.0.0.1:8000').trim().replace(/\/+$/, '');
const WS_PATH_RAW = String(__ENV.WS_PATH || '/ws/global-announcement/').trim();
const WS_PATH = WS_PATH_RAW.startsWith('/') ? WS_PATH_RAW : `/${WS_PATH_RAW}`;
const COOKIE = String(__ENV.COOKIE || '').trim();
const DEBUG_WS = String(__ENV.DEBUG_WS || '').trim().toLowerCase() === '1' || String(__ENV.DEBUG_WS || '').trim().toLowerCase() === 'true';
const DEBUG_SAMPLE_MAX = Number(__ENV.DEBUG_SAMPLE_MAX || 5);

const wsConnectSuccess = new Rate('ws_connect_success');
const wsConnectFailures = new Counter('ws_connect_failures');
const wsHandshakeMs = new Trend('ws_handshake_ms');
const wsDebugLogged = new Counter('ws_debug_logged');

function toWsBase(url) {
  if (url.startsWith('wss://') || url.startsWith('ws://')) return url;
  if (url.startsWith('https://')) return `wss://${url.slice(8)}`;
  if (url.startsWith('http://')) return `ws://${url.slice(7)}`;
  return `ws://${url}`;
}

const WS_URL = `${toWsBase(BASE_URL)}${WS_PATH}`;

export const options = {
  scenarios: {
    ws_concurrency: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: `${RAMP_SECONDS}s`, target: TARGET },
        { duration: `${STEADY_SECONDS}s`, target: TARGET },
        { duration: `${RAMP_DOWN_SECONDS}s`, target: 0 },
      ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    checks: ['rate>0.99'],
    ws_connect_success: ['rate>0.99'],
    ws_handshake_ms: ['p(95)<1500'],
  },
};

export default function () {
  const startedAt = Date.now();
  let lastSocketError = '';
  const params = {
    headers: {},
    tags: { endpoint: WS_PATH },
  };

  if (COOKIE) {
    params.headers.Cookie = COOKIE;
  }

  const res = ws.connect(WS_URL, params, function (socket) {
    socket.on('open', () => {
      wsConnectSuccess.add(true);
      wsHandshakeMs.add(Date.now() - startedAt);
      socket.setInterval(() => {
        try {
          socket.ping();
        } catch (_) {
          // keep test loop resilient
        }
      }, 15000);
      socket.setTimeout(() => socket.close(), HOLD_SECONDS * 1000);
    });

    socket.on('error', () => {
      wsConnectSuccess.add(false);
      wsConnectFailures.add(1);
      lastSocketError = 'socket_error';
    });
  });

  const ok = check(res, {
    'ws handshake status is 101': (r) => !!r && r.status === 101,
  });

  if (!ok) {
    wsConnectSuccess.add(false);
    wsConnectFailures.add(1);

    // Optional lightweight diagnostics for first few failures.
    if (DEBUG_WS) {
      const alreadyLogged = wsDebugLogged.value || 0;
      if (alreadyLogged < DEBUG_SAMPLE_MAX) {
        const status = res && typeof res.status !== 'undefined' ? res.status : 'n/a';
        const err = (res && res.error) ? String(res.error) : (lastSocketError || 'unknown');
        console.log(`[ws-debug] url=${WS_URL} status=${status} error=${err}`);
        wsDebugLogged.add(1);
      }
    }

    // Avoid retry storms when the server is saturated.
    sleep(Math.max(0, FAIL_SLEEP_SECONDS));
  }

  sleep(0.1);
}
