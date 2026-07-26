# Portable Music Intelligence

## Product promise

> Train EchoSense once. Take your music intelligence everywhere.

Streaming providers deliver catalogs and audio. EchoSense owns the provider-neutral understanding of the user: preferences, context, feedback, confidence, novelty tolerance, and the evidence behind each recommendation.

The first release is music-only. Podcasts, audiobooks, meditation, news, and other audio formats remain roadmap extensions through additional content adapters.

## Ten-second customer story

1. Connect a music service.
2. EchoSense learns permitted taste signals.
3. EchoSense understands the current moment.
4. EchoSense recommends and explains a track.
5. The selected provider streams it.
6. Feedback improves the same intelligence profile regardless of provider.

## V1 release boundary

The first production integration targets Apple Music.

V1 includes:

- Apple Music account authorization and explicit consent
- import of permitted library, playlist, favorite, and recent-play metadata where the provider API allows it
- normalization into provider-neutral artists, tracks, genres, affinities, recency, and exposure signals
- contextual recommendation using EchoSense memory and ranking
- catalog resolution from a provider-neutral recommendation to an Apple Music catalog item
- playback handoff to Apple Music or MusicKit-controlled playback
- visible explanation and confidence
- explicit feedback and memory updates
- account disconnect, data-source visibility, and deletion

V1 does not include:

- EchoSense hosting, transcoding, or redistributing audio
- copying an entire provider catalog into EchoSense
- demographic inference as the primary cold-start mechanism
- silent automatic playback without user permission
- simultaneous playback across multiple providers

## Provider responsibilities

### Streaming provider

- authenticates the subscriber
- exposes permitted catalog and user-library metadata
- enforces subscription and territorial availability
- resolves playable catalog identifiers
- streams the licensed audio

### EchoSense

- maintains provider-neutral consent and source provenance
- normalizes provider metadata into a portable taste profile
- combines taste with current context
- ranks candidates using context, preference, collaborative evidence, novelty, diversity, and safety
- explains the recommendation
- records feedback and updates memory
- selects a playback provider according to user preference and availability

## Multiple connected providers

Users may connect one or more providers. EchoSense keeps one cognitive music identity rather than a separate profile per provider.

For each provider, the connector records:

- connection status
- consented scopes
- last successful synchronization
- supported capabilities
- preferred playback priority
- region and subscription constraints when exposed

EchoSense imports only useful, permitted metadata. It does not need to duplicate full provider catalogs.

At recommendation time:

1. The cognitive engine describes the desired musical item and ranking evidence.
2. Provider adapters search or resolve equivalent catalog items.
3. EchoSense filters unavailable items.
4. The user’s preferred provider wins when multiple providers can play the item.
5. A fallback provider may be offered when the preferred provider cannot resolve it.
6. Only one provider plays at a time.

## Normalized provider contract

Each provider adapter should implement equivalent operations:

```text
connect
refresh_authorization
disconnect
sync_user_signals
search_catalog
resolve_track
prepare_playback
report_capabilities
```

Normalized user signals include:

```text
favorite_artist
favorite_track
library_add
playlist_membership
recent_play
skip
completion
explicit_like
explicit_dislike
```

Each signal retains provider, source identifier, observed time, confidence, consent purpose, and provenance. Provider-specific identifiers remain adapter data and must not become the cognitive model’s primary identity.

## Cold start

When imported signals are absent or insufficient, onboarding asks only for high-information inputs:

1. Choose up to three favorite artists.
2. Choose common listening moments: driving, working, exercising, relaxing, or social.
3. Choose discovery preference: familiar, balanced, or surprise me.

The initial profile is low confidence and exploration-aware. EchoSense explains experimental recommendations and learns quickly from plays, completions, skips, saves, likes, and explicit corrections.

Demographics are not used as the default predictor. They may only be considered when legally appropriate, consented, clearly useful, and protected against stereotyping.

## Context interaction model

EchoSense is assistive by default.

When context changes and confidence is low or medium, it asks a concise question with a reason:

> You seem to be starting a high-energy drive. Want something faster?

As confidence and user trust increase, prompts taper off. Users may explicitly enable automatic modes for low-risk situations. Overrides are treated as learning evidence.

Sensitive or ambiguous signals must not trigger confident claims. For example, EchoSense should not infer sadness from a single weak signal. It should use neutral language, expose uncertainty, and ask rather than assume.

## Recommendation policy

Every decision should balance:

- contextual fit
- learned preference
- cross-provider evidence
- novelty
- diversity
- safety
- provider availability

Novelty is a first-class control. EchoSense should exploit the destination provider’s catalog without abandoning the user’s established identity. A provider switch therefore creates an opportunity for bounded discovery, not a reset.

## Explainability contract

The customer experience should answer four questions:

1. What did EchoSense notice?
2. What did it remember?
3. Why did this track win?
4. What did it learn from the result?

Developer mode may additionally expose provider identifiers, scores, trace IDs, capability resolution, and raw evidence.

## Privacy contract

- every imported signal is tied to consent and source provenance
- disconnecting a provider stops future synchronization
- users can inspect connected sources and last-sync status
- users can delete provider-derived and EchoSense-derived memories
- raw provider tokens must be encrypted and isolated from cognitive memory
- explanations must not reveal sensitive source data unnecessarily

## Success criteria for the Apple Music milestone

A successful end-to-end demonstration proves:

1. a user connects Apple Music
2. EchoSense imports permitted metadata or completes cold-start onboarding
3. a scenario supplies current context
4. EchoSense produces a grounded recommendation
5. the recommendation is resolved in Apple Music
6. Apple Music owns playback
7. EchoSense records the outcome
8. the next recommendation visibly reflects the learning
9. the user can inspect why and delete the data

## Roadmap

### Release 1 — Apple Music vertical

Authorization, metadata sync, contextual recommendation, catalog resolution, playback handoff, explanation, feedback, and deletion.

### Release 2 — Second provider

Add Spotify or another viable provider to prove portable intelligence and provider switching.

### Release 3 — Context expansion

Add opt-in driving, schedule, weather, wearable, and activity signals with confidence-aware prompts.

### Release 4 — Personal audio intelligence

Extend the same cognitive identity to podcasts, audiobooks, meditation, learning, and other audio experiences.
