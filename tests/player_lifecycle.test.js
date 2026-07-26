const assert = require("node:assert/strict");
const {
  PlayerLifecycle,
} = require("../src/echosense/web/player-lifecycle.js");

class FakePlayer {
  constructor() {
    this.listeners = new Map();
    this.connectCalls = 0;
    this.disconnectCalls = 0;
  }
  addListener(name, listener) {
    this.listeners.set(name, listener);
  }
  connect() {
    this.connectCalls += 1;
    return true;
  }
  disconnect() {
    this.disconnectCalls += 1;
  }
  emit(name, payload) {
    this.listeners.get(name)?.(payload);
  }
}

function harness() {
  const players = [];
  const lifecycle = new PlayerLifecycle({
    createPlayer: () => {
      const player = new FakePlayer();
      players.push(player);
      return player;
    },
  });
  return { lifecycle, players };
}

{
  const { lifecycle, players } = harness();
  lifecycle.setSdk({});
  assert.equal(players.length, 0);
  lifecycle.setConnection(true);
  assert.equal(players.length, 1);
}

{
  const { lifecycle, players } = harness();
  lifecycle.setConnection(true);
  assert.equal(players.length, 0);
  lifecycle.setSdk({});
  assert.equal(players.length, 1);
}

{
  const { lifecycle, players } = harness();
  lifecycle.setConnection(true);
  lifecycle.setSdk({});
  lifecycle.setSdk({});
  lifecycle.setConnection(true);
  lifecycle.start();
  assert.equal(players.length, 1);
  assert.equal(players[0].connectCalls, 1);
}

{
  const { lifecycle, players } = harness();
  lifecycle.setConnection(true);
  lifecycle.setSdk({});
  const player = players[0];
  player.emit("ready", { device_id: "browser" });
  assert.equal(lifecycle.snapshot().sdk, "READY");
  assert.equal(lifecycle.snapshot().device, "INACTIVE");
  lifecycle.markDeviceActive();
  assert.equal(lifecycle.snapshot().device, "ACTIVE");
  player.emit("player_state_changed", { paused: true });
  assert.equal(lifecycle.snapshot().playback, "PAUSED");
  player.emit("player_state_changed", { paused: false });
  assert.equal(lifecycle.snapshot().playback, "PLAYING");
  lifecycle.setConnection(false);
  assert.equal(player.disconnectCalls, 1);
  assert.equal(lifecycle.snapshot().connection, "DISCONNECTED");
  assert.equal(lifecycle.snapshot().device, "NONE");
}
