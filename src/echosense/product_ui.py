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
    return FileResponse(
        UI_DIR / "player-lifecycle.js",
        media_type="text/javascript",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


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
    .playlist-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-top:20px; }
    .playlist-card { min-height:112px; text-align:left; background:var(--soft); color:var(--text); }
    .playlist-card strong,.playlist-card span { display:block; }
    .playlist-card span,.playlist-track span { color:var(--muted); font-size:.84rem; margin-top:6px; }
    .track-list { display:grid; gap:8px; margin-top:18px; }
    .playlist-track { width:100%; display:flex; justify-content:space-between; gap:18px; text-align:left; background:var(--soft); color:var(--text); }
    .track-copy { min-width:0; flex:1; }
    .track-actions { display:flex; align-items:center; gap:8px; flex:0 0 auto; }
    .track-actions button { padding:8px 11px; font-size:.78rem; }
    .playlist-track[disabled] { text-decoration:none; }
    button,select,.button-link { border:1px solid #343d4f; border-radius:12px; padding:12px 16px; font:inherit; font-weight:680; cursor:pointer; text-decoration:none; display:inline-block; }
    .primary { background:#f5f7fb; color:#090b10; border-color:#f5f7fb; }
    .secondary { background:#171d27; color:var(--text); }
    button:disabled { opacity:.45; cursor:not-allowed; }
    .small-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
    .dna-list { display:grid; gap:14px; margin-top:22px; }
    .dna-line { display:flex; justify-content:space-between; gap:20px; padding-bottom:14px; border-bottom:1px solid var(--line); }
    .journey { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:22px; }
    .journey-step { padding:10px 13px; background:var(--soft); border:1px solid var(--line); border-radius:999px; }
    .context-chips,.factor-chips { display:flex; flex-wrap:wrap; gap:7px; margin-top:12px; }
    .context-chip,.factor-chip { padding:7px 10px; border:1px solid var(--line); border-radius:999px; color:var(--muted); font-size:.78rem; }
    .factor-chip { padding:5px 8px; font-size:.72rem; }
    .context-compact { align-items:center; padding-block:24px; }
    .context-compact h2 { margin-bottom:5px; }
    .context-compact .connection-copy { margin:0; }
    .context-compact .context-chips { margin-top:10px; }
    .privacy-note { color:var(--muted); font-size:.78rem; margin-top:10px; }
    .privacy-note summary { cursor:pointer; width:max-content; }
    .table-wrap { overflow-x:auto; margin-top:20px; border:1px solid var(--line); border-radius:16px; }
    .dna-table { width:100%; min-width:840px; border-collapse:collapse; font-size:.86rem; }
    .dna-table th { padding:11px 12px; color:var(--muted); background:var(--soft); text-align:left; font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; white-space:nowrap; }
    .dna-table td { padding:14px 12px; border-top:1px solid var(--line); vertical-align:middle; }
    .dna-table td.metric { text-align:center; font-variant-numeric:tabular-nums; white-space:nowrap; }
    .dna-table .track-cell { min-width:210px; }
    .dna-table .track-cell strong,.dna-table .track-cell span { display:block; }
    .dna-table .track-cell span,.dna-table .why-cell { color:var(--muted); }
    .dna-table .why-cell { min-width:210px; line-height:1.35; }
    .dna-table .track-actions { white-space:nowrap; }
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
    <section id="live-context-panel" class="panel connection context-compact"><div><div class="eyebrow">Live context</div><h2>Why this music now</h2><p id="context-status" class="connection-copy">Time is automatic. Add weather and location when useful.</p><div id="context-chips" class="context-chips"></div><details class="privacy-note"><summary>Privacy</summary>Location is used only to resolve current conditions; raw coordinates are not stored.</details></div><button id="context-toggle" class="secondary" type="button">Enable context</button></section>
    <section id="temporal-mood-panel" class="panel connection"><div><div class="eyebrow">Learned listening rhythm</div><h2>Mood patterns, with your control</h2><p id="temporal-mood-status" class="connection-copy">EchoSense needs repeated qualified listening before it claims a time-based mood pattern.</p><div id="temporal-mood-chips" class="context-chips"></div><p class="evidence">Listening trends describe music choices, never your mental or medical state.</p></div><div class="actions"><button id="temporal-mood-correct" class="secondary" type="button" disabled>Not my pattern</button><button id="temporal-mood-toggle" class="secondary" type="button">Disable learning</button><button id="temporal-mood-reset" class="secondary" type="button">Reset patterns</button></div></section>
    <div class="stack">
      <section class="panel"><div class="pick-top"><div><div id="pick-label" class="eyebrow">Today's pick</div><h2 id="pick-heading" class="track">Finding your track…</h2><div id="artist" class="artist"></div></div><div id="match" class="match"></div></div><p id="reason" class="reason">Listening to your recent patterns…</p><p id="evidence" class="evidence"></p><div class="actions"><select id="moment" class="secondary" aria-label="Listening moment"><option value="general">Any moment</option><option value="driving">Driving</option><option value="working">Working</option><option value="exercising">Exercising</option><option value="relaxing">Relaxing</option><option value="social">Social</option></select><button id="play" class="primary" type="button">Play recommendation</button><button id="save" class="secondary" type="button" aria-pressed="false" disabled>Save</button><button id="skip" class="secondary" type="button">Skip current song</button></div><div id="toast" aria-live="polite"></div></section>
      <section id="dna-queue-panel" class="panel" hidden><div class="pick-top"><div><div class="eyebrow">Music DNA Autopilot</div><h2>Up next, continuously</h2><p class="copy">EchoSense keeps a rolling queue ready while you listen.</p><p id="autopilot-status" class="evidence" aria-live="polite">Autopilot starts with your first song.</p></div><span class="context-chip">Autopilot on</span></div><div id="dna-queue-items" class="table-wrap"></div></section>
      <section id="queue-panel" class="panel" hidden><div class="pick-top"><div><div class="eyebrow">Spotify playback queue</div><h2>Now and next</h2></div><div class="actions"><button id="queue-skip" class="primary" type="button">Skip to next</button><button id="queue-refresh" class="secondary" type="button">Refresh</button></div></div><div id="queue-items" class="track-list"></div></section>
      <section id="playlists-panel" class="panel" hidden><div class="pick-top"><div><div class="eyebrow">Your Spotify playlists</div><h2>Browse and play here</h2><p class="copy">Owned and collaborative playlists can play inside EchoSense.</p><p id="playlists-status" class="evidence" aria-live="polite"></p></div><button id="more-playlists" class="secondary" type="button" hidden>Load more</button></div><div id="playlists" class="playlist-grid"></div><div id="playlist-detail" hidden><h2 id="playlist-title"></h2><div id="playlist-tracks" class="track-list"></div><button id="more-tracks" class="secondary" type="button" hidden>Load more tracks</button></div></section>
      <div class="small-grid"><section class="panel"><div class="eyebrow">EchoSense noticed</div><h2>One thing worth knowing</h2><p id="insight" class="copy">Reading your listening…</p></section><section class="panel"><div class="eyebrow">Your Music DNA</div><h2>A simple view of your taste</h2><div id="dna" class="dna-list"></div></section></div>
      <section class="panel"><div class="eyebrow">Your journey</div><h2>Your taste, told as a story</h2><div id="timeline" class="journey"></div></section>
    </div>
  </main>

  <section class="player" aria-label="EchoSense player">
    <div class="now"><img id="player-cover" class="cover" alt=""><div class="meta"><strong id="player-title">Nothing playing</strong><span id="player-artist">Connect Spotify to listen here</span><span id="player-status" class="player-status">EchoSense Browser</span></div></div>
    <div class="transport"><div class="controls"><button id="previous" class="icon" aria-label="Previous">‹</button><button id="toggle" class="icon toggle" aria-label="Play or pause">▶</button><button id="next" class="icon" aria-label="Next">›</button></div><div class="progress-row"><span id="elapsed">0:00</span><input id="progress" type="range" min="0" max="1000" value="0"><span id="duration">0:00</span></div></div>
    <div class="player-side"><button id="shuffle" class="secondary" type="button" aria-pressed="false">Shuffle</button><select id="repeat" class="secondary" aria-label="Repeat mode"><option value="off">Repeat off</option><option value="context">Repeat context</option><option value="track">Repeat track</option></select><span>🔊</span><input id="volume" class="volume" type="range" min="0" max="100" value="70"><select id="device-picker" class="secondary" aria-label="Playback device"><option value="">Choose device</option></select><button id="transfer-device" class="secondary" type="button" disabled>Transfer</button><button id="activate" class="secondary" type="button">Use this browser</button></div>
  </section>

  <script src="https://sdk.scdn.co/spotify-player.js"></script>
  <script src="/ui/player-lifecycle.js?v=audible-playback-v2"></script>
  <script>
    let currentRecommendationId = null;
    let currentTrackId = null;
    let currentPlayOutcomeId = null;
    let currentQueueCommandId = null;
    let currentTrackSaved = false;
    let recommendationSlate = [];
    let activePlaybackTrackId = null;
    let activePlaybackDecisionId = null;
    const decisionByTrackId = new Map();
    let liveContext = null;
    let temporalMoodProfile = null;
    let contextWatchId = null;
    let lastContextKey = '';
    let playlistsNextOffset = null;
    let selectedPlaylistId = null;
    let tracksNextOffset = null;
    let spotifyConnected = false;
    let deviceId = null;
    let playerState = null;
    let progressTimer = null;
    let restoreRequest = 0;
    let skipInFlight = false;
    let autopilotFilling = false;
    let autopilotTimer = null;
    const autopilotHistory = [];
    const AUTOPILOT_HORIZON = 5;
    const reportedSignals = new Set();
    const lifecycle = new EchoSensePlayerLifecycle.PlayerLifecycle({
      createPlayer: SpotifyApi => new SpotifyApi.Player({name:'EchoSense Browser',volume:.7,getOAuthToken:async cb=>{try{const token=await (await api('/v1/player/token')).json();cb(token.access_token);}catch(e){setText('#toast',e.message);}}}),
      onReady: async ({device_id}) => {
        deviceId=device_id;
        $('#activate').disabled=false;
        const restored=await restorePlaybackState();
        if (!restored) setText('#player-status','EchoSense Browser ready');
      },
      onNotReady: () => setText('#player-status','EchoSense Browser offline'),
      onPlayback: renderPlayer,
      onError: (kind, error) => {
        const messages={
          autoplay_failed:'Browser blocked audio. Click Start listening again to allow sound.',
          account_error:'Browser playback requires Spotify Premium.',
          authentication_error:'Spotify player authorization expired. Reconnect Spotify.',
          initialization_error:'This browser could not initialize protected Spotify audio.',
          playback_error:'Spotify could not load audio in this browser. Reconnect the player and try again.',
        };
        setText('#toast',messages[kind]||error?.message||'Spotify playback needs attention.');
        setText('#player-status','Player needs attention');
      }
    });

    const $ = (selector) => document.querySelector(selector);
    const setText = (selector, value) => { $(selector).textContent = value || ''; };
    const greetingForHour = (h) => h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
    const formatTime = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2,'0')}`;

    function dnaLine(label, value) { const row=document.createElement('div'); row.className='dna-line'; const key=document.createElement('span'); key.textContent=label; const strong=document.createElement('strong'); strong.textContent=value; row.append(key,strong); return row; }
    function renderTimeline(items) { const c=$('#timeline'); c.replaceChildren(); items.forEach((label,index)=>{ if(index){const a=document.createElement('span');a.className='arrow';a.textContent='→';c.appendChild(a);} const s=document.createElement('span');s.className='journey-step';s.textContent=label;c.appendChild(s); }); }

    async function api(path, options={}) {
      const response = await fetch(path, {headers:{'Content-Type':'application/json', ...(options.headers||{})}, ...options});
      if (!response.ok && response.status !== 204) { let detail={}; try { detail=await response.json(); } catch (_) {} throw new Error(detail.detail?.spotify?.error?.message || detail.detail?.message || detail.detail?.code || `Request failed (${response.status})`); }
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

    async function loadLiveSpotify(moment=$('#moment').value, exclusions=[], updateCurrentPick=true) {
      const hour=new Date().getHours(); const automaticDaypart=hour<6?'late_night':hour<12?'morning':hour<17?'afternoon':hour<21?'evening':'night';
      const params=new URLSearchParams({moment,daypart:liveContext?.daypart||automaticDaypart});
      if(liveContext){['weather','region','road_setting','activity'].forEach(key=>liveContext[key]&&params.set(key,liveContext[key]));}
      exclusions.slice(-50).forEach(itemId=>params.append('exclude',itemId));
      const response=await api(`/auth/spotify/data?${params}`); const data=await response.json();
      if(!data.profile||typeof data.profile.display_name!=='string')throw new Error('Spotify returned an incomplete listening profile. Please retry or reconnect.');
      const profile=data.profile; const pick=data.recommendation; recommendationSlate=data.recommendations||[pick].filter(Boolean);
      recommendationSlate.forEach(item=>item?.id&&item?.decision_id&&decisionByTrackId.set(item.id,item.decision_id));
      if(!updateCurrentPick){renderDnaQueue();return data;}
      temporalMoodProfile=data.temporal_mood||null; renderTemporalMood();
      setText('#greeting', `${greetingForHour(new Date().getHours())}, ${profile.display_name}.`);
      if (pick) { setText('#pick-heading',pick.title); setText('#artist',`${pick.artist} · Recommended from your Spotify taste`); setText('#match',`${pick.match_score}% match`); setText('#reason',pick.reason); const genres=pick.evidence?.matched_genres||[]; setText('#evidence',`${pick.evidence?.noticed||''} ${genres.length?`Context evidence: ${genres.join(', ')}.`:'EchoSense is using your ranked listening history.'}`); currentRecommendationId=pick.decision_id; currentTrackId=pick.id; currentPlayOutcomeId=`out_${crypto.randomUUID?.()||Date.now()}`; currentQueueCommandId=`queue_${crypto.randomUUID?.()||Date.now()}`; reportedSignals.clear(); syncPickLabel(); await refreshSavedState(pick.id); }
      setText('#insight',data.insight); const dna=$('#dna'); dna.replaceChildren(); const genres=profile.genres||[];
      dna.appendChild(dnaLine('Mostly',genres[0]?.name||'Still learning')); dna.appendChild(dnaLine('Also drawn to',genres[1]?.name||'More signals needed')); dna.appendChild(dnaLine('Popularity profile',profile.average_popularity>=70?'Mainstream':profile.average_popularity>=40?'Balanced':'Deep cuts'));
      renderTimeline(data.timeline.length?data.timeline:['Connected','Listening','Learning']); renderDnaQueue();
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
        paused:state.continuity?.requires_confirmation?true:!state.is_playing,
        position:state.progress_ms||0,
        duration:track?.duration_ms||0,
        track_window:{current_track:track},
        device:state.device||null,
        shuffle_state:state.shuffle_state,
        repeat_state:state.repeat_state,
        continuity:state.continuity||null,
        updatedAt:Date.now(),
        source:'api'
      };
    }

    function syncPickLabel() {
      setText('#pick-label',activePlaybackTrackId?'Recommended next':'Today’s pick');
    }

    function renderPlayer(rawState) {
      const state=normalizePlayerState(rawState);
      const previous=playerState;
      playerState=state;
      const track=state?.track_window?.current_track; const image=track?.album?.images?.[0]?.url;
      if(track?.id) {
        activePlaybackTrackId=track.id;
        activePlaybackDecisionId=decisionByTrackId.get(track.id)||(track.id===currentTrackId?currentRecommendationId:null);
      } else {
        activePlaybackTrackId=null;
        activePlaybackDecisionId=null;
      }
      syncPickLabel();
      setText('#player-title',track?.name||'Nothing playing'); setText('#player-artist',track?.artists?.map(a=>a.name).join(', ')||'Choose a recommendation');
      $('#player-cover').src=image||''; $('#player-cover').style.visibility=image?'visible':'hidden'; $('#toggle').textContent=state?.paused?'▶':'❚❚';
      $('#progress').max=state?.duration||1000; $('#progress').value=state?.position||0; setText('#elapsed',formatTime(state?.position||0)); setText('#duration',formatTime(state?.duration||0));
      const shuffle=state?.shuffle_state??state?.shuffle??false; $('#shuffle').setAttribute('aria-pressed',String(shuffle)); $('#shuffle').textContent=shuffle?'Shuffle on':'Shuffle';
      const repeat=state?.repeat_state??({0:'off',1:'context',2:'track'}[state?.repeat_mode]||'off'); $('#repeat').value=repeat;
      if(spotifyConnected && track?.id===currentTrackId && previous?.paused===false && state?.paused && state.duration && state.position/state.duration>=.95) {
        feedback('completed',{completion_ratio:state.position/state.duration,playback_seconds:state.position/1000}).catch(()=>{});
      }
      const previousTrackId=previous?.track_window?.current_track?.id;
      if(spotifyConnected&&track?.id&&track.id!==previousTrackId) {
        rememberAutopilotTrack(previousTrackId);
        maintainAutopilot().catch(()=>{});
      }
    }

    function updateProgressClock() {
      if (!playerState) return;
      const elapsed=playerState.paused ? playerState.position : Math.min(playerState.duration, playerState.position + (Date.now()-playerState.updatedAt));
      $('#progress').value=elapsed; setText('#elapsed',formatTime(elapsed));
    }

    async function restorePlaybackState() {
      if (!spotifyConnected) return null;
      const request=++restoreRequest;
      const response=await fetch('/v1/player/state');
      if (request!==restoreRequest) return null;
      if (response.status===204) { renderPlayer(null); return null; }
      if (!response.ok) return null;
      const state=await response.json();
      renderPlayer(state);
      if (state.continuity?.source==='snapshot') setText('#player-status','Last session restored · choose a device to resume');
      else if (state.device?.id===deviceId) setText('#player-status','EchoSense Browser active');
      else if (state.device?.name) setText('#player-status',`Playing on ${state.device.name}`);
      return normalizePlayerState(state);
    }

    async function activateBrowser(play=false) {
      if (!deviceId) throw new Error('The EchoSense player is still starting.');
      await lifecycle.activateElement();
      await api('/v1/player/transfer',{method:'PUT',body:JSON.stringify({device_id:deviceId,play})}); lifecycle.markDeviceActive(); setText('#player-status','EchoSense Browser active');
    }
    async function waitForAudibleBrowserPlayback(expectedTrackId=null) {
      for(let attempt=0;attempt<12;attempt+=1) {
        const local=await lifecycle.player?.getCurrentState?.();
        const trackId=local?.track_window?.current_track?.id||null;
        if(local&&local.paused===false&&(!expectedTrackId||trackId===expectedTrackId)) {
          renderPlayer(local);
          setText('#player-status','Playing with browser audio');
          return local;
        }
        await new Promise(resolve=>setTimeout(resolve,300));
      }
      throw new Error('The track started on Spotify, but browser audio did not start. Click Start listening again or choose EchoSense Browser as your Spotify device.');
    }
    async function loadDevices() {
      const payload=await (await api('/v1/player/devices')).json(); const picker=$('#device-picker'); picker.replaceChildren();
      const placeholder=document.createElement('option'); placeholder.value=''; placeholder.textContent=payload.items.length?'Choose device':'No devices available'; picker.appendChild(placeholder);
      payload.items.forEach(device=>{const option=document.createElement('option');option.value=device.id;option.textContent=`${device.name}${device.active?' · active':''}${device.restricted?' · unavailable':''}`;option.disabled=device.restricted;option.dataset.name=device.name;picker.appendChild(option);});
      $('#transfer-device').disabled=true;
    }
    async function transferSelectedDevice() {
      const picker=$('#device-picker'); if(!picker.value)return;
      await api('/v1/player/transfer',{method:'PUT',body:JSON.stringify({device_id:picker.value,play:false})});
      setText('#player-status',`Transferred to ${picker.selectedOptions[0].dataset.name}`); await restorePlaybackState(); await loadDevices();
    }
    function renderPlaybackQueue(queue) {
      const container=$('#queue-items'); container.replaceChildren();
      [queue.current,...queue.up_next].filter(Boolean).forEach((track,index)=>{const row=document.createElement('div');row.className='playlist-track';const title=document.createElement('strong');title.textContent=`${index===0?'Now':'Next'} · ${track.title}`;const artist=document.createElement('span');artist.textContent=track.artists.join(', ');row.append(title,artist);container.appendChild(row);});
      $('#queue-panel').hidden=false;
    }
    async function loadQueue() {
      const queue=await (await api('/v1/player/queue')).json();
      renderPlaybackQueue(queue);
      return queue;
    }
    function rememberAutopilotTrack(itemId) {
      if(!itemId)return;
      const index=autopilotHistory.indexOf(itemId);
      if(index>=0)autopilotHistory.splice(index,1);
      autopilotHistory.push(itemId);
      if(autopilotHistory.length>20)autopilotHistory.splice(0,autopilotHistory.length-20);
    }
    async function maintainAutopilot(force=false) {
      if(!spotifyConnected||autopilotFilling||(!force&&playerState?.paused!==false))return;
      autopilotFilling=true;
      try {
        let queue=await loadQueue();
        rememberAutopilotTrack(queue.current?.id);
        let queuedIds=new Set([queue.current,...queue.up_next].filter(Boolean).map(track=>track.id));
        let distinctAhead=new Set(queue.up_next.filter(track=>track?.id&&track.id!==queue.current?.id).map(track=>track.id));
        if(distinctAhead.size<AUTOPILOT_HORIZON) {
          let available=recommendationSlate.filter(item=>item?.id&&!queuedIds.has(item.id)&&!autopilotHistory.includes(item.id));
          if(available.length<AUTOPILOT_HORIZON-distinctAhead.size) {
            await loadLiveSpotify($('#moment').value,[...autopilotHistory,...queuedIds],false);
            available=recommendationSlate.filter(item=>item?.id&&!queuedIds.has(item.id));
            if(!available.length) {
              await loadLiveSpotify($('#moment').value,[...queuedIds],false);
              available=recommendationSlate.filter(item=>item?.id&&!queuedIds.has(item.id));
            }
          }
          for(const item of available) {
            if(distinctAhead.size>=AUTOPILOT_HORIZON)break;
            const result=await (await api('/v1/player/queue',{method:'POST',body:JSON.stringify({item_id:item.id,command_id:`autopilot_${item.decision_id}_${item.id}`,device_id:queue.current?.device_id||deviceId})})).json();
            if(result.applied||result.status==='already_queued'){queuedIds.add(item.id);distinctAhead.add(item.id);}
          }
          queue=await loadQueue();
          distinctAhead=new Set(queue.up_next.filter(track=>track?.id&&track.id!==queue.current?.id).map(track=>track.id));
        }
        setText('#autopilot-status',`Autopilot on · ${distinctAhead.size} distinct track${distinctAhead.size===1?'':'s'} ready ahead`);
      } catch(error) {
        setText('#autopilot-status',`Autopilot is retrying · ${error.message}`);
      } finally {
        autopilotFilling=false;
      }
    }
    function renderDnaQueue() {
      const container=$('#dna-queue-items'); container.replaceChildren();
      const factorNames=[...new Set(recommendationSlate.flatMap(item=>(item.why_now?.factors||[]).map(factor=>factor.name)))];
      const table=document.createElement('table'); table.className='dna-table';
      const head=document.createElement('thead'); const header=document.createElement('tr');
      ['Track',...factorNames,'Why now','Override'].forEach(label=>{const cell=document.createElement('th');cell.scope='col';cell.textContent=label;header.appendChild(cell);});
      head.appendChild(header); table.appendChild(head);
      const body=document.createElement('tbody');
      recommendationSlate.forEach(item=>{
        const row=document.createElement('tr');
        const track=document.createElement('td');track.className='track-cell';const title=document.createElement('strong');title.textContent=`${item.rank||''}. ${item.title}`;const artist=document.createElement('span');artist.textContent=item.artist;track.append(title,artist);row.appendChild(track);
        const scores=new Map((item.why_now?.factors||[]).map(factor=>[factor.name,factor.score]));
        factorNames.forEach(name=>{const cell=document.createElement('td');cell.className='metric';const score=scores.get(name);cell.textContent=Number.isFinite(score)?`${score}%`:'—';row.appendChild(cell);});
        const why=document.createElement('td');why.className='why-cell';why.textContent=item.why_now?.summary||item.reason||'Ranked from your Music DNA.';row.appendChild(why);
        const actionCell=document.createElement('td');const play=document.createElement('button');play.type='button';play.className='secondary';play.textContent='Play now';play.addEventListener('click',()=>playDnaTrack(item).catch(e=>setText('#toast',e.message)));actionCell.appendChild(play);row.appendChild(actionCell);body.appendChild(row);
      });
      table.appendChild(body);container.appendChild(table);
      $('#dna-queue-panel').hidden=recommendationSlate.length<2;
    }
    function renderLiveContext() {
      const chips=$('#context-chips'); chips.replaceChildren();
      if(!liveContext)return;
      const values=[
        liveContext.daypart?.replace('_',' '),
        liveContext.weather==='unknown'?'Weather unavailable':`${liveContext.weather?.replace('_',' ')}${liveContext.temperature_f!==null?` · ${liveContext.temperature_f}°F`:''}`,
        liveContext.region,
        liveContext.road_setting!=='general'?`${liveContext.road_setting?.replace('_',' ')} drive`:null,
        liveContext.activity?.replace('_',' '),
        liveContext.speed_mph!==null?`${liveContext.speed_mph} mph`:null,
      ].filter(Boolean);
      values.forEach(value=>{const chip=document.createElement('span');chip.className='context-chip';chip.textContent=value;chips.appendChild(chip);});
      setText('#context-status',liveContext.faster_than_usual?'Faster-than-usual driving detected. Energy is increased gradually.':'Live context is shaping candidate generation and ranking.');
    }
    function renderTemporalMood() {
      const chips=$('#temporal-mood-chips'); chips.replaceChildren();
      if(!temporalMoodProfile)return;
      setText('#temporal-mood-status',temporalMoodProfile.explanation||'Still learning your listening rhythm.');
      [temporalMoodProfile.mood,temporalMoodProfile.pattern_type?.replace('_',' '),temporalMoodProfile.evidence_count?`${temporalMoodProfile.evidence_count} qualifying signals`:null,temporalMoodProfile.confidence?`${Math.round(temporalMoodProfile.confidence*100)}% confidence`:null].filter(Boolean).forEach(value=>{const chip=document.createElement('span');chip.className='context-chip';chip.textContent=value;chips.appendChild(chip);});
      $('#temporal-mood-correct').disabled=!temporalMoodProfile.mood;
      $('#temporal-mood-toggle').textContent=temporalMoodProfile.enabled===false?'Enable learning':'Disable learning';
    }
    async function correctTemporalMood() {
      if(!temporalMoodProfile?.mood)return;
      await api('/auth/spotify/temporal-mood/correct',{method:'POST',body:JSON.stringify({daypart:temporalMoodProfile.daypart,mood:temporalMoodProfile.mood})});
      setText('#toast','Pattern corrected. EchoSense will relearn from future qualified listening.');
      await loadLiveSpotify();
    }
    async function toggleTemporalMood() {
      const enabled=temporalMoodProfile?.enabled===false;
      await api('/auth/spotify/temporal-mood/settings',{method:'PUT',body:JSON.stringify({enabled})});
      setText('#toast',enabled?'Temporal mood learning enabled.':'Temporal mood learning disabled.');
      await loadLiveSpotify();
    }
    async function resetTemporalMood() {
      await api('/auth/spotify/temporal-mood',{method:'DELETE'});
      setText('#toast','Temporal mood patterns reset. Your other Music DNA remains intact.');
      await loadLiveSpotify();
    }
    function speedBaseline(speed) {
      const samples=JSON.parse(localStorage.getItem('echosenseDrivingSpeeds')||'[]').filter(value=>Number.isFinite(value)&&value>=8);
      const baseline=samples.length>=3?samples.reduce((total,value)=>total+value,0)/samples.length:null;
      if(Number.isFinite(speed)&&speed>=8){samples.push(speed);localStorage.setItem('echosenseDrivingSpeeds',JSON.stringify(samples.slice(-20)));}
      return baseline;
    }
    async function resolveLiveContext(position) {
      const speed=Number.isFinite(position.coords.speed)?Math.max(0,position.coords.speed):null;
      const snapshot=await (await api('/v1/context/resolve',{method:'POST',body:JSON.stringify({latitude:position.coords.latitude,longitude:position.coords.longitude,local_hour:new Date().getHours(),speed_mps:speed,baseline_speed_mps:speedBaseline(speed)})})).json();
      const key=JSON.stringify([snapshot.daypart,snapshot.weather,snapshot.region,snapshot.road_setting,snapshot.activity,snapshot.faster_than_usual]);
      liveContext=snapshot; renderLiveContext();
      if(key!==lastContextKey){lastContextKey=key;if(spotifyConnected)await loadLiveSpotify();}
    }
    function enableLiveContext() {
      if(!navigator.geolocation){setText('#context-status','This browser does not provide location or motion context. Time-based context remains active.');return;}
      localStorage.setItem('echosenseContextConsent','granted'); $('#context-toggle').textContent='Disable context';
      contextWatchId=navigator.geolocation.watchPosition(position=>resolveLiveContext(position).catch(e=>setText('#context-status',e.message)),error=>setText('#context-status',`Live context unavailable: ${error.message}`),{enableHighAccuracy:true,maximumAge:30000,timeout:10000});
    }
    function disableLiveContext() {
      if(contextWatchId!==null)navigator.geolocation.clearWatch(contextWatchId);
      contextWatchId=null; liveContext=null; lastContextKey=''; localStorage.removeItem('echosenseContextConsent'); $('#context-toggle').textContent='Enable context'; $('#context-chips').replaceChildren();
      setText('#context-status','Live context disabled. Time and manually selected moments remain available.');
      if(spotifyConnected)loadLiveSpotify().catch(e=>setText('#toast',e.message));
    }
    function toggleLiveContext() {
      if(contextWatchId!==null||localStorage.getItem('echosenseContextConsent')==='granted')disableLiveContext();else enableLiveContext();
    }
    async function playDnaTrack(item) {
      if(!deviceId)throw new Error('Player is not ready yet.');
      activePlaybackTrackId=item.id; activePlaybackDecisionId=item.decision_id;
      await activateBrowser(false);
      await api(`/v1/player/recommendations/${encodeURIComponent(item.decision_id)}/play`,{method:'PUT',body:JSON.stringify({device_id:deviceId,outcome_id:`out_${crypto.randomUUID?.()||Date.now()}`})});
      await restorePlaybackState();
      await waitForAudibleBrowserPlayback(item.id);
      await maintainAutopilot(true);
      setText('#toast',`Playing ${item.title}. Autopilot will keep the Music DNA queue moving.`);
    }
    async function toggleShuffle() {
      const enabled=$('#shuffle').getAttribute('aria-pressed')!=='true';
      await api('/v1/player/shuffle',{method:'PUT',body:JSON.stringify({enabled,device_id:deviceId})}); await restorePlaybackState();
    }
    async function setRepeat() {
      await api('/v1/player/repeat',{method:'PUT',body:JSON.stringify({mode:$('#repeat').value,device_id:deviceId})}); await restorePlaybackState();
    }

    function initializeSpotifyPlayer() {
      return lifecycle.setConnection(spotifyConnected);
    }

    window.onSpotifyWebPlaybackSDKReady = () => {
      lifecycle.setSdk(window.Spotify);
    };

    async function playRecommendation() {
      if(!spotifyConnected){location.href='/auth/spotify/login';return;}
      if(!deviceId) throw new Error('Player is not ready yet.');
      if(!currentRecommendationId||!currentPlayOutcomeId) throw new Error('Recommendation is not ready yet.');
      activePlaybackTrackId=currentTrackId; activePlaybackDecisionId=currentRecommendationId;
      await activateBrowser(false);
      await api(`/v1/player/recommendations/${encodeURIComponent(currentRecommendationId)}/play`,{method:'PUT',body:JSON.stringify({device_id:deviceId,outcome_id:currentPlayOutcomeId})});
      await restorePlaybackState();
      await waitForAudibleBrowserPlayback(currentTrackId);
      await maintainAutopilot(true);
      setText('#toast','EchoSense Autopilot started. Your Music DNA queue will replenish continuously.');
    }
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
    function playlistCard(item) {
      const button=document.createElement('button'); button.className='playlist-card'; button.type='button'; button.disabled=!item.can_browse;
      const name=document.createElement('strong'); name.textContent=item.name;
      const meta=document.createElement('span'); meta.textContent=item.can_browse?`${item.track_count} tracks · ${item.owner_name}`:'Spotify limits browsing for this playlist';
      button.append(name,meta);
      if(item.can_browse) button.addEventListener('click',()=>loadPlaylistTracks(item.id,item.name,0).catch(e=>setText('#toast',e.message)));
      return button;
    }
    async function loadPlaylists(offset=0) {
      const page=await (await api(`/auth/spotify/playlists?limit=8&offset=${offset}`)).json();
      if(offset===0) $('#playlists').replaceChildren();
      page.items.forEach(item=>$('#playlists').appendChild(playlistCard(item)));
      playlistsNextOffset=page.next_offset;
      setText('#playlists-status',''); $('#more-playlists').textContent='Load more';
      $('#more-playlists').hidden=playlistsNextOffset===null;
    }
    async function loadPlaylistsSafely(offset=0) {
      try { await loadPlaylists(offset); }
      catch (_) {
        playlistsNextOffset=0; setText('#playlists-status','Spotify playlists are temporarily unavailable. Recommendations and playback still work.');
        $('#more-playlists').textContent='Retry'; $('#more-playlists').hidden=false;
      }
    }
    function playlistTrackRow(item) {
      const button=document.createElement('button'); button.className='playlist-track'; button.type='button'; button.disabled=!item.playable;
      const label=document.createElement('strong'); label.textContent=item.track?.title||'Unavailable track';
      const meta=document.createElement('span'); meta.textContent=item.track?.artists?.join(', ')||item.unavailable_reason||'Unavailable';
      button.append(label,meta);
      if(item.playable) button.addEventListener('click',()=>playPlaylistTrack(item.track).catch(e=>setText('#toast',e.message)));
      return button;
    }
    async function loadPlaylistTracks(playlistId,name,offset=0) {
      const page=await (await api(`/auth/spotify/playlists/${encodeURIComponent(playlistId)}/tracks?limit=20&offset=${offset}`)).json();
      selectedPlaylistId=playlistId; tracksNextOffset=page.next_offset; $('#playlist-detail').hidden=false; setText('#playlist-title',name);
      if(offset===0) $('#playlist-tracks').replaceChildren();
      page.items.forEach(item=>$('#playlist-tracks').appendChild(playlistTrackRow(item)));
      $('#more-tracks').hidden=tracksNextOffset===null;
    }
    async function playPlaylistTrack(track) {
      if(!deviceId) throw new Error('Player is not ready yet.');
      await activateBrowser(false);
      await api('/v1/player/play',{method:'PUT',body:JSON.stringify({device_id:deviceId,spotify_uri:track.uri})});
      setText('#toast',`Playing ${track.title} from your playlist.`);
      await restorePlaybackState();
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
      const decisionId=activePlaybackTrackId?activePlaybackDecisionId:currentRecommendationId;
      if(!decisionId)return;
      if(!spotifyConnected) {
        const reaction=signal==='skipped'?'not_for_me':signal;
        await api('/v1/demo/feedback',{method:'POST',body:JSON.stringify({recommendation_id:decisionId,reaction})});
      } else {
        const key=`${decisionId}:${signal}`;
        if(reportedSignals.has(key))return;
        const outcomeId=`out_${crypto.randomUUID?.()||Date.now()}`;
        await api('/auth/spotify/feedback',{method:'POST',body:JSON.stringify({outcome_id:outcomeId,decision_id:decisionId,signal,...metrics})});
        reportedSignals.add(key);
      }
      setText('#toast','Understood. EchoSense will adjust your next pick.');
    }
    async function skipAndPlayNext() {
      if(skipInFlight)return;
      if(!spotifyConnected)throw new Error('Connect Spotify before skipping playback.');
      skipInFlight=true; $('#skip').disabled=true; $('#queue-skip').disabled=true;
      try {
        const before=await restorePlaybackState();
        const previousId=before?.track_window?.current_track?.id||null;
        if(!previousId)throw new Error('No active Spotify track is available to skip.');
        const queue=await (await api('/v1/player/queue')).json();
        const nextDistinct=(queue.up_next||[]).find(track=>track?.id&&track.id!==previousId);
        await feedback('skipped');
        const targetDeviceId=before?.device?.id||deviceId||'';
        await api(`/v1/player/next?device_id=${encodeURIComponent(targetDeviceId)}`,{method:'POST'});
        let changed=null;
        for(let attempt=0;attempt<3&&!changed;attempt+=1) {
          await new Promise(resolve=>setTimeout(resolve,400));
          const state=await restorePlaybackState();
          const nextId=state?.track_window?.current_track?.id||null;
          if(state?.continuity?.source!=='snapshot'&&nextId&&nextId!==previousId)changed=state;
        }
        if(!changed&&nextDistinct) {
          await api('/v1/player/play',{method:'PUT',body:JSON.stringify({device_id:targetDeviceId,spotify_uri:`spotify:track:${nextDistinct.id}`})});
          for(let attempt=0;attempt<10&&!changed;attempt+=1) {
            await new Promise(resolve=>setTimeout(resolve,400));
            const state=await restorePlaybackState();
            const nextId=state?.track_window?.current_track?.id||null;
            if(state?.continuity?.source!=='snapshot'&&nextId===nextDistinct.id)changed=state;
          }
        }
        if(!changed)throw new Error('Spotify did not advance playback. Make sure an active device is playing, then try again.');
        await Promise.allSettled([loadQueue(),loadLiveSpotify()]);
        await maintainAutopilot(true);
        const title=changed.track_window.current_track?.name||'the next track';
        setText('#toast',`Skipped. EchoSense learned from it, verified ${title} is playing, and refreshed your recommendations.`);
      } finally {
        skipInFlight=false; $('#skip').disabled=false; $('#queue-skip').disabled=false;
      }
    }

    async function load() {
      $('#account-action').addEventListener('click',event=>disconnectSpotify(event).catch(e=>setText('#toast',e.message)));
      const session=await loadSpotifySession(); if(session){ initializeSpotifyPlayer(); await loadLiveSpotify(); $('#playlists-panel').hidden=false; await Promise.allSettled([loadPlaylistsSafely(),loadDevices()]); } else await loadDemo();
      $('#play').addEventListener('click',()=>playRecommendation().catch(e=>setText('#toast',e.message)));
      $('#save').addEventListener('click',()=>toggleSaved().catch(e=>{renderSavedState(currentTrackSaved);setText('#toast',e.message);}));
      $('#queue-refresh').addEventListener('click',()=>loadQueue().catch(e=>setText('#toast',e.message)));
      $('#more-playlists').addEventListener('click',()=>loadPlaylistsSafely(playlistsNextOffset||0));
      $('#more-tracks').addEventListener('click',()=>loadPlaylistTracks(selectedPlaylistId,$('#playlist-title').textContent,tracksNextOffset).catch(e=>setText('#toast',e.message)));
      $('#skip').addEventListener('click',()=>skipAndPlayNext().catch(e=>setText('#toast',e.message)));
      $('#queue-skip').addEventListener('click',()=>skipAndPlayNext().catch(e=>setText('#toast',e.message)));
      $('#context-toggle').addEventListener('click',toggleLiveContext);
      $('#temporal-mood-correct').addEventListener('click',()=>correctTemporalMood().catch(e=>setText('#toast',e.message)));
      $('#temporal-mood-toggle').addEventListener('click',()=>toggleTemporalMood().catch(e=>setText('#toast',e.message)));
      $('#temporal-mood-reset').addEventListener('click',()=>resetTemporalMood().catch(e=>setText('#toast',e.message)));
      $('#moment').addEventListener('change',()=>spotifyConnected&&loadLiveSpotify($('#moment').value).then(()=>maintainAutopilot()).catch(e=>setText('#toast',e.message)));
      $('#toggle').addEventListener('click',()=>togglePlayback().catch(e=>setText('#toast',e.message)));
      $('#previous').addEventListener('click',()=>api(`/v1/player/previous?device_id=${encodeURIComponent(deviceId||'')}`,{method:'POST'}).then(restorePlaybackState).catch(e=>setText('#toast',e.message))); $('#next').addEventListener('click',()=>api(`/v1/player/next?device_id=${encodeURIComponent(deviceId||'')}`,{method:'POST'}).then(restorePlaybackState).catch(e=>setText('#toast',e.message)));
      $('#activate').disabled=true; $('#activate').addEventListener('click',()=>activateBrowser(false).catch(e=>setText('#toast',e.message)));
      $('#device-picker').addEventListener('change',()=>{$('#transfer-device').disabled=!$('#device-picker').value;});
      $('#transfer-device').addEventListener('click',()=>transferSelectedDevice().catch(e=>setText('#toast',e.message)));
      $('#progress').addEventListener('change',()=>api('/v1/player/seek',{method:'PUT',body:JSON.stringify({device_id:deviceId,position_ms:Number($('#progress').value)})}).then(restorePlaybackState).catch(e=>setText('#toast',e.message)));
      $('#volume').addEventListener('input',()=>api('/v1/player/volume',{method:'PUT',body:JSON.stringify({device_id:deviceId,volume_percent:Number($('#volume').value)})}).catch(e=>setText('#toast',e.message)));
      $('#shuffle').addEventListener('click',()=>toggleShuffle().catch(e=>setText('#toast',e.message)));
      $('#repeat').addEventListener('change',()=>setRepeat().catch(e=>setText('#toast',e.message)));
      progressTimer=setInterval(updateProgressClock,500);
      autopilotTimer=setInterval(()=>maintainAutopilot().catch(()=>{}),10000);
      document.addEventListener('visibilitychange',()=>{if(!document.hidden) restorePlaybackState();});
      window.addEventListener('focus',restorePlaybackState);
      if(session) { await restorePlaybackState(); await maintainAutopilot(); }
      if(localStorage.getItem('echosenseContextConsent')==='granted')enableLiveContext();
    }
    load().catch(e=>setText('#toast',e.message||'EchoSense could not load.'));
  </script>
</body>
</html>"""
