# EchoSense Release Regression Catalog

## Blocking policy

A release candidate is blocked by any failed critical journey or unresolved severity-1 or
severity-2 defect.

## Required evidence

| Gate | Evidence |
|---|---|
| Application profiles | `/healthz` passes for API, legacy, and product compositions |
| Static quality | Ruff lint and formatting |
| Contracts | Full non-infrastructure pytest suite |
| Lifecycle | SDK/session initialization permutation suite |
| Spotify CUJ | Guardian Playwright journey from connection through disconnect |
| Recovery | Refresh snapshot, token retry, rate limiting, device loss |
| Controls | Play, pause, seek, volume, device transfer, queue, shuffle, repeat |
| Library | Save/unsave consistency and playlist unavailable-track guard |

Guardian writes `artifacts/guardian/release-evidence.json` for every release candidate.
