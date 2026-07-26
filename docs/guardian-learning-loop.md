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
| Stale application mistaken for current MVP | Release evidence identifies commit and application profile | Profile smoke report and `/healthz` |

Guardian tests behavior and failure handling, not only successful rendering. Provider errors,
malformed payloads, retries, duplicate actions, stale processes, and partial initialization
are first-class release scenarios.
