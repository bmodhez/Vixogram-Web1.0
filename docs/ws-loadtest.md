# WebSocket load test (100, 250, 500 concurrency)

This project already had `scripts/loadtest/k6-http-smoke.js` for HTTP.
Use the new script `scripts/loadtest/k6-ws-concurrency.js` for websocket concurrency checks.

## 1) Install k6 (Windows)

Pick one:

- Winget:
  - `winget install k6.k6`
- Chocolatey:
  - `choco install k6`

Verify:

- `k6 version`

## 2) Pick WebSocket endpoint

Default endpoint in script is:

- `/ws/global-announcement/`

Why this default: it does not require login and is good for connection-capacity tests.

If you want to test auth-required endpoints (`/ws/online-status/`, `/ws/notify/`, etc), pass:

- `WS_PATH` with that endpoint
- `COOKIE` containing a valid Django session cookie

## 3) Run 100, 250, 500 concurrent tests

Run from repo root.

### PowerShell one-by-one

```powershell
$base = "https://your-domain.onrender.com"
foreach ($target in 100,250,500) {
  Write-Host "\n=== WS concurrency test: $target ==="
  k6 run scripts/loadtest/k6-ws-concurrency.js `
    -e BASE_URL=$base `
    -e TARGET=$target `
    -e STEADY_SECONDS=120 `
    -e HOLD_SECONDS=45
}
```

### Single run example (250)

```powershell
k6 run scripts/loadtest/k6-ws-concurrency.js `
  -e BASE_URL=https://your-domain.onrender.com `
  -e TARGET=250 `
  -e RAMP_SECONDS=30 `
  -e STEADY_SECONDS=120 `
  -e RAMP_DOWN_SECONDS=20 `
  -e HOLD_SECONDS=45
```

## 4) What to watch in results

- `ws_connect_success` should stay very high (target > 99%)
- `ws_connect_failures` should stay near zero
- `ws_handshake_ms p(95)` should stay low and stable
- k6 exit code should be success (thresholds not broken)

## 5) Suggested pass/fail for each stage

- 100 users: should pass comfortably
- 250 users: still pass with low failures
- 500 users: if this fails on free plan, move to paid instance + Redis + Postgres tuning

## 6) Optional: test authenticated endpoint

Example for online-status endpoint:

```powershell
$cookie = "sessionid=your_sessionid_here; csrftoken=your_csrf_here"
k6 run scripts/loadtest/k6-ws-concurrency.js `
  -e BASE_URL=https://your-domain.onrender.com `
  -e WS_PATH=/ws/online-status/ `
  -e COOKIE="$cookie" `
  -e TARGET=100
```

## 7) Practical note

Do not run heavy load test against production without a maintenance window.
Test first on staging or at low traffic hours.
