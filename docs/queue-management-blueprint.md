# Queue Inspection and Management Blueprint

Spotify owns queue ordering. EchoSense exposes normalized current/up-next items and never
reorders provider results. Add commands require an idempotency key; repeated commands return
the prior outcome without adding duplicates. A new command for a track already present in the
live Spotify queue is also rejected, and the client disables Add next after a successful or
duplicate outcome. Unavailable items remain visible but non-playable.

Guardian covers ordering, duplicates, concurrent command conflicts, unavailable items, device
loss, rate limits, provider failures, and malformed or unsuccessful profile responses. Every
HTTP response must pass both status and payload-shape checks before the UI dereferences it.
