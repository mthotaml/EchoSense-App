const { test, expect } = require('@playwright/test');

test('Guardian certifies the Spotify reference journey', async ({ page }) => {
  let connected = true;
  let playbackStarted = false;
  let skippedToNext = false;
  let restoreFromSnapshot = false;
  const playRequests = [];
  const recommendationPlays = [];
  const transfers = [];
  const queueCommands = [];
  const queuedTrackIds = [];
  const playbackModes = [];
  const savedTracks = new Set();
  const libraryMutations = [];
  const feedback = [];
  const controlEvents = [];
  const contextDataRequests = [];

  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        watchPosition(success) {
          setTimeout(() => success({
            coords: {latitude: 33.68, longitude: -117.82, speed: 18},
          }), 0);
          return 7;
        },
        clearWatch() {},
      },
    });
  });
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
          activateElement() {
            window.__activateElementCalls = (window.__activateElementCalls || 0) + 1;
            return Promise.resolve();
          }
          disconnect() {}
          getCurrentState() { return Promise.resolve(window.__sdkPlaybackState || null); }
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
    contextDataRequests.push(route.request().url());
    const moment = new URL(route.request().url()).searchParams.get('moment');
    const working = moment === 'working';
    const selectedId = skippedToNext ? 'post-skip-track' : working ? 'working-track' : 'general-track';
    const selectedTitle = skippedToNext ? 'Fresh Horizon' : working ? 'Focused Motion' : 'Open Road';
    const selectedDecision = skippedToNext ? 'decision-post-skip' : working ? 'decision-working' : 'decision-general';
    return route.fulfill({
      json: {
        profile: {
          display_name: 'Guardian Listener',
          genres: [{name: 'Ambient'}, {name: 'Indie'}],
          average_popularity: 55,
        },
        recommendation: {
          id: selectedId,
          title: selectedTitle,
          artist: 'Echo Artist',
          spotify_url: `https://open.spotify.com/track/${selectedId}`,
          decision_id: selectedDecision,
          match_score: 96,
          reason: working ? 'For working, this matches your Music DNA.' : 'This matches your Music DNA.',
          evidence: {
            noticed: `You selected ${moment}.`,
            matched_genres: working ? ['ambient'] : [],
          },
        },
        recommendations: [
          {
            id: selectedId,
            decision_id: selectedDecision,
            rank: 1,
            title: selectedTitle,
            artist: 'Echo Artist',
            reason: 'Ranked from your Music DNA.',
            why_now: {
              summary: 'Selected from your Music DNA with live-context fit.',
              factors: [
                {name: 'Music DNA affinity', score: 95},
                {name: 'Live context fit', score: 88},
                {name: 'Time pattern', score: 83},
              ],
              observations: ['sunny weather', 'Southern California', 'coastal drive matched to your Music DNA'],
            },
          },
          {
            id: working ? 'distinct-track' : 'alternate-track',
            decision_id: working ? 'decision-distinct' : 'decision-alternate',
            rank: 2,
            title: working ? 'Distinct Motion' : 'Open Sky',
            artist: 'Another Artist',
            reason: 'Adds artist diversity.',
          },
          {
            id: 'autopilot-3',
            decision_id: 'decision-autopilot-3',
            rank: 3,
            title: 'Open Current',
            artist: 'Third Artist',
            reason: 'Extends the listening flow.',
          },
          {
            id: 'autopilot-4',
            decision_id: 'decision-autopilot-4',
            rank: 4,
            title: 'Night Lines',
            artist: 'Fourth Artist',
            reason: 'Balances familiarity and discovery.',
          },
          {
            id: 'autopilot-5',
            decision_id: 'decision-autopilot-5',
            rank: 5,
            title: 'Coastal Signal',
            artist: 'Fifth Artist',
            reason: 'Keeps the queue diverse.',
          },
        ],
        insight: 'Your listening is becoming more focused.',
        timeline: ['Indie', 'Ambient'],
        temporal_mood: {
          daypart: 'afternoon',
          mood: 'uplifting',
          pattern_type: 'stable_pattern',
          evidence_count: 4,
          distinct_days: 3,
          confidence: 0.83,
          enabled: true,
          explanation: 'You often choose uplifting music during afternoon. EchoSense keeps this signal bounded by your Music DNA and feedback.',
        },
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
              id: skippedToNext ? 'next-track' : 'working-track',
              name: skippedToNext ? 'Next Motion' : 'Focused Motion',
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
  await page.route('**/v1/context/resolve', route =>
    route.fulfill({
      json: {
        daypart: 'afternoon',
        weather: 'sunny',
        temperature_f: 78,
        region: 'Southern California',
        road_setting: 'coastal',
        elevation_m: 24,
        activity: 'driving',
        speed_mph: 40,
        faster_than_usual: false,
        weather_available: true,
        location_precision: 'coarse',
      },
    }),
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
  await page.route('**/v1/player/play', async route => {
    playbackStarted = true;
    const request = await route.request().postDataJSON();
    playRequests.push(request);
    if (request.spotify_uri === 'spotify:track:next-track') {
      controlEvents.push('distinct-play');
      skippedToNext = true;
    }
    return route.fulfill({status: 204});
  });
  await page.route('**/v1/player/queue', async route => {
    if (route.request().method() === 'POST') {
      const command = await route.request().postDataJSON();
      queueCommands.push(command);
      const applied = !queuedTrackIds.includes(command.item_id);
      if (applied) queuedTrackIds.push(command.item_id);
      return route.fulfill({json: {status: applied ? 'queued' : 'already_queued', item_id: command.item_id, applied}});
    }
    return route.fulfill({
      json: {
        current: {id: 'working-track', title: 'Focused Motion', artists: ['Echo Artist'], playable: true},
        up_next: [
          {id: 'next-track', title: 'Next Motion', artists: ['Echo Artist'], playable: true},
          ...queuedTrackIds.map(id => ({id, title: id, artists: ['Autopilot Artist'], playable: true})),
        ],
      },
    });
  });
  await page.route('**/v1/player/next?*', route => {
    controlEvents.push('next');
    return route.fulfill({status: 204});
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
    await route.fulfill({
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
    const trackId = decisionId === 'decision-distinct' ? 'distinct-track' : 'working-track';
    await page.evaluate(id => {
      const state = {
        paused: false,
        position: 0,
        duration: 180000,
        track_window: {
          current_track: {
            id,
            name: id === 'distinct-track' ? 'Distinct Motion' : 'Focused Motion',
            duration_ms: 180000,
            artists: [{name: 'Echo Artist'}],
            album: {images: []},
          },
        },
      };
      window.__sdkPlaybackState = state;
      window.__mockPlayer.emit(state);
    }, trackId);
  });
  await page.route('**/auth/spotify/feedback', async route => {
    feedback.push(await route.request().postDataJSON());
    controlEvents.push('feedback');
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
  await page.locator('#context-toggle').click();
  await expect(page.locator('#context-chips')).toContainText('Southern California');
  await expect(page.locator('#context-chips')).toContainText('sunny · 78°F');
  await expect(page.locator('#context-chips')).toContainText('coastal drive');
  await expect.poll(() => contextDataRequests.some(url => url.includes('weather=sunny'))).toBe(
    true,
  );
  await expect.poll(() => contextDataRequests.some(url => url.includes('road_setting=coastal'))).toBe(
    true,
  );
  await expect(page.locator('#dna-queue-items thead')).toContainText(
    'Music DNA affinity',
  );
  await expect(page.locator('#dna-queue-items thead')).toContainText(
    'Live context fit',
  );
  await expect(page.locator('#dna-queue-items thead')).toContainText('Time pattern');
  await expect(page.locator('#dna-queue-items tbody tr').first()).toContainText('95%');
  await expect(page.locator('#dna-queue-items tbody tr').first()).toContainText('88%');
  await expect(page.locator('#dna-queue-items tbody tr').first()).toContainText('83%');
  await expect(page.locator('#temporal-mood-status')).toContainText(
    'often choose uplifting music during afternoon',
  );
  await expect(page.locator('#temporal-mood-chips')).toContainText('4 qualifying signals');
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
  await expect(page.locator('#playlist-tracks .playlist-track')).toHaveCount(2);
  await expect(page.locator('#playlist-tracks .playlist-track').nth(1)).toBeDisabled();
  await page.getByRole('button', {name: /Playlist Focus/}).click();
  await expect.poll(() => playRequests.map(item => item.spotify_uri)).toContain(
    'spotify:track:playlist-track',
  );

  await page.locator('#moment').selectOption('working');
  await expect(page.locator('#pick-heading')).toHaveText('Focused Motion');
  await expect(page.locator('#evidence')).toContainText('Context evidence: ambient');
  await expect(page.locator('#save')).toHaveText('Save');
  await expect(page.locator('#queue-add')).toHaveCount(0);
  await expect(page.locator('#dna-queue-add')).toHaveCount(0);
  await page.locator('#dna-queue-items tbody tr').nth(1).getByRole('button', {name: 'Play'}).click();
  await expect.poll(() => recommendationPlays.map(item => item.decision_id)).toContain(
    'decision-distinct',
  );
  await expect.poll(() => new Set(queueCommands.map(item => item.item_id)).size).toBe(4);
  await expect(page.locator('#autopilot-status')).toContainText('5 distinct tracks ready ahead');

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
  await expect.poll(() => recommendationPlays).toHaveLength(2);
  expect(recommendationPlays[1]).toMatchObject({
    decision_id: 'decision-working',
    device_id: 'guardian-device',
  });
  await expect.poll(() => page.evaluate(() => window.__activateElementCalls || 0)).toBeGreaterThan(0);
  await expect(page.locator('#player-status')).toContainText('browser audio');
  await page.locator('#play').click();
  await expect.poll(() => recommendationPlays).toHaveLength(3);
  expect(recommendationPlays[2].outcome_id).toBe(recommendationPlays[1].outcome_id);

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
  expect(feedback.find(item => item.signal === 'completed').decision_id).toBe(
    'decision-working',
  );

  await page.locator('#skip').click();
  await expect.poll(() => feedback.map(item => item.signal)).toContain('skipped');
  await expect.poll(() => controlEvents.slice(-3)).toEqual([
    'feedback',
    'next',
    'distinct-play',
  ]);
  await expect(page.locator('#player-title')).toHaveText('Next Motion');
  await expect(page.locator('#pick-heading')).toHaveText('Fresh Horizon');
  await expect(page.locator('#pick-label')).toHaveText('Recommended next');
  await expect(page.locator('#toast')).toContainText('verified Next Motion is playing');

  restoreFromSnapshot = true;
  await page.reload();
  await expect(page.locator('#player-title')).toHaveText('Next Motion');
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

test('Guardian isolates a Spotify playlist outage from core listening', async ({page}) => {
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
      json: {
        profile: {
          display_name: 'Guardian Listener',
          genres: [],
          average_popularity: 50,
        },
        recommendation: {
          id: 'guardian-track',
          title: 'Resilient Listening',
          artist: 'Echo Artist',
          decision_id: 'guardian-decision',
          match_score: 92,
          reason: 'Core listening remains available.',
          evidence: {matched_genres: []},
        },
        insight: 'Optional surfaces degrade independently.',
        timeline: ['Connected', 'Listening'],
      },
    }),
  );
  await page.route('**/auth/spotify/library/tracks/*', route =>
    route.fulfill({json: {saved: false}}),
  );
  await page.route('**/auth/spotify/playlists?*', route =>
    route.fulfill({
      status: 502,
      json: {detail: {code: 'spotify_library_failed'}},
    }),
  );
  await page.route('**/v1/player/devices', route =>
    route.fulfill({json: {items: []}}),
  );
  await page.route('**/v1/player/state', route => route.fulfill({status: 204}));
  await page.route('**/auth/spotify/feedback', route =>
    route.fulfill({json: {applied: true}}),
  );
  await page.route('**/v1/player/next?*', route => route.fulfill({status: 204}));

  await page.goto('/');

  await expect(page.locator('#pick-heading')).toHaveText('Resilient Listening');
  await expect(page.locator('#playlists-status')).toContainText('temporarily unavailable');
  await expect(page.locator('#more-playlists')).toHaveText('Retry');
  await expect(page.locator('#queue-add')).toHaveCount(0);
  await page.locator('#skip').click();
  await expect(page.locator('#toast')).toContainText('No active Spotify track is available to skip');
});
