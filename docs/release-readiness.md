# EchoSense Release Readiness

## Required pull-request checks

Protect `main` and require these checks before merge:

- `Quality`
- `Unit tests`
- `Browser lifecycle`
- `Guardian`
- `Dependency audit`
- `Secret scan`

Require pull requests, one approving review, dismissal of stale approvals, resolution of
review conversations, and branches to be current before merge. Block force pushes and
deletion of `main`.

Infrastructure tests run weekly and on demand because they start PostgreSQL, Redpanda,
and Neo4j. A release candidate must have a successful `Infrastructure` run against its
commit before tagging.

## Release gate

1. All required pull-request checks pass.
2. The infrastructure workflow passes on the release commit.
3. No unresolved critical or high dependency vulnerability exists.
4. No secret-scanning finding remains unresolved.
5. Spotify connect, session restore, token refresh, playback activation, and disconnect
   complete successfully in the production-like environment.
6. Database migrations and rollback steps are reviewed.
7. Required runtime configuration is present:
   `ECHOSENSE_DATABASE_URL`, `ECHOSENSE_TOKEN_ENCRYPTION_KEY` or rotation key list,
   Spotify client credentials, and the validated redirect URI.
8. Logs contain no credentials, OAuth state, PKCE verifier, cookies, or provider payloads
   with sensitive account data.

## Local verification

```bash
python -m pip install -e ".[dev]"
pre-commit run --all-files
pytest -m "not infrastructure and not postgres and not neo4j"
node tests/player_lifecycle.test.js
python scripts/validate_guardian.py
npm ci
npx playwright install chromium
npm run test:e2e
```

Run infrastructure verification separately:

```bash
docker compose up -d --wait
pytest -m "infrastructure or postgres or neo4j"
docker compose down --volumes
```
