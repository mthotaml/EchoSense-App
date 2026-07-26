const appleMusicButton = document.getElementById("connect-apple-music");
const appleMusicCard = document.getElementById("apple-music-card");
const appleMusicState = document.getElementById("apple-music-state");
const appleMusicStatus = document.getElementById("apple-music-status");
const appleMusicAuthorization = document.getElementById("apple-music-authorization");
const appleMusicLastSync = document.getElementById("apple-music-last-sync");
const preferenceMemory = document.getElementById("preference-memory");
const semanticMemory = document.getElementById("semantic-memory");
const appleMusicUserId = localStorage.getItem("echosense-user-id") || `user-${crypto.randomUUID()}`;
localStorage.setItem("echosense-user-id", appleMusicUserId);

function setAppleMusicState(state, label, detail, options = {}) {
  appleMusicCard.dataset.state = state;
  appleMusicState.textContent = label;
  appleMusicStatus.textContent = detail;
  appleMusicButton.textContent = options.buttonLabel || "Connect Apple Music";
  appleMusicButton.disabled = Boolean(options.disabled);
  appleMusicAuthorization.textContent = options.authorization || "Required";
  appleMusicLastSync.textContent = options.lastSync || "Never";
}

async function jsonRequest(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail?.message || body.detail || detail;
    } catch (_) {
      // Keep the HTTP status when the body is not JSON.
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.status === 204 ? null : response.json();
}

function renderTasteProfile(profile) {
  if (!preferenceMemory || profile.status !== "ready") return;
  const artists = profile.top_artists.map((item) => `${item.name} (${item.evidence_count})`).join(" · ") || "No artist evidence yet";
  const albums = profile.top_albums.map((item) => item.name).join(" · ") || "No album evidence yet";
  preferenceMemory.classList.remove("muted");
  preferenceMemory.innerHTML = `<strong>Top artists</strong><br>${artists}<br><br><strong>Top albums</strong><br>${albums}`;
  if (semanticMemory) {
    semanticMemory.classList.remove("muted");
    semanticMemory.innerHTML = `${profile.summary}<br><br><strong>Confidence:</strong> ${Math.round(profile.confidence * 100)}% · <strong>Discovery:</strong> ${Math.round(profile.discovery_ratio * 100)}%`;
  }
}

async function loadTasteProfile() {
  const profile = await jsonRequest(`/v1/users/${encodeURIComponent(appleMusicUserId)}/taste-profile`);
  renderTasteProfile(profile);
  return profile;
}

function renderCompletedSync(sync) {
  const completed = sync.completed_at ? new Date(sync.completed_at).toLocaleString() : "Just now";
  setAppleMusicState(
    "connected",
    "Synced",
    `${sync.library_songs} library songs and ${sync.recent_plays} recent plays imported into EchoSense.`,
    {
      buttonLabel: "Sync again",
      disabled: false,
      authorization: "Authorized",
      lastSync: completed,
    },
  );
}

async function syncAppleMusic() {
  setAppleMusicState("connecting", "Syncing", "Importing permitted Apple Music library and recent-play metadata.", {
    buttonLabel: "Syncing…",
    disabled: true,
    authorization: "Authorized",
    lastSync: "In progress",
  });
  const sync = await jsonRequest(`/v1/users/${encodeURIComponent(appleMusicUserId)}/providers/apple-music/sync`, {
    method: "POST",
  });
  renderCompletedSync(sync);
  await loadTasteProfile();
}

async function connectAppleMusic() {
  if (appleMusicCard.dataset.state === "connected") {
    try {
      await syncAppleMusic();
    } catch (error) {
      setAppleMusicState("error", "Sync error", error.message, {
        buttonLabel: "Try sync again",
        disabled: false,
        authorization: "Authorized",
        lastSync: "Failed",
      });
    }
    return;
  }

  setAppleMusicState("connecting", "Connecting", "Opening Apple Music authorization.", {
    buttonLabel: "Connecting…",
    disabled: true,
    authorization: "In progress",
  });

  try {
    if (!window.MusicKit) {
      throw new Error("MusicKit JS did not load. Check your internet connection.");
    }

    const config = await jsonRequest("/v1/providers/apple-music/config");
    if (!config.configured || !config.developer_token) {
      throw new Error("Apple Music credentials are not configured on this server yet.");
    }

    MusicKit.configure({
      developerToken: config.developer_token,
      app: { name: config.app_name, build: config.app_build },
    });

    const music = MusicKit.getInstance();
    const musicUserToken = await music.authorize();
    if (!musicUserToken) {
      throw new Error("Apple Music did not return a user authorization token.");
    }

    await jsonRequest(`/v1/users/${encodeURIComponent(appleMusicUserId)}/providers/apple-music/token`, {
      method: "PUT",
      body: JSON.stringify({ music_user_token: musicUserToken }),
    });

    await syncAppleMusic();
  } catch (error) {
    setAppleMusicState("error", "Connection error", error.message, {
      buttonLabel: "Try again",
      disabled: false,
      authorization: "Unavailable",
    });
  }
}

async function restoreSyncState() {
  try {
    const sync = await jsonRequest(`/v1/users/${encodeURIComponent(appleMusicUserId)}/providers/apple-music/sync`);
    if (sync.status === "completed") {
      renderCompletedSync(sync);
      await loadTasteProfile();
      return;
    }
    if (sync.status === "failed") {
      setAppleMusicState("error", "Sync error", sync.error || "The previous sync failed.", {
        buttonLabel: "Try again",
        disabled: false,
        authorization: "Authorized",
        lastSync: "Failed",
      });
      return;
    }
  } catch (_) {
    // A missing status should not block the connection experience.
  }
  setAppleMusicState("disconnected", "Not connected", "Connect your account to begin building portable music intelligence.");
}

restoreSyncState();
appleMusicButton?.addEventListener("click", connectAppleMusic);
