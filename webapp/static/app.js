'use strict';
const $ = s => document.querySelector(s);
const BURN = '#ff6a1f', GLIDE = '#1fe0a8', SIGNAL = '#ffd23f', DANGER = '#ff3b60', MUTE = '#566576';

const GROUPS = [
  {name:'VEHICLE', items:[
    {k:'mass_car',label:'Car mass',unit:'kg',min:10,max:120,step:1,dec:0},
    {k:'mass_driver',label:'Driver mass',unit:'kg',min:40,max:110,step:1,dec:0},
    {k:'Cd',label:'Drag coeff',unit:'',min:0,max:0.5,step:0.001,dec:3},
    {k:'frontal_area',label:'Frontal area',unit:'m²',min:0.2,max:1.0,step:0.005,dec:3},
    {k:'Crr',label:'Rolling resistance',unit:'',min:0.0005,max:0.02,step:0.0001,dec:4},
    {k:'driveline_eff',label:'Driveline η',unit:'',min:0.7,max:1.0,step:0.01,dec:2},
    {k:'inertia_factor',label:'Rotating inertia',unit:'',min:0,max:0.1,step:0.005,dec:3},
    {k:'corner_loss',label:'Cornering loss',unit:'',min:0,max:1.0,step:0.01,dec:2},
  ]},
  {name:'ENGINE · HONDA GX35', items:[
    {k:'burn_power_wheel',label:'Burst power (wheel)',unit:'W',min:100,max:1200,step:10,dec:0},
    {k:'bsfc',label:'BSFC',unit:'g/kWh',min:250,max:700,step:5,dec:0},
    {k:'restart_fuel_g',label:'Restart cost',unit:'g',min:0,max:0.2,step:0.005,dec:3},
  ]},
  {name:'RACE · ARTICLE 226', items:[
    {k:'n_laps',label:'Laps',unit:'',min:1,max:30,step:1,dec:0},
    {k:'total_time_limit',label:'Time limit',unit:'s',min:600,max:4000,step:10,dec:0},
    {k:'time_margin',label:'Safety margin',unit:'',min:0,max:0.2,step:0.01,dec:2},
  ]},
  {name:'GRIP & AIR', items:[
    {k:'a_lat_max',label:'Lateral grip',unit:'m/s²',min:2,max:8,step:0.1,dec:1},
    {k:'rho',label:'Air density',unit:'kg/m³',min:1.0,max:1.3,step:0.01,dec:2},
  ]},
  {name:'WIND', items:[
    {k:'wind_speed_kmh',label:'Wind speed',unit:'km/h',min:0,max:50,step:0.5,dec:1},
    {k:'wind_dir_deg',label:'Wind from (bearing)',unit:'°',min:0,max:360,step:5,dec:0},
  ]},
];

let TRACK = null, STATE = {}, LAST = null, PRESET_LIST = [], PRESET_FIRST = null;

// shapes (burn zones, avg line …) rebuilt on each draw; kept so the hover
// crosshair can be overlaid without wiping them out.
let SPEED_SHAPES = [], ELEV_SHAPES = [];
// indices of the hover-catcher and (initially empty) cursor traces in the map.
let MAP_CURSOR_IDX = -1, MAP_CATCHER_IDX = -1;

const LAYOUT = () => ({
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'JetBrains Mono, monospace', size:10, color:'#7c8a9b'},
  margin:{l:48,r:14,t:8,b:34}, showlegend:false, hovermode:'closest',
  xaxis:{gridcolor:'#141c27',zeroline:false,linecolor:'#1b2531',tickcolor:'#1b2531'},
  yaxis:{gridcolor:'#141c27',zeroline:false,linecolor:'#1b2531',tickcolor:'#1b2531'},
});
const CFG = {displayModeBar:false, responsive:true};

// ---- helpers -------------------------------------------------------------
function runs(u, val){          // contiguous [i0,i1] index runs where u==val
  const out=[]; let a=null;
  for(let i=0;i<u.length;i++){
    if(u[i]===val && a===null) a=i;
    if((u[i]!==val||i===u.length-1) && a!==null){ out.push([a, u[i]===val?i:i-1]); a=null; }
  }
  return out;
}
function burnShapes(u, s){
  return runs(u,1).map(([a,b])=>({type:'rect',xref:'x',yref:'paper',
    x0:s[a],x1:s[Math.min(b+1,s.length-1)],y0:0,y1:1,
    fillcolor:'rgba(255,106,31,.15)',line:{width:0},layer:'below'}));
}

// ---- controls ------------------------------------------------------------
function renderControls(){
  const root = $('#paramGroups'); root.innerHTML='';
  GROUPS.forEach(g=>{
    const wrap=document.createElement('div'); wrap.className='pgroup';
    wrap.innerHTML=`<div class="pgroup-hd">${g.name}</div>`;
    g.items.forEach(it=>{
      const f=document.createElement('div'); f.className='field';
      f.innerHTML=`
        <div class="field-top">
          <span class="field-label">${it.label}</span>
          <span class="field-val"><input type="number" id="n_${it.k}" min="${it.min}" max="${it.max}" step="${it.step}"><span class="unit">${it.unit}</span></span>
        </div>
        <input type="range" id="r_${it.k}" min="${it.min}" max="${it.max}" step="${it.step}">`;
      wrap.appendChild(f);
    });
    root.appendChild(wrap);
  });
  GROUPS.flatMap(g=>g.items).forEach(it=>{
    const r=$('#r_'+it.k), n=$('#n_'+it.k);
    const setFill=v=>r.style.setProperty('--fill',((v-it.min)/(it.max-it.min)*100)+'%');
    const sync=(v,from)=>{ v=Math.min(it.max,Math.max(it.min,v)); STATE[it.k]= it.dec===0?Math.round(v):v;
      r.value=v; if(from!=='n') n.value=Number(v).toFixed(it.dec); setFill(v); };
    r.addEventListener('input',()=>sync(parseFloat(r.value),'r'));
    n.addEventListener('change',()=>sync(parseFloat(n.value)||it.min,'n'));
    sync(STATE[it.k] ?? it.min);
  });
}
function applyParams(p){ Object.assign(STATE,p); renderControls(); }

// ---- status / overlay ----------------------------------------------------
function setStatus(state, txt){ const p=$('#statusPill'); p.dataset.state=state; $('#statusTxt').textContent=txt; }
function busy(on){ $('#overlay').classList.toggle('show',on); if(on) setStatus('busy','COMPUTING'); }

// ---- optimise ------------------------------------------------------------
async function optimise(targetOverride){
  busy(true);
  $('#ovSub').textContent = STATE.quality==='accurate' ? 'high-resolution DP…' : 'solving dynamic program…';
  const body = {...STATE};
  if(targetOverride) body.target_override = targetOverride;
  try{
    const r = await fetch('/api/optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    LAST = await r.json();
    render(LAST);
    setStatus(LAST.feasible?'ready':'dq', LAST.feasible?'OPTIMAL':'DISQUALIFIED');
  }catch(e){ setStatus('dq','ERROR'); console.error(e); }
  busy(false);
}

function render(res){
  const s=res.summary;
  $('#kpiLap').textContent=s.lap_time.toFixed(1);
  $('#kpiFuel').textContent=s.fuel_ml.toFixed(2);
  $('#kpiEco').textContent=Math.round(s.km_l);
  $('#kpiPulse').textContent=s.n_pulses;
  $('#kpiSpd').textContent=s.avg_speed_kmh.toFixed(1);
  $('#kpiMargin').textContent=(s.margin_s>=0?'+':'')+s.margin_s.toFixed(0);
  const mc=$('#kpiMarginCell'); mc.classList.toggle('is-good',s.margin_s>=0); mc.classList.toggle('is-bad',s.margin_s<0);
  drawMap(res); drawSpeed(res); drawElev(res); drawPareto(res); drawCheat(res);
}

// ---- plots ---------------------------------------------------------------
function drawMap(res){
  const {x,y}=TRACK, u=res.u, traces=[];
  traces.push({x,y,mode:'lines',line:{color:'#1b2531',width:7},hoverinfo:'skip'}); // base
  [[1,BURN],[0,GLIDE]].forEach(([val,col])=>runs(u,val).forEach(([a,b])=>{
    traces.push({x:x.slice(a,b+2),y:y.slice(a,b+2),mode:'lines',
      line:{color:col,width:4.5},hoverinfo:'skip'});
  }));

  // Yellow markers: speed at the start and end of each acceleration (BURN) phase.
  if(res.phases && res.phases.length){
    const mx=[],my=[],mtxt=[];
    res.phases.filter(p=>p.kind==='BURN').forEach(p=>{
      const i0=Math.round(p.from_m/TRACK.lap_length*x.length)%x.length;
      const i1=Math.round(p.to_m  /TRACK.lap_length*x.length)%x.length;
      mx.push(x[i0]); my.push(y[i0]); mtxt.push(p.v_in.toFixed(0));
      mx.push(x[i1]); my.push(y[i1]); mtxt.push(p.v_out.toFixed(0));
    });
    if(mx.length) traces.push({x:mx,y:my,mode:'markers+text',text:mtxt,textposition:'top center',
      textfont:{color:SIGNAL,size:10},
      marker:{color:SIGNAL,size:9,line:{color:'#0a0e15',width:1.5}},
      hovertemplate:'%{text} km/h<extra></extra>'});
  }

  traces.push({x:[x[0]],y:[y[0]],mode:'markers',marker:{symbol:'diamond',color:SIGNAL,size:12,line:{color:'#0a0e15',width:1}},hoverinfo:'skip'});

  // Invisible full-track hover catcher: pointNumber maps 1:1 to track index,
  // letting the map drive the synchronized crosshair.
  traces.push({x,y,mode:'markers',marker:{size:9,color:'rgba(0,0,0,0)'},
    hovertemplate:'%{customdata:.0f} m<extra></extra>',customdata:TRACK.s});
  MAP_CATCHER_IDX = traces.length-1;

  // Cursor marker (synchronized hover indicator) — starts empty.
  traces.push({x:[],y:[],mode:'markers',
    marker:{symbol:'circle-open',color:SIGNAL,size:16,line:{color:SIGNAL,width:2.5}},hoverinfo:'skip'});
  MAP_CURSOR_IDX = traces.length-1;

  const lay=LAYOUT(); lay.margin={l:8,r:8,t:8,b:8}; lay.hovermode='closest';
  lay.xaxis={visible:false}; lay.yaxis={visible:false,scaleanchor:'x',scaleratio:1};
  lay.annotations = windAnnotations();
  Plotly.react('mapPlot',traces,lay,CFG);
}

// Wind read-out for the map: an arrow pointing the way the wind blows + a label.
function windAnnotations(){
  const spd = +(STATE.wind_speed_kmh ?? 0), dir = +(STATE.wind_dir_deg ?? 0);
  const label = {xref:'paper',yref:'paper',x:0.99,y:0.985,xanchor:'right',yanchor:'top',
    showarrow:false,align:'right',
    text:`WIND&nbsp;<b>${spd.toFixed(1)}</b>&nbsp;km/h${spd>0?`<br>from ${dir.toFixed(0)}°`:''}`,
    font:{color:SIGNAL,size:10,family:'JetBrains Mono, monospace'},
    bgcolor:'rgba(7,10,14,.6)',bordercolor:'rgba(255,210,63,.35)',borderwidth:1,borderpad:4};
  if(spd<=0) return [label];
  const to=(dir+180)*Math.PI/180, L=30;          // bearing wind blows TOWARD; px length
  const arrow={xref:'paper',yref:'paper',x:0.93,y:0.90,axref:'pixel',ayref:'pixel',
    ax:-L*Math.sin(to), ay:L*Math.cos(to),       // tail offset (pixel y grows downward)
    showarrow:true,arrowhead:3,arrowsize:1.5,arrowwidth:2.4,arrowcolor:SIGNAL,text:''};
  return [arrow,label];
}
function drawSpeed(res){
  const s=TRACK.s, lay=LAYOUT();
  lay.shapes=burnShapes(res.u,s);
  lay.yaxis.title={text:'km/h',font:{size:9}};
  const avg=res.summary.avg_speed_kmh;
  lay.shapes.push({type:'line',xref:'paper',x0:0,x1:1,yref:'y',y0:avg,y1:avg,line:{color:GLIDE,width:1,dash:'dot'}});
  SPEED_SHAPES = lay.shapes.slice();
  Plotly.react('speedPlot',[
    {x:s,y:res.cap_kmh,mode:'lines',line:{color:DANGER,width:1,dash:'dash'},name:'cap',hovertemplate:'cap %{y:.0f}<extra></extra>'},
    {x:s,y:res.v_kmh,mode:'lines',line:{color:'#cfe0ee',width:2},name:'speed',hovertemplate:'%{x:.0f} m · %{y:.1f} km/h<extra></extra>'},
  ],lay,CFG);
}
function drawElev(res){
  const s=TRACK.s, lay=LAYOUT(); lay.shapes=burnShapes(res.u,s);
  lay.yaxis.title={text:'m',font:{size:9}};
  ELEV_SHAPES = lay.shapes.slice();
  Plotly.react('elevPlot',[
    {x:s,y:TRACK.elev,mode:'lines',line:{color:'#8aa0b6',width:1.6},fill:'tozeroy',
      fillcolor:'rgba(138,160,182,.05)',hovertemplate:'%{x:.0f} m · %{y:.1f} m<extra></extra>'},
  ],lay,CFG);
  Plotly.relayout('elevPlot',{'yaxis.range':[Math.min(...TRACK.elev)-0.5,Math.max(...TRACK.elev)+0.5]});
}

// ---- synchronized hover --------------------------------------------------
function nearestIdx(distM){
  const s=TRACK.s; if(distM<=s[0]) return 0; if(distM>=s[s.length-1]) return s.length-1;
  let lo=0, hi=s.length-1;                      // binary search (s is sorted)
  while(hi-lo>1){ const mid=(lo+hi)>>1; if(s[mid]<distM) lo=mid; else hi=mid; }
  return (distM-s[lo] <= s[hi]-distM) ? lo : hi;
}
function vline(x){ return {type:'line',xref:'x',x0:x,x1:x,yref:'paper',y0:0,y1:1,
  line:{color:SIGNAL,width:1.2,dash:'dot'}}; }
function showCursor(i){
  if(i==null||i<0||!TRACK) return;
  const x=TRACK.s[i];
  Plotly.relayout('speedPlot',{shapes:SPEED_SHAPES.concat([vline(x)])});
  Plotly.relayout('elevPlot', {shapes:ELEV_SHAPES.concat([vline(x)])});
  if(MAP_CURSOR_IDX>=0)
    Plotly.restyle('mapPlot',{x:[[TRACK.x[i]]],y:[[TRACK.y[i]]]},[MAP_CURSOR_IDX]);
}
function hideCursor(){
  if(!TRACK) return;
  Plotly.relayout('speedPlot',{shapes:SPEED_SHAPES});
  Plotly.relayout('elevPlot', {shapes:ELEV_SHAPES});
  if(MAP_CURSOR_IDX>=0) Plotly.restyle('mapPlot',{x:[[]],y:[[]]},[MAP_CURSOR_IDX]);
}
function wireHover(){
  ['speedPlot','elevPlot'].forEach(id=>{
    const el=$('#'+id);
    el.on('plotly_hover',ev=>showCursor(nearestIdx(ev.points[0].x)));
    el.on('plotly_unhover',hideCursor);
  });
  const m=$('#mapPlot');
  m.on('plotly_hover',ev=>{ const p=ev.points[0];
    if(p && p.curveNumber===MAP_CATCHER_IDX) showCursor(p.pointNumber); });
  m.on('plotly_unhover',hideCursor);
}
function drawPareto(res){
  const p=res.pareto, t=p.map(r=>r[1]), f=p.map(r=>r[2]), lay=LAYOUT();
  lay.xaxis.title={text:'lap time (s)',font:{size:9}}; lay.yaxis.title={text:'mL/lap',font:{size:9}};
  lay.shapes=[{type:'line',x0:res.summary.target_lap_time,x1:res.summary.target_lap_time,yref:'paper',y0:0,y1:1,
    line:{color:DANGER,width:1.2,dash:'dash'}}];
  lay.annotations=[{x:res.summary.target_lap_time,y:1,yref:'paper',text:'DQ limit',showarrow:false,
    font:{color:DANGER,size:9},xanchor:'left',yanchor:'top'}];
  Plotly.react('paretoPlot',[
    {x:t,y:f,mode:'lines+markers',line:{color:'#5c6b7d',width:1.5},marker:{color:GLIDE,size:5},
      hovertemplate:'%{x:.0f} s · %{y:.2f} mL<extra></extra>'},
    {x:[res.summary.lap_time],y:[res.summary.fuel_ml],mode:'markers',
      marker:{symbol:'star',color:BURN,size:16,line:{color:'#0a0e15',width:1}},
      hovertemplate:'chosen · %{x:.0f} s · %{y:.2f} mL<extra></extra>'},
  ],lay,CFG);
  $('#paretoPlot').on('plotly_click',ev=>{ const x=ev.points[0].x; if(x) optimise(x); });
}
function drawCheat(res){
  const verb={BURN:'BURN ⛽',GLIDE:'GLIDE …',BRAKE:'BRAKE 🛑'};
  let rows=res.phases.map((p,i)=>{
    let note = p.kind==='BURN' ? `fire engine → ${p.v_out.toFixed(0)} km/h`
            : p.kind==='BRAKE' ? 'scrub speed for corner'
            : `engine OFF, coast → ${p.v_out.toFixed(0)} km/h`;
    return `<tr class="r-${p.kind.toLowerCase()}"><td>${verb[p.kind]||p.kind}</td>
      <td>${p.from_m.toFixed(0)}</td><td>${p.to_m.toFixed(0)}</td><td>${p.len_m.toFixed(0)}</td>
      <td>${p.v_in.toFixed(1)}</td><td>${p.v_out.toFixed(1)}</td><td class="note">${note}</td></tr>`;
  }).join('');
  $('#cheatBody').innerHTML=`<table class="sheet"><thead><tr>
    <th>ACTION</th><th>FROM m</th><th>TO m</th><th>LEN m</th><th>v IN</th><th>v OUT</th><th>NOTE</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

// ---- exports -------------------------------------------------------------
function download(name,text,type){
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([text],{type})); a.download=name; a.click(); URL.revokeObjectURL(a.href);
}
function exportCsv(){
  if(!LAST) return;
  let out='distance_m,speed_kmh,engine,cap_kmh\n';
  for(let i=0;i<TRACK.s.length;i++) out+=`${TRACK.s[i]},${LAST.v_kmh[i]},${LAST.u[i]},${LAST.cap_kmh[i]}\n`;
  download('trajectory.csv',out,'text/csv');
}
function exportJson(){
  if(!LAST) return;
  download('strategy.json',JSON.stringify({summary:LAST.summary,phases:LAST.phases},null,2),'application/json');
}

// ---- custom presets (server-side CRUD) -----------------------------------
function fillPresetSelect(keepSel){
  const sel=$('#presetSelect'), prev=keepSel ?? sel.value;
  sel.innerHTML='';
  if(!PRESET_LIST.length){
    sel.innerHTML='<option value="">— no saved presets —</option>';
  }else{
    PRESET_LIST.forEach(n=>{ const o=document.createElement('option'); o.value=n; o.textContent=n; sel.appendChild(o); });
    if(PRESET_LIST.includes(prev)) sel.value=prev;
  }
  const has=PRESET_LIST.length>0;
  $('#presetLoad').disabled=!has; $('#presetDelete').disabled=!has;
}
async function refreshPresets(keepSel){
  try{
    const d = await (await fetch('/api/presets')).json();
    PRESET_LIST = d.presets || [];
    PRESET_FIRST = d.first || null;
  }catch(e){ PRESET_LIST=[]; PRESET_FIRST=null; console.error(e); }
  fillPresetSelect(keepSel);
}
async function loadSelectedPreset(){
  const name=$('#presetSelect').value; if(!name) return;
  try{
    const d = await (await fetch('/api/presets/'+encodeURIComponent(name))).json();
    if(d.params){ applyParams(d.params); syncQualitySeg(); await optimise(); }
  }catch(e){ console.error(e); setStatus('dq','LOAD FAILED'); }
}
async function saveCurrentPreset(){
  const inp=$('#presetName'), name=inp.value.trim();
  if(!name){ inp.focus(); return; }
  if(PRESET_LIST.includes(name) && !confirm(`Overwrite preset “${name}”?`)) return;
  try{
    const r = await fetch('/api/presets',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name, params:{...STATE}})});
    if(!r.ok){ const e=await r.json().catch(()=>({})); throw new Error(e.detail||'save failed'); }
    inp.value=''; await refreshPresets(name);
  }catch(e){ console.error(e); alert('Could not save preset: '+e.message); }
}
async function deleteSelectedPreset(){
  const name=$('#presetSelect').value; if(!name) return;
  if(!confirm(`Delete preset “${name}”?`)) return;
  try{
    await fetch('/api/presets/'+encodeURIComponent(name),{method:'DELETE'});
    await refreshPresets();
  }catch(e){ console.error(e); }
}
function syncQualitySeg(){   // reflect STATE.quality in the segmented control
  document.querySelectorAll('.seg-btn').forEach(x=>
    x.classList.toggle('is-active', x.dataset.q===STATE.quality));
}

// ---- wiring --------------------------------------------------------------
async function boot(){
  const data = await (await fetch('/api/init')).json();
  TRACK=data.track; STATE={...data.defaults};
  $('#circuitMeta').textContent=`${TRACK.lap_length.toFixed(0)} m · ${TRACK.corners.length} corners`;
  renderControls();
  syncQualitySeg();
  drawMap({u:new Array(TRACK.x.length).fill(0)});   // show track immediately

  await refreshPresets();

  $('#presetLoad').onclick=loadSelectedPreset;
  $('#presetSave').onclick=saveCurrentPreset;
  $('#presetDelete').onclick=deleteSelectedPreset;
  $('#presetName').addEventListener('keydown',e=>{ if(e.key==='Enter') saveCurrentPreset(); });
  $('#presetSelect').addEventListener('dblclick',loadSelectedPreset);

  document.querySelectorAll('.seg-btn').forEach(b=>b.onclick=()=>{
    document.querySelectorAll('.seg-btn').forEach(x=>x.classList.remove('is-active'));
    b.classList.add('is-active'); STATE.quality=b.dataset.q;
  });
  $('#runBtn').onclick=()=>optimise();
  $('#expCsv').onclick=exportCsv; $('#expJson').onclick=exportJson;

  // Auto-load the first-created preset if one exists; otherwise run defaults.
  if(PRESET_FIRST){
    $('#presetSelect').value=PRESET_FIRST;
    await loadSelectedPreset();
  }else{
    await optimise();
  }
  wireHover();        // attach synchronized-hover handlers once plots exist
}
boot();
