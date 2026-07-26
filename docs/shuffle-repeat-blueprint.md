# Shuffle and Repeat Control Blueprint

Spotify owns shuffle and repeat state. EchoSense renders the live values returned by playback
state and sends explicit device-scoped commands. Repeat is limited to `off`, `track`, and
`context`; shuffle is boolean. Every command is followed by state reconciliation.

Guardian covers all state combinations, refresh restoration, device transfer, no active device,
token refresh, rate limits, and provider failures.
