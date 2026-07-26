# Queue Inspection and Management Blueprint

Spotify owns queue ordering. EchoSense exposes normalized current/up-next items and never
reorders provider results. Add commands require an idempotency key; repeated commands return
the prior outcome without adding duplicates. Unavailable items remain visible but non-playable.

Guardian covers ordering, duplicates, concurrent command conflicts, unavailable items, device
loss, rate limits, and provider failures.
