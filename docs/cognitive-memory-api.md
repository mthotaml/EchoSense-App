# Cognitive Memory API

The cognitive-memory API is a separate FastAPI surface backed by the same SQL storage and consent ledger as the contextual recommendation service.

Run locally:

```bash
uvicorn echosense.cognitive_memory_api:app --app-dir src --port 8083
```

## Consent

All operations require an active consent grant for purpose `cognitive_memory`.

## Record a memory

```http
PUT /v1/users/{user_id}/memories/{memory_id}
Content-Type: application/json
```

The body must include the same `memory_id` as the path, a memory type (`episodic`, `semantic`, or `working`), subject, predicate, object, context, confidence, provenance type, and provenance reference. Working memory also requires a future `expires_at` value.

Successful writes emit a `memory.recorded` event through the transactional outbox. Semantic conflicts return the new active memory with `supersedes_memory_id` populated.

## Read a memory

```http
GET /v1/users/{user_id}/memories/{memory_id}
```

Memory ownership is enforced by the path user. Cross-user reads return `404` rather than revealing that a memory ID exists.

## Search memory

```http
POST /v1/users/{user_id}/memories:search
Content-Type: application/json

{
  "query": "weekday rainy commute",
  "memory_type": "semantic",
  "context": "commute",
  "limit": 10
}
```

Search is bounded to 100 results and returns each memory with its deterministic relevance score. Expired working memories and superseded semantic memories are omitted.

## Operational boundaries

- the service does not expose cross-user or unbounded search
- confidence is evidence strength, not causal certainty
- provenance is retained with every record
- consent-derived deletion removes active and historical memories
- the initial search implementation has no external embedding dependency
