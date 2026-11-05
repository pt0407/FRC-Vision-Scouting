"""Generate a static HTML track-labeling tool.

Reads an `out/` dir (scouting.json + paths/*.json) and emits
`label.html`: a canvas top-down view of the field with every track's
trajectory drawn, plus a panel to assign roster team numbers. Export
copies a {track_key: team} JSON the user saves as labels.json next to
scouting.json; `frc-scout run --labels labels.json` merges it.
"""
import json
from pathlib import Path

FIELD_W = 16.541
FIELD_H = 8.069

HTML = r"""<!doctype html><meta charset=utf-8><title>frc-scout label</title>
<style>
body{font:14px/1.4 system-ui;background:#111;color:#eee;display:flex;gap:12px}
#cv{background:#1c2733;border:1px solid #333}
#side{width:340px;max-height:95vh;overflow:auto}
.track{padding:4px 6px;margin:2px 0;border-radius:4px;cursor:pointer}
.track.sel{outline:2px solid #fff}
.track .k{font-weight:600}
button{margin:2px;padding:3px 8px}
#exp{position:fixed;right:12px;bottom:12px;padding:10px 16px;font-size:16px}
</style>
<canvas id=cv width=900 height=520></canvas>
<div id=side></div>
<button id=exp>Export labels.json</button>
<script>
const DATA = __DATA__;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const W=900,H=520,M=30;
const sx = x => M + (x+8.2705)/16.541*(W-2*M);
const sz = z => H-M - (z+4.0345)/8.069*(H-2*M);
const TEAM_COLORS = {red:'#e33',blue:'#39f'};
let sel = null, labels = {};
const side = document.getElementById('side');
function draw(){
  ctx.fillStyle='#14202b';ctx.fillRect(0,0,W,H);
  ctx.strokeStyle='#567';ctx.lineWidth=2;
  ctx.strokeRect(sx(-8.2705),sz(-4.0345),sx(8.2705)-sx(-8.2705),sz(4.0345)-sz(-4.0345));
  // zones
  ctx.fillStyle='#ffffff10';
  for(const z of [['hub_west',-6.8,0,1.4],['hub_east',6.8,0,1.4],
                  ['tower_s',0,-3.2,1.1],['tower_n',0,3.2,1.1],['depot',0,0,2.6]]){
    ctx.beginPath();ctx.arc(sx(z[1]),sz(z[2]),z[3]/16.541*(W-2*M),0,7);ctx.fill();
  }
  for(const t of DATA.tracks){
    const col = TEAM_COLORS[t.alliance]||'#fff';
    ctx.strokeStyle = sel===t.key? '#ff0' : col+'88';
    ctx.lineWidth = sel===t.key?3:1.5;
    ctx.beginPath();
    t.samples.forEach((p,i)=>{const X=sx(p[1]),Y=sz(p[2]);i?ctx.lineTo(X,Y):ctx.moveTo(X,Y);});
    ctx.stroke();
    const last=t.samples[t.samples.length-1];
    ctx.fillStyle=col;ctx.beginPath();ctx.arc(sx(last[1]),sz(last[2]),4,0,7);ctx.fill();
  }
}
function panel(){
  side.innerHTML='';
  const sorted=[...DATA.tracks].sort((a,b)=>b.drive-b.drive);
  for(const t of sorted){
    const d=document.createElement('div');
    d.className='track'+(sel===t.key?' sel':'');
    d.innerHTML=`<span class=k style="color:${TEAM_COLORS[t.alliance]||'#fff'}">${t.key}</span>
      ${labels[t.key]?` → <b>${labels[t.key]}</b>`:''}
      <br><small>drive ${t.drive.toFixed(0)}s · avg ${t.avg.toFixed(2)} m/s · max ${t.max.toFixed(1)}</small>`;
    d.onclick=()=>{sel=t.key;panel();draw();};
    side.appendChild(d);
    if(sel===t.key){
      const row=document.createElement('div');
      row.style.padding='4px 6px';
      row.innerHTML='<b>assign team:</b> '+DATA.teams.map(tm=>
        `<button data-tm="${tm}">${tm}</button>`).join('')+
        ` <button data-tm="">clear</button>`;
      row.querySelectorAll('button').forEach(b=>b.onclick=()=>{
        if(b.dataset.tm) labels[sel]=b.dataset.tm; else delete labels[sel];
        panel();draw();});
      side.appendChild(row);
    }
  }
}
document.getElementById('exp').onclick=()=>{
  const out={match:DATA.match,labels};
  const blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='labels.json';a.click();};
draw();panel();
</script>"""


def generate(out_dir: Path):
    scouting = json.loads((out_dir / "scouting.json").read_text())
    teams = scouting.get("event", {})
    roster = teams.get("red", []) + teams.get("blue", [])
    if not roster:
        roster = sorted({t["team"] for t in scouting["teams"].values()
                         if not t["team"].startswith("track")})
    tracks = []
    for p in sorted((out_dir / "paths").glob("*.json")):
        d = json.loads(p.read_text())
        key = p.stem
        st = scouting["teams"].get(key, {})
        samples = [[s[0], s[1], s[2]] for s in d["samples"]]
        if len(samples) > 2000:
            step = len(samples) // 2000
            samples = samples[::step]
        tracks.append({
            "key": key, "alliance": d["alliance"],
            "drive": st.get("drive_time_s", 0),
            "avg": st.get("avg_speed_mps", 0),
            "max": st.get("max_speed_mps", 0),
            "samples": samples,
        })
    data = {"match": scouting.get("event", {}).get("match"),
            "teams": roster, "tracks": tracks}
    html = HTML.replace("__DATA__", json.dumps(data))
    dest = out_dir / "label.html"
    dest.write_text(html)
    print(f"wrote {dest} — open in browser, assign teams, export "
          f"labels.json")
    return dest
