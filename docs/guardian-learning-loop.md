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
