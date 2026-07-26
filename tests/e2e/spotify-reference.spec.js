const { test, expect } = require('@playwright/test');

test('Guardian certifies the Spotify reference journey', async ({ page }) => {
  let connected = true;
  let playbackStarted = false;
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
          },
        })
      : route.fulfill({status: 204}),
  );
  await page.route('**/v1/player/transfer', route => route.fulfill({status: 204}));
  await page.route('**/v1/player/play', route => {
    playbackStarted = true;
    return route.fulfill({status: 204});
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
  await page.route('**/auth/spotify/logout', route => {
    connected = false;
    return route.fulfill({json: {status: 'disconnected'}});
  });

  await page.goto('/');
  await expect(page.locator('#account-status')).toHaveText('Connected as Guardian Listener');
  await expect(page.locator('#player-status')).toContainText('ready');

  await page.locator('#moment').selectOption('working');
  await expect(page.locator('#pick-heading')).toHaveText('Focused Motion');
  await expect(page.locator('#evidence')).toContainText('Context evidence: ambient');
  await expect(page.locator('#save')).toHaveText('Save');

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
  await expect.poll(() => feedback.map(item => item.signal)).toContain('played');

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

  await page.reload();
  await expect(page.locator('#player-title')).toHaveText('Focused Motion');
  await expect(page.locator('#player-status')).toContainText('active');

  await page.locator('#account-action').click();
  await expect(page.locator('#account-status')).toHaveText('Spotify not connected');
  expect(connected).toBe(false);
});
