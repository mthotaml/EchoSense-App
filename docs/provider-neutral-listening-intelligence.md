# Provider-neutral listening intelligence

## Purpose

EchoSense owns its learning history independently of any streaming provider. Spotify is the first playback adapter; Apple Music and later providers link to the same EchoSense listener and canonical track whenever reliable recording evidence matches.

## Identity model

- `echo_user_id` is the durable EchoSense listener identity.
- `provider_user_aliases` links Spotify, Apple Music, or another provider account to that listener.
- `echo_track_id` is the canonical EchoSense recording identity.
- `provider_track_catalog` maps each provider's track ID and metadata to the canonical recording.
- ISRC is the strongest cross-provider match. Normalized title, artists, album, and duration provide bounded fallback evidence through the recording identity registry.
- Provider catalog metadata is retained as catalog evidence; it is not treated as user behavior.

## Behavior and learning model

`listening_events` is append-only and decision-bound. Supported evidence includes played, completed, skipped, saved, unsaved, liked, disliked, rated, and replayed. An `event_id` is idempotent and cannot be rebound to another listener, recording, or event type.

`user_track_intelligence` is a rebuildable projection containing counts, total listen time, and a bounded preference score. It is an input to future ranking—not an unexplained replacement for Music DNA, live context, learned preference, or diversity protection.

`listening_sessions` groups events into a provider connection session. A future sessionizer may split sessions after inactivity without changing the event contract.

## Product KPIs

The service exposes evidence-derived metrics only:

- distinct listeners and listening sessions;
- behavioral events and distinct tracks;
- total listening seconds;
- completion and skip rates over completed-plus-skipped outcomes;
- recommendation acceptance over observable completed, skipped, liked, saved, and disliked evidence.

An empty denominator returns `null`, never an invented success rate. Current product KPIs describe observed EchoSense traffic and are not represented as population-wide adoption until multi-user deployment exists.

## Playback identity contract

At any moment, one decision-owned track identity must drive all active surfaces:

1. the browser player's audible track;
2. the Hero's current recommendation;
3. the row marked `Playing` in the Final EchoSense Playback Plan;
4. feedback and listening-intelligence attribution.

Skip consumes the next uncompleted item in the displayed plan. A new six-track plan is generated only after the existing plan is exhausted. Natural completion follows the same successor rule. If Spotify advances to an unplanned provider-queue track, EchoSense restores the expected decision-owned successor before presenting success.

## Governance

- Deletion resolves a provider user ID to its canonical EchoSense user and removes linked aliases, sessions, events, and user-track projections.
- Global provider catalog and canonical recording data remain because they are non-user catalog facts.
- Deletion receipts contain counts and a salted subject hash, not the deleted identity.
- Raw events remain attributable to the ranking decision that produced the recommendation.

## Acceptance criteria

1. Spotify and Apple Music aliases can link to one `echo_user_id`.
2. The same ISRC across providers resolves to one `echo_track_id`.
3. Duplicate events do not double-count; conflicting event reuse fails closed.
4. Completion, skip, save, and listen-time evidence updates the correct canonical track.
5. Empty KPI denominators are explicit and truthful.
6. User deletion removes all provider-neutral behavioral data and reports exact counts.
7. Hero, active plan row, browser player, and feedback decision remain identical after play, skip, completion, refresh, and provider-autoplay recovery.
8. Guardian blocks release when any identity-alignment or persistence contract fails.

## Deliberately deferred

- Automatic Apple Music ingestion and playback adapter wiring.
- Offline event synchronization and conflict resolution across devices.
- Inactivity-based session splitting and cohort retention dashboards.
- ML model training from the preference projection.

These extensions must reuse the canonical identities and append-only event contract rather than introduce provider-specific learning stores.
