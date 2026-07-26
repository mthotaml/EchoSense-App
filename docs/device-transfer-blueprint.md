# Device Discovery and Transfer Blueprint

## State ownership

Spotify owns device availability and active playback. EchoSense exposes a normalized device
view and initiates transfer only after explicit user action.

## Acceptance criteria

- Active, available, and restricted devices are visibly distinct.
- Restricted devices cannot be selected.
- Transfer never starts playback automatically.
- Device loss refreshes the list without requiring account reconnection.
- The browser player remains an explicit transfer target.
- Provider errors retain stable codes and correlation IDs.

## Guardian matrix

Guardian covers one device, multiple devices, restricted devices, no devices, successful
transfer, a target disappearing, refresh restoration, and token/rate-limit recovery.
