# EchoSense Cognitive Dashboard

The MVP frontend is a zero-build operator dashboard served by the existing FastAPI application. It is intentionally not a consumer music player. Its purpose is to make the cognitive loop visible and inspectable.

## Run locally

```bash
cd implementation
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export ECHOSENSE_DATABASE_URL=sqlite:///./echosense-dashboard.db
export ECHOSENSE_MUSIC_PROVIDER=fixture
export ECHOSENSE_MEMORY_BACKEND=memory
uvicorn echosense.web_app:app --app-dir src --reload
```

Open `http://127.0.0.1:8000/`.

This disposable profile does not require Postgres, Redpanda, Neo4j, Apple Music credentials, Node, or Docker. Production and infrastructure profiles can continue to select their existing adapters through environment configuration.

## Demonstrated flow

The **Run cognitive loop** button performs real API requests against the same origin:

1. grants contextual-recommendation consent;
2. submits activity and weather observations;
3. displays the inferred context and confidence;
4. renders the persisted candidate slate and ranking evidence;
5. shows the selected recommendation and grounded explanation;
6. records a liked outcome and displays the learned preference weight;
7. deletes consent-derived user data and displays the deletion receipt.

The decision-trace panel renders the actual server response rather than a simulated frontend-only trace.

## Implementation choice

The first UI uses semantic HTML, CSS, and browser JavaScript with no Node or bundler dependency. FastAPI serves the assets from `echosense/web`. This keeps the MVP installation and CI surface small. A component framework can replace the frontend later without changing the backend API contracts.
