# DNA-Driven Diverse Queue

## Product outcome

EchoSense turns a single deterministic recommendation into a short, explainable listening
sequence. The queue is generated from the user's normalized Spotify top and recent tracks,
the selected listening moment, and durable item/context feedback. Spotify remains the
playback provider; EchoSense owns selection and explanation.

## Ranking and sequencing

The existing learning ranker scores every unique candidate with:

- provider rank as the base relevance signal
- explicit listening-moment fit
- context-specific learned preference from plays, completions, skips, saves, likes, dislikes,
  and ratings

The diverse-slate stage then applies hard sequencing constraints:

1. deduplicate provider IDs
2. deduplicate recordings by ISRC when available, otherwise normalized title and artist
3. exclude explicitly supplied live-queue IDs
4. cap each artist at two tracks
5. avoid adjacent tracks by the same primary artist
6. preserve ranking score order whenever the diversity constraints allow it
7. return at most five tracks

Each result includes its rank, score, and a plain-language reason. The product UI previews
the slate before mutation. **Add DNA queue** submits each track with a deterministic
decision/track command ID. The player boundary skips tracks already present in Spotify's
live queue.

## MVP boundary

This milestone uses top and recent Spotify tracks because those signals already pass through
the provider-neutral Music DNA import. Saved tracks, playlist affinity, audio features, and
cross-provider catalog expansion are follow-on candidate sources; they can join the slate
without changing its diversity contract.

## Guardian invariants

- the slate contains no duplicate recording identity
- adjacent results do not repeat an artist when another artist is available
- no artist appears more than twice
- already-queued tracks are skipped by the playback boundary
- every visible slate item contains decision evidence
- one failed queue command cannot silently masquerade as a successful mutation
