# Guardian Learning Loop

Every defect found during development, release testing, or live MVP validation becomes a
permanent regression asset. A fix is incomplete until Guardian can detect the same failure
without relying on a person to recognize it.

## Required closure

1. Record the user-visible symptom and the violated contract.
2. Identify the earliest deterministic detection point.
3. Add the smallest unit or contract test that reproduces the cause.
4. Add a critical-journey assertion when the failure crosses an API/UI boundary.
5. Add the named state to `guardian/guardian.json`.
6. Run the complete release gate and retain its evidence.

## Learned failures

| Failure | Contract | Permanent guard |
|---|---|---|
| Spotify error payload read as a profile | UI checks HTTP status and profile shape before dereferencing | Product UI contract test and Guardian provider-failure journey |
| Same track added under fresh command IDs | Queue idempotency covers both command identity and membership in the live provider queue | Player route regression and disabled Add next control |
| Spotify playlist `503` interrupted initialization | Optional provider surfaces retry once, degrade independently, and keep core listening interactive | Spotify client retry test and Guardian playlist-outage journey |
| Stale application mistaken for current MVP | Release evidence identifies commit and application profile | Profile smoke report and `/healthz` |
| Skip displayed success after provider command acceptance without proving a transition | A Spotify `204` acknowledges the command but does not prove that playback advanced | Guardian verifies a changed track ID before success and tests the no-active/no-transition path |
| Skip feedback changed memory but left the same recommendation visible | Successful skip refreshes playback state, provider queue, and the recommendation slate | Guardian asserts both the player title and Today's Pick change after a verified skip |
| Browser SDK readiness overwrote the restored-session status | Generic readiness must not outrank a more specific continuity state, and status computation must run before returning restored data | Restore state first on SDK readiness, use the generic ready label only when no state was restored, and retain the snapshot reload assertion |
| Skip targeted the browser SDK device while another Spotify device was actively playing | Playback commands must follow the active device reported immediately before the action | Target the live state's device, allow Spotify propagation time, and reject continuity snapshots as transition proof |
| Spotify accepted next but playback stayed on the same queued track | Consecutive duplicates and provider no-ops must not trap Skip on one song | Resolve the next distinct live-queue item, use it as a direct-play fallback, and verify its live track ID before success |
| Context and ranking explanations became repetitive visual clutter | Explainability must remain scannable as the candidate slate grows | Keep live context in one compact summary and compare per-track factors in shared table columns |
| Music DNA playback required repeated Add next/Add all intervention and stopped after a five-track slate | EchoSense owns continuous playback; five tracks are a rolling preview and queue horizon, not a session limit | One Play starts Autopilot, manual queue-add controls are absent, five distinct tracks are maintained ahead, consumed IDs rotate out through exclusions, and replenishment runs on track changes, skips, context changes, and a bounded timer |
| Background queue replenishment could replace the decision associated with the song currently playing | Future-candidate generation must not corrupt learning attribution for current playback | Autopilot may refresh the rolling preview, but completion and skip evidence must retain the current song's decision ID |
| Spotify showed a playing track and Autopilot filled the queue while the browser produced no sound | A successful Web API play response is not proof of audible browser playback; autoplay activation and local SDK state are separate contracts | Call `activateElement()` synchronously from the listener's click, transfer to the browser device, require an unpaused local SDK state for the expected track, and render actionable autoplay, account, authentication, initialization, and playback failures |
| New HTML called `activateElement()` while the browser reused an older lifecycle asset without that method | Coupled UI and lifecycle code must never be served as incompatible cached versions | Version the lifecycle asset URL, serve it with no-store headers, and assert that the delivered asset exposes the method required by the page |
| Today's Pick changed while another song was playing, making the app appear inconsistent and risking feedback against the wrong decision | Current playback and the upcoming recommendation are separate identities with separate decision provenance | Label the recommendation as Recommended next during playback, bind completion/skip only to the active track's known decision, and never fall back to the displayed next recommendation for an unknown externally playing track |
| A Spotify TLS handshake timeout leaked `_ssl.c` internals and left the recommendation surface empty | Safe provider reads retry once; repeated transport failure becomes a bounded, recoverable product state without exposing implementation details or discarding the saved connection | Transport retry unit tests, bounded API contract test, and `spotify-transport-timeout-recovery` Guardian invariant |
| A Spotify contract test passed locally through developer configuration but contacted the real token endpoint and failed in CI | Unit and contract tests must provide explicit dummy configuration and mock every provider boundary; developer secrets and outbound network are prohibited test dependencies | Run Spotify auth tests with provider environment variables removed and mock token refresh, catalog pagination, and search transport |
| Selecting Driving, Working, Exercising, Relaxing, or Social fetched a new ranking but active-track synchronization navigated the visible queue and Autopilot back to the old plan | A moment change preserves the audible current song while making the newly ranked slate the visible and authoritative successor plan; if evidence produces no ordering change, the UI must say so | Guardian browser journey verifies the new moment statement, changed plan rows, preserved current-track identity, and pending-plan transition ownership |
| Changing a recommendation boost fetched reweighted results but did not adopt them as the visible or audible successor plan | Music DNA affinity, live context, learned preference, and diversity boosts use the same transition contract: visibly rerank, preserve the current song, and play the boosted plan next | Guardian browser journey changes the Music DNA affinity boost, verifies a new six-track plan, preserves current playback, and asserts successor-plan ownership |
| Ranking-factor explanations existed in some surfaces but technical labels were repeated elsewhere without beginner guidance, while the hero repeated the same rationale in multiple text blocks | Each factor reference uses one shared accessible information control with a plain-language meaning and explicit listener benefit; primary surfaces show one concise rationale and defer formulas to the modal | Guardian verifies all four factor controls in recommendation, priority, and queue contexts, including keyboard-readable labels containing “Why it matters” |
| Repeated Spotify player-state callbacks checked whether the unchanged track was saved on every event, creating a request storm that exhausted Spotify's allowance and blocked recommendation loading | Saved status is fetched only for a changed track, cached for five minutes, deduplicated while in flight, and paused for the full Retry-After window; the server also serializes and caches checks across tabs | Guardian emits eight identical player states and permits no additional library request; API tests prove repeated and concurrent-style calls hit Spotify once and a 429 creates a provider-free cooldown |
| A Spotify 429 or transport outage made EchoSense appear empty and encouraged reconnect or refresh loops that prolonged the outage | The last successful recommendation response is persisted per listener and settings; provider Retry-After is a durable provider-wide cooldown, and degraded mode is disclosed without claiming live data | Storage restart tests prove cooldown and snapshot durability, the Spotify contract proves one failed provider call followed by provider-free cached responses, and Guardian verifies the visible cached-plan state suppresses more data requests |

Guardian tests behavior and failure handling, not only successful rendering. Provider errors,
malformed payloads, retries, duplicate actions, stale processes, and partial initialization
are first-class release scenarios.

## Prospective temporal-mood guards

Temporal mood intelligence must be guarded before release, not only after a production
failure. Its requirements and executable-test matrix are recorded in
`docs/temporal-mood-intelligence-requirements.md`.

Guardian must reject:

- a mood pattern inferred from one track;
- morning evidence leaking into an evening pattern;
- a recent mood shift that never decays;
- mood context overriding explicit negative feedback or the Music DNA floor;
- explanations without evidence provenance;
- repeated recordings presented as personalization;
- raw provider errors breaking core playback;
- reset or correction controls that do not change later decisions; and
- diagnostic or sensitive claims derived from listening behavior.

Adding a name to `planned_states` in `guardian/guardian.json` records the required contract.
It moves to certified `states` only with a matching executable assertion and release-evidence
entry.
