"use strict";
let DATA = {frames:{weekly:[],daily:[]}, generated:"", universe:0};
let tf = "weekly";

const $ = id => document.getElementById(id);
function frame(){ return (DATA.frames && DATA.frames[tf]) || []; }

// ---------- candlestick renderer (canvas, no libraries) ----------
function draw(cv, candles, level){
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W*dpr; cv.height = H*dpr;
  const x = cv.getContext("2d"); x.scale(dpr,dpr); x.clearRect(0,0,W,H);
  if(!candles || !candles.length) return;
  const padT=8, padB=8, padL=6, padR=50;
  let lo=Infinity, hi=-Infinity;
  for(const c of candles){ lo=Math.min(lo,c[3]); hi=Math.max(hi,c[2]); }
  if(level){ lo=Math.min(lo,level); hi=Math.max(hi,level); }
  const span=(hi-lo)||1; lo-=span*0.04; hi+=span*0.04;
  const y = v => padT + (hi-v)/(hi-lo)*(H-padT-padB);
  const n = candles.length, cw=(W-padL-padR)/n, bw=Math.max(1,Math.min(9,cw*0.62));
  if(level){
    x.strokeStyle="#ffc24b"; x.setLineDash([4,3]); x.lineWidth=1;
    x.beginPath(); x.moveTo(padL,y(level)); x.lineTo(W-padR,y(level)); x.stroke();
    x.setLineDash([]); x.fillStyle="#ffc24b"; x.font="10px Inter,sans-serif";
    x.fillText(level.toFixed(1), W-padR+3, y(level)+3);
  }
  for(let i=0;i<n;i++){
    const c=candles[i], cx=padL+cw*(i+0.5), up=c[4]>=c[1];
    const col = up ? "#28c785" : "#ff5f5f";
    x.strokeStyle=col; x.fillStyle=col; x.lineWidth=1;
    x.beginPath(); x.moveTo(cx,y(c[2])); x.lineTo(cx,y(c[3])); x.stroke();
    const yo=y(c[1]), yc=y(c[4]), top=Math.min(yo,yc), h=Math.max(1,Math.abs(yc-yo));
    x.fillRect(cx-bw/2, top, bw, h);
  }
  const last=candles[n-1][4];
  x.fillStyle="#94a0b0"; x.font="10px Inter,sans-serif";
  x.fillText(last.toFixed(1), W-padR+3, y(last)+3);
}

function chip(p){
  const b = p.status==="breakout";
  return '<span class="chip'+(b?' brk':'')+'">'+(b?'▲ ':'')+p.name+'</span>';
}

function render(){
  const pat=$("pat").value, q=$("q").value.trim().toUpperCase(),
        brkonly=$("brkonly").checked, sort=$("sort").value;
  let rows = frame().filter(r=>{
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
        '<span class="px">₹'+r.last+'</span></div>'+
      '<div class="chips">'+r.patterns.map(chip).join("")+'</div>'+
      '<canvas></canvas>'+
      '<div class="conf">confidence <b>'+r.conf.toFixed(2)+'</b> · '+r.brk+' breakout(s)</div>'+
      '<div class="det">'+r.patterns.map(p=>p.name+": "+p.detail).join(" · ")+'</div>';
    g.appendChild(d);
    draw(d.querySelector("canvas"), r.candles, r.level);
    d.onclick=()=>openModal(r);
  });
}

function openModal(r){
  const s=$("sheet");
  s.innerHTML =
    '<button class="close" onclick="closeModal()">✕ close</button>'+
    '<h2>'+r.symbol+' <span class="co">'+(r.company||"")+'</span></h2>'+
    '<div class="px">₹'+r.last+' · '+tf+' · confidence '+r.conf.toFixed(2)+'</div>'+
    '<canvas></canvas><ul class="plist">'+
    r.patterns.map(p=>'<li><span class="pn">'+(p.status==="breakout"?"▲ ":"")+p.name+
      '</span> <span class="conf">('+p.conf.toFixed(2)+')</span><br>'+
      '<span class="det" style="max-height:none">'+p.detail+'</span></li>').join("")+
    '</ul>';
  $("modal").classList.add("on");
  draw(s.querySelector("canvas"), r.candles, r.level);
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
["pat","sort","brkonly","q"].forEach(id=>{ const el=$(id); el.oninput=render; el.onchange=render; });
$("modal").onclick=e=>{ if(e.target.id==="modal") closeModal(); };
document.addEventListener("keydown",e=>{ if(e.key==="Escape") closeModal(); });
let rt; window.addEventListener("resize",()=>{ clearTimeout(rt); rt=setTimeout(render,120); });

fetch("data.json?_="+Date.now())
  .then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); })
  .then(d=>{ DATA=d; $("loading").hidden=true; buildPatternList(); stats(); render(); })
  .catch(e=>{ $("loading").textContent="Could not load scan data (data.json). Run the scanner to generate it. ["+e.message+"]"; });
