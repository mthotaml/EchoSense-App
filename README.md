# EchoSense MVP

This directory contains the executable contextual-music vertical slice for the EchoSense Cognitive Platform.

The MVP demonstrates one complete, explainable loop:

```text
Consent → Observe → Understand → Recommend → Explain → Learn → Re-rank → Delete
```

## See it work

The fastest path uses SQLite, the deterministic fixture provider, and in-memory preference memory. It does not require Postgres, Redpanda, Neo4j, Apple Music credentials, or Docker.

```bash
cd implementation
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
echosense-demo
```

The demo grants consent, submits rainy-driving observations, infers a `rainy_commute` context, evaluates a candidate slate, returns a grounded recommendation, records a liked outcome, demonstrates the learned preference and exposure-aware re-ranking on a second decision, deletes the user, and verifies that future processing is blocked.

Run the complete test suite with:

```bash
pytest
```

The HTTP-level MVP proof is `tests/test_mvp_demo.py`.

## Run the API locally

```bash
cd implementation
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn echosense.web_app:app --app-dir src --reload
```

Open `/docs` for the unified OpenAPI surface and `/` for the web dashboard.

## Connect a live Apple Music account

EchoSense never asks for or stores an Apple ID password. The browser uses Apple's MusicKit authorization dialog and receives a Music User Token after the user approves access. EchoSense encrypts that token before persistence.

### 1. Create Apple credentials

An active Apple Developer Program membership is required.

In Apple Developer Certificates, Identifiers & Profiles:

1. Create or select a Media ID for EchoSense and enable MusicKit.
2. Create a MusicKit private key associated with that Media ID.
3. Download the `.p8` private key immediately; Apple only offers the download once.
4. Record the 10-character Key ID.
5. Record the 10-character Team ID from Membership details.

Do not commit the `.p8` file or any generated token.

### 2. Configure EchoSense

```bash
cd implementation
cp .env.example .env
```

Edit `.env` and set:

```dotenv
ECHOSENSE_MUSIC_PROVIDER=apple_music
APPLE_MUSIC_TEAM_ID=YOUR_TEAM_ID
APPLE_MUSIC_KEY_ID=YOUR_KEY_ID
APPLE_MUSIC_PRIVATE_KEY_PATH=/absolute/path/to/AuthKey_YOUR_KEY_ID.p8
APPLE_MUSIC_STOREFRONT=us
ECHOSENSE_TOKEN_ENCRYPTION_KEY=YOUR_FERNET_KEY
```

Generate the encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Load the environment variables before starting the server:

```bash
set -a
source .env
set +a
uvicorn echosense.web_app:app --app-dir src --reload
```

### 3. Verify server configuration

Open this endpoint or request it from a terminal:

```bash
curl http://127.0.0.1:8000/v1/providers/apple-music/config
```

A correctly configured server returns `"configured": true` and a developer token. Never paste that token into source control, logs, screenshots, or support messages.

### 4. Authorize your Apple Music account

Open `http://127.0.0.1:8000/` and click **Connect Apple Music**. Sign in only inside Apple's authorization dialog. After approval, EchoSense stores the returned Music User Token, performs the first sync, builds the taste profile, and enables profile-aware recommendations.

If the authorization dialog does not open, check the browser console and confirm that the configuration endpoint reports `configured: true`. If sync returns `401` or `403`, verify the Team ID, Key ID, Media ID association, MusicKit service, `.p8` key, Apple Music subscription, and storefront.

The primary MVP endpoints include:

- `PUT /v1/consents`
- `POST /v1/recommendations`
- `GET /v1/users/{user_id}/taste-profile`
- `GET /v1/users/{user_id}/recommendations/profile-aware`
- `GET /v1/decision-traces/{decision_id}`
- `POST /v1/outcomes`
- `POST /v1/evaluations/outcomes`
- `POST /v1/users/{user_id}/deletions`
- `GET /health`

## Full infrastructure profile

Start the optional infrastructure integrations with:

```bash
docker compose up -d
```

Run the publisher and operations API separately after configuring the database, memory backend, broker, and Schema Registry:

```bash
echosense-outbox-publisher
uvicorn echosense.operations_api:app --app-dir src --port 8082
```

The operations surface exposes `GET /health/live`, `GET /health/ready`, and `GET /metrics`. Readiness probes the database, configured memory adapter, and Schema Registry without mutating state.

## Cognitive memory

`CognitiveMemoryStore` is separate from `PreferenceMemory`. Preference memory remains specialized learned-affinity memory; cognitive memory represents general provider-neutral episodes, propositions, and short-lived reasoning context.

Supported memory classes:

- episodic memory for timestamped experiences
- semantic memory for propositions about a subject and predicate
- working memory for expiring reasoning context

Every memory retains confidence, provenance, context, observed time, creation time, status, and optional expiry or supersession links. Semantic conflicts never silently overwrite evidence: the previous active proposition becomes `superseded`, and the new proposition links back to it.

Retrieval is user-scoped, deterministic, and capped at 100 results. The initial relevance function combines lexical overlap, confidence, and recency without requiring an embedding provider. Expired working memories and superseded semantic memories are excluded by default.

Consent-derived deletion removes active and historical cognitive memories and includes their count in the deletion receipt.

See `specifications/cognitive-memory.md` and `architecture/decisions/ADR-0006-cognitive-memory-store.md`.

## Live outcome evaluation

Every recommendation decision persists the full reranked candidate slate. Each snapshot records provider, item ID, rank, provider base score, effective preference weight, final ranking score, and whether the item was selected.

Counterfactual evaluation is exposed separately from preference learning:

```http
POST /v1/evaluations/outcomes
Content-Type: application/json

{
  "outcome_id": "outcome-123",
  "user_id": "user-123",
  "decision_id": "dec-123",
  "outcome": "completed",
  "playback_seconds": 180,
  "completion_ratio": 0.95,
  "attribution_window_seconds": 3600
}
```

Retrieve a persisted report with:

```http
GET /v1/evaluations/outcomes/{outcome_id}?user_id={user_id}
```

Both endpoints require active `contextual_recommendation` consent and enforce decision ownership. Duplicate outcome IDs return the persisted report. Evaluation produces normalized reward, estimated alternative lift, estimated regret, and an evidence-based confidence level. These values are diagnostic estimates, not causal proof, and evaluation never writes to preference memory.

## Ranking policy

The live recommendation path combines provider relevance, decayed preference memory, novelty, and bounded exploration. Selected-item exposure counts are persisted and used to reduce novelty for repeatedly shown items. Candidates that are merely considered do not increment exposure.

Policy controls are bounded in code:

- preference influence is capped at `0.5`
- novelty influence is capped at `0.25`
- exploration rate is capped at `0.20`
- exploration is deterministic for the same seed material
- diversity is group-aware with deterministic score-order backfill

Decision traces record the complete candidate slate, prior exposure count, novelty score, preference weight, policy score, exploration status, and active policy parameters.

## Controlled DLQ replay

`ReplayService` revalidates dead-lettered envelopes against the current canonical schema before publication. Replay selection supports event ID, failure class, and occurrence-time windows. Dry-run mode performs selection and validation without broker writes. Records with a non-zero `replay_count` are rejected to prevent uncontrolled replay loops.

Replay attempts receive a replay ID and are durably audited with actor, filters, mode, per-event results, errors, and final status. Published records include the replay ID in message headers.

The operations API provides authenticated replay administration endpoints:

- `POST /admin/replays`
- `POST /admin/replays/broker-window`
- `GET /admin/replays/{replay_id}`

Administration is disabled unless an admin key is configured. Requests are capped at 100 records. Broker replay requires an explicit topic, partition, starting offset, and limit. Automatic consumer commits are disabled; offset commits are opt-in, unavailable for dry runs, and refused when any selected record is rejected.

The `echosense-dlq-replay` entrypoint intentionally refuses an unbounded replay. Operators must use a bounded source or the administration API rather than draining an entire dead-letter topic.

Baseline Prometheus alert rules are available in `operations/alerts.yml` for outbox backlog, stale events, validation failures, DLQ rate, replay rejection, and publisher retries.

## Event governance and dead-letter handling

All canonical events must conform to `schemas/event-envelope.v1.json` before publication. The publisher validates each envelope through either the local schema adapter or a Confluent-compatible Redpanda Schema Registry. Successful records include schema identity headers.

Schema violations route immediately to `echosense.events.dlq.v1`. Transport failures retry until `ECHOSENSE_OUTBOX_MAX_ATTEMPTS`, then dead-letter. The SQL row is marked complete only after canonical-topic or DLQ broker acknowledgement.

## Preference memory, ranking, and learning

Providers return bounded candidate sets with base relevance scores. EchoSense combines provider relevance with context-scoped, exponentially decayed preference memory and bounded ranking-policy adjustments.

Outcome learning is grounded in persisted decisions, idempotent by outcome ID, and clamps preference weights to `[-1.0, 1.0]`.

Live Spotify recommendations include a `decision_id`. Authenticated clients submit plays,
completions, skips, saves, likes/dislikes, or 1–5 ratings to
`POST /auth/spotify/feedback`. EchoSense records completion strength and playback duration,
updates the durable item/context preference, evaluates the historical candidate slate, and
uses the new weight during the next Spotify ranking pass.

## Consent-derived deletion

`POST /v1/users/{user_id}/deletions` requires the literal confirmation value `delete`. The resumable coordinator removes consent-derived SQL records, encrypted provider credentials, cognitive memory, preference memory, recommendation exposure history, attributed outcomes, counterfactual reports, and attributable learning outcomes.

Incomplete requests enter `retry_required`. The `echosense-deletion-retry` worker resumes the original deletion ID and receipt instead of creating a duplicate request. Completed receipts clear the raw user ID and retain only a salted subject hash and aggregate metadata.

## Delivery semantics

The canonical outbox provides durable at-least-once delivery. `event_id` is the Kafka key and downstream idempotency key. Consumers must deduplicate because a process can fail after broker acknowledgement but before the SQL publish marker commits.

## MVP boundary

The MVP intentionally defers goal-directed planning, generalized knowledge-graph inference, multi-agent orchestration, the capability registry, and production hardening. Those capabilities remain roadmap work after the current vertical slice is merged and demonstrated.
