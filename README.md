<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>LAM Ecoquest · Silesia Ring — Pulse-and-Glide Telemetry</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Saira+Condensed:wght@500;600;700&family=Saira:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<style>
:root{
  --bg:#06090d; --bg2:#0a1016; --panel:#0d1620; --panel2:#101e2a; --raise:#13212e;
  --line:#1b2a38; --line2:#273a4b; --grid:rgba(80,150,190,.05);
  --txt:#e2edf4; --muted:#8698a8; --dim:#566472;
  --accent:#d6fb41; --accent2:#37e0c8;
  --pulse:#ff7a3d; --glide:#42b8f2; --elev:#c79363;
  --danger:#ff3d63; --ok:#27d39a;
  --glow:0 0 14px;
  --mono:'IBM Plex Mono',ui-monospace,monospace;
  --cond:'Saira Condensed',sans-serif;
  --sans:'Saira',sans-serif;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{
  background:
    radial-gradient(1200px 700px at 78% -8%, rgba(54,224,200,.06), transparent 60%),
    radial-gradient(1000px 800px at -5% 110%, rgba(214,251,65,.05), transparent 55%),
    linear-gradient(180deg,#070b10,#05080c);
  color:var(--txt); font-family:var(--sans);
  -webkit-font-smoothing:antialiased; overflow:hidden;
}
/* faint blueprint grid + scanline atmosphere */
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:9999;
  background:repeating-linear-gradient(0deg,rgba(255,255,255,.014) 0 1px,transparent 1px 3px);
  mix-blend-mode:overlay;opacity:.5}
.app{display:grid;grid-template-rows:auto 1fr auto;height:100vh;gap:10px;padding:10px}

/* ---------- header / HUD ---------- */
header{display:flex;align-items:stretch;gap:14px;min-height:62px}
.brand{display:flex;flex-direction:column;justify-content:center;padding:6px 18px 6px 16px;
  background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);
  border-left:2px solid var(--accent);border-radius:4px;position:relative;min-width:268px}
.brand .k{font-family:var(--cond);font-weight:700;letter-spacing:.14em;font-size:19px;
  text-transform:uppercase;line-height:1}
.brand .k b{color:var(--accent)}
.brand .s{font-family:var(--mono);font-size:10.5px;color:var(--muted);letter-spacing:.16em;
  margin-top:5px;text-transform:uppercase}
.hud{flex:1;display:grid;grid-template-columns:repeat(6,1fr);gap:8px}
.g{background:linear-gradient(180deg,var(--panel),#0b131b);border:1px solid var(--line);
  border-radius:4px;padding:7px 12px;display:flex;flex-direction:column;justify-content:center;
  position:relative;overflow:hidden}
.g::after{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:var(--line2)}
.g .lab{font-family:var(--cond);font-weight:600;letter-spacing:.13em;font-size:10px;
  text-transform:uppercase;color:var(--muted)}
.g .val{font-family:var(--mono);font-weight:600;font-size:21px;line-height:1.05;margin-top:3px}
.g .val small{font-size:11px;color:var(--muted);font-weight:400;margin-left:3px}
.g.key .val{color:var(--accent);text-shadow:var(--glow) rgba(214,251,65,.28)}
.g.key::after{background:var(--accent)}
.g.status .val{font-family:var(--cond);font-weight:700;letter-spacing:.06em;font-size:18px}
.g.ok .val{color:var(--ok)} .g.ok::after{background:var(--ok)}
.g.bad .val{color:var(--danger)} .g.bad::after{background:var(--danger)}

/* ---------- main ---------- */
main{display:grid;grid-template-columns:1fr 330px;gap:10px;min-height:0}
.mapwrap{position:relative;border:1px solid var(--line);border-radius:4px;overflow:hidden;
  background:
    linear-gradient(var(--grid) 1px,transparent 1px) 0 0/34px 34px,
    linear-gradient(90deg,var(--grid) 1px,transparent 1px) 0 0/34px 34px,
    radial-gradient(900px 600px at 50% 40%, #0a141d, #070d13)}
#map{position:absolute;inset:0;background:transparent}
.leaflet-container{background:transparent;font-family:var(--mono)}
.leaflet-tile-pane{transition:opacity .25s}
.schematic .leaflet-tile-pane{opacity:0}
/* map overlays */
.ov{position:absolute;z-index:600;background:rgba(9,16,22,.86);border:1px solid var(--line2);
  border-radius:4px;backdrop-filter:blur(6px)}
.ov.tl{top:10px;left:10px;padding:8px}
.ov.tr{top:10px;right:10px;padding:8px 10px;display:flex;gap:14px;align-items:center}
.seg-title{font-family:var(--cond);font-weight:600;letter-spacing:.13em;font-size:9.5px;
  color:var(--muted);text-transform:uppercase;margin:0 0 6px}
.chipset{display:flex;gap:4px}
.chip{font-family:var(--cond);font-weight:600;letter-spacing:.08em;font-size:11px;text-transform:uppercase;
  color:var(--muted);background:#0c1620;border:1px solid var(--line2);padding:5px 9px;border-radius:3px;
  cursor:pointer;transition:.15s}
.chip:hover{color:var(--txt);border-color:#3a5163}
.chip.on{color:#06222a;background:var(--accent2);border-color:var(--accent2)}
.leg{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:10px;color:var(--muted)}
.dot{width:9px;height:9px;border-radius:2px;display:inline-block}
.swatch{height:8px;width:90px;border-radius:2px;
  background:linear-gradient(90deg,#2f6df0,#42b8f2,#37e0c8,#d6fb41,#ff7a3d,#ff3d63)}
.cursorbox{position:absolute;z-index:600;left:10px;bottom:10px;padding:8px 12px;
  background:rgba(9,16,22,.9);border:1px solid var(--line2);border-radius:4px;font-family:var(--mono);
  font-size:11px;color:var(--muted);min-width:188px}
.cursorbox b{color:var(--txt);font-weight:600}
.cursorbox .row{display:flex;justify-content:space-between;gap:14px;line-height:1.7}

/* ---------- control rail ---------- */
.rail{display:flex;flex-direction:column;gap:9px;min-height:0;overflow:auto;padding-right:2px}
.rail::-webkit-scrollbar{width:7px}
.rail::-webkit-scrollbar-thumb{background:var(--line2);border-radius:4px}
.card{background:linear-gradient(180deg,var(--panel),#0a121a);border:1px solid var(--line);
  border-radius:4px;padding:11px 12px 13px}
.card h3{margin:0 0 9px;font-family:var(--cond);font-weight:700;letter-spacing:.13em;font-size:11px;
  text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:7px}
.card h3::before{content:"";width:8px;height:8px;background:var(--accent2);border-radius:1px;
  box-shadow:var(--glow) rgba(55,224,200,.5)}
.card.strat h3::before{background:var(--accent);box-shadow:var(--glow) rgba(214,251,65,.5)}
.sl{margin:9px 0}
.sl .top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px}
.sl .nm{font-family:var(--sans);font-size:12px;color:var(--txt);font-weight:500}
.sl .nm i{color:var(--muted);font-style:normal;font-size:10.5px;font-family:var(--mono)}
.sl .vv{font-family:var(--mono);font-size:12.5px;color:var(--accent);font-weight:600}
input[type=range]{-webkit-appearance:none;width:100%;height:3px;border-radius:3px;
  background:linear-gradient(90deg,var(--accent2) var(--p,40%),#1a2a38 var(--p,40%));outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;
  background:#dff7ff;border:2px solid var(--accent2);cursor:pointer;box-shadow:0 0 0 3px rgba(55,224,200,.13)}
input[type=range]::-moz-range-thumb{width:13px;height:13px;border-radius:50%;background:#dff7ff;
  border:2px solid var(--accent2);cursor:pointer}
.card.strat input[type=range]{background:linear-gradient(90deg,var(--accent) var(--p,40%),#1a2a38 var(--p,40%))}
.card.strat input[type=range]::-webkit-slider-thumb{border-color:var(--accent);box-shadow:0 0 0 3px rgba(214,251,65,.13)}
.btns{display:flex;gap:8px;margin-top:4px}
button.act{flex:1;font-family:var(--cond);font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  font-size:13px;padding:11px;border-radius:4px;cursor:pointer;border:1px solid;transition:.15s}
.opt{background:var(--accent);color:#15240a;border-color:var(--accent)}
.opt:hover{box-shadow:var(--glow) rgba(214,251,65,.4)}
.opt:active{transform:translateY(1px)}
.rst{background:transparent;color:var(--muted);border-color:var(--line2)}
.rst:hover{color:var(--txt);border-color:#3a5163}

/* ---------- footer / charts ---------- */
footer{height:210px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.chart{position:relative;background:linear-gradient(180deg,var(--panel),#0a121a);
  border:1px solid var(--line);border-radius:4px;padding:8px 10px 6px;display:flex;flex-direction:column}
.chart .ct{font-family:var(--cond);font-weight:600;letter-spacing:.12em;font-size:10px;
  text-transform:uppercase;color:var(--muted);display:flex;justify-content:space-between;align-items:center}
.chart .ct b{font-family:var(--mono);font-weight:600;font-size:12px;color:var(--txt)}
.chart canvas{flex:1;width:100%;display:block;cursor:crosshair}
/* transport bar lives over the speed chart title area */
.transport{position:absolute;z-index:650;left:10px;bottom:10px;display:flex;align-items:center;gap:10px;
  background:rgba(9,16,22,.86);border:1px solid var(--line2);border-radius:4px;padding:6px 10px}
.play{width:30px;height:30px;border-radius:50%;border:1px solid var(--accent);background:rgba(214,251,65,.1);
  color:var(--accent);cursor:pointer;display:grid;place-items:center;font-size:13px}
.play:hover{background:rgba(214,251,65,.2)}
#scrub{width:180px}
.spd{font-family:var(--mono);font-size:10px;color:var(--muted);cursor:pointer;user-select:none}
.spd b{color:var(--accent2)}
.loading{position:fixed;inset:0;display:grid;place-items:center;background:#06090d;z-index:99999;
  font-family:var(--cond);letter-spacing:.2em;text-transform:uppercase;color:var(--muted);font-size:13px}
.leaflet-control-attribution{background:rgba(6,9,13,.7)!important;color:#5a6b78!important;font-size:9px!important}
.leaflet-control-zoom a{background:#0c1620!important;color:#9fb4c4!important;border-color:var(--line2)!important}
@media (max-width:1100px){main{grid-template-columns:1fr 290px}.hud{grid-template-columns:repeat(3,1fr)}}
</style>
</head>
<body>
<div class="loading" id="loading">INITIALISING TELEMETRY…</div>
<div class="app">
  <header>
    <div class="brand">
      <div class="k">LAM <b>ECOQUEST</b></div>
      <div class="s">Silesia Ring · Pulse-and-Glide Strategy</div>
    </div>
    <div class="hud" id="hud">
      <div class="g key"><div class="lab">Fuel / lap</div><div class="val" id="m_fuel">–</div></div>
      <div class="g key"><div class="lab">Economy</div><div class="val" id="m_econ">–</div></div>
      <div class="g"><div class="lab">Lap time</div><div class="val" id="m_time">–</div></div>
      <div class="g"><div class="lab">DQ margin</div><div class="val" id="m_margin">–</div></div>
      <div class="g"><div class="lab">Avg speed</div><div class="val" id="m_avg">–</div></div>
      <div class="g status ok" id="m_statusbox"><div class="lab">Status · 11 laps</div><div class="val" id="m_status">–</div></div>
    </div>
  </header>

  <main>
    <div class="mapwrap" id="mapwrap">
      <div id="map"></div>
      <div class="ov tl">
        <div class="seg-title">Colour by</div>
        <div class="chipset" id="colorChips">
          <div class="chip on" data-c="engine">Engine</div>
          <div class="chip" data-c="speed">Speed</div>
          <div class="chip" data-c="elev">Elevation</div>
        </div>
      </div>
      <div class="ov tr">
        <div class="leg" id="legend"></div>
        <div class="chipset"><div class="chip on" id="tileToggle" data-on="1">Map</div></div>
      </div>
      <div class="cursorbox" id="cursorbox">
        <div class="row"><span>DIST</span><b id="c_dist">0 m</b></div>
        <div class="row"><span>SPEED</span><b id="c_spd">–</b></div>
        <div class="row"><span>ENGINE</span><b id="c_eng">–</b></div>
        <div class="row"><span>ELEV</span><b id="c_elev">–</b></div>
      </div>
    </div>

    <div class="rail">
      <div class="card strat">
        <h3>Strategy</h3>
        <div class="sl" data-k="vLowKmh" data-min="10" data-max="40" data-step="0.5" data-unit="km/h"><div class="top"><span class="nm">Glide floor <i>V_low</i></span><span class="vv"></span></div><input type="range"></div>
        <div class="sl" data-k="vHighKmh" data-min="15" data-max="55" data-step="0.5" data-unit="km/h"><div class="top"><span class="nm">Pulse ceiling <i>V_high</i></span><span class="vv"></span></div><input type="range"></div>
        <div class="sl" data-k="pulseFrac" data-min="0.25" data-max="1" data-step="0.01" data-unit="%load" data-pct="1"><div class="top"><span class="nm">Pulse power</span><span class="vv"></span></div><input type="range"></div>
        <div class="btns">
          <button class="act opt" id="btnOpt">⟳ Optimise</button>
          <button class="act rst" id="btnReset">Reset</button>
        </div>
      </div>

      <div class="card">
        <h3>Vehicle</h3>
        <div class="sl" data-k="mass" data-min="60" data-max="140" data-step="1" data-unit="kg"><div class="top"><span class="nm">Total mass</span><span class="vv"></span></div><input type="range"></div>
        <div class="sl" data-k="cd" data-min="0.10" data-max="0.6" data-step="0.005" data-unit=""><div class="top"><span class="nm">Drag coeff <i>Cd</i></span><span class="vv"></span></div><input type="range"></div>
        <div class="sl" data-k="crr" data-min="0.0015" data-max="0.02" data-step="0.0005" data-unit=""><div class="top"><span class="nm">Rolling <i>Crr</i></span><span class="vv"></span></div><input type="range"></div>
      </div>

      <div class="card">
        <h3>Engine</h3>
        <div class="sl" data-k="powerKw" data-min="0.5" data-max="3" data-step="0.05" data-unit="kW"><div class="top"><span class="nm">Max power</span><span class="vv"></span></div><input type="range"></div>
        <div class="sl" data-k="bsfcMin" data-min="240" data-max="500" data-step="5" data-unit="g/kWh"><div class="top"><span class="nm">Best BSFC</span><span class="vv"></span></div><input type="range"></div>
        <div class="sl" data-k="restart" data-min="0" data-max="0.2" data-step="0.005" data-unit="g"><div class="top"><span class="nm">Restart cost</span><span class="vv"></span></div><input type="range"></div>
      </div>

      <div class="card">
        <h3>Environment &amp; Grip</h3>
        <div class="sl" data-k="rho" data-min="1.0" data-max="1.3" data-step="0.01" data-unit="kg/m³"><div class="top"><span class="nm">Air density <i>ρ</i></span><span class="vv"></span></div><input type="range"></div>
        <div class="sl" data-k="muLat" data-min="0.10" data-max="0.90" data-step="0.01" data-unit=""><div class="top"><span class="nm">Corner grip <i>μ eff</i></span><span class="vv"></span></div><input type="range"></div>
        <div class="sl" data-k="gradeUphill" data-min="1.0" data-max="1.4" data-step="0.01" data-unit="×"><div class="top"><span class="nm">Uphill penalty</span><span class="vv"></span></div><input type="range"></div>
      </div>
    </div>
  </main>

  <footer>
    <div class="chart"><div class="ct">Speed <span>·</span> km/h <b id="ct_spd"></b></div><canvas id="cv_spd"></canvas>
      <div class="transport">
        <button class="play" id="play">▶</button>
        <input type="range" id="scrub" min="0" max="1000" value="0">
        <span class="spd" id="spdctl">×<b>4</b></span>
      </div>
    </div>
    <div class="chart"><div class="ct">Elevation <span>·</span> m <b id="ct_elev"></b></div><canvas id="cv_elev"></canvas></div>
    <div class="chart"><div class="ct">Cumulative fuel <span>·</span> g <b id="ct_fuel"></b></div><canvas id="cv_fuel"></canvas></div>
  </footer>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
window.TRACK = __TRACK_DATA_JSON__;
</script>
<script>
/* ====================================================================
   Pulse-and-Glide telemetry — physics ported 1:1 from the Python model.
   ==================================================================== */
const T = window.TRACK, N = T.n, G = T.cfg;

// ---- live parameters (mutable, driven by sliders) ----
const P = {
  mass:G.mass, rotInertia:G.rot_inertia_factor, area:G.frontal_area, cd:G.cd, crr:G.crr,
  powerMax:G.power_max, bsfcMin:G.bsfc_min, loadOpt:G.bsfc_load_opt,
  betaLow:G.bsfc_beta_low, gammaHigh:G.bsfc_gamma_high, driveEff:G.drive_eff, muLong:G.mu_long,
  restart:G.restart_fuel_g, gradeUphill:G.grade_uphill_factor,
  fuelDensity:G.fuel_density, rho:G.rho_air, g:G.g,
  muLat:G.mu_lat, cornerSafety:G.corner_safety, vCornerCap:G.v_corner_cap,
  nLaps:G.n_laps, timeLimit:G.time_limit_s, timeMargin:G.time_safety_margin, vFloor:G.v_floor,
  vLow:T.opt.v_low, vHigh:T.opt.v_high, pulseFrac:T.opt.pulse_frac,
};
const DEFAULTS = JSON.parse(JSON.stringify(P));

// segment spacing (np.gradient equivalent)
const ds = new Float64Array(N);
for(let i=0;i<N;i++){const a=Math.max(i-1,0),b=Math.min(i+1,N-1);ds[i]=(T.s[b]-T.s[a])/(b-a);}

const meff=()=>P.mass*P.rotInertia;
function vCap(i){return Math.min(P.cornerSafety*Math.sqrt(P.muLat*P.g*T.radius[i]),P.vCornerCap);}
function resForce(v,sin,cos){const grade=P.mass*P.g*sin*(sin>0?P.gradeUphill:1.0);
  return 0.5*P.rho*P.cd*P.area*v*v + P.crr*P.mass*P.g*cos + grade;}
function bsfc(load){load=Math.min(Math.max(load,1e-3),1);const lo=P.loadOpt;
  const low=P.betaLow*Math.max(0,lo/load-1), hi=P.gammaHigh*Math.max(0,(load-lo)/(1-lo));
  return P.bsfcMin*(1+low+hi);}
function fuelRate(p){if(p<=0)return 0;return bsfc(p/P.powerMax)*(p/1000)/3600;}
function traction(p,v){if(p<=0)return 0;return Math.min(P.driveEff*p/Math.max(v,P.vFloor),P.muLong*P.mass*P.g);}

function brakeEnvelope(){
  const vl=new Float64Array(N), m=meff();
  for(let i=0;i<N;i++)vl[i]=vCap(i);
  for(let pass=0;pass<3;pass++){
    for(let i=N-2;i>=0;i--){let a=resForce(vl[i+1],T.sin[i+1],T.cos[i+1])/m;if(a<0)a=0;
      const vp=Math.sqrt(vl[i+1]*vl[i+1]+2*a*ds[i]);if(vp<vl[i])vl[i]=vp;}
    let a=resForce(vl[0],T.sin[0],T.cos[0])/m;if(a<0)a=0;
    const vp=Math.sqrt(vl[0]*vl[0]+2*a*ds[N-1]);if(vp<vl[N-1])vl[N-1]=vp;
  }
  return vl;
}

// continuous multi-lap sim; returns last settled lap telemetry + averaged metrics
function simulate(nLaps=6,warmup=3){
  const m=meff(), vl=brakeEnvelope(), pulse=P.pulseFrac*P.powerMax;
  let v=P.vLow, mode='PULSE'; const fuels=[],times=[]; let last=null;
  for(let lap=0;lap<nLaps;lap++){
    const v_=new Float64Array(N),on=new Uint8Array(N),fc=new Float64Array(N),tc=new Float64Array(N);
    let fuel=0,t=0,prevOn=false,pulses=0,brakeE=0; const vStart=v;
    for(let i=0;i<N;i++){
      const ceil=vl[i], vhi=Math.min(P.vHigh,ceil);
      if(mode==='GLIDE'){if(v<=P.vLow && v<ceil-0.1)mode='PULSE';}
      else{if(v>=vhi)mode='GLIDE';}
      if(v>=ceil-0.05)mode='GLIDE';
      const p=(mode==='PULSE')?pulse:0;
      const a=((p>0?traction(p,v):0)-resForce(v,T.sin[i],T.cos[i]))/m;
      let v2=v*v+2*a*ds[i], vNew=v2>P.vFloor*P.vFloor?Math.sqrt(v2):P.vFloor;
      const cap=vCap(i); if(vNew>cap){brakeE+=0.5*m*(vNew*vNew-cap*cap);vNew=cap;}
      const vMid=Math.max(0.5*(v+vNew),P.vFloor), dt=ds[i]/vMid;
      const on1=p>0; if(on1&&!prevOn){pulses++;fuel+=P.restart;} prevOn=on1;
      fuel+=on1?fuelRate(p)*dt:0; t+=dt;
      v_[i]=vNew; on[i]=on1?1:0; fc[i]=fuel; tc[i]=t; v=vNew;
    }
    last={v:v_,on,fuelCum:fc,tCum:tc,vStart,vEnd:v,fuel,time:t,pulses,brakeE};
    fuels.push(fuel);times.push(t);
  }
  const w=Math.min(warmup,nLaps-1); let fa=0,ta=0,c=0;
  for(let k=w;k<nLaps;k++){fa+=fuels[k];ta+=times[k];c++;} fa/=c;ta/=c;
  last.fuelAvg=fa; last.timeAvg=ta; return last;
}

function metrics(tel){
  const budget=P.timeLimit/P.nLaps, mlLap=tel.fuelAvg/P.fuelDensity;
  return {fuelG:tel.fuelAvg, fuelMl:mlLap, time:tel.timeAvg, budget,
    margin:budget-tel.timeAvg, feasible:tel.timeAvg<=budget,
    avgKmh:(T.lapLength/tel.timeAvg)*3.6, kmL:T.lapLength/mlLap,
    totMl:mlLap*P.nLaps, totG:tel.fuelAvg*P.nLaps, pulses:tel.pulses,
    brakeG:(tel.brakeE||0)*(P.bsfcMin/3.6e6)/P.driveEff};
}

function targetTime(){return (P.timeLimit/P.nLaps)*(1-P.timeMargin);}
function _cost(vLow,band,pf){
  if(!(vLow>=2&&vLow<=14&&band>=0.3&&band<=12&&pf>=0.25&&pf<=1)||vLow+band>28)return 1e9;
  const s=[P.vLow,P.vHigh,P.pulseFrac]; P.vLow=vLow;P.vHigh=vLow+band;P.pulseFrac=pf;
  const tel=simulate(6,3); P.vLow=s[0];P.vHigh=s[1];P.pulseFrac=s[2]; // match the display scoring
  const over=Math.max(0,tel.timeAvg-targetTime());
  return tel.fuelAvg+5e4*over*over;
}
function optimise(){
  const seeds=[];
  for(let vLow=4;vLow<=9.5;vLow+=0.5)for(let band=1;band<=8;band+=0.5)for(const pf of[0.5,0.7,0.9])
    seeds.push({c:_cost(vLow,band,pf),vLow,band,pf});
  seeds.sort((a,b)=>a.c-b.c);
  let best=seeds[0];
  for(let si=0;si<3;si++){           // multi-start coordinate descent from the 3 best seeds
    let{vLow,band,pf}=seeds[si], step=[0.4,0.5,0.08];
    for(let it=0;it<150;it++){let cur=_cost(vLow,band,pf),imp=false;
      for(const[a,b,c]of[[vLow+step[0],band,pf],[vLow-step[0],band,pf],[vLow,band+step[1],pf],
          [vLow,band-step[1],pf],[vLow,band,pf+step[2]],[vLow,band,pf-step[2]]]){
        const cc=_cost(a,b,c); if(cc<cur-1e-7){cur=cc;vLow=a;band=b;pf=c;imp=true;}}
      if(!imp){step=step.map(x=>x*0.5); if(step[0]<0.01)break;}}
    const c=_cost(vLow,band,pf); if(c<best.c)best={c,vLow,band,pf};
  }
  P.vLow=best.vLow;P.vHigh=best.vLow+best.band;P.pulseFrac=best.pf;
}

/* ====================================================================
   Rendering — map, charts, HUD, animation
   ==================================================================== */
const latlng=[]; for(let i=0;i<N;i++)latlng.push([T.lat[i],T.lon[i]]);
let TEL=null, colorMode='engine', cursorI=0;
const RSTEP=2; // render every 2 m for the colored track segments

// ---- Leaflet ----
const map=L.map('map',{zoomControl:true,attributionControl:true,preferCanvas:true});
const tiles=L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  {maxZoom:20,subdomains:'abcd',attribution:'© OpenStreetMap © CARTO'}).addTo(map);
const renderer=L.canvas({padding:.5});
const segs=[];
for(let k=0;k+RSTEP<N;k+=RSTEP){
  const pl=L.polyline([latlng[k],latlng[Math.min(k+RSTEP,N-1)]],
    {renderer,weight:5,opacity:.95,lineCap:'round'}).addTo(map);
  segs.push({pl,i:k});
}
map.fitBounds(L.latLngBounds(latlng).pad(.06));
const startMk=L.circleMarker(latlng[0],{radius:5,color:'#fff',weight:2,fillColor:'#06090d',fillOpacity:1}).addTo(map);
const car=L.circleMarker(latlng[0],{radius:7,color:'#06090d',weight:2,fillColor:'#d6fb41',fillOpacity:1,
  renderer:L.svg()}).addTo(map);
const cursorMk=L.circleMarker(latlng[0],{radius:10,color:'#ffffff',weight:1.5,opacity:.6,fill:false}).addTo(map);

// ---- colour helpers ----
const RAMP=[[47,109,240],[66,184,242],[55,224,200],[214,251,65],[255,122,61],[255,61,99]];
function ramp(t){t=Math.min(Math.max(t,0),1)*(RAMP.length-1);const i=Math.floor(t),f=t-i;
  const a=RAMP[i],b=RAMP[Math.min(i+1,RAMP.length-1)];
  return`rgb(${a[0]+(b[0]-a[0])*f|0},${a[1]+(b[1]-a[1])*f|0},${a[2]+(b[2]-a[2])*f|0})`;}
let spdMin=0,spdMax=10;
function segColor(i){
  if(colorMode==='engine')return TEL.on[i]?'#ff7a3d':'#42b8f2';
  if(colorMode==='speed')return ramp((TEL.v[i]-spdMin)/Math.max(spdMax-spdMin,1e-3));
  const e=T.elev,lo=T.elevMin,hi=T.elevMax;return ramp((e[i]-lo)/Math.max(hi-lo,1e-3));
}
function paintTrack(){for(const s of segs)s.pl.setStyle({color:segColor(s.i)});}

// ---- charts ----
function chart(id){const cv=document.getElementById(id),ctx=cv.getContext('2d');return{cv,ctx};}
const CS=chart('cv_spd'),CE=chart('cv_elev'),CF=chart('cv_fuel');
function fit(c){const r=c.cv.getBoundingClientRect(),dpr=devicePixelRatio||1;
  c.cv.width=r.width*dpr;c.cv.height=r.height*dpr;c.ctx.setTransform(dpr,0,0,dpr,0,0);c.W=r.width;c.H=r.height;}
function axes(c,pad){const{ctx,W,H}=c;ctx.clearRect(0,0,W,H);ctx.strokeStyle='rgba(120,170,200,.10)';
  ctx.lineWidth=1;for(let g=0;g<=4;g++){const y=pad.t+(H-pad.t-pad.b)*g/4;ctx.beginPath();
  ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke();}}
const X=(c,p,d)=>p.l+(c.W-p.l-p.r)*(d/T.lapLength);
function drawSpeed(){const c=CS,p={l:30,r:8,t:6,b:14};fit(c);axes(c,p);const{ctx,W,H}=c;
  let vmax=0;for(let i=0;i<N;i++)vmax=Math.max(vmax,TEL.v[i]);vmax=Math.max(vmax*3.6*1.12,10);
  // engine-on shading
  ctx.fillStyle='rgba(255,122,61,.13)';let s=-1;
  for(let i=0;i<N;i++){if(TEL.on[i]&&s<0)s=i;else if(!TEL.on[i]&&s>=0){
    ctx.fillRect(X(c,p,T.s[s]),p.t,X(c,p,T.s[i])-X(c,p,T.s[s]),H-p.t-p.b);s=-1;}}
  if(s>=0)ctx.fillRect(X(c,p,T.s[s]),p.t,X(c,p,T.s[N-1])-X(c,p,T.s[s]),H-p.t-p.b);
  // band lines
  ctx.setLineDash([3,3]);ctx.lineWidth=1;
  for(const[val,col]of[[P.vLow*3.6,'#42b8f2'],[P.vHigh*3.6,'#d6fb41']]){
    const y=p.t+(H-p.t-p.b)*(1-val/vmax);ctx.strokeStyle=col;ctx.globalAlpha=.5;
    ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(W-p.r,y);ctx.stroke();}
  ctx.globalAlpha=1;ctx.setLineDash([]);
  // trace
  ctx.strokeStyle='#bfe9ff';ctx.lineWidth=1.6;ctx.beginPath();
  for(let i=0;i<N;i++){const x=X(c,p,T.s[i]),y=p.t+(H-p.t-p.b)*(1-TEL.v[i]*3.6/vmax);
    i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();
  yLabels(c,p,vmax,0);cursorLine(c,p);}
function drawElev(){const c=CE,p={l:34,r:8,t:6,b:14};fit(c);axes(c,p);const{ctx,W,H}=c;
  const lo=T.elevMin,hi=T.elevMax,rng=Math.max(hi-lo,1);
  ctx.beginPath();for(let i=0;i<N;i++){const x=X(c,p,T.s[i]),y=p.t+(H-p.t-p.b)*(1-(T.elev[i]-lo)/rng);
    i?ctx.lineTo(x,y):ctx.moveTo(x,y);}
  ctx.lineTo(X(c,p,T.s[N-1]),H-p.b);ctx.lineTo(X(c,p,T.s[0]),H-p.b);ctx.closePath();
  const grd=ctx.createLinearGradient(0,p.t,0,H-p.b);grd.addColorStop(0,'rgba(199,147,99,.5)');
  grd.addColorStop(1,'rgba(199,147,99,.04)');ctx.fillStyle=grd;ctx.fill();
  ctx.strokeStyle='#c79363';ctx.lineWidth=1.4;ctx.beginPath();
  for(let i=0;i<N;i++){const x=X(c,p,T.s[i]),y=p.t+(H-p.t-p.b)*(1-(T.elev[i]-lo)/rng);
    i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();
  yLabels(c,p,hi,lo);cursorLine(c,p);}
function drawFuel(){const c=CF,p={l:34,r:8,t:6,b:14};fit(c);axes(c,p);const{ctx,W,H}=c;
  const fmax=Math.max(TEL.fuelCum[N-1]*1.1,1e-3);
  ctx.strokeStyle='#d6fb41';ctx.lineWidth=1.7;ctx.beginPath();
  for(let i=0;i<N;i++){const x=X(c,p,T.s[i]),y=p.t+(H-p.t-p.b)*(1-TEL.fuelCum[i]/fmax);
    i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();
  ctx.lineTo(X(c,p,T.s[N-1]),H-p.b);ctx.lineTo(p.l,H-p.b);ctx.closePath();
  ctx.fillStyle='rgba(214,251,65,.07)';ctx.fill();
  yLabels(c,p,fmax,0);cursorLine(c,p);}
function yLabels(c,p,hi,lo){const{ctx,W,H}=c;ctx.fillStyle='#5f7180';ctx.font='9px IBM Plex Mono';
  ctx.textAlign='right';for(let g=0;g<=4;g++){const v=lo+(hi-lo)*(1-g/4);
    ctx.fillText(v>=100?v.toFixed(0):v.toFixed(1),p.l-4,p.t+(H-p.t-p.b)*g/4+3);}ctx.textAlign='left';}
function cursorLine(c,p){const{ctx,W,H}=c,x=X(c,p,T.s[cursorI]);
  ctx.strokeStyle='rgba(255,255,255,.5)';ctx.lineWidth=1;ctx.setLineDash([2,2]);
  ctx.beginPath();ctx.moveTo(x,p.t);ctx.lineTo(x,H-p.b);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(x,p.t,2.5,0,7);ctx.fill();}
function drawCharts(){drawSpeed();drawElev();drawFuel();}

// ---- HUD ----
const $=id=>document.getElementById(id);
function setHUD(m){
  $('m_fuel').innerHTML=`${m.fuelG.toFixed(3)}<small>g · ${m.fuelMl.toFixed(2)} mL</small>`;
  $('m_econ').innerHTML=`${m.kmL.toFixed(0)}<small>km/L</small>`;
  $('m_time').innerHTML=`${m.time.toFixed(1)}<small>s</small>`;
  $('m_margin').innerHTML=`${m.margin>=0?'+':''}${m.margin.toFixed(1)}<small>s</small>`;
  $('m_avg').innerHTML=`${m.avgKmh.toFixed(1)}<small>km/h</small>`;
  $('m_status').textContent=m.feasible?'FEASIBLE':'DQ RISK';
  $('m_statusbox').className='g status '+(m.feasible?'ok':'bad');
  $('ct_spd').textContent=`${m.pulses} pulses · ${m.avgKmh.toFixed(1)} avg · ${m.brakeG.toFixed(2)} g brake`;
  $('ct_elev').textContent=`Δ ${(T.elevMax-T.elevMin).toFixed(1)} m`;
  $('ct_fuel').textContent=`11-lap ${m.totMl.toFixed(1)} mL`;
  $('m_margin').style.color=m.margin<0?'var(--danger)':'';
}

// ---- cursor / readout ----
function setCursor(i){cursorI=Math.min(Math.max(i|0,0),N-1);
  car.setLatLng(latlng[cursorI]);cursorMk.setLatLng(latlng[cursorI]);
  const on=TEL.on[cursorI];
  car.setStyle({fillColor:on?'#ff7a3d':'#42b8f2'});
  $('c_dist').textContent=`${T.s[cursorI].toFixed(0)} m`;
  $('c_spd').textContent=`${(TEL.v[cursorI]*3.6).toFixed(1)} km/h`;
  $('c_eng').innerHTML=on?'<span style="color:#ff7a3d">● PULSE</span>':'<span style="color:#42b8f2">○ GLIDE</span>';
  $('c_elev').textContent=`${T.elev[cursorI].toFixed(1)} m`;
  drawCharts();}

// ---- recompute everything ----
function recompute(){
  TEL=simulate(6,3); spdMin=Infinity;spdMax=0;
  for(let i=0;i<N;i++){spdMin=Math.min(spdMin,TEL.v[i]);spdMax=Math.max(spdMax,TEL.v[i]);}
  setHUD(metrics(TEL)); paintTrack(); setCursor(cursorI); buildLegend();
}

// ---- legend ----
function buildLegend(){const el=$('legend');
  if(colorMode==='engine')el.innerHTML=
    `<span class="dot" style="background:#ff7a3d"></span>Pulse&nbsp;&nbsp;<span class="dot" style="background:#42b8f2"></span>Glide`;
  else if(colorMode==='speed')el.innerHTML=
    `${(spdMin*3.6).toFixed(0)}<span class="swatch"></span>${(spdMax*3.6).toFixed(0)} km/h`;
  else el.innerHTML=`${T.elevMin.toFixed(0)}<span class="swatch"></span>${T.elevMax.toFixed(0)} m`;
}

/* ====================================================================
   Controls wiring
   ==================================================================== */
function paramFromUI(k,val){
  if(k==='vLowKmh')P.vLow=val/3.6;
  else if(k==='vHighKmh')P.vHigh=val/3.6;
  else if(k==='powerKw')P.powerMax=val*1000;
  else P[k]=val;
}
function uiFromParam(k){
  if(k==='vLowKmh')return P.vLow*3.6;
  if(k==='vHighKmh')return P.vHigh*3.6;
  if(k==='powerKw')return P.powerMax/1000;
  return P[k];
}
const sliders=[...document.querySelectorAll('.sl')].map(el=>{
  const k=el.dataset.k,inp=el.querySelector('input'),vv=el.querySelector('.vv');
  inp.min=el.dataset.min;inp.max=el.dataset.max;inp.step=el.dataset.step;
  const fmt=v=>{if(el.dataset.pct)return(v*100).toFixed(0)+'%';
    const dec=(+el.dataset.step<0.01)?4:(+el.dataset.step<1?(+el.dataset.step<0.1?2:1):0);
    return v.toFixed(dec)+(el.dataset.unit?' '+el.dataset.unit:'');};
  function sync(){const v=uiFromParam(k);inp.value=v;vv.textContent=fmt(+v);
    inp.style.setProperty('--p',((v-inp.min)/(inp.max-inp.min)*100)+'%');}
  inp.addEventListener('input',()=>{paramFromUI(k,+inp.value);vv.textContent=fmt(+inp.value);
    inp.style.setProperty('--p',((inp.value-inp.min)/(inp.max-inp.min)*100)+'%');
    clearTimeout(inp._t);inp._t=setTimeout(recompute,30);});
  return{k,el,inp,vv,sync,fmt};
});
function syncSliders(){sliders.forEach(s=>s.sync());}

$('btnOpt').addEventListener('click',()=>{const b=$('btnOpt');b.textContent='⟳ Working…';
  setTimeout(()=>{optimise();syncSliders();recompute();b.textContent='⟳ Optimise';},20);});
$('btnReset').addEventListener('click',()=>{Object.assign(P,JSON.parse(JSON.stringify(DEFAULTS)));
  syncSliders();recompute();});

document.querySelectorAll('#colorChips .chip').forEach(c=>c.addEventListener('click',()=>{
  document.querySelectorAll('#colorChips .chip').forEach(x=>x.classList.remove('on'));
  c.classList.add('on');colorMode=c.dataset.c;paintTrack();buildLegend();}));
$('tileToggle').addEventListener('click',function(){const on=this.dataset.on==='1';
  this.dataset.on=on?'0':'1';this.classList.toggle('on',!on);this.textContent=on?'Schematic':'Map';
  document.getElementById('mapwrap').classList.toggle('schematic',on);});

// chart hover → cursor
[CS,CE,CF].forEach(c=>{c.cv.addEventListener('mousemove',e=>{const r=c.cv.getBoundingClientRect();
  const p=34,frac=(e.clientX-r.left-p)/(r.width-p-8);setCursor(Math.round(frac*(N-1)));pause();});});

// ---- animation / transport ----
let playing=false,simT=0,simSpeed=4,raf=null,lastTs=0;
const scrub=$('scrub');
function tick(ts){if(!playing){return;}const dt=(ts-lastTs)/1000||0;lastTs=ts;
  simT+=dt*simSpeed; const lapT=TEL.timeAvg||TEL.time; if(simT>=lapT)simT-=lapT;
  // map simT -> index via tCum
  let i=cursorI; const tc=TEL.tCum;
  if(simT<tc[i])i=0; while(i<N-1&&tc[i]<simT)i++;
  setCursor(i); scrub.value=(T.s[i]/T.lapLength*1000)|0;
  raf=requestAnimationFrame(tick);}
function play(){playing=true;lastTs=performance.now();$('play').textContent='⏸';raf=requestAnimationFrame(tick);}
function pause(){playing=false;$('play').textContent='▶';if(raf)cancelAnimationFrame(raf);}
$('play').addEventListener('click',()=>{playing?pause():(simT=TEL.tCum[cursorI]||0,play());});
scrub.addEventListener('input',()=>{pause();const d=scrub.value/1000*T.lapLength;
  let i=0;while(i<N-1&&T.s[i]<d)i++;simT=TEL.tCum[i]||0;setCursor(i);});
$('spdctl').addEventListener('click',()=>{const sp=[1,2,4,8,16];simSpeed=sp[(sp.indexOf(simSpeed)+1)%sp.length];
  $('spdctl').innerHTML='×<b>'+simSpeed+'</b>';});

// ---- boot ----
function boot(){syncSliders();recompute();drawCharts();
  setTimeout(()=>{map.invalidateSize();map.fitBounds(L.latLngBounds(latlng).pad(.06));drawCharts();},120);
  $('loading').style.display='none';}
window.addEventListener('resize',()=>{clearTimeout(window._rz);window._rz=setTimeout(drawCharts,120);});
if(window.L){boot();}else{window.addEventListener('load',boot);}
</script>
</body>
</html>
