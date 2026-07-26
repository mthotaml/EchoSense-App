from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from echosense.music_dna_service import music_dna_service

router = APIRouter(tags=["product-ui"])
UI_DIR = Path(__file__).with_name("web")


class DemoFeedbackRequest(BaseModel):
    recommendation_id: str
    reaction: Literal["love", "not_for_me", "save", "play"]


@router.get("/", response_class=HTMLResponse)
def landing_page() -> str:
    return PAGE


@router.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    return PAGE


@router.get("/ui/player-lifecycle.js", include_in_schema=False)
def player_lifecycle_script() -> FileResponse:
    return FileResponse(UI_DIR / "player-lifecycle.js", media_type="text/javascript")


@router.get("/v1/demo/taste-profile")
def demo_taste_profile() -> dict[str, object]:
    return music_dna_service.get_profile()


@router.get("/v1/demo/insights")
def demo_insights() -> dict[str, object]:
    return {"items": music_dna_service.get_insights()}


@router.get("/v1/demo/timeline")
def demo_timeline() -> dict[str, object]:
    return {"items": music_dna_service.get_timeline()}


@router.get("/v1/demo/recommendations")
def demo_recommendations() -> dict[str, object]:
    return {
        "items": music_dna_service.get_recommendations(),
        "generated_at": datetime.now(UTC),
    }


@router.post("/v1/demo/feedback", status_code=202)
def demo_feedback(request: DemoFeedbackRequest) -> dict[str, str]:
    return music_dna_service.record_feedback(
        recommendation_id=request.recommendation_id,
        reaction=request.reaction,
    )


PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EchoSense — Listen here</title>
  <style>
    :root { color-scheme:dark; --bg:#07090d; --surface:#11151d; --soft:#0c1017; --text:#f5f7fb; --muted:#929caf; --line:#242b38; --accent:#d8ffea; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:radial-gradient(circle at 50% -12%,#172133 0,#07090d 38%); color:var(--text); padding-bottom:112px; }
    nav { max-width:920px; margin:auto; padding:24px; display:flex; justify-content:space-between; align-items:center; gap:20px; }
    .brand { font-weight:760; letter-spacing:-.04em; font-size:1.2rem; }
    .account { display:flex; align-items:center; gap:12px; color:var(--muted); font-size:.9rem; }
    main { max-width:920px; margin:auto; padding:48px 24px 72px; }
    .intro { max-width:720px; margin-bottom:38px; }
    .eyebrow { color:var(--accent); font-size:.76rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; }
    h1 { margin:14px 0; font-size:clamp(2.9rem,7vw,5.5rem); line-height:.98; letter-spacing:-.065em; }
    h2 { margin:10px 0 12px; font-size:1.65rem; letter-spacing:-.035em; }
    .lead,.copy,.connection-copy { color:var(--muted); line-height:1.6; }
    .stack { display:grid; gap:18px; }
    .panel { background:rgba(17,21,29,.93); border:1px solid var(--line); border-radius:24px; padding:clamp(24px,4vw,38px); }
    .connection,.pick-top { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; }
    .track { margin:16px 0 4px; font-size:clamp(2.2rem,6vw,4.4rem); letter-spacing:-.055em; line-height:1; }
    .artist { color:var(--muted); font-size:1.15rem; }
    .match { color:var(--accent); font-weight:700; white-space:nowrap; margin-top:18px; }
    .reason { max-width:650px; margin:26px 0 30px; color:#c9d0db; font-size:1.08rem; line-height:1.65; }
    .evidence { color:var(--muted); font-size:.9rem; margin:-16px 0 24px; }
    .actions { display:flex; gap:10px; flex-wrap:wrap; }
    button,select,.button-link { border:1px solid #343d4f; border-radius:12px; padding:12px 16px; font:inherit; font-weight:680; cursor:pointer; text-decoration:none; display:inline-block; }
    .primary { background:#f5f7fb; color:#090b10; border-color:#f5f7fb; }
    .secondary { background:#171d27; color:var(--text); }
    button:disabled { opacity:.45; cursor:not-allowed; }
    .small-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
    .dna-list { display:grid; gap:14px; margin-top:22px; }
    .dna-line { display:flex; justify-content:space-between; gap:20px; padding-bottom:14px; border-bottom:1px solid var(--line); }
    .journey { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:22px; }
    .journey-step { padding:10px 13px; background:var(--soft); border:1px solid var(--line); border-radius:999px; }
    .arrow { color:#667186; }
    #toast { min-height:22px; margin-top:14px; color:var(--accent); }
    .player { position:fixed; left:0; right:0; bottom:0; z-index:20; min-height:96px; border-top:1px solid #30394a; background:rgba(8,11,16,.96); backdrop-filter:blur(18px); display:grid; grid-template-columns:minmax(220px,1fr) minmax(280px,1.3fr) minmax(180px,1fr); align-items:center; gap:24px; padding:14px 24px; }
    .now { display:flex; min-width:0; align-items:center; gap:12px; }
    .cover { width:64px; height:64px; border-radius:10px; background:#1b2230; object-fit:cover; flex:0 0 auto; }
    .meta { min-width:0; }
    .meta strong,.meta span { display:block; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
    .meta span,.player-status { color:var(--muted); font-size:.88rem; margin-top:4px; }
    .transport { display:grid; justify-items:center; gap:8px; }
    .controls { display:flex; align-items:center; gap:10px; }
    .icon { width:40px; height:40px; border-radius:50%; padding:0; background:#171d27; color:var(--text); }
    .toggle { width:46px; height:46px; background:#f5f7fb; color:#090b10; }
    .progress-row { width:min(100%,520px); display:grid; grid-template-columns:40px 1fr 40px; align-items:center; gap:9px; color:var(--muted); font-size:.75rem; }
    input[type=range] { width:100%; accent-color:#f5f7fb; }
    .player-side { display:flex; justify-content:flex-end; align-items:center; gap:10px; }
    .volume { width:110px; }
    @media (max-width:760px) { .small-grid { grid-template-columns:1fr; } .pick-top,.connection { display:block; } .player { grid-template-columns:1fr auto; padding:12px; } .transport { justify-items:end; } .progress-row,.player-side { display:none; } .cover { width:52px; height:52px; } .account span { display:none; } }
  </style>
</head>
<body>
  <nav><div class="brand">EchoSense</div><div class="account"><span id="account-status">Spotify not connected</span><a id="account-action" class="button-link secondary" href="/auth/spotify/login">Connect Spotify</a></div></nav>
  <main>
    <section class="intro"><div class="eyebrow">Your daily listening companion</div><h1 id="greeting">Good evening.</h1><p class="lead">EchoSense listens to you. A persistent listening surface powered by your Music DNA.</p></section>
    <section id="connection-panel" class="panel connection"><div><div class="eyebrow">Train once. Listen everywhere.</div><h2 id="connection-title">Connect your first music provider</h2><p id="connection-copy" class="connection-copy">Spotify gives EchoSense the signals needed to begin building your real Music DNA.</p></div><a id="connect-button" class="button-link primary" href="/auth/spotify/login">Connect Spotify</a></section>
    <div class="stack">
      <section class="panel"><div class="pick-top"><div><div class="eyebrow">Today's pick</div><h2 id="pick-heading" class="track">Finding your track…</h2><div id="artist" class="artist"></div></div><div id="match" class="match"></div></div><p id="reason" class="reason">Listening to your recent patterns…</p><p id="evidence" class="evidence"></p><div class="actions"><select id="moment" class="secondary" aria-label="Listening moment"><option value="general">Any moment</option><option value="driving">Driving</option><option value="working">Working</option><option value="exercising">Exercising</option><option value="relaxing">Relaxing</option><option value="social">Social</option></select><button id="play" class="primary" type="button">Play in EchoSense</button><button id="save" class="secondary" type="button" aria-pressed="false" disabled>Save</button><button id="skip" class="secondary" type="button">Not for me</button></div><div id="toast" aria-live="polite"></div></section>
      <div class="small-grid"><section class="panel"><div class="eyebrow">EchoSense noticed</div><h2>One thing worth knowing</h2><p id="insight" class="copy">Reading your listening…</p></section><section class="panel"><div class="eyebrow">Your Music DNA</div><h2>A simple view of your taste</h2><div id="dna" class="dna-list"></div></section></div>
      <section class="panel"><div class="eyebrow">Your journey</div><h2>Your taste, told as a story</h2><div id="timeline" class="journey"></div></section>
    </div>
  </main>

  <section class="player" aria-label="EchoSense player">
    <div class="now"><img id="player-cover" class="cover" alt=""><div class="meta"><strong id="player-title">Nothing playing</strong><span id="player-artist">Connect Spotify to listen here</span><span id="player-status" class="player-status">EchoSense Browser</span></div></div>
    <div class="transport"><div class="controls"><button id="previous" class="icon" aria-label="Previous">‹</button><button id="toggle" class="icon toggle" aria-label="Play or pause">▶</button><button id="next" class="icon" aria-label="Next">›</button></div><div class="progress-row"><span id="elapsed">0:00</span><input id="progress" type="range" min="0" max="1000" value="0"><span id="duration">0:00</span></div></div>
    <div class="player-side"><span>🔊</span><input id="volume" class="volume" type="range" min="0" max="100" value="70"><button id="activate" class="secondary" type="button">Use this browser</button></div>
  </section>

  <script src="https://sdk.scdn.co/spotify-player.js"></script>
  <script src="/ui/player-lifecycle.js"></script>
  <script>
    let currentRecommendationId = null;
    let currentTrackUri = null;
    let currentTrackId = null;
    let currentTrackSaved = false;
    let spotifyConnected = false;
    let deviceId = null;
    let playerState = null;
    let progressTimer = null;
    let restoreRequest = 0;
    const reportedSignals = new Set();
    const lifecycle = new EchoSensePlayerLifecycle.PlayerLifecycle({
      createPlayer: SpotifyApi => new SpotifyApi.Player({name:'EchoSense Browser',volume:.7,getOAuthToken:async cb=>{try{const token=await (await api('/v1/player/token')).json();cb(token.access_token);}catch(e){setText('#toast',e.message);}}}),
      onReady: async ({device_id}) => {deviceId=device_id;setText('#player-status','EchoSense Browser ready');$('#activate').disabled=false;await restorePlaybackState();},
      onNotReady: () => setText('#player-status','EchoSense Browser offline'),
      onPlayback: renderPlayer,
      onError: (_, error) => {setText('#toast',error.message);setText('#player-status','Player needs attention');}
    });

    const $ = (selector) => document.querySelector(selector);
    const setText = (selector, value) => { $(selector).textContent = value || ''; };
    const greetingForHour = (h) => h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
    const formatTime = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2,'0')}`;
    const spotifyUri = (url, id) => id ? `spotify:track:${id}` : (url || '').replace('https://open.spotify.com/track/', 'spotify:track:').split('?')[0];

    function dnaLine(label, value) { const row=document.createElement('div'); row.className='dna-line'; const key=document.createElement('span'); key.textContent=label; const strong=document.createElement('strong'); strong.textContent=value; row.append(key,strong); return row; }
    function renderTimeline(items) { const c=$('#timeline'); c.replaceChildren(); items.forEach((label,index)=>{ if(index){const a=document.createElement('span');a.className='arrow';a.textContent='→';c.appendChild(a);} const s=document.createElement('span');s.className='journey-step';s.textContent=label;c.appendChild(s); }); }

    async function api(path, options={}) {
      const response = await fetch(path, {headers:{'Content-Type':'application/json', ...(options.headers||{})}, ...options});
      if (!response.ok && response.status !== 204) { let detail={}; try { detail=await response.json(); } catch (_) {} throw new Error(detail.detail?.spotify?.error?.message || detail.detail?.message || `Request failed (${response.status})`); }
      return response;
    }

    async function loadSpotifySession() {
      const response = await fetch('/auth/spotify/session');
      if (!response.ok) return null;
      const session = await response.json(); spotifyConnected = session.connected;
      if (!session.connected) return null;
      const name = session.profile.display_name || 'Spotify listener';
      setText('#account-status', `Connected as ${name}`); setText('#account-action','Disconnect'); $('#account-action').href='#';
      setText('#connection-title', `Spotify connected as ${name}`); setText('#connection-copy','Your Spotify history and browser player are powering EchoSense.');
      setText('#connect-button','Reconnect for player permissions'); $('#connect-button').href='/auth/spotify/login';
      return session;
    }

    async function disconnectSpotify(event) {
      if(!spotifyConnected)return;
      event.preventDefault();
      await api('/auth/spotify/logout',{method:'POST'});
      spotifyConnected=false;
      location.reload();
    }

    async function loadLiveSpotify(moment=$('#moment').value) {
      const data = await (await fetch(`/auth/spotify/data?moment=${encodeURIComponent(moment)}`)).json(); const profile=data.profile; const pick=data.recommendation;
      setText('#greeting', `${greetingForHour(new Date().getHours())}, ${profile.display_name}.`);
      if (pick) { setText('#pick-heading',pick.title); setText('#artist',`${pick.artist} · From your Spotify taste`); setText('#match',`${pick.match_score}% match`); setText('#reason',pick.reason); const genres=pick.evidence?.matched_genres||[]; setText('#evidence',`${pick.evidence?.noticed||''} ${genres.length?`Context evidence: ${genres.join(', ')}.`:'EchoSense is using your ranked listening history.'}`); currentRecommendationId=pick.decision_id; currentTrackId=pick.id; currentTrackUri=spotifyUri(pick.spotify_url,pick.id); reportedSignals.clear(); await refreshSavedState(pick.id); }
      setText('#insight',data.insight); const dna=$('#dna'); dna.replaceChildren(); const genres=profile.genres||[];
      dna.appendChild(dnaLine('Mostly',genres[0]?.name||'Still learning')); dna.appendChild(dnaLine('Also drawn to',genres[1]?.name||'More signals needed')); dna.appendChild(dnaLine('Popularity profile',profile.average_popularity>=70?'Mainstream':profile.average_popularity>=40?'Balanced':'Deep cuts'));
      renderTimeline(data.timeline.length?data.timeline:['Connected','Listening','Learning']);
    }

    async function loadDemo() {
      const [p,i,r,t]=await Promise.all(['/v1/demo/taste-profile','/v1/demo/insights','/v1/demo/recommendations','/v1/demo/timeline'].map(x=>fetch(x).then(y=>y.json()))); const pick=r.items[0];
      setText('#greeting',`${greetingForHour(new Date().getHours())}, ${p.display_name}.`); setText('#pick-heading',pick.title); setText('#artist',`${pick.artist} · ${pick.context}`); setText('#match',`${pick.match_score}% match`); setText('#reason',pick.reason); setText('#insight',i.items[0].detail); currentRecommendationId=pick.recommendation_id;
      setText('#evidence','Demo evidence · Connect Spotify for your real listening context.');
      const dna=$('#dna'); dna.replaceChildren(); dna.appendChild(dnaLine('Mostly',p.genres[0].name)); dna.appendChild(dnaLine('Recently exploring',p.genres[2].name)); dna.appendChild(dnaLine('Listening rhythm','After 8 PM')); renderTimeline(t.items.map(x=>x.label));
    }

    function normalizePlayerState(state) {
      if (!state) return null;
      if (state.track_window) {
        return {...state, updatedAt:Date.now(), source:'sdk'};
      }
      const track=state.item;
      return {
        paused:!state.is_playing,
        position:state.progress_ms||0,
        duration:track?.duration_ms||0,
        track_window:{current_track:track},
        device:state.device||null,
        updatedAt:Date.now(),
        source:'api'
      };
    }

    function renderPlayer(rawState) {
      const state=normalizePlayerState(rawState);
      const previous=playerState;
      playerState=state;
      const track=state?.track_window?.current_track; const image=track?.album?.images?.[0]?.url;
      setText('#player-title',track?.name||'Nothing playing'); setText('#player-artist',track?.artists?.map(a=>a.name).join(', ')||'Choose a recommendation');
      $('#player-cover').src=image||''; $('#player-cover').style.visibility=image?'visible':'hidden'; $('#toggle').textContent=state?.paused?'▶':'❚❚';
      $('#progress').max=state?.duration||1000; $('#progress').value=state?.position||0; setText('#elapsed',formatTime(state?.position||0)); setText('#duration',formatTime(state?.duration||0));
      if(spotifyConnected && track?.id===currentTrackId && previous?.paused===false && state?.paused && state.duration && state.position/state.duration>=.95) {
        feedback('completed',{completion_ratio:state.position/state.duration,playback_seconds:state.position/1000}).catch(()=>{});
      }
    }

    function updateProgressClock() {
      if (!playerState) return;
      const elapsed=playerState.paused ? playerState.position : Math.min(playerState.duration, playerState.position + (Date.now()-playerState.updatedAt));
      $('#progress').value=elapsed; setText('#elapsed',formatTime(elapsed));
    }

    async function restorePlaybackState() {
      if (!spotifyConnected) return;
      const request=++restoreRequest;
      const response=await fetch('/v1/player/state');
      if (request!==restoreRequest) return;
      if (response.status===204) { renderPlayer(null); return; }
      if (!response.ok) return;
      const state=await response.json();
      renderPlayer(state);
      if (state.device?.id===deviceId) setText('#player-status','EchoSense Browser active');
      else if (state.device?.name) setText('#player-status',`Playing on ${state.device.name}`);
    }

    async function activateBrowser(play=false) {
      if (!deviceId) throw new Error('The EchoSense player is still starting.');
      await api('/v1/player/transfer',{method:'PUT',body:JSON.stringify({device_id:deviceId,play})}); lifecycle.markDeviceActive(); setText('#player-status','EchoSense Browser active');
    }

    function initializeSpotifyPlayer() {
      return lifecycle.setConnection(spotifyConnected);
    }

    window.onSpotifyWebPlaybackSDKReady = () => {
      lifecycle.setSdk(window.Spotify);
    };

    async function playRecommendation() { if(!spotifyConnected){location.href='/auth/spotify/login';return;} if(!deviceId) throw new Error('Player is not ready yet.'); await activateBrowser(false); await api('/v1/player/play',{method:'PUT',body:JSON.stringify({device_id:deviceId,spotify_uri:currentTrackUri})}); await feedback('played'); setText('#toast','Playing inside EchoSense.'); }
    function renderSavedState(saved) {
      currentTrackSaved=saved;
      $('#save').textContent=saved?'Saved':'Save';
      $('#save').setAttribute('aria-pressed',String(saved));
      $('#save').disabled=!spotifyConnected||!currentTrackId;
    }
    async function refreshSavedState(trackId) {
      $('#save').disabled=true;
      const status=await (await api(`/auth/spotify/library/tracks/${encodeURIComponent(trackId)}`)).json();
      if(currentTrackId===trackId) renderSavedState(status.saved);
    }
    async function toggleSaved() {
      if(!spotifyConnected||!currentTrackId||!currentRecommendationId)return;
      const trackId=currentTrackId;
      $('#save').disabled=true;
      const options=currentTrackSaved
        ? {method:'DELETE'}
        : {method:'PUT',body:JSON.stringify({outcome_id:`out_${crypto.randomUUID?.()||Date.now()}`,decision_id:currentRecommendationId})};
      const status=await (await api(`/auth/spotify/library/tracks/${encodeURIComponent(trackId)}`,options)).json();
      if(currentTrackId===trackId) renderSavedState(status.saved);
      setText('#toast',status.saved?'Saved to Spotify. EchoSense learned from this choice.':'Removed from Spotify.');
    }
    async function togglePlayback() {
      if(!spotifyConnected) { location.href='/auth/spotify/login'; return; }
      if(!deviceId) throw new Error('Player is not ready yet.');
      const latest=await lifecycle.player?.getCurrentState();
      if(latest) renderPlayer(latest); else await restorePlaybackState();
      if(playerState?.paused===false) {
        await api(`/v1/player/pause?device_id=${encodeURIComponent(deviceId)}`,{method:'PUT'});
        renderPlayer({...playerState,paused:true,position:Number($('#progress').value),updatedAt:Date.now()});
      } else {
        await activateBrowser(false);
        await api('/v1/player/play',{method:'PUT',body:JSON.stringify({device_id:deviceId,position_ms:Number($('#progress').value)})});
        if(playerState) renderPlayer({...playerState,paused:false,position:Number($('#progress').value),updatedAt:Date.now()});
      }
    }
    async function feedback(signal,metrics={}) {
      if(!currentRecommendationId)return;
      if(!spotifyConnected) {
        const reaction=signal==='skipped'?'not_for_me':signal;
        await api('/v1/demo/feedback',{method:'POST',body:JSON.stringify({recommendation_id:currentRecommendationId,reaction})});
      } else {
        const key=`${currentRecommendationId}:${signal}`;
        if(reportedSignals.has(key))return;
        const outcomeId=`out_${crypto.randomUUID?.()||Date.now()}`;
        await api('/auth/spotify/feedback',{method:'POST',body:JSON.stringify({outcome_id:outcomeId,decision_id:currentRecommendationId,signal,...metrics})});
        reportedSignals.add(key);
      }
      setText('#toast','Understood. EchoSense will adjust your next pick.');
    }

    async function load() {
      $('#account-action').addEventListener('click',event=>disconnectSpotify(event).catch(e=>setText('#toast',e.message)));
      const session=await loadSpotifySession(); if(session){ initializeSpotifyPlayer(); await loadLiveSpotify(); } else await loadDemo();
      $('#play').addEventListener('click',()=>playRecommendation().catch(e=>setText('#toast',e.message)));
      $('#save').addEventListener('click',()=>toggleSaved().catch(e=>{renderSavedState(currentTrackSaved);setText('#toast',e.message);}));
      $('#skip').addEventListener('click',()=>feedback('skipped').catch(e=>setText('#toast',e.message)));
      $('#moment').addEventListener('change',()=>spotifyConnected&&loadLiveSpotify($('#moment').value).catch(e=>setText('#toast',e.message)));
      $('#toggle').addEventListener('click',()=>togglePlayback().catch(e=>setText('#toast',e.message)));
      $('#previous').addEventListener('click',()=>api(`/v1/player/previous?device_id=${encodeURIComponent(deviceId||'')}`,{method:'POST'}).then(restorePlaybackState).catch(e=>setText('#toast',e.message))); $('#next').addEventListener('click',()=>api(`/v1/player/next?device_id=${encodeURIComponent(deviceId||'')}`,{method:'POST'}).then(restorePlaybackState).catch(e=>setText('#toast',e.message)));
      $('#activate').disabled=true; $('#activate').addEventListener('click',()=>activateBrowser(false).catch(e=>setText('#toast',e.message)));
      $('#progress').addEventListener('change',()=>api('/v1/player/seek',{method:'PUT',body:JSON.stringify({device_id:deviceId,position_ms:Number($('#progress').value)})}).then(restorePlaybackState).catch(e=>setText('#toast',e.message)));
      $('#volume').addEventListener('input',()=>api('/v1/player/volume',{method:'PUT',body:JSON.stringify({device_id:deviceId,volume_percent:Number($('#volume').value)})}).catch(e=>setText('#toast',e.message)));
      progressTimer=setInterval(updateProgressClock,500);
      document.addEventListener('visibilitychange',()=>{if(!document.hidden) restorePlaybackState();});
      window.addEventListener('focus',restorePlaybackState);
      if(session) await restorePlaybackState();
    }
    load().catch(e=>setText('#toast',e.message||'EchoSense could not load.'));
  </script>
</body>
</html>"""
