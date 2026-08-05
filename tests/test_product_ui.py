from fastapi.testclient import TestClient

from echosense.product_app import app

client = TestClient(app)


def test_landing_page_is_available() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "EchoSense" in response.text
    assert "EchoSense listens to you" in response.text
    assert "Current EchoSense recommendation" in response.text
    assert "Your Music DNA" in response.text


def test_product_copy_keeps_recommendations_provider_neutral() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "A connected provider gives EchoSense the permitted signals" in response.text
    assert "EchoSense will send you to Spotify to sign in" in response.text
    assert "your Spotify password is never entered here" in response.text
    assert "Sign in with Spotify" in response.text
    assert 'id="spotify-setup-panel"' in response.text
    assert "Spotify Client ID" in response.text
    assert "Spotify Client Secret" in response.text
    assert "Redirect URI" in response.text
    assert "Save setup and open Spotify sign-in" in response.text
    assert "These are Spotify app credentials" in response.text
    assert "EchoSense recommendation from your Music DNA" in response.text
    assert "[hidden] { display:none!important; }" in response.text
    assert "available listening evidence did not change this plan" in response.text
    assert "Connect a music provider for your real listening context" in response.text
    assert "more distinct provider candidates" in response.text
    assert "based on your Spotify taste" not in response.text
    assert "available Spotify evidence did not change this plan" not in response.text
    assert "more distinct Spotify candidates" not in response.text


def test_demo_profile_is_ready() -> None:
    response = client.get("/v1/demo/taste-profile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["display_name"] == "Mohan"
    assert payload["confidence"] > 0
    assert payload["genres"]
    assert payload["coach"]


def test_demo_insights_are_focused() -> None:
    response = client.get("/v1/demo/insights")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3
    assert all(item["title"] and item["detail"] for item in items)


def test_demo_timeline_is_available() -> None:
    response = client.get("/v1/demo/timeline")
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[-1]["period"] == "Now"


def test_demo_recommendations_are_explained() -> None:
    response = client.get("/v1/demo/recommendations")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert all(item["reason"] and item["match_score"] for item in items)


def test_demo_feedback_is_recorded() -> None:
    response = client.post(
        "/v1/demo/feedback",
        json={"recommendation_id": "demo-rec-1", "reaction": "play"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "recorded"


def test_browser_player_uses_explicit_playback_commands() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "player.togglePlay" not in response.text
    assert "restorePlaybackState" in response.text
    assert "/v1/player/pause" in response.text
    assert "/v1/player/play" in response.text
    assert "/v1/player/recommendations/" in response.text
    assert "currentPlayOutcomeId" in response.text
    assert "EchoSense Autopilot started" in response.text
    assert "lifecycle.activateElement()" in response.text
    assert "waitForAudibleBrowserPlayback" in response.text
    assert "Playing with browser audio" in response.text
    assert "Browser blocked audio" in response.text
    assert "browser audio did not start" in response.text
    assert "/auth/spotify/feedback" in response.text
    assert "pick.decision_id" in response.text
    assert "feedback('completed'" in response.text
    assert "feedback('skipped')" in response.text
    assert 'id="save"' in response.text
    assert "toggleSaved" in response.text
    assert "/auth/spotify/library/tracks/" in response.text
    assert "Saved to Spotify. EchoSense learned from this choice." in response.text
    assert 'id="playlists-panel"' in response.text
    assert "loadPlaylists" in response.text
    assert "loadPlaylistsSafely" in response.text
    assert "Spotify playlists are temporarily unavailable" in response.text
    assert "Promise.allSettled" in response.text
    assert "loadPlaylistTracks" in response.text
    assert "playPlaylistTrack" in response.text
    assert 'id="moment"' in response.text
    assert 'id="listening-controls"' in response.text
    assert "Shape what plays next" in response.text
    assert 'id="moment-panel"' in response.text
    assert "What are you doing?" in response.text
    assert "What should matter more?" in response.text
    assert 'id="moment-impact"' in response.text
    assert 'id="moment-proof"' in response.text
    assert "function renderMomentImpact(impact,item=null)" in response.text
    assert "No activity-specific candidate generation or reranking is applied" in response.text
    assert "entered through moment-specific candidates" in response.text
    assert 'id="intelligence-panel"' in response.text
    assert "Your listening intelligence" in response.text
    assert 'id="intelligence-metrics"' in response.text
    assert 'id="intelligence-history-list"' in response.text
    assert 'id="intelligence-product-metrics"' in response.text
    assert "Current-listener indicators only" in response.text
    assert "function renderListeningIntelligence(data)" in response.text
    assert "/auth/spotify/intelligence?history_limit=30" in response.text
    assert "Verified deletion unavailable" in response.text
    assert response.text.index('id="moment-panel"') < response.text.index('id="boost-panel"')
    assert response.text.index('id="boost-panel"') < response.text.index('id="live-context-panel"')
    assert "/auth/spotify/data?" in response.text
    assert "Context evidence:" in response.text
    assert 'id="provider-resilience"' in response.text
    assert "Spotify is cooling down" in response.text
    assert "lastSpotifyData" in response.text
    assert "spotifyProviderCooldownUntil" in response.text
    assert "Date.now()<spotifyProviderCooldownUntil&&lastSpotifyData" in response.text
    assert "Cached playback plan active. No reconnect is needed." in response.text
    assert 'id="provider-health"' in response.text
    assert 'id="provider-resilience-details"' in response.text
    assert "/auth/spotify/resilience/status" in response.text
    assert "Spotify development quota reached" in response.text
    assert "EchoSense prevented a Spotify lockout" in response.text
    assert "no reconnect needed" in response.text
    assert "Spotify protected · cached" in response.text
    assert "$('#context-statement').hidden=cachedPlan" in response.text
    assert (
        "data.resilience={...(data.resilience||{}),...(spotifyProviderCooldownStatus||{}),mode:'last_known_good'}"
        in response.text
    )
    assert "const spotifyDataInFlight = new Map()" in response.text
    assert "function invalidateSpotifyRecommendationCache()" in response.text
    assert response.text.count("invalidateSpotifyRecommendationCache();") >= 3
    assert "if(spotifyDataInFlight.has(key))" in response.text
    assert "disconnectSpotify" in response.text
    assert "/auth/spotify/logout" in response.text
    assert "setInterval(updateProgressClock,500)" in response.text
    assert "Last session restored · choose a device to resume" in response.text
    assert "continuity?.requires_confirmation" in response.text
    assert 'id="device-picker"' in response.text
    assert "loadDevices" in response.text
    assert "transferSelectedDevice" in response.text
    assert 'id="queue-panel"' in response.text
    assert "loadQueue" in response.text
    assert "Spotify returned an incomplete listening profile" in response.text
    assert "detail.detail?.code" in response.text
    assert 'id="shuffle"' in response.text
    assert 'id="repeat"' in response.text
    assert "/v1/player/shuffle" in response.text
    assert "/v1/player/repeat" in response.text
    assert 'id="dna-queue-panel"' in response.text
    assert "playDnaTrack" in response.text
    assert "maintainAutopilot" in response.text
    assert "EchoSense controls playback" in response.text
    assert "recommendationExplanation" in response.text
    assert "item.why_now?.summary||contextReason" in response.text
    assert "Picked because ${factors.join(', ')}" not in response.text
    autopilot = response.text[
        response.text.index("async function maintainAutopilot") : response.text.index(
            "function recommendationExplanation"
        )
    ]
    assert "/v1/player/queue" not in autopilot
    assert "DNA_ROUND_SIZE = 6" in response.text
    assert "AUTOPILOT_HORIZON = DNA_ROUND_SIZE" in response.text
    assert "autopilotTimer=setInterval" in response.text
    assert "updateCurrentPick=true" in response.text
    assert "if(!updateCurrentPick){renderDnaQueue();return data;}" in response.text
    assert "EchoSense playback plan" in response.text
    assert "<h2>Up next</h2>" in response.text
    assert 'id="dna-pagination"' in response.text
    assert "rememberDnaRound" in response.text
    assert "generateNextDnaRound('completed')" in response.text
    assert "if(roundGenerationInFlight)return roundGenerationInFlight" in response.text
    assert "if(skipInFlight)return" in response.text
    assert "completionTransitionInFlight" in response.text
    assert "playbackPlanReconciliationInFlight" in response.text
    assert "playbackCommandInFlight" in response.text
    assert "function playbackPlanSuccessor(trackId)" in response.text
    assert "async function reconcilePlaybackPlan(previousTrackId,observedTrackId)" in response.text
    assert "await playDnaTrack(expected)" in response.text
    assert "Spotify advanced outside the EchoSense Playback Plan" in response.text
    assert "if(observedDecisionId)" in response.text
    assert "const completedIndex=activeRound.findIndex" in response.text
    assert ".slice(transitionsIntoNewestPlan?0:completedIndex+1)" in response.text
    assert "await playDnaTrack(next)" in response.text
    assert "dnaContinuationDecisionIds" in response.text
    assert "continuation_decision_ids:dnaContinuationDecisionIds(item)" in response.text
    assert "continuation_decision_ids:dnaContinuationDecisionIds(nextDna)" in response.text
    assert "continued with ${next.title} from your Playback Plan" in response.text
    live_loader = response.text[
        response.text.index("async function loadLiveSpotify(") : response.text.index(
            "async function loadDemo()"
        )
    ]
    assert "return data;" in live_loader
    assert "skipAndPlayNext(true)" in response.text
    assert ">▶ Play</button>" in response.text
    assert "Skip current song" in response.text
    assert 'id="pick-label"' in response.text
    assert "Current EchoSense recommendation" in response.text
    assert "activePlaybackDecisionId" in response.text
    assert "decisionByTrackId" in response.text
    assert "function syncRecommendationSurfaces(trackId)" in response.text
    assert "async function changeListeningMoment()" in response.text
    assert "pendingPlanTransitionFromTrackId=activePlaybackTrackId" in response.text
    assert "trackId===pendingPlanTransitionFromTrackId" in response.text
    assert "then EchoSense will play this newly ranked plan" in response.text
    assert "syncRecommendationSurfaces(item.id)" in response.text
    assert "syncRecommendationSurfaces(nextDna.id)" in response.text
    assert "let liveRecommendationReady = false" in response.text
    assert "liveRecommendationReady=true" in response.text
    assert "function bindControls()" in response.text
    assert "function resetProviderStatus()" in response.text
    assert "function showSpotifySetup(config={})" in response.text
    assert "function refreshSpotifySetupState()" in response.text
    assert "function connectStreamingService(event)" in response.text
    assert "function saveSpotifySetup(event)" in response.text
    assert "function showSpotifyCallbackNotice()" in response.text
    assert "Spotify sign-in expired or was opened from an old tab." in response.text
    assert "Spotify sign-in needs local token storage setup first." in response.text
    assert "EchoSense could not open local token storage." in response.text
    assert "showSpotifyCallbackNotice();" in response.text
    assert "Enter the Spotify app Client ID and Client Secret" in response.text
    assert "Client ID, Client Secret, and Redirect URI are all required." in response.text
    assert "Setup saved for this local session. Opening Spotify sign-in..." in response.text
    assert "spotifyConnected?disconnectSpotify(event)" in response.text
    assert "$('#connect-button').addEventListener('click',connectStreamingService)" in response.text
    assert "$('#spotify-setup-form').addEventListener('submit'" in response.text
    assert "function requireStreamingConnection(action='playing this track')" in response.text
    assert "Connect a streaming service before ${action}." in response.text
    assert "Demo recommendations are preview-only until a provider is connected." in response.text
    assert "async function loadConnectedSpotifyExperience(session)" in response.text
    assert "Demo mode is ready while Spotify recovers." in response.text
    assert "Spotify connected · recommendation data unavailable" in response.text
    assert "bindControls();" in response.text
    assert (
        "const session=await loadSpotifySession(); if(session){ await loadConnectedSpotifyExperience(session); }"
        in response.text
    )
    assert "aria-current" in response.text
    assert (
        "const sameTrackFinished=track?.id&&track.id===previous?.track_window?.current_track?.id"
        in response.text
    )
    assert "activePlaybackDecisionId && sameTrackFinished" in response.text
    assert (
        "const decisionId=activePlaybackTrackId?activePlaybackDecisionId:currentRecommendationId"
        in response.text
    )
    assert 'id="queue-add"' not in response.text
    assert 'id="dna-queue-add"' not in response.text
    assert "Skip &amp; play next" not in response.text
    assert "skipAndPlayNext" in response.text
    assert "skipInFlight" in response.text
    assert "Spotify did not start the selected EchoSense recommendation" in response.text
    assert "if(!requireStreamingConnection('playing this track'))return;" in response.text
    assert "if(!requireStreamingConnection('controlling playback'))return;" in response.text
    assert (
        "Spotify recommendations are temporarily unavailable. Refresh EchoSense to retry."
        in response.text
    )
    assert "Promise.allSettled([loadQueue(),recommendationRefresh])" in response.text
    assert "const refreshExclusions=startNewRound" in response.text
    assert "refreshExclusions," in response.text
    assert (
        "selected the next planned recommendation and verified ${title} is playing" in response.text
    )
    assert "targetDeviceId=before?.device?.id||deviceId||''" in response.text
    assert "state?.continuity?.source!=='snapshot'" in response.text
    assert "nextDna=orderedCandidates.find" in response.text
    assert (
        "/v1/player/recommendations/${encodeURIComponent(nextDna.decision_id)}/play"
        in response.text
    )
    assert "nextId===nextDna.id" in response.text
    assert (
        "api(`/v1/player/next?"
        not in response.text[
            response.text.index(
                "async function skipAndPlayNext(startNewRound=false)"
            ) : response.text.index("async function load()")
        ]
    )
    assert "className='dna-table'" in response.text
    assert "factorExplanations" in response.text
    assert "function renderScoreRecipe(item)" in response.text
    assert "className='score-ring'" in response.text
    assert "className='factor-meter'" in response.text
    assert "Taste match" in response.text
    assert "Moment fit" in response.text
    assert "Learning" in response.text
    assert "Freshness" in response.text
    assert "Matches this track to the artists, genres, and songs you enjoy" in response.text
    assert "Checks the current time, weather, area, road, and activity" in response.text
    assert "Learns from your plays, completions, saves, and skips" in response.text
    assert "Limits recently repeated tracks and artists" in response.text
    assert response.text.count("Why it matters:") == 4
    assert "className='factor-info'" in response.text
    assert "info.setAttribute('aria-label'" in response.text
    assert "EchoSense Recommendation Score: the final normalized result" in response.text
    assert "% EchoSense score" in response.text
    assert "Final score" in response.text
    assert "Why this fits" in response.text
    assert "Compare what shaped each pick." not in response.text
    assert 'id="queue-skip"' in response.text
    assert 'id="live-context-panel"' in response.text
    assert "enableLiveContext" in response.text
    assert "navigator.geolocation.watchPosition" in response.text
    assert "/v1/context/resolve" in response.text
    assert "road_setting" in response.text
    assert "road_setting?.replace" in response.text
    assert "raw coordinates are not stored" in response.text
    assert "why_now?.factors" in response.text
    assert 'id="temporal-mood-panel"' in response.text
    assert "renderTemporalMood" in response.text
    assert "/auth/spotify/temporal-mood/correct" in response.text
    assert "/auth/spotify/temporal-mood/settings" in response.text
    assert "Temporal mood patterns reset" in response.text
    assert "never your mental or medical state" in response.text
    from echosense.product_ui import PLAYER_LIFECYCLE_VERSION

    assert f"/ui/player-lifecycle.js?v={PLAYER_LIFECYCLE_VERSION}" in response.text
    assert "__PLAYER_LIFECYCLE_VERSION__" not in response.text

    lifecycle = client.get("/ui/player-lifecycle.js")
    assert lifecycle.status_code == 200
    assert "class PlayerLifecycle" in lifecycle.text
    assert "activateElement()" in lifecycle.text
    assert lifecycle.headers["cache-control"] == "no-store, max-age=0"


def test_explainable_product_surface_is_complete_and_governance_is_honest() -> None:
    response = client.get("/")
    assert response.status_code == 200
    page = response.text

    assert 'id="hero-cover"' in page
    assert 'id="why-pill"' in page
    assert 'id="hero-factors"' in page
    assert "renderHeroFactors" in page
    assert 'id="factor-modal"' in page
    assert "factorFormulas" in page
    assert "DNA affinity = (0.60 × artist/track affinity) + (0.40 × category fit)" in page

    assert 'id="episodic-memory"' in page
    assert 'id="semantic-memory"' in page
    assert 'id="working-memory"' in page
    assert "renderMemory" in page

    assert 'id="consent-context"' in page
    assert 'id="consent-retention"' in page
    assert 'id="delete-data"' in page
    assert 'delete-data" class="danger" type="button" disabled' in page
    assert (
        "Deletion remains locked until the receipt-generating governance endpoint is implemented."
        in page
    )
    assert "Server-side enforcement requires the governance API." in page
    assert "Any moment is selected" in page
    assert "Choose Driving, Working, Exercising, Relaxing, or Social" in page
    assert "factor.name==='Diversity guard'" in page
    assert "?'Passed':'Limited'" in page
    assert "function factorInfoButton(name,location='Recommendation')" in page
    assert "`${location} factor: ${name}. ${factorExplanations[name]}`" in page
    assert "You selected general" not in page
    assert "Why it matters: your queue stays fresh" in page
    assert "factorInfoButton(label,'Priority')" in page
    assert "factorInfoButton(factor.name,'Current recommendation')" in page
    assert "factorInfoButton(factor.name,'Queue')" in page
    assert 'id="dna-load-more"' in page
    assert "Plan ${dnaPageIndex+1} of ${dnaRounds.length}" in page


def test_recommendation_boosters_drive_every_spotify_recommendation_request() -> None:
    page = client.get("/").text

    assert 'id="boost-controls"' in page
    assert 'id="context-statement"' in page
    assert "boostDefinitions.forEach(([key])=>params.set(`boost_${key}`" in page
    assert "echosenseRecommendationBoosts" in page
    assert "data.context_statement" in page
    assert "async function changeRecommendationBoost(label)" in page
    assert "changeRecommendationBoost(label)" in page
    assert "`${label} boost`" in page
    assert "pendingPlanTransitionLabel" in page


def test_saved_library_status_is_cached_deduplicated_and_rate_limit_aware() -> None:
    page = client.get("/").text

    assert "if(changed)refreshSavedState(item.id)" in page
    assert "const savedStateCache = new Map()" in page
    assert "const savedStateRequests = new Map()" in page
    assert "savedStateRequests.has(trackId)" in page
    assert "now<savedStateCooldownUntil" in page
    assert "error.status===429" in page
    assert "error.retryAfter" in page


def test_live_context_names_unavailable_movement_instead_of_showing_unknown() -> None:
    page = client.get("/").text

    assert "?'Movement unavailable':liveContext.activity.replace" in page
    assert "Road setting unavailable" in page
    assert "liveContext.activity?.replace('_',' ')" not in page


def test_playback_verification_prefers_owned_dna_and_collapses_provider_duplicates() -> None:
    page = client.get("/").text

    assert "Now and next · EchoSense controlled" in page
    assert 'id="queue-status"' in page
    assert "const providerUnique=[...new Map" in page
    assert "const momentTransition=currentId&&currentId===pendingPlanTransitionFromTrackId" in page
    assert "? dnaRounds.at(-1)" in page
    assert "ownedTracks.length?ownedTracks:providerUnique" in page
    assert "repeated Spotify queue entr" in page
    assert "EchoSense Playback Plan" in page
    assert "Spotify diagnostic view" in page


def test_final_playback_plan_names_the_exact_ranked_dna_sequence() -> None:
    page = client.get("/").text

    assert "EchoSense playback plan" in page
    assert "<h2>Up next</h2>" in page
    assert "Your ranked listening order." in page
    assert 'id="dna-plan-statement"' in page
    assert "Plan ${dnaPageIndex+1} of ${dnaRounds.length}" in page
    assert "Prepare six more" in page
    assert "Final score" in page
    assert "Why this fits" in page
    assert "item.why_now?.overall_score??item.match_score" in page
    assert "Final EchoSense score after all signals are combined" in page
