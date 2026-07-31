# Context fusion and recommendation explainability

EchoSense combines stable Music DNA with transient listening context. Music DNA remains
provider-neutral: Spotify supplies normalized listening evidence and playback identifiers,
while EchoSense owns context, ranking, explanations, feedback learning, and diversity.

## First implementation slice

The product can now use:

- the browser's local daypart automatically;
- current weather from Open-Meteo after location permission;
- a coarse region such as Southern California;
- a confident coastal, mountain, or general road setting;
- motion speed reported by a mobile browser;
- a bounded, browser-local driving-speed baseline; and
- learned positive and negative playback feedback.

Time is always available. Location and motion require an explicit browser permission.
Raw latitude and longitude are sent only to the context resolver, rounded for the weather
request, and are neither returned to the UI nor written to EchoSense storage. The UI stores
only recent driving speeds for the faster-than-usual comparison.

## Candidate generation and ranking

Context must expand the candidate catalog rather than merely reorder the user's familiar
tracks. EchoSense therefore combines:

1. normalized top tracks;
2. Spotify catalog candidates for weather, coarse region, activity, and daypart; and
3. normalized recent tracks.

Duplicate provider track IDs are removed before ranking. The ranking score combines Music
DNA affinity, live context fit, learned preference, and a diversity guard. Live context has
enough weight to surface a timely catalog candidate, but cannot erase the user's taste or
the distinct-track rule.

Southern California uses a `California Los Angeles` catalog query while preserving
`Southern California` as the user-facing evidence label. Driving uses a driving query;
faster-than-usual driving uses an upbeat-driving query.

The displayed match score is derived from the same utility used for ranking. The raw utility
is `Music DNA base + context weight × context fit + 0.25 × learned preference`. Its
theoretical range (`-0.25` through `1 + context weight + 0.25`) is mapped monotonically to
`0–100`. Normalization therefore makes the value readable without changing candidate order.
The score is never hard-coded, values outside the theoretical range are clamped, and
diversity remains a post-ranking eligibility guard rather than an additive percentage.

The initial road-setting classifier uses Open-Meteo elevation for mountain detection and a
bounded Southern California coastal corridor for coastal detection. A coastal drive adds
beach/coastal candidates; a mountain drive adds scenic mountain candidates. Both retain
Music DNA affinity, feedback learning, and diversity in the final score.

## Explanation contract

Each visible Music DNA candidate carries a `why_now` object containing:

- a concise summary;
- scored factors for Music DNA affinity, live context fit, learned preference, and
  diversity; and
- accessible information controls in the table headers explain long-term taste,
  current situation, learned behavioral feedback, and repetition protection without
  repeating those definitions in every track row; and
- observable evidence such as sunny weather, afternoon timing, Southern California, or
  a coastal or mountain drive.

The interface renders these factors alongside each track so users can distinguish stable
taste evidence from a transient reason to play the song now.

## Failure isolation

Weather and optional catalog-search failures do not break the core recommendation surface.
EchoSense falls back to time, motion when available, and the normalized listening profile.
The unsuccessful optional source is omitted from the explanation instead of being exposed
as a raw provider error.

## Known boundaries

- Desktop browsers normally provide location but not useful driving speed. Motion-aware
  testing is best performed on a phone.
- Browser geolocation requires a secure context; localhost is accepted for local testing,
  while a deployed build must use HTTPS.
- The first catalog expansion is thematic search, not an audio-feature or semantic model.
  A future provider-neutral candidate service can replace it without changing the context
  or explanation contracts.
- The driving baseline is intentionally small and local. EchoSense does not build a raw
  location history in this slice.
- Coastal detection is initially bounded to a conservative Southern California corridor.
  Other regions safely return `general` until the provider-neutral geospatial layer expands.
