from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from echosense.music_dna_service import music_dna_service

router = APIRouter(tags=["product-ui"])
UI_DIR = Path(__file__).with_name("web")
PLAYER_LIFECYCLE_PATH = UI_DIR / "player-lifecycle.js"
PLAYER_LIFECYCLE_VERSION = sha256(PLAYER_LIFECYCLE_PATH.read_bytes()).hexdigest()[:12]


class DemoFeedbackRequest(BaseModel):
    recommendation_id: str
    reaction: Literal["love", "not_for_me", "save", "play"]


@router.get("/", response_class=HTMLResponse)
def landing_page() -> str:
    return PAGE.replace("__PLAYER_LIFECYCLE_VERSION__", PLAYER_LIFECYCLE_VERSION)


@router.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    return PAGE.replace("__PLAYER_LIFECYCLE_VERSION__", PLAYER_LIFECYCLE_VERSION)


@router.get("/ui/player-lifecycle.js", include_in_schema=False)
def player_lifecycle_script() -> FileResponse:
    return FileResponse(
        PLAYER_LIFECYCLE_PATH,
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
    .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
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
    .resilience-banner { display:flex; justify-content:space-between; gap:18px; align-items:center; padding:14px 18px; border:1px solid rgba(255,183,77,.35); border-radius:16px; background:rgba(255,183,77,.08); color:#ffe0ad; }
    .resilience-banner strong,.resilience-banner span { display:block; }
    .resilience-banner span { margin-top:3px; color:var(--muted); font-size:.84rem; }
    .resilience-banner details { min-width:220px; color:var(--muted); font-size:.78rem; }
    .provider-health { color:#bfffd5; border-color:rgba(30,215,96,.25); }
    .provider-health.cooldown { color:#ffe0ad; border-color:rgba(255,183,77,.35); }
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
    .boost-grid { display:grid; grid-template-columns:repeat(4,minmax(150px,1fr)); gap:14px; margin-top:20px; }
    .boost-control { padding:14px; border:1px solid var(--line); border-radius:14px; background:rgba(7,10,15,.46); }
    .boost-heading,.boost-value { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:.82rem; font-weight:650; }
    .boost-heading label { flex:1; }
    .boost-control input { margin-top:14px; }
    .boost-value { margin-top:7px; color:var(--muted); font-size:.72rem; font-weight:500; }
    .control-center { padding:28px; }
    .control-center-header { display:flex; align-items:flex-start; justify-content:space-between; gap:24px; margin-bottom:20px; }
    .control-center-header .copy { max-width:720px; margin-bottom:0; }
    .control-groups { display:grid; grid-template-columns:minmax(220px,.72fr) minmax(0,2fr); gap:16px; align-items:stretch; }
    .control-group { padding:20px; border:1px solid var(--line); border-radius:16px; background:rgba(7,10,15,.46); }
    .control-group h3 { margin:4px 0 7px; }
    .control-group .copy { margin-bottom:14px; }
    .moment-select { width:100%; min-height:48px; }
    .moment-impact { margin:12px 0 0; padding:10px 12px; border-radius:10px; background:rgba(100,181,246,.08); color:#d9ecff; font-size:.8rem; line-height:1.45; }
    .moment-proof { display:inline-flex; margin:10px 0 0; padding:7px 10px; border:1px solid rgba(100,181,246,.35); border-radius:999px; color:#d9ecff; background:rgba(100,181,246,.07); font-size:.76rem; font-weight:650; }
    .intelligence-tabs { display:flex; gap:7px; margin:20px 0; padding:5px; border:1px solid var(--line); border-radius:13px; background:rgba(7,10,15,.5); overflow-x:auto; }
    .intelligence-tab { flex:0 0 auto; padding:9px 13px; border:0; border-radius:9px; background:transparent; color:var(--muted); font-weight:700; }
    .intelligence-tab[aria-selected="true"] { color:#08110c; background:var(--green); }
    .intelligence-view[hidden] { display:none; }
    .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(130px,1fr)); gap:12px; }
    .metric-card { min-height:116px; padding:16px; border:1px solid var(--line); border-radius:14px; background:linear-gradient(145deg,rgba(25,31,42,.9),rgba(9,13,19,.8)); }
    .metric-card span { display:block; color:var(--muted); font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.08em; }
    .metric-card strong { display:block; margin-top:12px; color:var(--text); font-size:1.8rem; line-height:1; }
    .metric-card small { display:block; margin-top:8px; color:var(--muted); line-height:1.35; }
    .intelligence-split { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:14px; }
    .insight-card { padding:17px; border:1px solid var(--line); border-radius:14px; background:rgba(7,10,15,.46); }
    .signal-bars { display:grid; gap:9px; margin-top:12px; }
    .signal-row { display:grid; grid-template-columns:minmax(82px,1fr) 3fr auto; gap:10px; align-items:center; color:var(--muted); font-size:.78rem; }
    .signal-bar { height:8px; border-radius:99px; background:#1c2431; overflow:hidden; }
    .signal-bar span { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,var(--blue),var(--green)); }
    .history-list { display:grid; gap:9px; }
    .history-row { display:grid; grid-template-columns:minmax(0,1.7fr) .7fr .7fr auto; gap:14px; align-items:center; padding:13px; border:1px solid var(--line); border-radius:12px; background:rgba(7,10,15,.44); }
    .history-row strong,.history-row span { display:block; }
    .history-row span { color:var(--muted); font-size:.75rem; margin-top:3px; }
    .signal-badge { display:inline-flex!important; width:max-content; margin:0!important; padding:5px 8px; border-radius:999px; color:#d9ecff!important; background:rgba(100,181,246,.1); text-transform:capitalize; }
    .control-actions { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
    .control-action { padding:17px; border:1px solid var(--line); border-radius:14px; background:rgba(7,10,15,.46); }
    .control-action button { width:100%; margin-top:12px; }
    .scope-badge { display:inline-flex; padding:6px 9px; border:1px solid var(--line); border-radius:999px; color:var(--muted); font-size:.72rem; }
    .context-group { grid-column:1/-1; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:20px; align-items:center; }
    .context-group .context-chips { margin-top:9px; }
    .context-group .privacy-note { margin-top:10px; }
    .context-statement { margin:18px 0 0; padding:13px 15px; border-left:3px solid var(--blue); border-radius:0 10px 10px 0; color:#d9ecff; background:rgba(100,181,246,.07); line-height:1.5; }
    .privacy-note { color:var(--muted); font-size:.78rem; margin-top:10px; }
    .privacy-note summary { cursor:pointer; width:max-content; }
    .table-wrap { overflow-x:auto; margin-top:20px; border:1px solid var(--line); border-radius:16px; }
    .dna-table { width:100%; min-width:840px; border-collapse:collapse; font-size:.86rem; }
    .dna-table th { padding:11px 12px; color:var(--muted); background:var(--soft); text-align:left; font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; white-space:nowrap; }
    .dna-table td { padding:14px 12px; border-top:1px solid var(--line); vertical-align:middle; }
    .dna-table tr[aria-current="true"] { background:linear-gradient(90deg,rgba(30,215,96,.13),rgba(100,181,246,.05)); box-shadow:inset 3px 0 0 var(--green); }
    .dna-table tr[aria-current="true"] .track-cell strong::after { content:"Playing"; display:inline-flex; margin-left:9px; padding:3px 7px; border-radius:999px; color:#07130c; background:var(--green); font-size:.62rem; letter-spacing:.06em; text-transform:uppercase; vertical-align:middle; }
    .dna-table td.metric { text-align:center; font-variant-numeric:tabular-nums; white-space:nowrap; }
    .dna-table .track-cell { min-width:210px; }
    .dna-table .track-cell strong,.dna-table .track-cell span { display:block; }
    .dna-table .track-cell span,.dna-table .why-cell { color:var(--muted); }
    .dna-table .why-cell { min-width:210px; line-height:1.35; }
    .dna-table .track-actions { white-space:nowrap; }
    .dna-pagination { display:flex; justify-content:center; align-items:center; gap:10px; margin-top:18px; }
    .dna-pagination span { min-width:110px; color:var(--muted); text-align:center; font-size:.86rem; }
    .factor-heading { display:inline-flex; align-items:center; gap:6px; }
    .factor-info { position:relative; display:inline-grid; place-items:center; width:18px; height:18px; padding:0; border:0; border-radius:50%; background:rgba(100,181,246,.12); color:var(--blue); font:700 12px/1 system-ui,sans-serif; text-transform:none; cursor:help; }
    .factor-info:hover,.factor-info:focus-visible { color:var(--text); border-color:var(--accent); outline:none; }
    .factor-info::after { content:attr(data-tooltip); position:absolute; z-index:20; left:50%; bottom:calc(100% + 9px); width:240px; padding:10px 12px; border:1px solid var(--line); border-radius:10px; background:#171d27; color:var(--text); box-shadow:0 12px 28px rgba(0,0,0,.35); font-size:.78rem; font-weight:500; line-height:1.4; letter-spacing:0; text-align:left; text-transform:none; white-space:normal; opacity:0; pointer-events:none; transform:translate(-50%,4px); transition:opacity .15s ease,transform .15s ease; }
    .factor-info:hover::after,.factor-info:focus-visible::after { opacity:1; transform:translate(-50%,0); }
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
    /* EchoSense explainable product surface */
    :root { --bg:#0a0a0c; --surface:rgba(24,24,28,.75); --soft:rgba(11,15,22,.78); --text:#fff; --muted:#a0a0a0; --line:rgba(255,255,255,.08); --accent:#1ed760; --blue:#64b5f6; --amber:#ffb74d; --purple:#b388ff; --danger:#ff5252; }
    body { background:radial-gradient(circle at 14% -8%,rgba(30,215,96,.10),transparent 28%),radial-gradient(circle at 90% 4%,rgba(100,181,246,.10),transparent 26%),var(--bg); }
    nav,main { max-width:1180px; }
    nav { position:sticky; top:0; z-index:18; padding-block:16px; background:rgba(10,10,12,.76); backdrop-filter:blur(22px); border-bottom:1px solid var(--line); }
    .brand { display:flex; align-items:center; gap:10px; font-size:1.15rem; }
    .brand-mark { display:grid; place-items:center; width:34px; height:34px; border-radius:11px; color:#07110a; background:linear-gradient(135deg,var(--accent),var(--blue)); font-size:1.35rem; }
    .status-dot { width:8px; height:8px; border-radius:50%; background:#666; box-shadow:0 0 0 0 rgba(30,215,96,.4); }
    .account.connected .status-dot { background:var(--accent); animation:pulse 2s infinite; }
    @keyframes pulse { 60% { box-shadow:0 0 0 7px rgba(30,215,96,0); } }
    main { padding-top:38px; }
    h1 { font-size:clamp(2.8rem,6vw,5rem); }
    h2 { font-size:1.35rem; line-height:1.3; }
    .panel { background:var(--surface); border-color:var(--line); border-radius:20px; backdrop-filter:blur(18px); box-shadow:0 18px 60px rgba(0,0,0,.18); }
    .eyebrow { color:var(--accent); }
    .eyebrow.blue { color:var(--blue); }
    button,select,.button-link { border-color:rgba(255,255,255,.14); }
    .primary { background:var(--accent); color:#061109; border-color:var(--accent); }
    .secondary { background:rgba(255,255,255,.035); }
    .hero-content { display:grid; grid-template-columns:160px 1fr; gap:28px; align-items:start; }
    .hero-art { width:160px; height:160px; border-radius:12px; object-fit:cover; background:linear-gradient(135deg,#18221b,#161b27); box-shadow:0 14px 40px rgba(0,0,0,.35); }
    .hero-art:not([src]) { visibility:hidden; }
    .track { margin-top:10px; font-size:clamp(2.2rem,5vw,4rem); }
    .reason { margin:18px 0 14px; }
    .reason-pill,.genre-pill { display:inline-flex; width:max-content; max-width:100%; padding:8px 11px; border:1px solid rgba(30,215,96,.24); border-radius:999px; color:#cffff0; background:rgba(30,215,96,.07); font-size:.78rem; font-weight:650; }
    .genre-pill { border-color:rgba(100,181,246,.25); color:#cbe8ff; background:rgba(100,181,246,.08); margin-top:10px; }
    .factor-bars { display:grid; grid-template-columns:repeat(2,minmax(180px,1fr)); gap:12px 18px; margin:22px 0; }
    .factor-label { display:flex; justify-content:space-between; gap:10px; color:var(--muted); font-size:.78rem; }
    .bar-track { height:6px; margin-top:7px; overflow:hidden; border-radius:99px; background:rgba(255,255,255,.07); }
    .bar-fill { height:100%; border-radius:inherit; background:linear-gradient(90deg,var(--accent),var(--blue)); }
    .table-wrap { border-color:var(--line); }
    .dna-table { min-width:980px; }
    .dna-table th { background:rgba(7,10,15,.76); }
    .track-identity { display:flex; gap:10px; align-items:center; }
    .queue-cover { width:44px; height:44px; border-radius:8px; object-fit:cover; background:#151b24; }
    .category-pill { display:inline-flex; padding:5px 8px; border-radius:999px; color:#cbe8ff; background:rgba(100,181,246,.09); border:1px solid rgba(100,181,246,.18); font-size:.72rem; }
    .memory-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
    .memory-card { min-height:180px; padding:20px; border:1px solid var(--line); border-radius:16px; background:rgba(7,10,15,.46); }
    .memory-card ul { padding-left:18px; color:var(--muted); line-height:1.55; font-size:.86rem; }
    .governance-grid { display:grid; grid-template-columns:1fr auto; gap:28px; align-items:center; }
    .toggle-row { display:flex; justify-content:space-between; align-items:center; gap:20px; padding:14px 0; border-bottom:1px solid var(--line); }
    .switch { width:48px; height:26px; padding:3px; border-radius:99px; background:#292d35; }
    .switch::after { content:''; display:block; width:18px; height:18px; border-radius:50%; background:#fff; transition:.2s; }
    .switch[aria-pressed=true] { background:var(--accent); }
    .switch[aria-pressed=true]::after { transform:translateX(20px); }
    .danger { color:#ffd5d5; background:rgba(255,82,82,.10); border-color:rgba(255,82,82,.35); }
    .modal { position:fixed; inset:0; z-index:60; display:grid; place-items:center; padding:24px; background:rgba(0,0,0,.72); }
    .modal[hidden] { display:none; }
    .modal-card { width:min(560px,100%); padding:28px; border:1px solid var(--line); border-radius:20px; background:#15161b; box-shadow:0 30px 90px #000; }
    .formula { margin:18px 0; padding:15px; border-radius:12px; color:#cbe8ff; background:rgba(100,181,246,.08); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
    .player { border-top-color:var(--line); background:rgba(10,10,12,.92); }
    @media (max-width:1024px) { .memory-grid { grid-template-columns:1fr; } .boost-grid { grid-template-columns:repeat(2,1fr); } .control-groups { grid-template-columns:1fr; } .context-group { grid-column:auto; } .metric-grid { grid-template-columns:repeat(2,1fr); } }
    @media (max-width:760px) { .small-grid,.hero-content,.governance-grid,.boost-grid,.context-group,.intelligence-split,.control-actions { grid-template-columns:1fr; } .control-center,.control-group { padding:18px; } .control-center-header { display:block; } .metric-grid { grid-template-columns:1fr 1fr; } .history-row { grid-template-columns:1fr 1fr; } .hero-art { width:112px; height:112px; } .factor-bars { grid-template-columns:1fr; } .pick-top,.connection { display:block; } .player { grid-template-columns:1fr auto; padding:12px; } .transport { justify-items:end; } .progress-row,.player-side { display:none; } .cover { width:52px; height:52px; } .account span { display:none; } }
  </style>
</head>
<body>
  <nav><div class="brand"><span class="brand-mark">≋</span>EchoSense</div><div id="account" class="account"><span class="status-dot" aria-hidden="true"></span><span id="account-status">Spotify not connected</span><span id="provider-health" class="scope-badge provider-health" hidden>Spotify protected</span><button id="settings-trigger" class="secondary" type="button">Settings</button><a id="account-action" class="button-link secondary" href="/auth/spotify/login">Connect Spotify</a></div></nav>
  <main>
    <section class="intro"><div class="eyebrow">Your daily listening companion</div><h1 id="greeting">Good evening.</h1><p class="lead">EchoSense listens to you. Music selected from your DNA, your context, and what it learns—with every decision explained.</p></section>
    <section id="connection-panel" class="panel connection"><div><div class="eyebrow">Train once. Listen everywhere.</div><h2 id="connection-title">Connect your first music provider</h2><p id="connection-copy" class="connection-copy">A connected provider gives EchoSense the permitted signals needed to begin building your real Music DNA.</p></div><a id="connect-button" class="button-link primary" href="/auth/spotify/login">Connect Spotify</a></section>
    <aside id="provider-resilience" class="resilience-banner" role="status" aria-live="polite" hidden><div><strong id="provider-resilience-title">Spotify is cooling down</strong><span id="provider-resilience-copy">EchoSense is using your last verified playback plan.</span></div><div><span id="provider-resilience-timer"></span><details><summary>Request protection details</summary><span id="provider-resilience-details">Loading request budget…</span></details></div></aside>
    <section id="listening-controls" class="panel control-center"><div class="control-center-header"><div><div class="eyebrow blue">Listening controls</div><h2>Shape what plays next</h2></div></div><div class="control-groups"><section id="moment-panel" class="control-group"><div class="eyebrow">Listening moment</div><h3>What are you doing?</h3><label class="sr-only" for="moment">Listening moment</label><select id="moment" class="secondary moment-select" aria-label="Listening moment"><option value="general">Any moment</option><option value="driving">Driving</option><option value="working">Working</option><option value="exercising">Exercising</option><option value="relaxing">Relaxing</option><option value="social">Social</option></select><p id="moment-impact" class="moment-impact" aria-live="polite">Choose an activity to tune the order.</p></section><section id="boost-panel" class="control-group"><div class="eyebrow blue">Recommendation priorities</div><h3>What should matter more?</h3><div id="boost-controls" class="boost-grid"></div></section><section id="live-context-panel" class="control-group context-group"><div><div class="eyebrow">Live context</div><h3>Add situational signals</h3><p id="context-status" class="connection-copy">Optional: weather, area, road, and movement.</p><div id="context-chips" class="context-chips"></div><details class="privacy-note"><summary>Privacy</summary>Location resolves current conditions; raw coordinates are not stored.</details></div><button id="context-toggle" class="secondary" type="button">Enable context</button></section></div><p id="context-statement" class="context-statement" aria-live="polite">Preparing your next-track context…</p></section>
    <section id="temporal-mood-panel" class="panel connection"><div><div class="eyebrow">Learned listening rhythm</div><h2>Mood patterns, with your control</h2><p id="temporal-mood-status" class="connection-copy">EchoSense needs repeated qualified listening before it claims a time-based mood pattern.</p><div id="temporal-mood-chips" class="context-chips"></div><p class="evidence">Listening trends describe music choices, never your mental or medical state.</p></div><div class="actions"><button id="temporal-mood-correct" class="secondary" type="button" disabled>Not my pattern</button><button id="temporal-mood-toggle" class="secondary" type="button">Disable learning</button><button id="temporal-mood-reset" class="secondary" type="button">Reset patterns</button></div></section>
    <div class="stack">
      <section class="panel"><div class="hero-content"><img id="hero-cover" class="hero-art" alt="Recommendation album art"><div><div class="pick-top"><div><div id="pick-label" class="eyebrow">Current EchoSense recommendation</div><h2 id="pick-heading" class="track">Finding your track…</h2><div id="artist" class="artist"></div><span id="hero-genre" class="genre-pill" hidden></span></div><div id="match" class="match"></div></div><p id="reason" class="sr-only">Listening to your recent patterns…</p><div id="why-pill" class="reason-pill">✨ Building your recommendation…</div><div id="moment-proof" class="moment-proof">Any moment · broad mix</div><div id="hero-factors" class="factor-bars"></div><p id="evidence" class="sr-only"></p><div class="actions"><button id="play" class="primary" type="button">▶ Play</button><button id="save" class="secondary" type="button" aria-pressed="false" disabled>♥ Save</button><button id="skip" class="secondary" type="button">⏭ Skip current song</button></div><div id="toast" aria-live="polite"></div></div></div></section>
      <section id="dna-queue-panel" class="panel" hidden><div class="pick-top"><div><div class="eyebrow">EchoSense playback plan</div><h2>Up next</h2><p class="copy">Your ranked listening order.</p><p id="dna-plan-statement" class="context-statement">Preparing this playback plan…</p><p id="autopilot-status" class="evidence" aria-live="polite">Autopilot starts with your first song.</p></div></div><div id="dna-queue-items" class="table-wrap"></div><nav id="dna-pagination" class="dna-pagination" aria-label="Music DNA playback-plan rounds" hidden><button id="dna-page-previous" class="secondary" type="button">Previous plan</button><span id="dna-page-status">Plan 1 of 1</span><button id="dna-page-next" class="secondary" type="button">Next plan</button></nav><div class="actions" style="justify-content:center;margin-top:16px"><button id="dna-load-more" class="secondary" type="button">＋ Prepare six more</button></div></section>
      <section id="intelligence-panel" class="panel"><div class="pick-top"><div><div class="eyebrow blue">Your EchoSense</div><h2>Your listening intelligence</h2><p class="copy">A transparent view of what EchoSense has learned from qualified playback outcomes.</p></div><span class="scope-badge">Connected listener · persisted signals</span></div><div class="intelligence-tabs" role="tablist" aria-label="Listening intelligence views"><button class="intelligence-tab" type="button" role="tab" aria-selected="true" aria-controls="intelligence-overview" data-intelligence-view="overview">Overview</button><button class="intelligence-tab" type="button" role="tab" aria-selected="false" aria-controls="intelligence-history" data-intelligence-view="history">Recommendation history</button><button class="intelligence-tab" type="button" role="tab" aria-selected="false" aria-controls="intelligence-product" data-intelligence-view="product">Product signals</button><button class="intelligence-tab" type="button" role="tab" aria-selected="false" aria-controls="intelligence-controls" data-intelligence-view="controls">Your controls</button></div><div id="intelligence-overview" class="intelligence-view" role="tabpanel"><div id="intelligence-metrics" class="metric-grid"></div><div class="intelligence-split"><article class="insight-card"><div class="eyebrow">Listening moments</div><h3>Where EchoSense has evidence</h3><div id="intelligence-moments" class="signal-bars"></div></article><article class="insight-card"><div class="eyebrow blue">Recent learning</div><h3>Qualified signals over time</h3><div id="intelligence-trend" class="signal-bars"></div></article></div></div><div id="intelligence-history" class="intelligence-view" role="tabpanel" hidden><div class="pick-top"><div><h3>Recommendation history</h3><p class="copy">Every outcome remains bound to the recommendation decision and provider track.</p></div></div><div id="intelligence-history-list" class="history-list"></div></div><div id="intelligence-product" class="intelligence-view" role="tabpanel" hidden><div class="pick-top"><div><h3>Adoption and recommendation health</h3><p class="copy">Current-listener indicators only. Cohort-level product analytics require the provider-neutral intelligence warehouse.</p></div><span class="scope-badge">Not a global cohort</span></div><div id="intelligence-product-metrics" class="metric-grid"></div></div><div id="intelligence-controls" class="intelligence-view" role="tabpanel" hidden><div class="control-actions"><article class="control-action"><h3>Correct history</h3><p class="copy">Mark an earlier recommendation as a poor fit from the History tab.</p><button class="secondary" type="button" data-open-intelligence="history">Review history</button></article><article class="control-action"><h3>Export my intelligence</h3><p class="copy">Portable export will be enabled after canonical EchoSense track IDs are fully integrated.</p><button class="secondary" type="button" disabled>Export unavailable</button></article><article class="control-action"><h3>Reset or delete</h3><p class="copy">These actions remain locked until every source and derived aggregate participates in verified deletion.</p><button class="danger" type="button" disabled>Verified deletion unavailable</button></article></div></div><p id="intelligence-status" class="evidence" aria-live="polite">Loading persisted listening intelligence…</p></section>
      <section id="queue-panel" class="panel" hidden><div class="pick-top"><div><div class="eyebrow">Playback verification</div><h2>Now and next · EchoSense controlled</h2><p id="queue-status" class="copy" aria-live="polite">Checking Spotify against the active EchoSense Playback Plan.</p></div><div class="actions"><button id="queue-skip" class="primary" type="button">Skip to next planned track</button><button id="queue-refresh" class="secondary" type="button">Verify</button></div></div><div id="queue-items" class="track-list"></div></section>
      <section id="playlists-panel" class="panel" hidden><div class="pick-top"><div><div class="eyebrow">Your Spotify playlists</div><h2>Browse and play here</h2><p class="copy">Owned and collaborative playlists can play inside EchoSense.</p><p id="playlists-status" class="evidence" aria-live="polite"></p></div><button id="more-playlists" class="secondary" type="button" hidden>Load more</button></div><div id="playlists" class="playlist-grid"></div><div id="playlist-detail" hidden><h2 id="playlist-title"></h2><div id="playlist-tracks" class="track-list"></div><button id="more-tracks" class="secondary" type="button" hidden>Load more tracks</button></div></section>
      <div class="small-grid"><section class="panel"><div class="eyebrow">EchoSense noticed</div><h2>One thing worth knowing</h2><p id="insight" class="copy">Reading your listening…</p></section><section class="panel"><div class="eyebrow">Your Music DNA</div><h2>A simple view of your taste</h2><div id="dna" class="dna-list"></div></section></div>
      <section class="panel"><div class="eyebrow">Your journey</div><h2>Your taste, told as a story</h2><div id="timeline" class="journey"></div></section>
      <section id="memory-panel" class="panel"><div class="eyebrow blue">Cognitive memory</div><h2>What EchoSense remembers—and why</h2><p class="copy">Inspectable evidence behind personalization. No hidden mood or medical inference.</p><div class="memory-grid"><article class="memory-card"><div class="eyebrow blue">Episodic memory</div><h3>Recent experiences</h3><ul id="episodic-memory"></ul></article><article class="memory-card"><div class="eyebrow blue">Semantic propositions</div><h3>Learned preferences</h3><ul id="semantic-memory"></ul></article><article class="memory-card"><div class="eyebrow" style="color:var(--amber)">Working memory · expiring</div><h3>Current reasoning context</h3><ul id="working-memory"></ul></article></div></section>
      <section id="governance-panel" class="panel"><div class="governance-grid"><div><div class="eyebrow blue">Privacy & governance</div><h2>Your data, your controls</h2><div class="toggle-row"><span><strong>Contextual recommendations</strong><br><small class="copy">Use consented live context in ranking.</small></span><button id="consent-context" class="switch" type="button" aria-pressed="false" aria-label="Contextual recommendations"></button></div><div class="toggle-row"><span><strong>Data retention</strong><br><small class="copy">Retain learning signals for future sessions.</small></span><button id="consent-retention" class="switch" type="button" aria-pressed="true" aria-label="Data retention"></button></div></div><div><button id="delete-data" class="danger" type="button" disabled title="Requires the governed deletion API before activation">Delete all my data</button><p class="privacy-note">Deletion remains locked until the receipt-generating governance endpoint is implemented.</p></div></div></section>
    </div>
  </main>

  <div id="factor-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="factor-modal-title" hidden><div class="modal-card"><div class="pick-top"><div><div class="eyebrow blue">Factor explanation</div><h2 id="factor-modal-title">Music DNA affinity</h2></div><button id="factor-modal-close" class="secondary" type="button">Close</button></div><div id="factor-formula" class="formula"></div><p id="factor-detail" class="copy"></p></div></div>

  <section class="player" aria-label="EchoSense player">
    <div class="now"><img id="player-cover" class="cover" alt=""><div class="meta"><strong id="player-title">Nothing playing</strong><span id="player-artist">Connect Spotify to listen here</span><span id="player-status" class="player-status">EchoSense Browser</span></div></div>
    <div class="transport"><div class="controls"><button id="previous" class="icon" aria-label="Previous">‹</button><button id="toggle" class="icon toggle" aria-label="Play or pause">▶</button><button id="next" class="icon" aria-label="Next">›</button></div><div class="progress-row"><span id="elapsed">0:00</span><input id="progress" type="range" min="0" max="1000" value="0"><span id="duration">0:00</span></div></div>
    <div class="player-side"><button id="shuffle" class="secondary" type="button" aria-pressed="false">Shuffle</button><select id="repeat" class="secondary" aria-label="Repeat mode"><option value="off">Repeat off</option><option value="context">Repeat context</option><option value="track">Repeat track</option></select><span>🔊</span><input id="volume" class="volume" type="range" min="0" max="100" value="70"><select id="device-picker" class="secondary" aria-label="Playback device"><option value="">Choose device</option></select><button id="transfer-device" class="secondary" type="button" disabled>Transfer</button><button id="activate" class="secondary" type="button">Use this browser</button></div>
  </section>

  <script src="https://sdk.scdn.co/spotify-player.js"></script>
  <script src="/ui/player-lifecycle.js?v=__PLAYER_LIFECYCLE_VERSION__"></script>
  <script>
    let currentRecommendationId = null;
    let currentTrackId = null;
    let currentPlayOutcomeId = null;
    let currentQueueCommandId = null;
    let currentTrackSaved = false;
    const savedStateCache = new Map();
    const savedStateRequests = new Map();
    let savedStateCooldownUntil = 0;
    const SAVED_STATE_CACHE_MS = 300000;
    let recommendationSlate = [];
    const dnaRounds = [];
    let dnaPageIndex = 0;
    const completedDnaTrackIds = new Set();
    let roundGenerationInFlight = null;
    let completionTransitionInFlight = null;
    let playbackPlanReconciliationInFlight = null;
    let pendingPlanTransitionFromTrackId = null;
    let playbackCommandInFlight = 0;
    let activePlaybackTrackId = null;
    let activePlaybackDecisionId = null;
    let liveRecommendationReady = false;
    const decisionByTrackId = new Map();
    let liveContext = null;
    let temporalMoodProfile = null;
    let contextWatchId = null;
    let lastContextKey = '';
    let playlistsNextOffset = null;
    let selectedPlaylistId = null;
    let tracksNextOffset = null;
    let spotifyConnected = false;
    let lastSpotifyData = null;
    const spotifyDataCache = new Map();
    const spotifyDataInFlight = new Map();
    const SPOTIFY_DATA_CACHE_MS = 15000;
    let spotifyProviderCooldownUntil = 0;
    let spotifyProviderCooldownStatus = null;
    let providerStatusTimer = null;
    let deviceId = null;
    let playerState = null;
    let progressTimer = null;
    let restoreRequest = 0;
    let skipInFlight = false;
    let autopilotFilling = false;
    let autopilotTimer = null;
    const autopilotHistory = [];
    const DNA_ROUND_SIZE = 6;
    const AUTOPILOT_HORIZON = DNA_ROUND_SIZE;
    const reportedSignals = new Set();
    const boostDefinitions=[
      ['music_dna','Music DNA affinity'],
      ['live_context','Live context fit'],
      ['learned_preference','Learned preference'],
      ['diversity','Diversity guard'],
    ];
    const recommendationBoosts=JSON.parse(localStorage.getItem('echosenseRecommendationBoosts')||'{}');
    let boostRefreshTimer=null;
    let pendingPlanTransitionLabel=null;
    const factorExplanations={
      'Music DNA affinity':'Matches this track to the artists, genres, and songs you enjoy. Why it matters: recommendations still feel like your taste.',
      'Live context fit':'Checks the current time, weather, area, road, and activity when available. Why it matters: the music better fits what you are doing now.',
      'Learned preference':'Learns from your plays, completions, saves, and skips in similar moments. Why it matters: EchoSense improves from your actual choices.',
      'Diversity guard':'Limits recently repeated tracks and artists. Why it matters: your queue stays fresh and avoids listening fatigue.',
      'Time pattern':'Evidence that you repeatedly choose similar music around this time or daypart.'
    };
    const factorFormulas={
      'Music DNA affinity':'DNA affinity = (0.60 × artist/track affinity) + (0.40 × category fit)',
      'Live context fit':'Context fit = bounded(daypart + weather + location + activity), capped at 35%',
      'Learned preference':'Preference adjustment = clamp(feedback evidence, −0.20, +0.20)',
      'Diversity guard':'Diversity = artist cap + duplicate prevention + recent-history exclusion',
      'Time pattern':'Time pattern = confidence × recency decay × repeated-evidence strength'
    };
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

    function renderBoostControls(effectiveWeights={}) {
      const container=$('#boost-controls');container.replaceChildren();
      boostDefinitions.forEach(([key,label])=>{
        const card=document.createElement('div');card.className='boost-control';
        const heading=document.createElement('div');heading.className='boost-heading';const name=document.createElement('label');name.htmlFor=`boost-${key}`;name.textContent=label;heading.append(name,factorInfoButton(label,'Priority'));
        const amount=document.createElement('strong');amount.textContent=`+${Number(recommendationBoosts[key]||0)}%`;heading.appendChild(amount);
        const slider=document.createElement('input');slider.id=`boost-${key}`;slider.type='range';slider.min='0';slider.max='100';slider.step='10';slider.value=String(recommendationBoosts[key]||0);slider.setAttribute('aria-label',`Boost ${label}`);
        const weight=document.createElement('div');weight.className='boost-value';weight.textContent=Number.isFinite(effectiveWeights[key])?`Effective weight ${Math.round(effectiveWeights[key]*100)}%`:'Balanced baseline';
        slider.addEventListener('input',()=>{recommendationBoosts[key]=Number(slider.value);amount.textContent=`+${slider.value}%`;localStorage.setItem('echosenseRecommendationBoosts',JSON.stringify(recommendationBoosts));clearTimeout(boostRefreshTimer);boostRefreshTimer=setTimeout(()=>{if(spotifyConnected)changeRecommendationBoost(label).catch(e=>setText('#toast',e.message));},350);});
        card.append(heading,slider,weight);container.appendChild(card);
      });
    }

    function dnaLine(label, value) { const row=document.createElement('div'); row.className='dna-line'; const key=document.createElement('span'); key.textContent=label; const strong=document.createElement('strong'); strong.textContent=value; row.append(key,strong); return row; }
    function renderTimeline(items) { const c=$('#timeline'); c.replaceChildren(); items.forEach((label,index)=>{ if(index){const a=document.createElement('span');a.className='arrow';a.textContent='→';c.appendChild(a);} const s=document.createElement('span');s.className='journey-step';s.textContent=label;c.appendChild(s); }); }
    function openFactorModal(name) { setText('#factor-modal-title',name);setText('#factor-formula',factorFormulas[name]||'Score = normalized evidence contribution to the final rank');setText('#factor-detail',factorExplanations[name]||'This factor contributes bounded evidence to the recommendation decision.');$('#factor-modal').hidden=false; }
    function closeFactorModal() { $('#factor-modal').hidden=true; }
    function factorInfoButton(name,location='Recommendation') { const info=document.createElement('button');info.type='button';info.className='factor-info';info.textContent='i';info.dataset.tooltip=factorExplanations[name];info.setAttribute('aria-label',`${location} factor: ${name}. ${factorExplanations[name]}`);info.addEventListener('click',event=>{event.preventDefault();openFactorModal(name);});return info; }
    function renderHeroFactors(item) {
      const container=$('#hero-factors');container.replaceChildren();
      const factors=(item?.why_now?.factors||[]).filter(factor=>factorExplanations[factor.name]).slice(0,4);
      factors.forEach(factor=>{const wrapper=document.createElement('div');wrapper.className='factor-bar';const label=document.createElement('div');label.className='factor-label';const title=document.createElement('span');title.className='factor-heading';title.append(document.createTextNode(factor.name),factorInfoButton(factor.name,'Current recommendation'));const score=document.createElement('strong');score.textContent=factor.name==='Diversity guard'?(factor.score>=100?'Passed':'Limited'):`${factor.score}%`;label.append(title,score);const track=document.createElement('div');track.className='bar-track';const fill=document.createElement('div');fill.className='bar-fill';fill.style.width=`${Math.max(0,Math.min(100,factor.score))}%`;track.appendChild(fill);wrapper.append(label,track);container.appendChild(wrapper);});
    }
    function renderMemory(profile,data={}) {
      const episodic=$('#episodic-memory');episodic.replaceChildren();
      (profile.recent_tracks||[]).slice(0,3).forEach(track=>{const item=document.createElement('li');item.textContent=`Played ${track.title} · ${track.artist}`;episodic.appendChild(item);});
      if(!episodic.children.length){const item=document.createElement('li');item.textContent=`${profile.evidence_count||0} qualified listening signals observed`;episodic.appendChild(item);}
      const semantic=$('#semantic-memory');semantic.replaceChildren();
      (profile.top_artists||[]).slice(0,3).forEach(artist=>{const item=document.createElement('li');item.textContent=`Listener → prefers ${artist.name}`;semantic.appendChild(item);});
      if(!semantic.children.length){const item=document.createElement('li');item.textContent='Still collecting stable preference evidence';semantic.appendChild(item);}
      const working=$('#working-memory');working.replaceChildren();
      const signals=[`Moment: ${$('#moment').selectedOptions[0]?.textContent||'Any moment'}`,liveContext?.weather?`Weather: ${liveContext.weather.replace('_',' ')}`:'Weather: not shared',liveContext?.road_setting?`Road: ${liveContext.road_setting.replace('_',' ')}`:'Road setting unavailable'];
      signals.forEach(signal=>{const item=document.createElement('li');item.textContent=signal;working.appendChild(item);});
    }

    async function api(path, options={}) {
      const response = await fetch(path, {headers:{'Content-Type':'application/json', ...(options.headers||{})}, ...options});
      if (!response.ok && response.status !== 204) { let detail={}; try { detail=await response.json(); } catch (_) {} const error=new Error(detail.detail?.spotify?.error?.message || detail.detail?.message || detail.detail?.code || `Request failed (${response.status})`);error.status=response.status;error.retryAfter=Number(response.headers.get('Retry-After')||detail.detail?.retry_after_seconds||0);throw error; }
      return response;
    }

    async function loadSpotifySession() {
      const response = await fetch('/auth/spotify/session');
      if (!response.ok) return null;
      const session = await response.json(); spotifyConnected = session.connected;
      if (!session.connected) return null;
      const name = session.profile.display_name || 'Spotify listener';
      setText('#account-status', `Connected as ${name}`); setText('#account-action','Disconnect'); $('#account-action').href='#'; $('#account').classList.add('connected');
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

    function rememberDnaRound(items) {
      const round=(items||[]).filter(item=>item?.id&&item?.decision_id).slice(0,DNA_ROUND_SIZE);
      if(!round.length)return;
      const signature=round.map(item=>item.id).join('|');
      if(dnaRounds.at(-1)?.map(item=>item.id).join('|')===signature){dnaPageIndex=dnaRounds.length-1;return;}
      dnaRounds.push(round);
      dnaPageIndex=dnaRounds.length-1;
      completedDnaTrackIds.clear();
    }

    function renderProviderResilience(resilience={mode:'live'}) {
      const cached=resilience.mode==='last_known_good';
      $('#provider-resilience').hidden=!cached;
      if(!cached){spotifyProviderCooldownUntil=0;return;}
      const health=$('#provider-health');health.hidden=false;health.classList.add('cooldown');setText('#provider-health','Spotify protected · cached');
      const retryAfter=Math.max(1,Number(resilience.retry_after_seconds||60));
      spotifyProviderCooldownUntil=Date.now()+retryAfter*1000;
      savedStateCooldownUntil=Math.max(savedStateCooldownUntil,spotifyProviderCooldownUntil);
      const reason=String(resilience.reason||'').toLowerCase();
      setText('#provider-resilience-title',reason==='quota_exceeded'?'Spotify development quota reached':reason==='local_request_budget'?'EchoSense prevented a Spotify lockout':'Spotify asked EchoSense to slow down');
      const cachedCopy=resilience.exact_context_match?'Using the last verified plan for these settings.':'Using your most recent verified plan until live context returns.';
      setText('#provider-resilience-copy',resilience.message||cachedCopy);
      setText('#provider-resilience-timer',`Try live Spotify again in about ${Math.ceil(retryAfter/60)} min`);
      setText('#toast','Cached playback plan active. No reconnect is needed.');
    }

    function renderProviderStatus(status={mode:'live'}) {
      const health=$('#provider-health');health.hidden=false;
      const cooldown=status.mode==='cooldown';
      health.classList.toggle('cooldown',cooldown);
      setText('#provider-health',cooldown?'Spotify protected · cached':'Spotify protected · live');
      if(!cooldown){spotifyProviderCooldownUntil=0;spotifyProviderCooldownStatus=null;$('#provider-resilience').hidden=true;return;}
      spotifyProviderCooldownStatus={...status};
      const retryAfter=Math.max(1,Number(status.retry_after_seconds||60));
      spotifyProviderCooldownUntil=Date.now()+retryAfter*1000;
      $('#provider-resilience').hidden=false;
      const reason=String(status.reason||'').toLowerCase();
      const quota=reason==='quota_exceeded';
      const preventive=reason==='local_request_budget';
      setText('#provider-resilience-title',quota?'Spotify development quota reached':preventive?'EchoSense prevented a Spotify lockout':'Spotify asked EchoSense to slow down');
      setText('#provider-resilience-copy',status.message||'EchoSense is using verified recommendations until live access resumes automatically.');
      setText('#provider-resilience-timer',`Live access retry in about ${Math.ceil(retryAfter/60)} min · no reconnect needed`);
      const budget=status.budget||{};const telemetry=status.telemetry||{};
      const endpoints=(telemetry.top_endpoints||[]).map(item=>`${item.endpoint_group}: ${item.request_count}`).join(' · ');
      setText('#provider-resilience-details',`${budget.requests_in_window||0}/${budget.limit||0} requests in ${budget.window_seconds||30}s. Last 15 min: ${telemetry.total_requests||0} total, ${telemetry.rate_limits||0} rate limits, ${telemetry.quota_limits||0} quota limits.${endpoints?` Top paths: ${endpoints}`:''}`);
    }

    async function loadProviderStatus() {
      if(!spotifyConnected)return;
      try { const response=await api('/auth/spotify/resilience/status');renderProviderStatus(await response.json()); }
      catch(error) { if(error.status!==401)setText('#provider-health','Spotify protection status unavailable'); }
    }

    function invalidateSpotifyRecommendationCache() {
      spotifyDataCache.clear();
    }

    async function fetchSpotifyData(params) {
      const key=params.toString();
      const cached=spotifyDataCache.get(key);
      if(cached&&Date.now()-cached.savedAt<SPOTIFY_DATA_CACHE_MS)return structuredClone(cached.data);
      if(spotifyDataInFlight.has(key))return structuredClone(await spotifyDataInFlight.get(key));
      const request=(async()=>{
        const response=await api(`/auth/spotify/data?${key}`);
        const data=await response.json();
        spotifyDataCache.set(key,{savedAt:Date.now(),data});
        return data;
      })();
      spotifyDataInFlight.set(key,request);
      try{return structuredClone(await request);}
      finally{spotifyDataInFlight.delete(key);}
    }

    function renderMomentImpact(impact,item=null) {
      const selected=$('#moment').selectedOptions[0]?.textContent||'Any moment';
      if(!impact?.applied) {
        setText('#moment-impact','Any moment is active. No activity-specific candidate generation or reranking is applied.');
        setText('#moment-proof','Any moment · no activity-specific reranking');
        return;
      }
      setText('#moment-impact',impact.message||`${selected} was applied to the current ranking.`);
      const detail=item?.why_now?.moment_impact||null;
      if(!detail) {
        setText('#moment-proof',`${selected} applied · impact evidence unavailable`);
        return;
      }
      const fit=Number.isFinite(detail.context_fit)?`${detail.context_fit}% ${selected} fit`: `${selected} applied`;
      const movement=detail.baseline_rank==null
        ? 'entered through moment-specific candidates'
        : detail.rank_change>0
          ? `moved up ${detail.rank_change} place${detail.rank_change===1?'':'s'}`
          : detail.rank_change<0
            ? `moved down ${Math.abs(detail.rank_change)} place${detail.rank_change===-1?'':'s'}`
            : 'rank unchanged';
      setText('#moment-proof',`${fit} · ${movement}`);
      $('#moment-proof').title=(detail.evidence||[]).length
        ? `Evidence: ${detail.evidence.join(', ')}`
        : impact.message;
    }

    async function loadLiveSpotify(moment=$('#moment').value, exclusions=[], updateCurrentPick=true, recordRound=updateCurrentPick, adoptAsNextPlan=false, transitionLabel=null) {
      const hour=new Date().getHours(); const automaticDaypart=hour<6?'late_night':hour<12?'morning':hour<17?'afternoon':hour<21?'evening':'night';
      const params=new URLSearchParams({moment,daypart:liveContext?.daypart||automaticDaypart});
      boostDefinitions.forEach(([key])=>params.set(`boost_${key}`,String(recommendationBoosts[key]||0)));
      if(liveContext){['weather','region','road_setting','activity'].forEach(key=>liveContext[key]&&params.set(key,liveContext[key]));}
      exclusions.slice(-50).forEach(itemId=>params.append('exclude',itemId));
      let data;
      if(Date.now()<spotifyProviderCooldownUntil&&lastSpotifyData) {
        data=JSON.parse(JSON.stringify(lastSpotifyData));
        data.resilience={...(data.resilience||{}),...(spotifyProviderCooldownStatus||{}),mode:'last_known_good'};
      } else {
        data=await fetchSpotifyData(params);lastSpotifyData=data;
      }
      renderProviderResilience(data.resilience);
      if(!data.profile||typeof data.profile.display_name!=='string')throw new Error('Spotify returned an incomplete listening profile. Please retry or reconnect.');
      const profile=data.profile; const pick=data.recommendation; recommendationSlate=data.recommendations||[pick].filter(Boolean);
      recommendationSlate.forEach(item=>item?.id&&item?.decision_id&&decisionByTrackId.set(item.id,item.decision_id));
      if(recordRound)rememberDnaRound(recommendationSlate);
      const newestPlanIndex=dnaRounds.length-1;
      if(!updateCurrentPick){renderDnaQueue();return data;}
      temporalMoodProfile=data.temporal_mood||null; renderTemporalMood();
      renderBoostControls(data.effective_weights||{});renderMomentImpact(data.moment_impact);const cachedPlan=data.resilience?.mode==='last_known_good';$('#context-statement').hidden=cachedPlan;if(!cachedPlan)setText('#context-statement',data.context_statement||'Music DNA and the current listening moment are shaping the next track.');setText('#dna-plan-statement',`${data.moment_impact?.message||''} ${data.context_statement||'Music DNA and the current listening moment shaped this final playback order.'}`.trim());
      setText('#greeting', `${greetingForHour(new Date().getHours())}, ${profile.display_name}.`);
      if (pick) { liveRecommendationReady=true; const explained=recommendationSlate.find(item=>item.id===pick.id)||pick;setText('#pick-heading',pick.title); setText('#artist',`${pick.artist} · EchoSense recommendation from your Music DNA`); setText('#match',`${pick.match_score}% EchoSense score`);$('#match').title='EchoSense Recommendation Score: the final normalized result after Music DNA affinity, live context, learned preference, diversity, and boosts are applied.';$('#match').setAttribute('aria-label',`${pick.match_score}% EchoSense Recommendation Score. ${$('#match').title}`);setText('#reason',pick.reason);setText('#why-pill',`✨ ${explained.why_now?.summary||pick.reason||'Selected as an EchoSense recommendation'}`);renderMomentImpact(data.moment_impact,explained);renderHeroFactors(explained);const cover=pick.image_url||explained.image_url||'';$('#hero-cover').src=cover;$('#hero-cover').style.visibility=cover?'visible':'hidden';const genres=pick.evidence?.matched_genres||[];setText('#hero-genre',genres[0]||'Music DNA');$('#hero-genre').hidden=false; const anyMomentGuidance='Any moment is selected, so EchoSense is playing broadly suitable songs from your Music DNA. Choose Driving, Working, Exercising, Relaxing, or Social for recommendations tailored to that moment and your taste.';setText('#evidence',$('#moment').value==='general'?anyMomentGuidance:`${pick.evidence?.noticed||''} ${genres.length?`Context evidence: ${genres.join(', ')}.`:'EchoSense used moment-specific catalog evidence and your ranked listening history.'}`); currentRecommendationId=pick.decision_id; currentTrackId=pick.id; currentPlayOutcomeId=`out_${crypto.randomUUID?.()||Date.now()}`; currentQueueCommandId=`queue_${crypto.randomUUID?.()||Date.now()}`; reportedSignals.clear(); syncPickLabel(); await refreshSavedState(pick.id); }
      setText('#insight',data.insight); const dna=$('#dna'); dna.replaceChildren(); const genres=profile.genres||[];
      dna.appendChild(dnaLine('Mostly',genres[0]?.name||'Still learning')); dna.appendChild(dnaLine('Also drawn to',genres[1]?.name||'More signals needed')); dna.appendChild(dnaLine('Popularity profile',profile.average_popularity>=70?'Mainstream':profile.average_popularity>=40?'Balanced':'Deep cuts'));
      renderTimeline(data.timeline.length?data.timeline:['Connected','Listening','Learning']); renderMemory(profile,data); renderDnaQueue();
      if(activePlaybackTrackId) {
        syncRecommendationSurfaces(activePlaybackTrackId);
        if(adoptAsNextPlan&&recordRound&&newestPlanIndex>=0) {
          pendingPlanTransitionFromTrackId=activePlaybackTrackId;
          pendingPlanTransitionLabel=transitionLabel||$('#moment').selectedOptions[0]?.textContent||'Selected priorities';
          dnaPageIndex=newestPlanIndex;
          renderDnaQueue();
          const selected=pendingPlanTransitionLabel;
          setText('#autopilot-status',`${selected} plan applied · ${dnaRounds[newestPlanIndex].length} reranked tracks will follow the current song`);
          setText('#dna-plan-statement',`${data.moment_impact?.message||`${selected} is active.`} The current song will finish or can be skipped; then EchoSense will play this newly ranked plan.`);
        }
      }
      return data;
    }

    async function changeListeningMoment() {
      const moment=$('#moment').value;
      const previousPlan=(dnaRounds[dnaPageIndex]||[]).map(item=>item.id).join('|');
      const data=await loadLiveSpotify(moment,[],true,true,true,$('#moment').selectedOptions[0]?.textContent||'Selected moment');
      const currentPlan=(dnaRounds.at(-1)||[]).map(item=>item.id).join('|');
      const selected=$('#moment').selectedOptions[0]?.textContent||'Selected moment';
      if(data.moment_impact?.applied&&previousPlan===currentPlan) {
        setText('#autopilot-status',`${selected} was applied, but the available listening evidence did not change this plan.`);
      }
      await maintainAutopilot(true);
    }

    async function changeRecommendationBoost(label) {
      const previousPlan=(dnaRounds[dnaPageIndex]||[]).map(item=>item.id).join('|');
      await loadLiveSpotify($('#moment').value,[],true,true,true,`${label} boost`);
      const currentPlan=(dnaRounds.at(-1)||[]).map(item=>item.id).join('|');
      if(previousPlan===currentPlan) {
        setText('#autopilot-status',`${label} boost was applied, but the available listening evidence did not change this plan.`);
        return;
      }
      await maintainAutopilot(true);
    }

    function metricCard(label,value,detail) {
      const card=document.createElement('article');card.className='metric-card';
      const name=document.createElement('span');name.textContent=label;
      const metric=document.createElement('strong');metric.textContent=value;
      const note=document.createElement('small');note.textContent=detail;
      card.append(name,metric,note);return card;
    }
    function formatListeningTime(seconds) {
      const total=Math.max(0,Number(seconds)||0);
      if(total<60)return `${Math.round(total)} sec`;
      if(total<3600)return `${Math.round(total/60)} min`;
      return `${(total/3600).toFixed(1)} hr`;
    }
    function renderSignalBars(container,items,labelKey,valueKey) {
      container.replaceChildren();
      if(!items.length){const empty=document.createElement('p');empty.className='copy';empty.textContent='Not enough persisted evidence yet.';container.appendChild(empty);return;}
      const max=Math.max(...items.map(item=>Number(item[valueKey])||0),1);
      items.forEach(item=>{const row=document.createElement('div');row.className='signal-row';const label=document.createElement('span');label.textContent=String(item[labelKey]||'Unknown').replaceAll('_',' ');const bar=document.createElement('div');bar.className='signal-bar';const fill=document.createElement('span');fill.style.width=`${Math.max(4,(Number(item[valueKey])||0)/max*100)}%`;bar.appendChild(fill);const value=document.createElement('strong');value.textContent=String(Math.round(Number(item[valueKey])||0));row.append(label,bar,value);container.appendChild(row);});
    }
    function showIntelligenceView(name) {
      document.querySelectorAll('.intelligence-tab').forEach(tab=>tab.setAttribute('aria-selected',String(tab.dataset.intelligenceView===name)));
      document.querySelectorAll('.intelligence-view').forEach(view=>view.hidden=view.id!==`intelligence-${name}`);
    }
    async function correctHistoryDecision(item,button) {
      button.disabled=true;
      try {
        await api('/auth/spotify/feedback',{method:'POST',body:JSON.stringify({outcome_id:`out_${crypto.randomUUID?.()||Date.now()}`,decision_id:item.decision_id,signal:'disliked'})});
        setText('#intelligence-status',`${item.title} was marked as a poor fit. Future recommendations will reduce similar choices.`);
        await loadListeningIntelligence();
      } catch(error) {
        button.disabled=false;setText('#intelligence-status',error.message);
      }
    }
    function renderListeningIntelligence(data) {
      const summary=data.summary||{};const metrics=$('#intelligence-metrics');metrics.replaceChildren();
      [
        ['Listening time',formatListeningTime(summary.total_listen_seconds),'Qualified playback time persisted'],
        ['Tracks learned',String(summary.tracks_observed||0),'Distinct provider tracks with outcomes'],
        ['Completed',String(summary.completed||0),'Completion outcomes'],
        ['Saved + loved',String((summary.saved||0)+(summary.loved||0)),'Strong positive preference signals'],
      ].forEach(item=>metrics.appendChild(metricCard(...item)));
      renderSignalBars($('#intelligence-moments'),data.moments||[],'moment','signals');
      renderSignalBars($('#intelligence-trend'),(data.trend||[]).map(item=>({...item,value:(item.positive||0)+(item.skips||0)})),'date','value');
      const product=$('#intelligence-product-metrics');product.replaceChildren();
      [
        ['Completion rate',summary.completion_rate==null?'—':`${summary.completion_rate}%`,'Completed versus completed + skipped'],
        ['Acceptance rate',summary.recommendation_acceptance_rate==null?'—':`${summary.recommendation_acceptance_rate}%`,'Completed, saved, or loved outcomes per decision'],
        ['Early skips',String(summary.early_skips||0),'Skips before 20% completion'],
        ['Decisions observed',String(summary.recommendations_with_outcomes||0),'Recommendations with persisted outcomes'],
      ].forEach(item=>product.appendChild(metricCard(...item)));
      const history=$('#intelligence-history-list');history.replaceChildren();
      if(!(data.history||[]).length){const empty=document.createElement('article');empty.className='insight-card';const title=document.createElement('h3');title.textContent='EchoSense is still learning';const copy=document.createElement('p');copy.className='copy';copy.textContent='Play, complete, skip, save, or love recommendations to build your history.';empty.append(title,copy);history.appendChild(empty);}
      (data.history||[]).forEach(item=>{const row=document.createElement('article');row.className='history-row';const identity=document.createElement('div');const title=document.createElement('strong');title.textContent=item.title;const artist=document.createElement('span');artist.textContent=`${item.artist} · ${item.provider}`;identity.append(title,artist);const signal=document.createElement('div');const badge=document.createElement('span');badge.className='signal-badge';badge.textContent=item.signal;signal.appendChild(badge);const context=document.createElement('div');const moment=document.createElement('strong');moment.textContent=String(item.moment||'general').replaceAll('_',' ');const detail=document.createElement('span');detail.textContent=item.completion_ratio==null?formatListeningTime(item.playback_seconds):`${Math.round(item.completion_ratio*100)}% completed`;context.append(moment,detail);const action=document.createElement('button');action.type='button';action.className='secondary';action.textContent='Poor fit';action.disabled=item.signal==='disliked';action.setAttribute('aria-label',`Mark ${item.title} as a poor fit`);action.addEventListener('click',()=>correctHistoryDecision(item,action));row.append(identity,signal,context,action);history.appendChild(row);});
      setText('#intelligence-status',data.data_status==='ready'?`Updated from ${data.history.length} persisted outcomes. Metrics reflect this connected listener only.`:'No qualified outcomes yet. EchoSense will populate this view as you listen.');
    }
    async function loadListeningIntelligence() {
      if(!spotifyConnected)return;
      try {const data=await (await api('/auth/spotify/intelligence?history_limit=30')).json();renderListeningIntelligence(data);}
      catch(error){setText('#intelligence-status',`Listening intelligence is temporarily unavailable: ${error.message}`);}
    }

    async function loadDemo() {
      const [p,i,r,t]=await Promise.all(['/v1/demo/taste-profile','/v1/demo/insights','/v1/demo/recommendations','/v1/demo/timeline'].map(x=>fetch(x).then(y=>y.json()))); const pick=r.items[0];
      setText('#greeting',`${greetingForHour(new Date().getHours())}, ${p.display_name}.`); setText('#pick-heading',pick.title); setText('#artist',`${pick.artist} · ${pick.context}`); setText('#match',`${pick.match_score}% EchoSense score`); setText('#reason',pick.reason);setText('#why-pill',`✨ ${pick.reason}`);setText('#hero-genre',p.genres[0]?.name||'Music DNA');$('#hero-genre').hidden=false; setText('#insight',i.items[0].detail); currentRecommendationId=pick.recommendation_id;
      setText('#evidence','Demo evidence · Connect a music provider for your real listening context.');
      const dna=$('#dna'); dna.replaceChildren(); dna.appendChild(dnaLine('Mostly',p.genres[0].name)); dna.appendChild(dnaLine('Recently exploring',p.genres[2].name)); dna.appendChild(dnaLine('Listening rhythm','After 8 PM')); renderTimeline(t.items.map(x=>x.label));renderMemory(p,{});
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
      setText('#pick-label','Current EchoSense recommendation');
    }

    function recommendationForTrack(trackId) {
      if(!trackId)return null;
      for(let index=dnaRounds.length-1;index>=0;index-=1) {
        const item=dnaRounds[index].find(candidate=>candidate?.id===trackId);
        if(item)return {item,roundIndex:index};
      }
      const item=recommendationSlate.find(candidate=>candidate?.id===trackId);
      return item?{item,roundIndex:null}:null;
    }

    function syncRecommendationSurfaces(trackId) {
      const match=recommendationForTrack(trackId);
      if(!match?.item?.decision_id)return false;
      const item=match.item;
      const changed=currentTrackId!==item.id||currentRecommendationId!==item.decision_id;
      activePlaybackTrackId=item.id;
      activePlaybackDecisionId=item.decision_id;
      if(pendingPlanTransitionFromTrackId&&trackId!==pendingPlanTransitionFromTrackId&&dnaRounds.at(-1)?.some(candidate=>candidate.id===trackId)){pendingPlanTransitionFromTrackId=null;pendingPlanTransitionLabel=null;}
      currentTrackId=item.id;
      currentRecommendationId=item.decision_id;
      if(changed) {
        currentPlayOutcomeId=`out_${crypto.randomUUID?.()||Date.now()}`;
        currentQueueCommandId=`queue_${crypto.randomUUID?.()||Date.now()}`;
        reportedSignals.clear();
      }
      setText('#pick-heading',item.title||'Current recommendation');
      setText('#artist',`${item.artist||'Unknown artist'} · Playing from your EchoSense Playback Plan`);
      const score=item.match_score??item.why_now?.overall_score;
      setText('#match',Number.isFinite(score)?`${score}% EchoSense score`:'EchoSense selected');
      setText('#reason',item.reason||item.why_now?.summary||'Selected from your final EchoSense Playback Plan.');
      setText('#why-pill',`✨ ${item.why_now?.summary||item.reason||'This track is the active EchoSense recommendation.'}`);
      const cover=item.image_url||'';$('#hero-cover').src=cover;$('#hero-cover').style.visibility=cover?'visible':'hidden';
      renderHeroFactors(item);
      syncPickLabel();
      if(match.roundIndex!==null)dnaPageIndex=match.roundIndex;
      renderDnaQueue();
      if(changed)refreshSavedState(item.id).catch(()=>{});
      return true;
    }

    function playbackPlanSuccessor(trackId) {
      if(!trackId)return null;
      if(trackId===pendingPlanTransitionFromTrackId) {
        return (dnaRounds.at(-1)||[]).find(item=>item?.id&&item?.decision_id&&!completedDnaTrackIds.has(item.id))||null;
      }
      const round=[...dnaRounds].reverse().find(items=>items.some(item=>item.id===trackId))||[];
      const index=round.findIndex(item=>item.id===trackId);
      if(index<0)return null;
      return round.slice(index+1).find(item=>item?.id&&item?.decision_id&&!completedDnaTrackIds.has(item.id))||null;
    }

    async function reconcilePlaybackPlan(previousTrackId,observedTrackId) {
      if(!spotifyConnected||!previousTrackId||!observedTrackId||previousTrackId===observedTrackId)return;
      const expected=playbackPlanSuccessor(previousTrackId);
      if(!expected)return;
      if(observedTrackId===expected.id) {
        activePlaybackTrackId=expected.id;
        activePlaybackDecisionId=expected.decision_id;
        return;
      }
      if(playbackPlanReconciliationInFlight||playbackCommandInFlight||skipInFlight||completionTransitionInFlight)return;
      playbackPlanReconciliationInFlight=(async()=>{
        setText('#toast',`Spotify advanced outside the EchoSense Playback Plan. Restoring ${expected.title}.`);
        await playDnaTrack(expected);
        setText('#toast',`Playback restored. ${expected.title} is playing from your EchoSense Playback Plan.`);
      })();
      try {
        await playbackPlanReconciliationInFlight;
      } finally {
        playbackPlanReconciliationInFlight=null;
      }
    }

    function renderPlayer(rawState) {
      const state=normalizePlayerState(rawState);
      const previous=playerState;
      playerState=state;
      const track=state?.track_window?.current_track; const image=track?.album?.images?.[0]?.url;
      if(track?.id) {
        const observedDecisionId=decisionByTrackId.get(track.id)||(track.id===currentTrackId?currentRecommendationId:null);
        if(observedDecisionId) {
          activePlaybackTrackId=track.id;
          activePlaybackDecisionId=observedDecisionId;
          syncRecommendationSurfaces(track.id);
        }
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
      const sameTrackFinished=track?.id&&track.id===previous?.track_window?.current_track?.id;
      if(spotifyConnected && activePlaybackDecisionId && sameTrackFinished && previous?.paused===false && state?.paused && state.duration && state.position/state.duration>=.95) {
        feedback('completed',{completion_ratio:state.position/state.duration,playback_seconds:state.position/1000}).catch(()=>{});
      }
      const previousTrackId=previous?.track_window?.current_track?.id;
      const previousFinished=previousTrackId&&previous?.duration&&previous.position/previous.duration>=.95&&(track?.id!==previousTrackId||state?.paused);
      const changedTrack=track?.id&&previousTrackId&&track.id!==previousTrackId;
      const plannedSuccessor=changedTrack?playbackPlanSuccessor(previousTrackId):null;
      if(spotifyConnected&&changedTrack&&plannedSuccessor) {
        reconcilePlaybackPlan(previousTrackId,track.id).catch(error=>setText('#toast',error.message));
      } else if(spotifyConnected&&previousFinished) {
        markDnaTrackCompleted(previousTrackId).catch(error=>setText('#toast',error.message));
      }
      if(spotifyConnected&&track?.id&&track.id!==previousTrackId) {
        rememberAutopilotTrack(previousTrackId);
        maintainAutopilot().catch(()=>{});
      }
    }

    function allGeneratedDnaIds() {
      return [...new Set(dnaRounds.flat().map(item=>item.id).filter(Boolean))];
    }

    function dnaContinuationDecisionIds(item) {
      const round=[...dnaRounds].reverse().find(
        candidateRound=>candidateRound.some(candidate=>candidate.id===item?.id)
      )||[];
      const index=round.findIndex(candidate=>candidate.id===item?.id);
      if(index<0)return [];
      return round.slice(index+1).map(candidate=>candidate.decision_id).filter(Boolean);
    }

    async function generateNextDnaRound(reason='skip') {
      if(roundGenerationInFlight)return roundGenerationInFlight;
      roundGenerationInFlight=(async()=>{
        const exclusions=[...autopilotHistory,...allGeneratedDnaIds()];
        const data=await loadLiveSpotify($('#moment').value,exclusions,true,true);
        const next=(data.recommendations||[]).find(
          item=>item?.id&&item?.decision_id&&item.id!==activePlaybackTrackId
        );
        if(!next)throw new Error('EchoSense needs more distinct provider candidates before preparing another playback plan.');
        setText('#autopilot-status',`Plan ${dnaRounds.length} ready · ${Math.min(DNA_ROUND_SIZE,data.recommendations.length)} EchoSense recommendations`);
        return next;
      })();
      try {
        return await roundGenerationInFlight;
      } finally {
        roundGenerationInFlight=null;
      }
    }

    async function markDnaTrackCompleted(trackId) {
      const activeRound=dnaRounds.at(-1)||[];
      const completedIndex=activeRound.findIndex(item=>item.id===trackId);
      const transitionsIntoNewestPlan=trackId===pendingPlanTransitionFromTrackId;
      if((completedIndex<0&&!transitionsIntoNewestPlan)||completedDnaTrackIds.has(trackId))return;
      completedDnaTrackIds.add(trackId);
      if(skipInFlight)return;
      if(completionTransitionInFlight)return completionTransitionInFlight;
      completionTransitionInFlight=(async()=>{
        const nextInRound=activeRound
          .slice(transitionsIntoNewestPlan?0:completedIndex+1)
          .find(item=>item?.id&&item?.decision_id&&!completedDnaTrackIds.has(item.id));
        const next=nextInRound||await generateNextDnaRound('completed');
        if(!next)throw new Error('EchoSense could not select the next planned track after completion.');
        await playDnaTrack(next);
        setText('#toast',`Completed. EchoSense continued with ${next.title} from your Playback Plan.`);
        return next;
      })();
      try {
        return await completionTransitionInFlight;
      } finally {
        completionTransitionInFlight=null;
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
      const providerTracks=[queue.current,...queue.up_next].filter(track=>track?.id);
      const providerUnique=[...new Map(providerTracks.map(track=>[track.id,track])).values()];
      const duplicateCount=providerTracks.length-providerUnique.length;
      const currentId=queue.current?.id||activePlaybackTrackId;
      const momentTransition=currentId&&currentId===pendingPlanTransitionFromTrackId;
      const ownedRound=momentTransition
        ? dnaRounds.at(-1)
        : [...dnaRounds].reverse().find(items=>items.some(item=>item.id===currentId));
      const currentIndex=ownedRound?.findIndex(item=>item.id===currentId)??-1;
      const ownedTracks=momentTransition
        ? [queue.current&&{...queue.current,source:'Current Spotify playback'},...ownedRound.map(item=>({id:item.id,title:item.title,artists:[item.artist],source:'New listening-moment plan'}))].filter(Boolean)
        : currentIndex>=0
        ? ownedRound.slice(currentIndex).map(item=>({id:item.id,title:item.title,artists:[item.artist],source:'EchoSense Playback Plan'}))
        : [];
      const displayed=ownedTracks.length?ownedTracks:providerUnique.map(track=>({...track,source:'Spotify diagnostic view'}));
      if(ownedTracks.length) {
        const duplicateNote=duplicateCount?` ${duplicateCount} repeated Spotify queue entr${duplicateCount===1?'y was':'ies were'} ignored.`:'';
        setText('#queue-status',`Verified: the EchoSense Playback Plan is authoritative.${duplicateNote}`);
      } else {
        setText('#queue-status','Spotify is not playing an active EchoSense recommendation. Showing its deduplicated queue for diagnosis; it is not the EchoSense Playback Plan.');
      }
      displayed.forEach((track,index)=>{const row=document.createElement('div');row.className='playlist-track';const title=document.createElement('strong');title.textContent=`${index===0?'Now':'Next'} · ${track.title}`;const artist=document.createElement('span');artist.textContent=`${(track.artists||[]).join(', ')} · ${track.source}`;row.append(title,artist);container.appendChild(row);});
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
        const round=activePlaybackTrackId===pendingPlanTransitionFromTrackId
          ? dnaRounds.at(-1)||[]
          : [...dnaRounds].reverse().find(items=>items.some(item=>item.id===activePlaybackTrackId))||dnaRounds.at(-1)||recommendationSlate.slice(0,DNA_ROUND_SIZE);
        const currentIndex=round.findIndex(item=>item.id===activePlaybackTrackId);
        const readyAhead=(currentIndex>=0?round.slice(currentIndex+1):round).filter(item=>item?.id&&item?.decision_id);
        if(activePlaybackTrackId===pendingPlanTransitionFromTrackId) {
          const selected=pendingPlanTransitionLabel||$('#moment').selectedOptions[0]?.textContent||'Selected priorities';
          setText('#autopilot-status',`${selected} plan applied · ${readyAhead.length} reranked tracks will follow the current song`);
        } else {
          setText('#autopilot-status',`EchoSense controls playback · ${readyAhead.length} planned track${readyAhead.length===1?'':'s'} ready ahead`);
        }
      } catch(error) {
        setText('#autopilot-status',`Autopilot is retrying · ${error.message}`);
      } finally {
        autopilotFilling=false;
      }
    }
    function recommendationExplanation(item) {
      const observations=(item.why_now?.observations||[]).filter(Boolean).slice(0,2);
      const contextReason=observations.length?observations.join(' · '):'';
      return item.why_now?.summary||contextReason||item.reason||'Chosen for your current listening plan.';
    }
    function renderDnaQueue() {
      const container=$('#dna-queue-items'); container.replaceChildren();
      const displayedRound=dnaRounds[dnaPageIndex]||recommendationSlate.slice(0,DNA_ROUND_SIZE);
      const factorNames=[...new Set(displayedRound.flatMap(item=>(item.why_now?.factors||[]).map(factor=>factor.name)))];
      const table=document.createElement('table'); table.className='dna-table';
      const head=document.createElement('thead'); const header=document.createElement('tr');
      ['#','Track','EchoSense score','Genre',...factorNames,'Why now','Actions'].forEach(label=>{const cell=document.createElement('th');cell.scope='col';const explanation=factorExplanations[label];if(explanation){const heading=document.createElement('span');heading.className='factor-heading';heading.append(document.createTextNode(label),factorInfoButton(label,'Queue'));cell.appendChild(heading);}else{cell.textContent=label;}header.appendChild(cell);});
      head.appendChild(header); table.appendChild(head);
      const body=document.createElement('tbody');
      displayedRound.forEach(item=>{
        const row=document.createElement('tr');row.setAttribute('aria-current',String(item.id===activePlaybackTrackId));
        const rank=document.createElement('td');rank.className='metric';rank.textContent=item.rank||displayedRound.indexOf(item)+1;row.appendChild(rank);
        const track=document.createElement('td');track.className='track-cell';const identity=document.createElement('div');identity.className='track-identity';const image=document.createElement('img');image.className='queue-cover';image.alt='';image.src=item.image_url||'';const copy=document.createElement('div');const title=document.createElement('strong');title.textContent=item.title;const artist=document.createElement('span');artist.textContent=item.artist;copy.append(title,artist);identity.append(image,copy);track.appendChild(identity);row.appendChild(track);
        const recommendationScore=document.createElement('td');recommendationScore.className='metric';const finalScore=item.why_now?.overall_score;recommendationScore.textContent=Number.isFinite(finalScore)?`${finalScore}%`:'—';recommendationScore.title='Final EchoSense Recommendation Score after all factors and boosts';row.appendChild(recommendationScore);
        const category=document.createElement('td');const categoryPill=document.createElement('span');categoryPill.className='category-pill';categoryPill.textContent=item.genre||item.category||(item.evidence?.matched_genres||[])[0]||'Music DNA';category.appendChild(categoryPill);row.appendChild(category);
        const scores=new Map((item.why_now?.factors||[]).map(factor=>[factor.name,factor.score]));
        factorNames.forEach(name=>{const cell=document.createElement('td');cell.className='metric';const score=scores.get(name);cell.textContent=Number.isFinite(score)?(name==='Diversity guard'?(score>=100?'Passed':'Limited'):`${score}%`):'—';row.appendChild(cell);});
        const why=document.createElement('td');why.className='why-cell';why.textContent=recommendationExplanation(item);row.appendChild(why);
        const actionCell=document.createElement('td');actionCell.className='track-actions';const play=document.createElement('button');play.type='button';play.className='primary';play.textContent='▶';play.setAttribute('aria-label',`Play ${item.title}`);play.addEventListener('click',()=>playDnaTrack(item).catch(e=>setText('#toast',e.message)));const like=document.createElement('button');like.type='button';like.className='secondary';like.textContent='♥';like.setAttribute('aria-label',`Like ${item.title}`);like.addEventListener('click',()=>feedbackForDecision(item,'love'));const dislike=document.createElement('button');dislike.type='button';dislike.className='secondary';dislike.textContent='×';dislike.setAttribute('aria-label',`Not for me: ${item.title}`);dislike.addEventListener('click',()=>feedbackForDecision(item,'not_for_me'));actionCell.append(play,like,dislike);row.appendChild(actionCell);body.appendChild(row);
      });
      table.appendChild(body);container.appendChild(table);
      $('#dna-queue-panel').hidden=displayedRound.length<2;
      const pagination=$('#dna-pagination'); pagination.hidden=dnaRounds.length<2;
      setText('#dna-page-status',`Plan ${dnaPageIndex+1} of ${dnaRounds.length}`);
      $('#dna-page-previous').disabled=dnaPageIndex===0;
      $('#dna-page-next').disabled=dnaPageIndex>=dnaRounds.length-1;
    }

    async function feedbackForDecision(item,reaction) {
      if(!item?.decision_id)return;
      try {
        if(!spotifyConnected)await api('/v1/demo/feedback',{method:'POST',body:JSON.stringify({recommendation_id:item.decision_id,reaction})});
        else await api('/auth/spotify/feedback',{method:'POST',body:JSON.stringify({outcome_id:`out_${crypto.randomUUID?.()||Date.now()}`,decision_id:item.decision_id,signal:reaction})});
        setText('#toast',reaction==='love'?`Liked ${item.title}. EchoSense will learn from it.`:`Marked ${item.title} as not for me.`);
      } catch(error) { setText('#toast',error.message); }
    }

    function changeDnaPage(offset) {
      dnaPageIndex=Math.max(0,Math.min(dnaRounds.length-1,dnaPageIndex+offset));
      renderDnaQueue();
    }
    function renderLiveContext() {
      const chips=$('#context-chips'); chips.replaceChildren();
      if(!liveContext)return;
      const values=[
        liveContext.daypart?.replace('_',' '),
        liveContext.weather==='unknown'?'Weather unavailable':`${liveContext.weather?.replace('_',' ')}${liveContext.temperature_f!==null?` · ${liveContext.temperature_f}°F`:''}`,
        liveContext.region,
        liveContext.road_setting!=='general'?`${liveContext.road_setting?.replace('_',' ')} drive`:null,
        !liveContext.activity||liveContext.activity==='unknown'?'Movement unavailable':liveContext.activity.replace('_',' '),
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
      invalidateSpotifyRecommendationCache();
      await loadLiveSpotify();
    }
    async function toggleTemporalMood() {
      const enabled=temporalMoodProfile?.enabled===false;
      await api('/auth/spotify/temporal-mood/settings',{method:'PUT',body:JSON.stringify({enabled})});
      setText('#toast',enabled?'Temporal mood learning enabled.':'Temporal mood learning disabled.');
      invalidateSpotifyRecommendationCache();
      await loadLiveSpotify();
    }
    async function resetTemporalMood() {
      await api('/auth/spotify/temporal-mood',{method:'DELETE'});
      setText('#toast','Temporal mood patterns reset. Your other Music DNA remains intact.');
      invalidateSpotifyRecommendationCache();
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
    function requireStreamingConnection(action='playing this track') {
      if(spotifyConnected)return true;
      setText('#toast',`Connect a streaming service before ${action}. Demo recommendations are preview-only until a provider is connected.`);
      $('#connection-panel').scrollIntoView({behavior:'smooth',block:'center'});
      return false;
    }
    async function playDnaTrack(item) {
      if(!requireStreamingConnection('playing this track'))return;
      if(!deviceId)throw new Error('Player is not ready yet.');
      playbackCommandInFlight+=1;
      try {
        activePlaybackTrackId=item.id; activePlaybackDecisionId=item.decision_id;
        await activateBrowser(false);
        await api(`/v1/player/recommendations/${encodeURIComponent(item.decision_id)}/play`,{method:'PUT',body:JSON.stringify({device_id:deviceId,outcome_id:`out_${crypto.randomUUID?.()||Date.now()}`,continuation_decision_ids:dnaContinuationDecisionIds(item)})});
        await restorePlaybackState();
        await waitForAudibleBrowserPlayback(item.id);
        syncRecommendationSurfaces(item.id);
        await maintainAutopilot(true);
        setText('#toast',`Playing ${item.title}. Autopilot will keep the EchoSense Playback Plan moving.`);
      } finally {
        playbackCommandInFlight-=1;
      }
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
      if(!requireStreamingConnection('playing this track'))return;
      if(!deviceId) throw new Error('Player is not ready yet.');
      if(!liveRecommendationReady) throw new Error('Spotify recommendations are temporarily unavailable. Refresh EchoSense to retry.');
      if(!currentRecommendationId||!currentPlayOutcomeId) throw new Error('Recommendation is not ready yet.');
      playbackCommandInFlight+=1;
      try {
        activePlaybackTrackId=currentTrackId; activePlaybackDecisionId=currentRecommendationId;
        await activateBrowser(false);
        await api(`/v1/player/recommendations/${encodeURIComponent(currentRecommendationId)}/play`,{method:'PUT',body:JSON.stringify({device_id:deviceId,outcome_id:currentPlayOutcomeId,continuation_decision_ids:dnaContinuationDecisionIds({id:currentTrackId})})});
        await restorePlaybackState();
        await waitForAudibleBrowserPlayback(currentTrackId);
        await maintainAutopilot(true);
        setText('#toast','EchoSense Autopilot started. Your Playback Plan will replenish continuously.');
      } finally {
        playbackCommandInFlight-=1;
      }
    }
    function renderSavedState(saved) {
      currentTrackSaved=saved;
      $('#save').textContent=saved?'Saved':'Save';
      $('#save').setAttribute('aria-pressed',String(saved));
      $('#save').disabled=!spotifyConnected||!currentTrackId;
    }
    async function refreshSavedState(trackId,{force=false}={}) {
      if(!trackId)return;
      const now=Date.now();
      const cached=savedStateCache.get(trackId);
      if(!force&&cached&&cached.expiresAt>now){if(currentTrackId===trackId)renderSavedState(cached.saved);return cached.saved;}
      if(now<savedStateCooldownUntil){$('#save').disabled=true;$('#save').title='Spotify library checks are paused during rate-limit recovery.';return null;}
      if(savedStateRequests.has(trackId))return savedStateRequests.get(trackId);
      $('#save').disabled=true;
      const request=(async()=>{
        try {
          const status=await (await api(`/auth/spotify/library/tracks/${encodeURIComponent(trackId)}`)).json();
          savedStateCache.set(trackId,{saved:Boolean(status.saved),expiresAt:Date.now()+SAVED_STATE_CACHE_MS});
          if(currentTrackId===trackId){$('#save').title='';renderSavedState(Boolean(status.saved));}
          return Boolean(status.saved);
        } catch(error) {
          if(error.status===429){savedStateCooldownUntil=Date.now()+Math.max(1,error.retryAfter||60)*1000;$('#save').disabled=true;$('#save').title='Spotify library checks are paused during rate-limit recovery.';return null;}
          throw error;
        } finally { savedStateRequests.delete(trackId); }
      })();
      savedStateRequests.set(trackId,request);
      return request;
    }
    async function toggleSaved() {
      if(!spotifyConnected||!currentTrackId||!currentRecommendationId)return;
      const trackId=currentTrackId;
      $('#save').disabled=true;
      const options=currentTrackSaved
        ? {method:'DELETE',body:JSON.stringify({outcome_id:`out_${crypto.randomUUID?.()||Date.now()}`,decision_id:currentRecommendationId})}
        : {method:'PUT',body:JSON.stringify({outcome_id:`out_${crypto.randomUUID?.()||Date.now()}`,decision_id:currentRecommendationId})};
      const status=await (await api(`/auth/spotify/library/tracks/${encodeURIComponent(trackId)}`,options)).json();
      savedStateCache.set(trackId,{saved:Boolean(status.saved),expiresAt:Date.now()+SAVED_STATE_CACHE_MS});
      if(currentTrackId===trackId) renderSavedState(status.saved);
      setText('#toast',status.saved?'Saved to Spotify. EchoSense learned from this choice.':'Removed from Spotify.');
      await loadListeningIntelligence();
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
      if(!requireStreamingConnection('controlling playback'))return;
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
      if(spotifyConnected)loadListeningIntelligence().catch(()=>{});
    }
    async function skipAndPlayNext(startNewRound=false) {
      if(skipInFlight)return;
      if(!spotifyConnected)throw new Error('Connect Spotify before skipping playback.');
      skipInFlight=true; $('#skip').disabled=true; $('#queue-skip').disabled=true;
      try {
        const before=await restorePlaybackState();
        const previousId=before?.track_window?.current_track?.id||null;
        if(!previousId)throw new Error('No active Spotify track is available to skip.');
        await feedback('skipped');
        let nextDna=playbackPlanSuccessor(previousId);
        if(!nextDna&&startNewRound) {
          nextDna=await generateNextDnaRound('skip');
        } else if(!nextDna) {
          const currentIndex=recommendationSlate.findIndex(item=>item?.id===previousId);
          const orderedCandidates=currentIndex>=0
            ? [...recommendationSlate.slice(currentIndex+1),...recommendationSlate.slice(0,currentIndex)]
            : recommendationSlate;
          nextDna=orderedCandidates.find(item=>item?.id&&item?.decision_id&&item.id!==previousId);
        }
        if(!nextDna)throw new Error('EchoSense could not find another planned track. Refresh recommendations and try again.');
        const targetDeviceId=before?.device?.id||deviceId||'';
        await activateBrowser(false);
        await api(`/v1/player/recommendations/${encodeURIComponent(nextDna.decision_id)}/play`,{
          method:'PUT',
          body:JSON.stringify({
            device_id:targetDeviceId,
            outcome_id:`out_${crypto.randomUUID?.()||Date.now()}`,
            continuation_decision_ids:dnaContinuationDecisionIds(nextDna)
          })
        });
        let changed=null;
        for(let attempt=0;attempt<10&&!changed;attempt+=1) {
          await new Promise(resolve=>setTimeout(resolve,400));
          const state=await restorePlaybackState();
          const nextId=state?.track_window?.current_track?.id||null;
          if(state?.continuity?.source!=='snapshot'&&nextId===nextDna.id)changed=state;
        }
        if(!changed)throw new Error(`Spotify did not start the selected EchoSense recommendation (${nextDna.title}). Make sure the EchoSense browser player is active, then try again.`);
        activePlaybackTrackId=nextDna.id;
        activePlaybackDecisionId=nextDna.decision_id;
        syncRecommendationSurfaces(nextDna.id);
        rememberAutopilotTrack(previousId);
        const refreshExclusions=startNewRound
          ? [...autopilotHistory,...allGeneratedDnaIds()]
          : [];
        const recommendationRefresh=loadLiveSpotify(
          $('#moment').value,
          refreshExclusions,
          true,
          false
        );
        await Promise.allSettled([loadQueue(),recommendationRefresh]);
        await maintainAutopilot(true);
        const title=changed.track_window.current_track?.name||'the next track';
        setText('#toast',`Skipped. EchoSense selected the next planned recommendation and verified ${title} is playing.`);
      } finally {
        skipInFlight=false; $('#skip').disabled=false; $('#queue-skip').disabled=false;
      }
    }

    async function loadConnectedSpotifyExperience(session) {
      initializeSpotifyPlayer();
      await loadProviderStatus();
      try {
        const initialData=await loadLiveSpotify();
        const degraded=initialData.resilience?.mode==='last_known_good';
        $('#playlists-panel').hidden=degraded;
        await Promise.allSettled([degraded?Promise.resolve():loadPlaylistsSafely(),loadDevices(),loadListeningIntelligence()]);
      } catch(error) {
        liveRecommendationReady=false;
        $('#playlists-panel').hidden=true;
        await loadDemo();
        await Promise.allSettled([loadDevices(),loadListeningIntelligence()]);
        setText('#player-status','Spotify connected · recommendation data unavailable');
        setText('#toast',`${error.message} Demo mode is ready while Spotify recovers.`);
      }
    }

    async function load() {
      renderBoostControls();
      bindControls();
      const session=await loadSpotifySession(); if(session){ await loadConnectedSpotifyExperience(session); } else {await loadDemo();renderListeningIntelligence({data_status:'learning',summary:{},moments:[],trend:[],history:[]});}
      progressTimer=setInterval(updateProgressClock,500);
      autopilotTimer=setInterval(()=>maintainAutopilot().catch(()=>{}),10000);
      providerStatusTimer=setInterval(()=>loadProviderStatus(),30000);
      document.addEventListener('visibilitychange',()=>{if(!document.hidden) restorePlaybackState();});
      window.addEventListener('focus',restorePlaybackState);
      if(session) { await restorePlaybackState(); await maintainAutopilot(); }
      if(localStorage.getItem('echosenseContextConsent')==='granted'){$('#consent-context').setAttribute('aria-pressed','true');enableLiveContext();}
    }
    function bindControls() {
      $('#account-action').addEventListener('click',event=>disconnectSpotify(event).catch(e=>setText('#toast',e.message)));
      $('#play').addEventListener('click',()=>playRecommendation().catch(e=>setText('#toast',e.message)));
      $('#save').addEventListener('click',()=>toggleSaved().catch(e=>{renderSavedState(currentTrackSaved);setText('#toast',e.message);}));
      $('#queue-refresh').addEventListener('click',()=>loadQueue().catch(e=>setText('#toast',e.message)));
      $('#more-playlists').addEventListener('click',()=>loadPlaylistsSafely(playlistsNextOffset||0));
      $('#more-tracks').addEventListener('click',()=>loadPlaylistTracks(selectedPlaylistId,$('#playlist-title').textContent,tracksNextOffset).catch(e=>setText('#toast',e.message)));
      $('#skip').addEventListener('click',()=>skipAndPlayNext(true).catch(e=>setText('#toast',e.message)));
      $('#queue-skip').addEventListener('click',()=>skipAndPlayNext(false).catch(e=>setText('#toast',e.message)));
      $('#dna-page-previous').addEventListener('click',()=>changeDnaPage(-1));
      $('#dna-page-next').addEventListener('click',()=>changeDnaPage(1));
      $('#dna-load-more').addEventListener('click',()=>generateNextDnaRound('manual').catch(e=>setText('#toast',e.message)));
      document.querySelectorAll('.intelligence-tab').forEach(tab=>tab.addEventListener('click',()=>showIntelligenceView(tab.dataset.intelligenceView)));
      document.querySelectorAll('[data-open-intelligence]').forEach(button=>button.addEventListener('click',()=>showIntelligenceView(button.dataset.openIntelligence)));
      $('#context-toggle').addEventListener('click',toggleLiveContext);
      $('#settings-trigger').addEventListener('click',()=>$('#governance-panel').scrollIntoView({behavior:'smooth',block:'center'}));
      $('#factor-modal-close').addEventListener('click',closeFactorModal);
      $('#factor-modal').addEventListener('click',event=>{if(event.target===$('#factor-modal'))closeFactorModal();});
      $('#consent-context').addEventListener('click',()=>{const enabled=$('#consent-context').getAttribute('aria-pressed')!=='true';$('#consent-context').setAttribute('aria-pressed',String(enabled));if(enabled)enableLiveContext();else disableLiveContext();});
      $('#consent-retention').addEventListener('click',()=>{const enabled=$('#consent-retention').getAttribute('aria-pressed')!=='true';$('#consent-retention').setAttribute('aria-pressed',String(enabled));localStorage.setItem('echosenseRetentionConsent',String(enabled));setText('#toast','Retention preference saved locally. Server-side enforcement requires the governance API.');});
      $('#temporal-mood-correct').addEventListener('click',()=>correctTemporalMood().catch(e=>setText('#toast',e.message)));
      $('#temporal-mood-toggle').addEventListener('click',()=>toggleTemporalMood().catch(e=>setText('#toast',e.message)));
      $('#temporal-mood-reset').addEventListener('click',()=>resetTemporalMood().catch(e=>setText('#toast',e.message)));
      $('#moment').addEventListener('change',()=>spotifyConnected&&changeListeningMoment().catch(e=>setText('#toast',e.message)));
      $('#toggle').addEventListener('click',()=>togglePlayback().catch(e=>setText('#toast',e.message)));
      $('#previous').addEventListener('click',()=>api(`/v1/player/previous?device_id=${encodeURIComponent(deviceId||'')}`,{method:'POST'}).then(restorePlaybackState).catch(e=>setText('#toast',e.message))); $('#next').addEventListener('click',()=>api(`/v1/player/next?device_id=${encodeURIComponent(deviceId||'')}`,{method:'POST'}).then(restorePlaybackState).catch(e=>setText('#toast',e.message)));
      $('#activate').disabled=true; $('#activate').addEventListener('click',()=>activateBrowser(false).catch(e=>setText('#toast',e.message)));
      $('#device-picker').addEventListener('change',()=>{$('#transfer-device').disabled=!$('#device-picker').value;});
      $('#transfer-device').addEventListener('click',()=>transferSelectedDevice().catch(e=>setText('#toast',e.message)));
      $('#progress').addEventListener('change',()=>api('/v1/player/seek',{method:'PUT',body:JSON.stringify({device_id:deviceId,position_ms:Number($('#progress').value)})}).then(restorePlaybackState).catch(e=>setText('#toast',e.message)));
      $('#volume').addEventListener('input',()=>api('/v1/player/volume',{method:'PUT',body:JSON.stringify({device_id:deviceId,volume_percent:Number($('#volume').value)})}).catch(e=>setText('#toast',e.message)));
      $('#shuffle').addEventListener('click',()=>toggleShuffle().catch(e=>setText('#toast',e.message)));
      $('#repeat').addEventListener('change',()=>setRepeat().catch(e=>setText('#toast',e.message)));
    }
    load().catch(e=>setText('#toast',e.message||'EchoSense could not load.'));
  </script>
</body>
</html>"""
