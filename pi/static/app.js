"use strict";
const $ = id => document.getElementById(id);
let lastState = null;
let lastFetch = 0;
const number = (n, digits=0) => n == null ? "—" : Number(n).toLocaleString(undefined, {maximumFractionDigits:digits, minimumFractionDigits:digits});
const write = (id, value) => { $(id).textContent = value; };
const colors = ["#46e1ae", "#ff7a8e", "#7ca7ff"];
function canvas(id) {
  const element = $(id), rect = element.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
  element.width = Math.round(rect.width * ratio); element.height = Math.round(rect.height * ratio);
  const context = element.getContext("2d"); context.scale(ratio,ratio);
  return {ctx:context,w:rect.width,h:rect.height};
}
function drawLatency(points) {
  const {ctx,w,h} = canvas("latency-chart");
  const left=45, right=9, top=10, bottom=22, plotH=h-top-bottom, plotW=w-left-right;
  const max = Math.max(1000, ...points.map(p=>p.us))*1.15;
  ctx.font="9px ui-monospace, monospace";
  for(let i=0;i<4;i++) {
    const y=top+plotH*i/3;
    ctx.strokeStyle="#263448";ctx.lineWidth=.65;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();
    ctx.fillStyle="#7890ad";ctx.textAlign="right";ctx.fillText(number(max*(1-i/3)),left-7,y+3);
  }
  $("chart-empty").hidden=points.length>0;
  if (!points.length) return;
  const t0=points[0].t, t1=Math.max(t0+1,points[points.length-1].t);
  const x=p=>left+(p.t-t0)/(t1-t0)*plotW, y=p=>top+plotH*(1-p.us/max);
  ctx.strokeStyle="#83afff";ctx.lineWidth=2;ctx.beginPath();
  points.forEach((p,i)=>{ if(i===0 || p.t-points[i-1].t>2) ctx.moveTo(x(p),y(p)); else ctx.lineTo(x(p),y(p)); });ctx.stroke();
  if(points.length===1){ctx.fillStyle="#83afff";ctx.beginPath();ctx.arc(x(points[0]),y(points[0]),3,0,Math.PI*2);ctx.fill();}
  ctx.textAlign="left";ctx.fillStyle="#7890ad";ctx.fillText(new Date(t0*1000).toLocaleTimeString(),left,h-4);
  ctx.textAlign="right";ctx.fillText(new Date(points[points.length-1].t*1000).toLocaleTimeString(),w-right,h-4);
}
function drawDecisions(counts) {
  const {ctx,w,h}=canvas("decision-chart"), r=Math.min(w,h)*.36, cx=w/2, cy=h/2;
  if(w===0 || h===0)return;
  const values=[counts.BUY,counts.SELL,counts.STAY], total=values.reduce((a,b)=>a+b,0);
  ctx.lineWidth=15;ctx.strokeStyle="#223044";ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.stroke();
  let start=-Math.PI/2;
  values.forEach((value,i)=>{if(!value||!total)return;const angle=value/total*Math.PI*2;ctx.strokeStyle=colors[i];ctx.beginPath();ctx.arc(cx,cy,r,start,start+angle);ctx.stroke();start+=angle;});
  write("classified",number(total));
  ["buy","sell","stay"].forEach((k,i)=>write(k+"-percent",total?number(values[i]/total*100,1)+"%":"—"));
}
function renderRows(rows) {
  const filter=$("decision-filter").value;
  rows=rows.filter(row=>filter==="ALL"||(filter==="UNUSUAL"?["BUY","SELL"].includes(row.decision):row.decision===filter));
  if(!rows.length) {
    const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=8;td.className="table-empty";
    td.textContent=filter==="ALL"?"Waiting for the ESP32. No fallback feed is generated.":"No matching decisions among the most recent 100 accepted readings.";
    tr.append(td);$("signals").replaceChildren(tr);return;
  }
  const fragment=document.createDocumentFragment();
  rows.slice(0,14).forEach(row=>{
    const tr=document.createElement("tr");
    const cells=[String(row.index).padStart(6,"0")+" / "+row.sequence,row.symbol,
      (row.movement_pct>=0?"+":"")+number(row.movement_pct,2)+"%",
      row.z==null?"—":(row.z>=0?"+":"")+number(row.z,2),row.decision,number(row.latency_us)+" µs",number(row.analysis_us,1)+" µs",row.history_n];
    cells.forEach((text,i)=>{const td=document.createElement("td");
      if(i===4){const badge=document.createElement("span");badge.className="badge "+row.decision;badge.textContent=text;td.append(badge);}
      else td.textContent=text;
      if(i===2)td.className=row.movement_pct>=0?"positive":"negative";
      tr.append(td);
    });
    tr.title=`Received: ${row.received_at}\nMean: ${number(row.mean_pct,4)}% · sample std: ${number(row.std_pct,4)}%\nPi analysis: ${number(row.analysis_us,1)} µs · ESP32 boot: ${row.boot_id}`;
    fragment.append(tr);
  });
  $("signals").replaceChildren(fragment);
}
function renderFocus(s, online) {
  write("profile",`${s.profile.toUpperCase()} · ${s.protocol} · ${s.target_rate?number(s.target_rate)+"/s target":"UNPACED"}`);
  const row=s.latest[0];
  write("latest-label",online?"LATEST RECEIVED SIGNAL":"LAST RECEIVED SIGNAL · HISTORICAL");
  if(row){
    write("live-symbol",row.symbol);write("live-movement",(row.movement_pct>=0?"+":"")+number(row.movement_pct,2)+"%");
    $("live-movement").className=row.movement_pct>=0?"positive":"negative";
    write("live-decision",row.decision);$("live-decision").className="badge "+row.decision;
    write("live-z","z "+(row.z==null?"—":number(row.z,2)));
    write("live-mean","mean "+number(row.mean_pct,3)+"%");write("live-std","σ "+number(row.std_pct,3)+"%");
    write("live-history","history "+row.history_n+"/128");write("live-seq","seq "+row.sequence);
    write("decision-reason",row.decision==="WARMUP"?"Collecting prior hardware observations before statistical classification.":
      !row.stats_valid?"Historical variation is too small for a reliable z-score. Variance guard: STAY.":
      row.movement_pct===0?"Zero movement: the direction rule keeps this signal at STAY.":
      Math.abs(row.z)>=s.threshold?`Unusual ${row.movement_pct>0?"positive":"negative"} movement: |z| ${number(Math.abs(row.z),2)} ≥ ${number(s.threshold,2)}.`:
      `Movement is within the threshold: |z| ${number(Math.abs(row.z),2)} < ${number(s.threshold,2)}.`);
  }
  const unusual=s.last_unusual;
  write("unusual-label",online?"MOST RECENT UNUSUAL SIGNAL":"MOST RECENT UNUSUAL SIGNAL · HISTORICAL");
  if(unusual){write("unusual-main",`${unusual.decision}  ${unusual.symbol}  ${unusual.movement_pct>=0?"+":""}${number(unusual.movement_pct,2)}%`);
    $("unusual-main").className=unusual.decision==="BUY"?"positive":"negative";
    write("unusual-detail",`Received ${new Date(unusual.received_at).toLocaleTimeString()} · z ${number(unusual.z,2)} · ${number(unusual.latency_us)} µs · seq ${unusual.sequence}`);
  }
  write("budget-pass",s.under_target_pct==null?"—":number(s.under_target_pct,1)+"%");
  write("budget-detail",`${number(s.target_us)} µs budget · ${number(s.over_target)} successful replies above budget`);
  write("success",s.success_pct==null?"—":number(s.success_pct,2)+"%");
  write("requests",`${number(s.requests)} requests · current pending request may be included`);
  write("analysis-avg",s.stages.analysis_us==null?"—":number(s.stages.analysis_us,1)+" µs");
  write("jitter",s.latency.p99==null?"—":number(s.latency.p99-s.latency.p50)+" µs");
  write("log-mode",`Evidence: ${s.log_mode} · ${number(s.log_written)} rows written · ${number(s.log_dropped)} selected rows lost`);
  const stageFragment=document.createDocumentFragment(), sum=(s.stages.write_us||0)+(s.stages.wait_us||0)+(s.stages.host_us||0);
  [["Write call","write_us"],["Await frame","wait_us"],["Validate + decide","host_us"]].forEach(([name,key],i)=>{
    const el=document.createElement("div");el.className="stage-row";
    const label=document.createElement("span");label.textContent=name;
    const track=document.createElement("div");track.className="stage-track";
    const fill=document.createElement("i");fill.style.width=(sum?s.stages[key]/sum*100:0)+"%";fill.className="stage-"+i;track.append(fill);
    const value=document.createElement("b");value.textContent=number(s.stages[key],1)+" µs";el.append(label,track,value);stageFragment.append(el);
  });$("stage-bars").replaceChildren(stageFragment);
  const watch=document.createDocumentFragment();
  Object.entries(s.history).forEach(([symbol,n])=>{const el=document.createElement("div");el.className="watch-row";const row=s.latest_by_symbol[symbol];
    const name=document.createElement("strong");name.textContent=symbol;
    const change=document.createElement("span");change.textContent=row?(row.movement_pct>=0?"+":"")+number(row.movement_pct,2)+"%":"—";
    if(row)change.className=row.movement_pct>=0?"positive":"negative";
    const badge=document.createElement("span");badge.className="badge "+(row?row.decision:"");badge.textContent=row?row.decision:"WAITING";
    el.append(name,change,badge);watch.append(el);
  });$("watchlist").replaceChildren(watch);
}
function render(s) {
  lastState=s;
  const online=s.status==="CONNECTED";
  document.body.classList.toggle("stale",!online);
  $("status-dot").classList.toggle("offline",!online);
  write("status",s.status);write("reason",s.reason);write("port",s.port||"No port selected");
  write("transport",s.transport+" · "+number(s.baud)+" baud");
  write("last",s.last_received?new Date(s.last_received).toLocaleTimeString()+" · "+number(s.last_age_s,1)+"s ago":"Never");
  write("total",number(s.total));["buy","sell","stay"].forEach(k=>write(k,number(s.counts[k.toUpperCase()])));
  const classified=s.counts.BUY+s.counts.SELL+s.counts.STAY;
  write("warmup",number(s.counts.WARMUP)+" warmup · "+number(classified)+" classified");
  $("throughput").replaceChildren(document.createTextNode(number(s.throughput,1)));const unit=document.createElement("em");unit.textContent="sig/s";$("throughput").append(unit);
  write("errors",number(s.error_count));write("error-detail",`CRC ${s.errors.crc_errors} · format ${s.errors.format_errors} · timeout ${s.errors.timeouts}`);
  ["avg","min","max","p50","p95","p99"].forEach(k=>write("l-"+k,number(s.latency[k])));
  write("percentile-note",`Percentiles: last ${number(s.latency.window_n)} samples · avg/min/max: full run`);
  write("threshold",`|z| ≥ ${number(s.threshold,2)}`);
  write("power",s.health.power);$("power").className=s.health.power==="OK"?"positive":s.health.power==="UNKNOWN"?"":"negative";
  write("temperature",s.health.temperature_c==null?"—":number(s.health.temperature_c,1)+" °C");
  write("connections",s.connections);write("resets",s.resets);write("gaps",s.sequence_gaps);
  write("uptime",Math.floor(s.uptime_s/60)+"m "+Math.floor(s.uptime_s%60)+"s");
  write("last-error",s.log_warning||s.last_error);
  write("history-source",s.history_source);
  const histories=document.createDocumentFragment();
  Object.entries(s.history).forEach(([symbol,n])=>{const row=document.createElement("div");row.className="history-row";
    const label=document.createElement("span");label.textContent=symbol;const track=document.createElement("div");track.className="history-track";
    const bar=document.createElement("i");bar.style.width=Math.min(100,n/128*100)+"%";track.append(bar);
    const value=document.createElement("b");value.textContent=n+"/128";row.append(label,track,value);histories.append(row);
  });$("history-bars").replaceChildren(histories);
  const requiredHistory=s.history_source.startsWith("Imported:")?100:128;
  const warming=Object.values(s.history).some(n=>n<requiredHistory);
  $("alert").hidden=online&&!warming&&!s.log_warning;
  $("alert").classList.toggle("good",online);
  write("alert",!online?`${s.status}: ${s.reason}. Retained values are past readings; no fallback signals are generated.`:
    s.log_warning||"Collecting the historical windows from real ESP32 responses. Each symbol starts classifying after its initial 128 readings.");
  drawLatency(s.chart);drawDecisions(s.counts);renderRows(s.latest);renderFocus(s,online);
}
function unreachable() {
  write("status","DASHBOARD SERVER UNREACHABLE");write("reason","Cannot verify hardware status. Check the Pi application and network.");
  $("status-dot").classList.add("offline");document.body.classList.add("stale");
  $("alert").hidden=false;$("alert").classList.remove("good");
  write("alert","Connection to the Pi dashboard server was lost. All displayed measurements are historical; hardware status is unknown.");
  write("latest-label","LAST RECEIVED SIGNAL · SERVER UNREACHABLE");
  write("unusual-label","MOST RECENT UNUSUAL SIGNAL · HISTORICAL");
}
async function poll() {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),1800);
  try {const response=await fetch("/api/state",{cache:"no-store",signal:controller.signal});if(!response.ok)throw Error(response.status);
    const data=await response.json();lastFetch=Date.now();render(data);
  }catch(_){unreachable();}finally{clearTimeout(timer);setTimeout(poll,250);}
}
setInterval(()=>{write("clock",new Date().toLocaleTimeString());if(lastFetch&&Date.now()-lastFetch>3000)unreachable();},1000);
window.addEventListener("resize",()=>{if(lastState){drawLatency(lastState.chart);drawDecisions(lastState.counts);}});
$("decision-filter").addEventListener("change",()=>{if(lastState)renderRows(lastState.latest);});
$("present").addEventListener("click",()=>{const active=document.body.classList.toggle("presentation");write("present",active?"Engineering view":"Presentation view");window.dispatchEvent(new Event("resize"));});
drawLatency([]);drawDecisions({BUY:0,SELL:0,STAY:0});poll();
