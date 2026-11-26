"use strict";
let DATA = {frames:{weekly:[],daily:[]}, generated:"", universe:0};
let tf = "weekly";

const $ = id => document.getElementById(id);
function frame(){ return (DATA.frames && DATA.frames[tf]) || []; }

// ---------- candlestick renderer (canvas, no libraries) ----------
// Draws candles + 50/200 EMA lines + a volume strip + breakout & 52-week-high lines.
function draw(cv, r){
  const candles=r.candles||[], level=r.level, e50=r.ema50||[], e200=r.ema200||[],
        vol=r.vol||[], hi52=r.hi52;
  const dpr=window.devicePixelRatio||1;
  const W=cv.clientWidth, H=cv.clientHeight;
  cv.width=W*dpr; cv.height=H*dpr;
  const x=cv.getContext("2d"); x.scale(dpr,dpr); x.clearRect(0,0,W,H);
  if(!candles.length) return;

  const padT=8, padL=6, padR=54, padB=6, gap=6;
  const volH=Math.max(24, H*0.20);            // bottom strip for volume
  const priceBot=H-volH-gap-padB;             // bottom of the price area
  const n=candles.length, cw=(W-padL-padR)/n, bw=Math.max(1,Math.min(10,cw*0.62));
  const cx=i=>padL+cw*(i+0.5);

  // price scale — include candles, level, 52w high and both EMAs so nothing clips
  let lo=Infinity, hi=-Infinity;
  for(const c of candles){ lo=Math.min(lo,c[3]); hi=Math.max(hi,c[2]); }
  if(level) { lo=Math.min(lo,level); hi=Math.max(hi,level); }
  if(hi52)  { hi=Math.max(hi,hi52); }
  for(const v of e50){ if(v){ lo=Math.min(lo,v); hi=Math.max(hi,v); } }
  for(const v of e200){ if(v){ lo=Math.min(lo,v); hi=Math.max(hi,v); } }
  const span=(hi-lo)||1; lo-=span*0.04; hi+=span*0.04;
  const y=v=>padT+(hi-v)/(hi-lo)*(priceBot-padT);

  // volume bars
  let vmax=0; for(const v of vol) if(v>vmax) vmax=v;
  if(vmax>0){
    const vTop=priceBot+gap, vBot=H-padB;
    for(let i=0;i<n;i++){
      const up=candles[i][4]>=candles[i][1];
      const vh=(vol[i]/vmax)*(vBot-vTop);
      x.fillStyle = up ? "rgba(40,199,133,.40)" : "rgba(255,95,95,.40)";
      x.fillRect(cx(i)-bw/2, vBot-vh, bw, Math.max(0.5,vh));
    }
    x.fillStyle="#6b7686"; x.font="9px Inter,sans-serif";
    x.fillText("Vol", padL+2, H-padB-2);
  }

  // 52-week high line
  if(hi52){
    x.strokeStyle="#8a6dff"; x.setLineDash([2,3]); x.lineWidth=1;
    x.beginPath(); x.moveTo(padL,y(hi52)); x.lineTo(W-padR,y(hi52)); x.stroke();
    x.setLineDash([]); x.fillStyle="#8a6dff"; x.font="10px Inter,sans-serif";
    x.fillText("52wH "+hi52.toFixed(1), W-padR+3, y(hi52)+3);
  }
  // breakout level line
  if(level){
    x.strokeStyle="#ffc24b"; x.setLineDash([4,3]); x.lineWidth=1;
    x.beginPath(); x.moveTo(padL,y(level)); x.lineTo(W-padR,y(level)); x.stroke();
    x.setLineDash([]); x.fillStyle="#ffc24b"; x.font="10px Inter,sans-serif";
    x.fillText(level.toFixed(1), W-padR+3, y(level)+3);
  }

  // EMA polylines
  function line(series,col){
    let on=false; x.strokeStyle=col; x.lineWidth=1.4; x.beginPath();
    for(let i=0;i<n;i++){ const v=series[i]; if(!v) continue;
      const px=cx(i), py=y(v);
      if(!on){ x.moveTo(px,py); on=true; } else x.lineTo(px,py); }
    if(on) x.stroke();
  }
  line(e200,"#4aa3ff");    // 200 EMA — blue
  line(e50,"#ffb02e");     // 50 EMA — amber

  // candles
  for(let i=0;i<n;i++){
    const c=candles[i], X=cx(i), up=c[4]>=c[1], col=up?"#28c785":"#ff5f5f";
    x.strokeStyle=col; x.fillStyle=col; x.lineWidth=1;
    x.beginPath(); x.moveTo(X,y(c[2])); x.lineTo(X,y(c[3])); x.stroke();
    const yo=y(c[1]),yc=y(c[4]),top=Math.min(yo,yc),h=Math.max(1,Math.abs(yc-yo));
    x.fillRect(X-bw/2,top,bw,h);
  }
  // last price
  const last=candles[n-1][4];
  x.fillStyle="#cdd6e0"; x.font="10px Inter,sans-serif";
  x.fillText(last.toFixed(1), W-padR+3, y(last)+3);

  // legend (top-left)
  x.font="9px Inter,sans-serif";
  x.fillStyle="#ffb02e"; x.fillText("EMA 50", padL+2, padT+9);
  x.fillStyle="#4aa3ff"; x.fillText("EMA 200", padL+2, padT+20);
}

function chip(p){
  const b = p.status==="breakout";
  return '<span class="chip'+(b?' brk':'')+'">'+(b?'▲ ':'')+p.name+'</span>';
}

function render(){
  const pat=$("pat").value, q=$("q").value.trim().toUpperCase(),
        brkonly=$("brkonly").checked, sort=$("sort").value,
        mkt=($("mkt")?$("mkt").value:"all");
  let rows = frame().filter(r=>{
    const m=r.mkt||"IN";
    if(mkt==="IN"    && m!=="IN") return false;
    if(mkt==="US"    && m!=="US") return false;                  // S&P 500 only
    if(mkt==="R3000" && !(m==="US"||m==="US2")) return false;    // Russell 3000 ⊇ S&P 500
    if(q && !r.symbol.includes(q)) return false;
    if(brkonly && !r.brk) return false;
    if(pat && !r.patterns.some(p=>p.name===pat)) return false;
    return true;
  });
  if(sort==="sym") rows.sort((a,b)=>a.symbol<b.symbol?-1:1);
  else if(sort==="conf") rows.sort((a,b)=>b.conf-a.conf);
  else rows.sort((a,b)=>(b.brk-a.brk)||(b.conf-a.conf));
  const g=$("grid"); g.innerHTML="";
  $("empty").hidden = rows.length>0;
  rows.forEach(r=>{
    const d=document.createElement("div"); d.className="card";
    d.innerHTML =
      '<div class="crow"><div><span class="sym">'+r.symbol+'</span> '+
        '<span class="co">'+(r.company||"")+'</span></div>'+
        '<span class="px">'+(r.cur||'₹')+r.last+'</span></div>'+
      '<div class="chips">'+r.patterns.map(chip).join("")+'</div>'+
      '<canvas></canvas>'+
      '<div class="conf">confidence <b>'+r.conf.toFixed(2)+'</b> · '+r.brk+' breakout(s)</div>'+
      '<div class="det">'+r.patterns.map(p=>p.name+": "+p.detail).join(" · ")+'</div>';
    g.appendChild(d);
    draw(d.querySelector("canvas"), r);
    d.onclick=()=>openModal(r);
  });
}

function openModal(r){
  const s=$("sheet");
  s.innerHTML =
    '<button class="close" onclick="closeModal()">✕ close</button>'+
    '<h2>'+r.symbol+' <span class="co">'+(r.company||"")+'</span></h2>'+
    '<div class="px">'+(r.cur||'₹')+r.last+' · '+tf+' · confidence '+r.conf.toFixed(2)+
      (r.hi52?(' · 52w high '+(r.cur||'₹')+r.hi52):'')+'</div>'+
    '<canvas></canvas><ul class="plist">'+
    r.patterns.map(p=>'<li><span class="pn">'+(p.status==="breakout"?"▲ ":"")+p.name+
      '</span> <span class="conf">('+p.conf.toFixed(2)+')</span><br>'+
      '<span class="det" style="max-height:none">'+p.detail+'</span></li>').join("")+
    '</ul>';
  $("modal").classList.add("on");
  draw(s.querySelector("canvas"), r);
}
function closeModal(){ $("modal").classList.remove("on"); }
window.closeModal = closeModal;

function buildPatternList(){
  const set=new Set();
  for(const f in DATA.frames) for(const r of DATA.frames[f]) for(const p of r.patterns) set.add(p.name);
  const sel=$("pat");
  [...set].sort().forEach(n=>{ const o=document.createElement("option"); o.value=o.textContent=n; sel.appendChild(o); });
}
function stats(){
  const w=DATA.frames.weekly||[], d=DATA.frames.daily||[];
  const wb=w.reduce((s,r)=>s+r.brk,0), db=d.reduce((s,r)=>s+r.brk,0);
  $("stats").innerHTML =
    'Weekly <b>'+w.length+'</b> stocks · <b class="hot">'+wb+'</b> breakouts &nbsp;|&nbsp; '+
    'Daily <b>'+d.length+'</b> stocks · <b class="hot">'+db+'</b> breakouts';
  $("gen").textContent = DATA.generated ? ("updated "+DATA.generated+" · "+DATA.universe+" scanned") : "";
  $("footgen").textContent = DATA.generated ? (" Last scan: "+DATA.generated+".") : "";
}

$("tfseg").querySelectorAll("button").forEach(b=>b.onclick=()=>{
  tf=b.dataset.tf;
  $("tfseg").querySelectorAll("button").forEach(x=>x.classList.remove("on"));
  b.classList.add("on"); render();
});
["mkt","pat","sort","brkonly","q"].forEach(id=>{ const el=$(id); if(!el) return; el.oninput=render; el.onchange=render; });
$("modal").onclick=e=>{ if(e.target.id==="modal") closeModal(); };
document.addEventListener("keydown",e=>{ if(e.key==="Escape") closeModal(); });
let rt; window.addEventListener("resize",()=>{ clearTimeout(rt); rt=setTimeout(render,120); });

function load(url){ return fetch(url+"?_="+Date.now()).then(r=>r.ok?r.json():null).catch(()=>null); }
Promise.all([load("data.json"), load("data_r3000.json")]).then(([a,b])=>{
  if(!a){ $("loading").textContent="Could not load scan data (data.json). Run the scanner to generate it."; return; }
  DATA=a;
  if(b && b.frames){                           // merge the Russell-3000 daily feed
    for(const tf of ["weekly","daily"]) DATA.frames[tf]=(DATA.frames[tf]||[]).concat(b.frames[tf]||[]);
    if(b.universe) DATA.universe=(DATA.universe||0)+b.universe;
    if(b.generated) DATA.r3000gen=b.generated;
  }
  $("loading").hidden=true; buildPatternList(); stats(); render();
});
