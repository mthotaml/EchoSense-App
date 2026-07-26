# ADR-0015: Playback session continuity

## Status

Accepted.

## Decision

Spotify remains the authoritative source for active playback and device ownership. EchoSense
stores a versioned, short-lived last-known playback snapshot after every successful provider
state read.

When Spotify reports no active state, EchoSense may return a snapshot younger than 15 minutes
for visual continuity. Snapshot state is explicitly marked as requiring confirmation and never
auto-starts playback. A subsequent live response always supersedes the snapshot.

This design prevents refreshes and brief provider gaps from resetting the experience while
avoiding split-brain playback control across devices.
