# Spotify provider resilience

## Product contract

EchoSense remains usable when Spotify returns `429`, times out, or has a temporary transport
failure. The most recently verified recommendation response is the last-known-good (LKG)
playback plan. EchoSense may display and continue that plan while catalog refresh is unavailable,
but it must label the plan as cached and must not imply that live context was refreshed.

## Runtime behavior

1. A successful Spotify recommendation response is persisted per listener and recommendation
   settings.
2. A `429` persists Spotify's `Retry-After` as a provider-wide cooldown. A timeout or transient
   provider failure creates a short bounded cooldown.
3. During cooldown, recommendation-data requests do not call Spotify. EchoSense returns the exact
   settings snapshot when available, otherwise the newest verified plan for that listener.
4. The UI shows **Spotify is cooling down**, identifies whether the settings match exactly, and
   says that reconnecting is unnecessary.
5. Playback commands remain explicit user actions. The cached plan does not fabricate live
   provider state or claim that a track started when Spotify did not confirm it.
6. A later successful live response replaces the snapshot and clears the cooldown.
7. Disconnect and verified user-data deletion remove both provider cooldown and snapshot records.

## Request governor

- One application-wide persistent 30-second budget covers catalog, search, library, playlist,
  device, queue, and player-state calls across listeners, tabs, ports, and application restarts.
- The default safety budget is 20 Spotify Web API calls per 30 seconds and can be lowered with
  `ECHOSENSE_SPOTIFY_REQUEST_BUDGET`. It is a protective EchoSense ceiling, not a claim about
  Spotify's unpublished account limit.
- If the safety budget is reached, EchoSense pauses outbound calls for 30 seconds before Spotify
  can impose a longer lockout.
- Spotify `429` bodies are classified as `QUOTA_EXCEEDED` or `RATE_LIMIT_EXCEEDED`, with the exact
  `Retry-After` retained.
- Telemetry stores only normalized endpoint groups, status, outcome, and timing. Spotify item IDs,
  access tokens, raw responses, and listening coordinates are never retained.
- The local provider-status endpoint exposes budget utilization and five highest-volume endpoint
  groups without making a Spotify request.
- Spotify calls time out after eight seconds by default, and two transport failures within one
  minute open a 30-second circuit so stalled provider traffic cannot exhaust application workers.

## Acceptance criteria

- One provider rate-limit response can occur; repeated recommendation reads during `Retry-After`
  make zero further Spotify catalog calls.
- Cooldown and LKG data survive application restart and work across browser tabs.
- A cached response is HTTP 200 with `resilience.mode = last_known_good`, a reason, capture time,
  retry duration, and exact-settings indicator.
- Without a verified snapshot, EchoSense returns the existing bounded 429/503 error.
- The page retains the recommendation and six-track playback plan, displays degraded status, and
  does not tell the listener to reconnect.
- Guardian covers persistence, server suppression, browser suppression, bounded no-cache failure,
  and governed deletion.
- Player state uses its last verified continuity snapshot during cooldown instead of erasing the
  current listening surface.
- The UI distinguishes provider quota exhaustion, ordinary Spotify backoff, and an EchoSense
  preventive pause; all states include a countdown and explicitly say whether reconnecting helps.
