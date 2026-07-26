# ADR-0014: Cross-provider recording identity

## Status

Accepted.

## Decision

EchoSense owns a canonical recording identity independent of any streaming provider. Provider
adapters supply normalized references and retain provider IDs solely as aliases for catalog
lookup and playback.

Resolution is conservative:

1. an exact ISRC plus compatible version metadata is a high-confidence match;
2. missing ISRC may fall back to normalized title, artist, duration, album, and version markers;
3. live, remastered, acoustic, remix, instrumental, demo, and karaoke variants do not merge
   with an unmarked studio recording;
4. artist disagreement prevents cover recordings from merging;
5. tied candidates remain separate and are reported as ambiguous.

Canonical identity is catalog-level data. User preference and outcome evidence refer to the
canonical identity in future migrations, while provider aliases remain provider-bound.

## Consequences

- Music DNA can remain stable when a listener changes providers.
- Playback still resolves through the selected provider adapter.
- False negatives are tolerated more readily than false merges.
- Identity corrections require an explicit future reconciliation workflow and audit trail.
