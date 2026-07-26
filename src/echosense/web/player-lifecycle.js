(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.EchoSensePlayerLifecycle = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const INITIAL_STATE = Object.freeze({
    connection: "DISCONNECTED",
    sdk: "NOT_LOADED",
    device: "NONE",
    playback: "UNKNOWN",
  });

  class PlayerLifecycle {
    constructor(options) {
      this.options = options;
      this.state = { ...INITIAL_STATE };
      this.player = null;
      this.initializing = false;
      this.spotify = null;
    }

    snapshot() {
      return { ...this.state };
    }

    transition(changes) {
      this.state = { ...this.state, ...changes };
      this.options.onState?.(this.snapshot());
    }

    setConnection(connected) {
      this.transition({
        connection: connected ? "CONNECTED" : "DISCONNECTED",
        ...(connected ? {} : { device: "NONE", playback: "UNKNOWN" }),
      });
      if (!connected) this.disconnect();
      return this.start();
    }

    setSdk(spotify) {
      this.spotify = spotify;
      this.transition({ sdk: "LOADED" });
      return this.start();
    }

    start() {
      if (
        this.state.connection !== "CONNECTED" ||
        this.state.sdk !== "LOADED" ||
        this.player ||
        this.initializing
      ) {
        return this.player;
      }
      this.initializing = true;
      this.transition({ sdk: "INITIALIZING", device: "REGISTERING" });
      const player = this.options.createPlayer(this.spotify);
      this.player = player;
      player.addListener("ready", (event) => {
        this.transition({ sdk: "READY", device: "INACTIVE" });
        this.options.onReady?.(event);
      });
      player.addListener("not_ready", (event) => {
        this.transition({ device: "INACTIVE" });
        this.options.onNotReady?.(event);
      });
      player.addListener("player_state_changed", (state) => {
        const playback = !state
          ? "STOPPED"
          : state.loading
            ? "BUFFERING"
            : state.paused
              ? "PAUSED"
              : "PLAYING";
        this.transition({ playback });
        this.options.onPlayback?.(state);
      });
      [
        "initialization_error",
        "authentication_error",
        "account_error",
        "playback_error",
      ].forEach((name) =>
        player.addListener(name, (error) => {
          this.transition({ sdk: "ERROR", playback: "ERROR" });
          this.options.onError?.(name, error);
        }),
      );
      Promise.resolve(player.connect())
        .then((connected) => {
          if (connected === false) this.transition({ sdk: "ERROR", device: "ERROR" });
        })
        .catch((error) => {
          this.transition({ sdk: "ERROR", device: "ERROR" });
          this.options.onError?.("initialization_error", error);
        })
        .finally(() => {
          this.initializing = false;
        });
      return player;
    }

    markDeviceActive() {
      this.transition({ device: "ACTIVE" });
    }

    disconnect() {
      const player = this.player;
      this.player = null;
      this.initializing = false;
      player?.disconnect?.();
    }
  }

  return { INITIAL_STATE, PlayerLifecycle };
});
