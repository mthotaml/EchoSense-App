const { test, expect } = require('@playwright/test');

test('Guardian certifies the Spotify reference journey', async ({ page }) => {
  let connected = true;
  let playbackStarted = false;
  let restoreFromSnapshot = false;
  const playRequests = [];
  const recommendationPlays = [];
  const transfers = [];
  const queueCommands = [];
  const playbackModes = [];
  const savedTracks = new Set();
  const libraryMutations = [];
  const feedback = [];

  await page.route('https://sdk.scdn.co/spotify-player.js', route =>
    route.fulfill({
      contentType: 'application/javascript',
      body: `
        class MockPlayer {
          constructor() { this.listeners = {}; window.__mockPlayer = this; }
          addListener(name, callback) { this.listeners[name] = callback; }
          connect() {
            setTimeout(() => this.listeners.ready?.({device_id:'guardian-device'}), 0);
            return Promise.resolve(true);
          }
          disconnect() {}
          getCurrentState() { return Promise.resolve(null); }
          emit(state) { this.listeners.player_state_changed?.(state); }
        }
        window.Spotify = {Player: MockPlayer};
        const sdkReady = setInterval(() => {
          if (window.onSpotifyWebPlaybackSDKReady) {
            clearInterval(sdkReady);
            window.onSpotifyWebPlaybackSDKReady();
          }
        }, 10);
      `,
    }),
  );
  await page.route('**/auth/spotify/session', route =>
    route.fulfill({
      json: connected
        ? {connected: true, profile: {display_name: 'Guardian Listener'}}
        : {connected: false},
    }),
  );
  await page.route('**/auth/spotify/data?moment=*', route => {
    const moment = new URL(route.request().url()).searchParams.get('moment');
    const working = moment === 'working';
    return route.fulfill({
      json: {
        profile: {
          display_name: 'Guardian Listener',
          genres: [{name: 'Ambient'}, {name: 'Indie'}],
          average_popularity: 55,
        },
        recommendation: {
          id: working ? 'working-track' : 'general-track',
          title: working ? 'Focused Motion' : 'Open Road',
          artist: 'Echo Artist',
          spotify_url: `https://open.spotify.com/track/${working ? 'working-track' : 'general-track'}`,
          decision_id: working ? 'decision-working' : 'decision-general',
          match_score: 96,
          reason: working ? 'For working, this matches your Music DNA.' : 'This matches your Music DNA.',
          evidence: {
            noticed: `You selected ${moment}.`,
            matched_genres: working ? ['ambient'] : [],
          },
        },
        insight: 'Your listening is becoming more focused.',
        timeline: ['Indie', 'Ambient'],
      },
    });
  });
  await page.route('**/v1/player/state', route =>
    playbackStarted
      ? route.fulfill({
          json: {
            is_playing: true,
            progress_ms: 30000,
            item: {
              id: 'working-track',
              name: 'Focused Motion',
              duration_ms: 180000,
              artists: [{name: 'Echo Artist'}],
              album: {images: []},
            },
            device: {id: 'guardian-device', name: 'EchoSense Browser'},
            continuity: restoreFromSnapshot
              ? {source: 'snapshot', requires_confirmation: true, revision: 2}
              : {source: 'live', requires_confirmation: false, revision: 1},
          },
        })
      : route.fulfill({status: 204}),
  );
  await page.route('**/v1/player/devices', route =>
    route.fulfill({
      json: {
        items: [
          {id: 'phone-device', name: 'Guardian Phone', type: 'smartphone', active: true, restricted: false},
          {id: 'restricted-device', name: 'Restricted Speaker', type: 'speaker', active: false, restricted: true},
        ],
      },
    }),
  );
  await page.route('**/v1/player/transfer', async route => {
    transfers.push(await route.request().postDataJSON());
    return route.fulfill({status: 204});
  });
  await page.route('**/v1/player/play', route => {
    playbackStarted = true;
    playRequests.push(route.request().postDataJSON());
    return route.fulfill({status: 204});
  });
  await page.route('**/v1/player/queue', async route => {
    if (route.request().method() === 'POST') {
      queueCommands.push(await route.request().postDataJSON());
      return route.fulfill({json: {status: 'queued', item_id: 'working-track', applied: queueCommands.length === 1}});
    }
    return route.fulfill({
      json: {
        current: {id: 'working-track', title: 'Focused Motion', artists: ['Echo Artist'], playable: true},
        up_next: [{id: 'next-track', title: 'Next Motion', artists: ['Echo Artist'], playable: true}],
      },
    });
  });
  await page.route('**/v1/player/shuffle', async route => {
    playbackModes.push({kind: 'shuffle', ...(await route.request().postDataJSON())});
    return route.fulfill({status: 204});
  });
  await page.route('**/v1/player/repeat', async route => {
    playbackModes.push({kind: 'repeat', ...(await route.request().postDataJSON())});
    return route.fulfill({status: 204});
  });
  await page.route('**/v1/player/recommendations/*/play', async route => {
    playbackStarted = true;
    const request = await route.request().postDataJSON();
    const decisionId = new URL(route.request().url()).pathname.split('/').at(-2);
    recommendationPlays.push({...request, decision_id: decisionId});
    return route.fulfill({
      json: {
        status: 'playing',
        decision_id: decisionId,
        provider: 'spotify',
        item_id: 'working-track',
        learning: {
          signal: 'played',
          applied: recommendationPlays.length === 1,
        },
      },
    });
  });
  await page.route('**/auth/spotify/feedback', async route => {
    feedback.push(await route.request().postDataJSON());
    return route.fulfill({
      json: {applied: true, weight: 0.1, evidence_count: feedback.length},
    });
  });
  await page.route('**/auth/spotify/library/tracks/*', async route => {
    const trackId = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop());
    const method = route.request().method();
    if (method === 'PUT') {
      const request = await route.request().postDataJSON();
      savedTracks.add(trackId);
      libraryMutations.push({method, trackId, request});
      return route.fulfill({
        json: {
          provider: 'spotify',
          track_id: trackId,
          saved: true,
          learning: {signal: 'saved', applied: true},
        },
      });
    }
    if (method === 'DELETE') {
      savedTracks.delete(trackId);
      libraryMutations.push({method, trackId});
      return route.fulfill({
        json: {provider: 'spotify', track_id: trackId, saved: false},
      });
    }
    return route.fulfill({
      json: {provider: 'spotify', track_id: trackId, saved: savedTracks.has(trackId)},
    });
  });
  await page.route('**/auth/spotify/playlists?*', route =>
    route.fulfill({
      json: {
        items: [
          {
            provider: 'spotify',
            id: 'focus-playlist',
            name: 'Guardian Focus',
            owner_name: 'Guardian Listener',
            track_count: 2,
            can_browse: true,
          },
          {
            provider: 'spotify',
            id: 'public-playlist',
            name: 'Public Mix',
            owner_name: 'Curator',
            track_count: 10,
            can_browse: false,
          },
        ],
        total: 2,
        offset: 0,
        limit: 8,
        next_offset: null,
      },
    }),
  );
  await page.route('**/auth/spotify/playlists/*/tracks?*', route =>
    route.fulfill({
      json: {
        items: [
          {
            position: 0,
            playable: true,
            unavailable_reason: null,
            track: {
              id: 'playlist-track',
              title: 'Playlist Focus',
              artists: ['Echo Artist'],
              uri: 'spotify:track:playlist-track',
            },
          },
          {
            position: 1,
            playable: false,
            unavailable_reason: 'Unavailable on Spotify',
            track: null,
          },
        ],
        total: 2,
        offset: 0,
        limit: 20,
        next_offset: null,
      },
    }),
  );
  await page.route('**/auth/spotify/logout', route => {
    connected = false;
    return route.fulfill({json: {status: 'disconnected'}});
  });

  await page.goto('/');
  await expect(page.locator('#account-status')).toHaveText('Connected as Guardian Listener');
  await expect(page.locator('#player-status')).toContainText('ready');
  await page.locator('#shuffle').click();
  await page.locator('#repeat').selectOption('track');
  await expect.poll(() => playbackModes).toContainEqual({kind: 'shuffle', enabled: true, device_id: 'guardian-device'});
  await expect.poll(() => playbackModes).toContainEqual({kind: 'repeat', mode: 'track', device_id: 'guardian-device'});
  await expect(page.locator('#device-picker option')).toHaveCount(3);
  await expect(page.locator('#device-picker option').nth(2)).toBeDisabled();
  await page.locator('#device-picker').selectOption('phone-device');
  await page.locator('#transfer-device').click();
  await expect.poll(() => transfers).toContainEqual({device_id: 'phone-device', play: false});
  await expect(page.locator('.playlist-card')).toHaveCount(2);
  await expect(page.locator('.playlist-card').nth(1)).toBeDisabled();

  await page.getByRole('button', {name: /Guardian Focus/}).click();
  await expect(page.locator('.playlist-track')).toHaveCount(2);
  await expect(page.locator('.playlist-track').nth(1)).toBeDisabled();
  await page.getByRole('button', {name: /Playlist Focus/}).click();
  await expect.poll(() => playRequests.map(item => item.spotify_uri)).toContain(
    'spotify:track:playlist-track',
  );

  await page.locator('#moment').selectOption('working');
  await expect(page.locator('#pick-heading')).toHaveText('Focused Motion');
  await expect(page.locator('#evidence')).toContainText('Context evidence: ambient');
  await expect(page.locator('#save')).toHaveText('Save');
  await page.locator('#queue-add').click();
  await expect(page.locator('#queue-items')).toContainText('Next Motion');
  await expect(page.locator('#queue-add')).toBeDisabled();
  expect(queueCommands).toHaveLength(1);

  await page.locator('#save').click();
  await expect(page.locator('#save')).toHaveText('Saved');
  await expect(page.locator('#save')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#toast')).toContainText('EchoSense learned');
  expect(libraryMutations[0]).toMatchObject({
    method: 'PUT',
    trackId: 'working-track',
    request: {decision_id: 'decision-working'},
  });

  await page.locator('#save').click();
  await expect(page.locator('#save')).toHaveText('Save');
  expect(libraryMutations[1]).toEqual({method: 'DELETE', trackId: 'working-track'});

  await page.locator('#play').click();
  await expect.poll(() => recommendationPlays).toHaveLength(1);
  expect(recommendationPlays[0]).toMatchObject({
    decision_id: 'decision-working',
    device_id: 'guardian-device',
  });
  await page.locator('#play').click();
  await expect.poll(() => recommendationPlays).toHaveLength(2);
  expect(recommendationPlays[1].outcome_id).toBe(recommendationPlays[0].outcome_id);

  await page.evaluate(() => {
    const track = {
      id: 'working-track',
      name: 'Focused Motion',
      duration_ms: 180000,
      artists: [{name: 'Echo Artist'}],
      album: {images: []},
    };
    window.__mockPlayer.emit({
      paused: false,
      position: 170000,
      duration: 180000,
      track_window: {current_track: track},
    });
    window.__mockPlayer.emit({
      paused: true,
      position: 178000,
      duration: 180000,
      track_window: {current_track: track},
    });
  });
  await expect.poll(() => feedback.map(item => item.signal)).toContain('completed');

  await page.locator('#skip').click();
  await expect.poll(() => feedback.map(item => item.signal)).toContain('skipped');

  restoreFromSnapshot = true;
  await page.reload();
  await expect(page.locator('#player-title')).toHaveText('Focused Motion');
  await expect(page.locator('#player-status')).toContainText('Last session restored');
  await expect(page.locator('#toggle')).toHaveText('▶');

  await page.locator('#account-action').click();
  await expect(page.locator('#account-status')).toHaveText('Spotify not connected');
  expect(connected).toBe(false);
});

test('Guardian renders Spotify data failures without leaking JavaScript errors', async ({page}) => {
  await page.route('https://sdk.scdn.co/spotify-player.js', route =>
    route.fulfill({contentType: 'application/javascript', body: ''}),
  );
  await page.route('**/auth/spotify/session', route =>
    route.fulfill({
      json: {connected: true, profile: {display_name: 'Guardian Listener'}},
    }),
  );
  await page.route('**/auth/spotify/data?moment=*', route =>
    route.fulfill({
      status: 502,
      json: {detail: {code: 'spotify_api_failed', message: 'Provider unavailable'}},
    }),
  );

  await page.goto('/');

  await expect(page.locator('#toast')).toHaveText('Provider unavailable');
  await expect(page.locator('#toast')).not.toContainText('display_name');
});
