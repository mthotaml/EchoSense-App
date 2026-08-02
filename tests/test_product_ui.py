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


def test_demo_profile_is_ready() -> None:
    response = client.get("/v1/demo/taste-profile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
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
    assert "Personalize what EchoSense plays next" in response.text
    assert 'id="moment-panel"' in response.text
    assert "What are you doing right now?" in response.text
    assert "What should matter more?" in response.text
    assert response.text.index('id="moment-panel"') < response.text.index('id="boost-panel"')
    assert response.text.index('id="boost-panel"') < response.text.index('id="live-context-panel"')
    assert "/auth/spotify/data?" in response.text
    assert "Context evidence:" in response.text
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
    assert "Picked because ${factors.join(', ')}" in response.text
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
    assert "Decision-owned sequence" in response.text
    assert "Tracks EchoSense plans to play—in this exact order" in response.text
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
    assert ".slice(completedIndex+1)" in response.text
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
    assert "factorNames" in response.text
    assert "factorExplanations" in response.text
    assert "How closely this track matches your long-term Spotify taste" in response.text
    assert "How well this track fits your current time, weather" in response.text
    assert "An adjustment learned from your plays, completions, saves, and skips" in response.text
    assert "avoids repeating the same tracks or artists" in response.text
    assert "className='factor-info'" in response.text
    assert "info.setAttribute('aria-label'" in response.text
    assert "EchoSense Recommendation Score: the final normalized result" in response.text
    assert "% EchoSense score" in response.text
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
    assert "`${factor.name}: ${factorExplanations[factor.name]}`" in page
    assert "`Queue factor: ${label}. ${explanation}`" in page
    assert "You selected general" not in page
    assert "A repetition safeguard, not a recommendation-match score" in page
    assert 'id="dna-load-more"' in page
    assert "Plan ${dnaPageIndex+1} of ${dnaRounds.length}" in page


def test_recommendation_boosters_drive_every_spotify_recommendation_request() -> None:
    page = client.get("/").text

    assert 'id="boost-controls"' in page
    assert 'id="context-statement"' in page
    assert "boostDefinitions.forEach(([key])=>params.set(`boost_${key}`" in page
    assert "echosenseRecommendationBoosts" in page
    assert "data.context_statement" in page


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
    assert "const ownedRound=[...dnaRounds].reverse().find" in page
    assert "ownedTracks.length?ownedTracks:providerUnique" in page
    assert "repeated Spotify queue entr" in page
    assert "EchoSense Playback Plan" in page
    assert "Spotify diagnostic view" in page


def test_final_playback_plan_names_the_exact_ranked_dna_sequence() -> None:
    page = client.get("/").text

    assert "Final EchoSense playback plan" in page
    assert "Tracks EchoSense plans to play—in this exact order" in page
    assert "after Music DNA affinity, live context, learned preference" in page
    assert 'id="dna-plan-statement"' in page
    assert "Decision-owned sequence" in page
    assert "Plan ${dnaPageIndex+1} of ${dnaRounds.length}" in page
    assert "Prepare another six-track plan" in page
    assert "EchoSense recommendation score" in page
    assert "item.why_now?.overall_score" in page
    assert "Final EchoSense Recommendation Score after all factors and boosts" in page
