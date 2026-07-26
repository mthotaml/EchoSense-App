# DNA Queue Playback Controls

The listening controls are colocated with the decision they affect. A user should not need
to discover the fixed player before they can act on a DNA recommendation.

## Controls

- **Play now** on Today's Pick starts the primary decision-owned recommendation.
- **Play now** on a DNA row starts that row's track and records a played outcome against that
  row's own persisted decision.
- **Add next** on a DNA row submits a deterministic decision/track command. The player
  boundary skips an item already present in Spotify's queue.
- **Skip & play next** records skipped feedback for the current primary decision before it
  sends Spotify's next command.
- **Skip to next** is repeated in the visible queue header so advancing playback does not
  depend on finding the fixed bottom player.

## Safety contracts

Every DNA slate item has a persisted decision trace before the UI receives it. A play command
cannot substitute a different item for that decision. Skip never advances first and records
feedback later: if learning fails, the next command is not sent. Guardian verifies command
ownership, idempotency, and this ordering.
