# Temporal Mood Intelligence Requirements

**Status:** Approved for implementation planning
**Scope:** EchoSense Music DNA learning, recommendation, playlist preparation, explanation,
privacy, and Guardian coverage

## Implementation status

The first executable slice now includes:

- qualified completion, save, like, rating, skip, and dislike evidence;
- three-event/two-day stable pattern detection;
- three-of-five recent-shift detection;
- daypart isolation and seven-day evidence decay;
- conservative romantic and melancholy metadata rules plus contextual mood provenance;
- learned mood candidate expansion bounded by the existing 35% context weight;
- visible stable-pattern/recent-shift explanations;
- correction, enable/disable, reset, and account-deletion behavior; and
- provider-outage fallback for optional mood candidate generation.

Guardian contracts with matching executable tests are certified in `states`. The following
remain planned: an explicit Music DNA compatibility-floor test, a dedicated mood-influence
weight test, a mood-specific queue-diversity journey, and cross-provider recording evidence
deduplication.

## 1. Product outcome

EchoSense should learn *when* a listener prefers a type of music, detect meaningful changes
in recent listening, and prepare a distinct playlist that fits both the current moment and
the listener's provider-neutral Music DNA.

The system must explain whether a recommendation was influenced by:

- a recurring time-of-day pattern;
- a recent listening shift;
- live context such as weather, driving, coast, or mountains;
- durable Music DNA affinity;
- explicit or implicit feedback; or
- a diversity/discovery decision.

EchoSense describes listening behavior, not a person's emotional condition. For example,
it may say `recent listening has shifted toward melancholy music`; it must not say or imply
that the listener is depressed.

## 2. Definitions

| Term | Meaning |
|---|---|
| Temporal pattern | Repeated positive listening behavior for a mood or style in the same daypart |
| Recent mood shift | A bounded change in recent listening behavior compared with the user's established pattern |
| Positive event | Like, save, replay, explicit positive rating, or sufficiently completed playback |
| Negative event | Skip, dislike, removal, or consistently short playback |
| Music DNA match | Provider-neutral affinity based on normalized artists, genres, recordings, feedback, and discovery preference |
| Mood label | An explainable content descriptor such as romantic, melancholy, calm, reflective, energetic, or uplifting |
| Daypart | Late night, morning, afternoon, evening, or night in the listener's local time |

## 3. Use cases committed to this capability

### TMI-UC-01 — Recurring romantic morning pattern

If the listener repeatedly completes, saves, likes, or replays romantic music in the
morning, EchoSense should increase similar DNA-compatible candidates in the same or nearby
morning window.

Example explanation:

> You often choose romantic music in the morning. This track matches that pattern and your
> preference for melodic pop, while adding a different artist.

### TMI-UC-02 — Recurring romantic evening pattern

Morning and evening behavior must be learned independently. An evening romantic pattern
must not automatically alter morning ranking.

### TMI-UC-03 — Recent melancholy-listening shift

When several recent positive listening events consistently move toward melancholy or
reflective music, EchoSense should temporarily increase similar DNA-compatible candidates.
One track, one search, or one accidental play is insufficient evidence.

Example explanation:

> Your recent evening listening has shifted toward reflective, lower-energy music. This
> song fits that recent pattern and your Music DNA.

### TMI-UC-04 — Stable habit versus recent shift

The ranker must distinguish:

- a stable pattern learned across multiple days; and
- a recent, temporary change in behavior.

Both may contribute to a decision, but the explanation must name them separately.

### TMI-UC-05 — Situation and mood fusion

Temporal mood patterns combine with live context. Examples include:

- romantic evening + coastal drive;
- melancholy morning + rain;
- energetic preference + faster-than-usual driving; and
- reflective evening + mountain drive.

No single contextual signal may completely override Music DNA or safety constraints.

### TMI-UC-06 — Similar music without repetition

EchoSense should generate songs with similar mood and DNA affinity, not repeatedly queue
the same recording. Existing recording deduplication, artist-fatigue limits, live-queue
membership checks, and skip feedback remain mandatory.

### TMI-UC-07 — Explainability

Every visible recommendation affected by temporal mood learning must include:

- the detected daypart;
- whether the evidence is a stable pattern or recent shift;
- the mood/style label;
- evidence count and confidence band;
- relevant Music DNA affinity;
- other live-context factors;
- diversity or discovery rationale; and
- a human-readable reason.

### TMI-UC-08 — Correction and reset

The listener must be able to:

- mark the interpretation as incorrect;
- reduce or remove a learned pattern;
- disable temporal mood personalization; and
- delete the stored temporal mood memory.

Correction must affect later ranking and appear in the decision trace.

### TMI-UC-09 — Cold start and sparse evidence

Before sufficient evidence exists, EchoSense should use Music DNA and live context without
claiming a learned temporal mood pattern. The interface may say `Still learning your
evening pattern`.

### TMI-UC-10 — Provider portability

Temporal pattern and mood memory belong to EchoSense. Provider adapters supply normalized
observations and playback identifiers. Switching providers must not require retraining the
entire pattern once equivalent normalized evidence is available.

## 4. Learning and ranking policy

Initial thresholds are release policy, not permanent model constants:

1. A stable temporal pattern requires at least three positive events across at least two
   distinct days within a rolling 28-day window.
2. A recent shift requires at least three agreeing positive events among the last five
   eligible events within seven days.
3. A completion counts as positive only after at least 60% of playable duration, unless a
   like, save, replay, or explicit rating supplies stronger evidence.
4. A skip or dislike supplies negative evidence; repeated skips suppress comparable
   candidates in the same daypart.
5. Recent-shift influence decays with a seven-day half-life unless reinforced.
6. Stable-pattern confidence decays when the pattern is not reinforced during the rolling
   window.
7. Temporal and mood context may contribute no more than 35% of the pre-diversity ranking
   score in the first release.
8. A candidate must meet a configurable Music DNA compatibility floor before temporal
   context can promote it.
9. Explicit negative feedback and safety constraints outrank inferred mood fit.
10. Recording deduplication and artist-fatigue rules apply after ranking.

Thresholds and factor weights must be stored in decision traces so later tuning remains
auditable.

## 5. Mood evidence contract

Each mood label must retain provenance. Acceptable evidence includes:

- provider-permitted audio descriptors;
- normalized playlist or catalog descriptors;
- explicit user labels or corrections;
- completed recommendations previously generated for that mood; and
- explainable metadata rules with a recorded rule version.

The system must not:

- infer mood from protected characteristics;
- use a camera, microphone, private message, or health signal without a separate explicit
  consented capability;
- treat a title keyword alone as high-confidence mood evidence;
- call a listening pattern a medical or psychological diagnosis; or
- silently use an unavailable provider feature as if it succeeded.

Conflicting or low-confidence evidence returns `unknown` and does not establish a pattern.

## 6. Acceptance criteria

| ID | Acceptance criterion |
|---|---|
| TMI-AC-01 | Three qualifying romantic-morning events across two days establish a morning pattern; fewer events do not |
| TMI-AC-02 | A romantic-evening pattern does not change morning pattern confidence |
| TMI-AC-03 | Three of the last five eligible melancholy events create a bounded recent shift |
| TMI-AC-04 | A single melancholy track never creates or displays a mood shift |
| TMI-AC-05 | Skips/dislikes reduce comparable mood/daypart ranking and are visible in the trace |
| TMI-AC-06 | Recent shifts decay when not reinforced and cannot remain permanently active |
| TMI-AC-07 | Recommendations below the Music DNA compatibility floor are not promoted solely by mood |
| TMI-AC-08 | Mood/time ranking never bypasses recording deduplication or artist-fatigue limits |
| TMI-AC-09 | Every promoted item explains pattern type, daypart, mood, confidence/evidence, DNA fit, and diversity |
| TMI-AC-10 | Low-confidence or conflicting mood evidence is shown as unknown, not fabricated |
| TMI-AC-11 | Provider descriptor outages preserve Music DNA/live-context recommendations without a raw error |
| TMI-AC-12 | Correcting a pattern changes subsequent ranking and records the correction |
| TMI-AC-13 | Reset removes temporal mood memory without deleting unrelated Music DNA unless requested |
| TMI-AC-14 | Local-time conversion handles UTC offsets and day-boundary crossings deterministically |
| TMI-AC-15 | Reimporting the same provider observation is idempotent |
| TMI-AC-16 | Cross-provider observations with the same recording identity do not double-count evidence |
| TMI-AC-17 | Decision traces record policy version, thresholds, factor weights, and evidence provenance |
| TMI-AC-18 | The UI never describes inferred listening behavior as a mental-health diagnosis |

## 7. Planned unit and contract tests

| Test file | Required test |
|---|---|
| `tests/test_temporal_mood_learning.py` | Minimum evidence and distinct-day threshold |
| `tests/test_temporal_mood_learning.py` | Morning and evening patterns remain isolated |
| `tests/test_temporal_mood_learning.py` | Recent-shift detection uses three-of-five rule |
| `tests/test_temporal_mood_learning.py` | One-track false-positive guard |
| `tests/test_temporal_mood_learning.py` | Seven-day decay and reinforcement |
| `tests/test_temporal_mood_learning.py` | Skip/dislike negative evidence |
| `tests/test_temporal_mood_learning.py` | Duplicate observation idempotency |
| `tests/test_temporal_mood_learning.py` | Cross-provider recording deduplication |
| `tests/test_temporal_mood_ranking.py` | DNA compatibility floor |
| `tests/test_temporal_mood_ranking.py` | Maximum temporal/mood influence |
| `tests/test_temporal_mood_ranking.py` | Stable pattern and recent shift scored separately |
| `tests/test_temporal_mood_ranking.py` | Explicit negative feedback wins over inferred mood |
| `tests/test_temporal_mood_explanations.py` | Complete factor and evidence contract |
| `tests/test_temporal_mood_explanations.py` | Unknown/conflicting evidence language |
| `tests/test_temporal_mood_explanations.py` | Diagnosis and sensitive-inference wording prohibited |
| `tests/test_temporal_mood_routes.py` | Local-time and UTC day-boundary behavior |
| `tests/test_temporal_mood_routes.py` | Correction, disable, reset, and deletion |
| `tests/test_temporal_mood_routes.py` | Provider outage returns graceful fallback |
| `tests/test_product_ui.py` | Pattern/shift explanation, correction, disable, and reset controls |
| `tests/e2e/spotify-reference.spec.js` | Full recurring-pattern, mood-shift, fallback, and correction journey |

All implementation tests must use synthetic metadata and listening events. Real user
listening history must not be checked into fixtures or release evidence.

## 8. Guardian contracts

Guardian must permanently verify these named states:

- `temporal-pattern-evidence-threshold`
- `daypart-pattern-isolated`
- `recent-mood-shift-bounded`
- `single-track-mood-inference-rejected`
- `temporal-pattern-decay-applied`
- `mood-negative-feedback-applied`
- `mood-dna-compatibility-floor`
- `mood-ranking-influence-bounded`
- `mood-queue-diversity-preserved`
- `temporal-mood-factor-explained`
- `mood-evidence-provenance-visible`
- `mood-provider-outage-isolated`
- `temporal-pattern-correction-applied`
- `temporal-mood-memory-reset`
- `temporal-observation-idempotent`
- `cross-provider-mood-evidence-deduplicated`
- `sensitive-mood-inference-prohibited`

These contracts enter `guardian/guardian.json` as `planned_states`. A state moves into
certified `states` only after it maps to an executable unit, contract, or browser assertion
and appears in release evidence.

## 9. Deferred use cases

The following are recorded but are not part of the first temporal mood implementation:

- calendar-event mood inference;
- microphone, voice-tone, camera, facial-expression, or biometric inference;
- mental-health or medical-state inference;
- social/group mood aggregation;
- lyric ingestion or lyric-based semantic classification;
- seasonal and annual pattern learning;
- automatic destination inference;
- generative music or alteration of provider audio;
- household identity separation on shared provider accounts; and
- fully global coastal/terrain classification beyond the initial geospatial capability.

Each deferred use case requires a separate privacy review, consent contract, data-retention
policy, acceptance criteria, and Guardian journey before implementation.

## 10. Definition of done

This capability is complete only when:

1. the requirements above are implemented with provider-neutral models;
2. all planned tests are executable and passing;
3. Guardian states are backed by release evidence;
4. correction, disable, reset, and deletion are functional;
5. explanations expose stable pattern versus recent shift;
6. provider failures degrade without breaking core listening;
7. privacy and sensitive-inference prohibitions are enforced; and
8. the complete release smoke and regression gate passes.
