const { test, expect } = require('@playwright/test');

test('Guardian certifies the Spotify reference journey', async ({ page }) => {
  let connected = true;
  let playbackStarted = false;
  let skippedToNext = false;
  let restoreFromSnapshot = false;
  let providerTrack = {id: 'working-track', name: 'Focused Motion'};
  const playRequests = [];
  const recommendationPlays = [];
  const transfers = [];
  const queueCommands = [];
  const queuedTrackIds = [];
  const playbackModes = [];
  const savedTracks = new Set();
  const libraryMutations = [];
  const libraryStatusRequests = [];
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
    const requestParams = new URL(route.request().url()).searchParams;
    const moment = requestParams.get('moment');
    const musicDnaBoosted = Number(requestParams.get('boost_music_dna') || 0) > 0;
    const working = moment === 'working';
    const social = moment === 'social';
    const contextual = moment !== 'general';
    const selectedId = musicDnaBoosted ? 'boost-track-1' : social ? 'social-track-1' : skippedToNext ? 'post-skip-track' : working ? 'working-track' : 'general-track';
    const selectedTitle = musicDnaBoosted ? 'DNA Lift' : social ? 'Open Road' : skippedToNext ? 'Fresh Horizon' : working ? 'Focused Motion' : 'Open Road';
    const selectedDecision = musicDnaBoosted ? 'decision-boost-1' : social ? 'decision-social-1' : skippedToNext ? 'decision-post-skip' : working ? 'decision-working' : 'decision-general';
    const momentImpact = contextual
      ? {
          moment, requested_moment: moment, source: 'selected', applied: true,
          changed_order: true, compared_candidates: 6,
          message: `${moment[0].toUpperCase()}${moment.slice(1)} selected changed the candidate ordering using moment-specific catalog evidence and context-fit scoring.`,
        }
      : {
          moment: 'general', requested_moment: 'general', source: 'general', applied: false,
          changed_order: false, compared_candidates: 6,
          message: 'Any moment is selected; no activity-specific reranking is applied.',
        };
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
                {name: 'Learned preference', score: 76},
                {name: 'Diversity guard', score: 91},
                {name: 'Time pattern', score: 83},
              ],
              observations: ['sunny weather', 'Southern California', 'coastal drive matched to your Music DNA'],
              moment_impact: working
                ? {...momentImpact, baseline_rank: 4, moment_rank: 1, rank_change: 3, context_fit: 88, evidence: ['selected working moment']}
                : {...momentImpact, baseline_rank: 1, moment_rank: 1, rank_change: 0, context_fit: 50, evidence: []},
            },
          },
          {
            id: musicDnaBoosted ? 'boost-track-2' : social ? 'social-track-2' : working ? 'distinct-track' : 'alternate-track',
            decision_id: musicDnaBoosted ? 'decision-boost-2' : social ? 'decision-social-2' : working ? 'decision-distinct' : 'decision-alternate',
            rank: 2,
            title: working ? 'Distinct Motion' : 'Open Sky',
            artist: 'Another Artist',
            reason: 'Adds artist diversity.',
          },
          {
            id: musicDnaBoosted ? 'boost-track-3' : social ? 'social-track-3' : 'autopilot-3',
            decision_id: musicDnaBoosted ? 'decision-boost-3' : social ? 'decision-social-3' : 'decision-autopilot-3',
            rank: 3,
            title: 'Open Current',
            artist: 'Third Artist',
            reason: 'Extends the listening flow.',
          },
          {
            id: musicDnaBoosted ? 'boost-track-4' : social ? 'social-track-4' : 'autopilot-4',
            decision_id: musicDnaBoosted ? 'decision-boost-4' : social ? 'decision-social-4' : 'decision-autopilot-4',
            rank: 4,
            title: 'Night Lines',
            artist: 'Fourth Artist',
            reason: 'Balances familiarity and discovery.',
          },
          {
            id: musicDnaBoosted ? 'boost-track-5' : social ? 'social-track-5' : 'autopilot-5',
            decision_id: musicDnaBoosted ? 'decision-boost-5' : social ? 'decision-social-5' : 'decision-autopilot-5',
            rank: 5,
            title: 'Coastal Signal',
            artist: 'Fifth Artist',
            reason: 'Keeps the queue diverse.',
          },
          {
            id: musicDnaBoosted ? 'boost-track-6' : social ? 'social-track-6' : 'autopilot-6',
            decision_id: musicDnaBoosted ? 'decision-boost-6' : social ? 'decision-social-6' : 'decision-autopilot-6',
            rank: 6,
            title: 'Pacific Light',
            artist: 'Sixth Artist',
            reason: 'Completes this listening round.',
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
        moment_impact: momentImpact,
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
              id: providerTrack.id,
              name: providerTrack.name,
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
    const tracksByDecision = {
      'decision-distinct': {id: 'distinct-track', name: 'Distinct Motion'},
      'decision-autopilot-3': {id: 'autopilot-3', name: 'Open Current'},
      'decision-autopilot-4': {id: 'autopilot-4', name: 'Night Lines'},
      'decision-autopilot-5': {id: 'autopilot-5', name: 'Coastal Signal'},
      'decision-post-skip': {id: 'post-skip-track', name: 'Fresh Horizon'},
    };
    providerTrack = tracksByDecision[decisionId] || {id: 'working-track', name: 'Focused Motion'};
    const trackId = providerTrack.id;
    if (decisionId === 'decision-autopilot-3' && feedback.some(item => item.signal === 'skipped')) {
      controlEvents.push('dna-play');
      skippedToNext = true;
    }
    if (decisionId === 'decision-autopilot-4' && feedback.some(item => item.signal === 'completed')) {
      controlEvents.push('dna-completion-play');
    }
    if (decisionId === 'decision-autopilot-5') {
      controlEvents.push('provider-autoplay-overridden');
    }
    await route.fulfill({
      json: {
        status: 'playing',
        decision_id: decisionId,
        provider: 'spotify',
        item_id: trackId,
        learning: {
          signal: 'played',
          applied: recommendationPlays.length === 1,
        },
      },
    });
    await page.evaluate(track => {
      const state = {
        paused: false,
        position: 0,
        duration: 180000,
        track_window: {
          current_track: {
            id: track.id,
            name: track.name,
            duration_ms: 180000,
            artists: [{name: 'Echo Artist'}],
            album: {images: []},
          },
        },
      };
      window.__sdkPlaybackState = state;
      window.__mockPlayer.emit(state);
    }, providerTrack);
  });
  await page.route('**/auth/spotify/feedback', async route => {
    const signal = await route.request().postDataJSON();
    feedback.push(signal);
    controlEvents.push(`feedback:${signal.signal}`);
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
    libraryStatusRequests.push(trackId);
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
  await page.route('**/auth/spotify/intelligence?*', route => route.fulfill({json: {
    generated_at: '2026-08-03T12:00:00Z', scope: 'connected_listener', data_status: 'ready',
    summary: {total_listen_seconds: 3720, tracks_observed: 18, completed: 12, skipped: 3, saved: 4, loved: 2, disliked: 1, early_skips: 1, completion_rate: 80, recommendation_acceptance_rate: 72, recommendations_with_outcomes: 18},
    moments: [{moment: 'working', signals: 9}, {moment: 'driving', signals: 6}],
    trend: [{date: '2026-08-02', listen_seconds: 1800, positive: 5, skips: 1}, {date: '2026-08-03', listen_seconds: 1920, positive: 6, skips: 2}],
    history: [{outcome_id: 'out-history', decision_id: 'decision-working', provider: 'spotify', provider_track_id: 'working-track', title: 'Focused Motion', artist: 'Echo Artist', signal: 'completed', moment: 'working', playback_seconds: 180, completion_ratio: .96, observed_at: '2026-08-03T12:00:00Z'}],
    capabilities: {history_correction: true, personalization_reset: false, data_export: false, verified_deletion: false},
  }}));

  await page.goto('/');
  await expect(page.locator('#account-status')).toHaveText('Connected as Guardian Listener');
  const listeningControls = page.locator('#listening-controls');
  await expect(listeningControls).toBeVisible();
  await expect(listeningControls.locator('#moment-panel')).toBeVisible();
  await expect(listeningControls.locator('#boost-panel')).toBeVisible();
  await expect(listeningControls.locator('#live-context-panel')).toBeVisible();
  await expect(page.locator('.hero-content #moment')).toHaveCount(0);
  await expect(page.locator('#intelligence-metrics')).toContainText('1.0 hr');
  await page.getByRole('tab', {name: 'Recommendation history'}).click();
  await expect(page.locator('#intelligence-history-list')).toContainText('Focused Motion');
  await page.getByRole('tab', {name: 'Product signals'}).click();
  await expect(page.locator('#intelligence-product-metrics')).toContainText('80%');
  await page.getByRole('tab', {name: 'Overview'}).click();
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
  await expect(
    page.locator('#hero-factors').getByRole('button', {name: /Current recommendation factor: Music DNA affinity.*Why it matters/}),
  ).toBeVisible();
  await expect(
    page.locator('#hero-factors').getByRole('button', {name: /Current recommendation factor: Live context fit.*Why it matters/}),
  ).toBeVisible();
  await expect(
    page.locator('#hero-factors').getByRole('button', {name: /Current recommendation factor: Learned preference.*Why it matters/}),
  ).toBeVisible();
  await expect(
    page.locator('#hero-factors').getByRole('button', {name: /Current recommendation factor: Diversity guard.*Why it matters/}),
  ).toBeVisible();
  await expect(page.locator('#boost-panel').getByRole('button', {name: /Priority factor: Music DNA affinity.*Why it matters/})).toBeVisible();
  await expect(page.locator('#dna-queue-items').getByRole('button', {name: /Queue factor: Music DNA affinity.*Why it matters/})).toBeVisible();
  await page.locator('#hero-factors').getByRole('button', {name: /Current recommendation factor: Music DNA affinity/}).click();
  await expect(page.locator('#factor-modal')).toBeVisible();
  await expect(page.locator('#factor-detail')).toContainText('Why it matters: recommendations still feel like your taste.');
  await page.locator('#factor-modal-close').click();
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
  await expect(page.locator('#moment-impact')).toContainText('Working selected changed the candidate ordering');
  await expect(page.locator('#moment-proof')).toContainText('88% Working fit · moved up 3 places');
  await expect(page.locator('#evidence')).toContainText('Context evidence: ambient');
  await expect(page.locator('#save')).toHaveText('Save');
  await expect(page.locator('#queue-add')).toHaveCount(0);
  await expect(page.locator('#dna-queue-add')).toHaveCount(0);
  await page.locator('#dna-queue-items tbody tr').nth(1).getByRole('button', {name: 'Play'}).click();
  await expect.poll(() => recommendationPlays.map(item => item.decision_id)).toContain(
    'decision-distinct',
  );
  expect(recommendationPlays.find(item => item.decision_id === 'decision-distinct')).toMatchObject({
    continuation_decision_ids: [
      'decision-autopilot-3',
      'decision-autopilot-4',
      'decision-autopilot-5',
      'decision-autopilot-6',
    ],
  });
  expect(queueCommands).toHaveLength(0);
  await expect(page.locator('#pick-heading')).toHaveText('Distinct Motion');
  await expect(page.locator('#player-title')).toHaveText('Distinct Motion');
  await expect(page.locator('#dna-queue-items tbody tr[aria-current="true"]')).toContainText('Distinct Motion');
  await expect.poll(() => libraryStatusRequests).toContain('distinct-track');
  const savedChecksBeforeRepeatedState = libraryStatusRequests.length;
  await page.evaluate(() => {
    for (let index = 0; index < 8; index += 1) window.__mockPlayer.emit(window.__sdkPlaybackState);
  });
  await page.waitForTimeout(100);
  expect(libraryStatusRequests).toHaveLength(savedChecksBeforeRepeatedState);
  await expect(page.locator('#dna-queue-items tbody tr')).toHaveCount(6);
  await expect(page.locator('#autopilot-status')).toContainText('4 planned tracks ready ahead');
  await expect(page.locator('#dna-queue-items tbody tr').first().locator('.why-cell')).toContainText(
    'Selected from your Music DNA with live-context fit.',
  );

  await page.locator('#save').click();
  await expect(page.locator('#save')).toHaveText('Saved');
  await expect(page.locator('#save')).toHaveAttribute('aria-pressed', 'true');
  expect(libraryMutations[0]).toMatchObject({
    method: 'PUT',
    trackId: 'distinct-track',
    request: {decision_id: 'decision-distinct'},
  });

  await page.locator('#save').click();
  await expect(page.locator('#save')).toHaveText('Save');
  expect(libraryMutations[1]).toEqual({method: 'DELETE', trackId: 'distinct-track'});

  await page.locator('#play').click();
  await expect.poll(() => recommendationPlays).toHaveLength(2);
  expect(recommendationPlays[1]).toMatchObject({
    decision_id: 'decision-distinct',
    device_id: 'guardian-device',
  });
  await expect.poll(() => page.evaluate(() => window.__activateElementCalls || 0)).toBeGreaterThan(0);
  await expect(page.locator('#player-status')).toContainText('browser audio');
  await page.locator('#play').click();
  await expect.poll(() => recommendationPlays).toHaveLength(3);
  expect(recommendationPlays[2].outcome_id).toBe(recommendationPlays[1].outcome_id);

  const roundsBeforeSkip = Number(
    (await page.locator('#dna-page-status').textContent()).match(/of (\d+)/)?.[1],
  );
  await page.locator('#skip').click();
  await expect.poll(() => feedback.map(item => item.signal)).toContain('skipped');
  await expect.poll(() => controlEvents).toContain('dna-play');
  expect(controlEvents.lastIndexOf('dna-play')).toBeGreaterThan(
    controlEvents.lastIndexOf('feedback:skipped'),
  );
  expect(controlEvents).not.toContain('next');
  expect(recommendationPlays.at(-1)).toMatchObject({
    decision_id: 'decision-autopilot-3',
    device_id: 'guardian-device',
  });
  await expect(page.locator('#player-title')).toHaveText('Open Current');
  await expect(page.locator('#pick-heading')).toHaveText('Open Current');
  await expect(page.locator('#dna-queue-items tbody tr[aria-current="true"]')).toContainText('Open Current');
  await expect(page.locator('#pick-label')).toHaveText('Current EchoSense recommendation');
  await expect(page.locator('#toast')).toContainText(
    'selected the next planned recommendation and verified Open Current is playing',
  );
  await expect(page.locator('#dna-page-status')).toHaveText(`Plan ${roundsBeforeSkip} of ${roundsBeforeSkip}`);
  await expect(page.locator('#dna-page-previous')).toBeEnabled();
  await page.locator('#dna-page-previous').click();
  await expect(page.locator('#dna-page-status')).toHaveText(
    `Plan ${roundsBeforeSkip - 1} of ${roundsBeforeSkip}`,
  );
  await page.locator('#dna-page-next').click();
  await expect(page.locator('#dna-page-status')).toHaveText(
    `Plan ${roundsBeforeSkip} of ${roundsBeforeSkip}`,
  );

  await page.evaluate(() => {
    const track = {
      id: 'autopilot-3',
      name: 'Open Current',
      duration_ms: 180000,
      artists: [{name: 'Echo Artist'}],
      album: {images: []},
    };
    window.__mockPlayer.emit({
      paused: false,
      position: 175000,
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
    'decision-autopilot-3',
  );
  await expect.poll(() => controlEvents).toContain('dna-completion-play');
  expect(controlEvents).not.toContain('next');
  expect(recommendationPlays.at(-1)).toMatchObject({
    decision_id: 'decision-autopilot-4',
    device_id: 'guardian-device',
  });
  await expect(page.locator('#player-title')).toHaveText('Night Lines');
  await expect(page.locator('#toast')).toContainText(
    'continued with Night Lines from your Playback Plan',
  );

  await page.evaluate(() => {
    const rogueTrack = {
      id: 'spotify-autoplay-track',
      name: 'Provider Autoplay Track',
      duration_ms: 180000,
      artists: [{name: 'Provider Artist'}],
      album: {images: []},
    };
    window.__mockPlayer.emit({
      paused: false,
      position: 1000,
      duration: 180000,
      track_window: {current_track: rogueTrack},
    });
  });
  await expect.poll(() => controlEvents).toContain('provider-autoplay-overridden');
  expect(recommendationPlays.at(-1)).toMatchObject({
    decision_id: 'decision-autopilot-5',
    device_id: 'guardian-device',
  });
  await expect(page.locator('#player-title')).toHaveText('Coastal Signal');
  await expect(page.locator('#toast')).toContainText(
    'Playback restored. Coastal Signal is playing from your EchoSense Playback Plan.',
  );

  restoreFromSnapshot = true;
  await page.reload();
  await expect(page.locator('#player-title')).toHaveText('Coastal Signal');
  await expect(page.locator('#player-status')).toContainText('Last session restored');
  await expect(page.locator('#toggle')).toHaveText('▶');

  await page.locator('#moment').selectOption('social');
  await expect(page.locator('#moment-impact')).toContainText(
    'Social selected changed the candidate ordering',
  );
  await expect(page.locator('#autopilot-status')).toContainText(
    'Social plan applied · 6 reranked tracks will follow the current song',
  );
  await expect(page.locator('#dna-plan-statement')).toContainText(
    'then EchoSense will play this newly ranked plan',
  );
  await expect(page.locator('#dna-queue-items tbody tr').first()).toContainText('Open Road');
  await expect(page.locator('#pick-heading')).toHaveText('Coastal Signal');
  await expect(page.locator('#player-title')).toHaveText('Coastal Signal');

  await page.locator('#boost-music_dna').fill('80');
  await expect.poll(() => contextDataRequests.some(url => url.includes('boost_music_dna=80'))).toBe(true);
  await expect(page.locator('#autopilot-status')).toContainText(
    'Music DNA affinity boost plan applied · 6 reranked tracks will follow the current song',
  );
  await expect(page.locator('#dna-queue-items tbody tr').first()).toContainText('DNA Lift');
  await expect(page.locator('#pick-heading')).toHaveText('Coastal Signal');
  await expect(page.locator('#player-title')).toHaveText('Coastal Signal');

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

for (const status of [401, 403, 429, 503]) {
  test(`Guardian safely renders Spotify ${status} failures`, async ({page}) => {
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
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
        status,
        json: {detail: {code: `spotify_${status}`, message: 'Spotify is temporarily unavailable'}},
      }),
    );

    await page.goto('/');

    await expect(page.locator('#toast')).toHaveText('Spotify is temporarily unavailable');
    expect(pageErrors).toEqual([]);
  });
}

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
