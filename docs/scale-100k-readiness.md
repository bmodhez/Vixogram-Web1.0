# Vixogram 100k Concurrency Readiness Plan

This plan is tailored to the current codebase and deployment shape.

## Current hard blockers

- `render.yaml` uses `plan: free` for the web service. This cannot handle large concurrent websocket traffic.
- Random video matching currently runs in-process inside `a_rtchat/random_video_consumers.py` using a cache-backed list scan. This is not suitable for six-figure concurrency.
- `RANDOM_VIDEO_ACTIVE_USERS_LIMIT` defaults to `2000` in `a_core/settings.py`, so higher usage is intentionally rejected.
- Local `runserver` is for development only and should never be used for load assumptions.

## Immediate production baseline (must have)

1. Move off free instance plan to autoscaled instances behind a load balancer.
2. Use managed Postgres with PgBouncer transaction pooling.
3. Use managed Redis (dedicated tier) for both cache and Channels.
4. Run Daphne/Uvicorn workers as multiple processes per instance.
5. Add observability: Sentry, request latency dashboards, Redis/DB saturation alerts.

## Recommended target architecture for 100k connected users

- Edge: CDN + TLS termination + WAF/rate limiting.
- App tier:
  - ASGI instances for websocket signaling and HTTP.
  - Horizontal autoscaling by CPU + connection count.
- Matchmaking tier:
  - Separate matchmaking worker/service (do not perform O(n^2) matching in websocket consumer).
  - Redis data structures (sorted sets/streams) or dedicated queue broker.
- Data tier:
  - Postgres primary + read replicas if needed.
  - PgBouncer to cap active DB connections.
- Realtime tier:
  - Redis cluster/sentinel depending on provider.
  - Channels configured with tuned capacity/expiry and monitoring.
- Media tier:
  - TURN/STUN fleet (coturn) with autoscaling and region placement.
  - Most bandwidth/cost load is on TURN for relayed calls.

## Environment knobs to set (added in settings)

- `CHANNEL_LAYER_CAPACITY` (default `2000`)
- `CHANNEL_LAYER_EXPIRY` (default `60`)
- `CHANNEL_LAYER_GROUP_EXPIRY` (default `86400`)
- `CHANNEL_LAYER_PREFIX` (default `vixogram`)
- `RANDOM_VIDEO_ACTIVE_USERS_LIMIT` (default `2000`)
- `RANDOM_VIDEO_REMATCH_COOLDOWN_SECONDS` (default `12`)
- `RANDOM_VIDEO_REMATCH_FALLBACK_WAIT_SECONDS` (default `10`)

## Load test strategy (phased)

1. Phase 1 (HTTP/API):
   - Validate login, room list, message APIs under burst.
   - Goal: p95 < 400ms, error rate < 1%.
2. Phase 2 (WebSocket signaling):
   - Ramp websocket connect/disconnect and signaling events.
   - Goal: connect success > 99%, drop rate < 0.5%.
3. Phase 3 (Soak):
   - 2-6 hour sustained load at 60-80% of target.
   - Goal: stable memory, no increasing error trend.
4. Phase 4 (Failure drills):
   - Redis failover, DB restart, rolling deploy during traffic.
   - Goal: graceful degradation and quick recovery.

## Suggested SLOs

- HTTP availability: 99.9%
- Websocket connect success: 99.5%+
- Match time (random video): p95 < 4s (normal traffic)
- API p95 latency: < 400ms
- Error rate: < 1%

## Practical note for random video

For true 100k concurrency, move matching logic out of `RandomVideoConsumer` into a dedicated matchmaking pipeline. Keep websocket consumers focused on signaling relay, not heavy queue scans.

## Rollout order

1. Add metrics and dashboards.
2. Perform 5k/10k/20k staged tests.
3. Refactor random matcher to dedicated service.
4. Increase active-user limit gradually.
5. Run 24h soak before public scale-up.
