"""CAD/mechanism review page: one card per team at an event.

Generates a local HTML page listing every team with links to their
TBA page, a CAD search, and mechanism checkboxes. Export produces
JSON that `frc-scout registry import` merges into teams.json.
"""
import html
import json
from pathlib import Path

from .registry import MECH_TYPES


def review_page(teams: list[str], event: str, out: Path,
                existing: dict | None = None):
    existing = existing or {}
    cards = []
    for tm in teams:
        tm_s = html.escape(tm)
        checked = {m["type"] for m in
                   existing.get(tm, {}).get("mechanisms", [])}
        cad = existing.get(tm, {}).get("cad_url", "")
        name = existing.get(tm, {}).get("robot_name", "")
        notes = existing.get(tm, {}).get("notes", "")
        boxes = "".join(
            f'<label><input type="checkbox" class="mech" '
            f'value="{mt}" {"checked" if mt in checked else ""}> {mt}'
            f'</label>'
            for mt in MECH_TYPES)
        cards.append(f'''
<div class="card" data-team="{tm_s}">
  <div class="hd">
    <b>{tm_s}</b>
    <input class="rname" placeholder="robot name"
           value="{html.escape(name)}">
  </div>
  <div class="links">
    <a href="https://www.thebluealliance.com/team/{tm_s}"
       target="_blank">TBA</a>
    <a href="https://www.google.com/search?q=FRC+{tm_s}+2026+robot+CAD+onshape"
       target="_blank">CAD search</a>
    <a href="https://www.google.com/search?q=FRC+{tm_s}+2026+robot+reveal"
       target="_blank">reveal video</a>
  </div>
  <input class="cad" placeholder="CAD / Onshape document URL"
         value="{html.escape(cad)}">
  <div class="mechs">{boxes}</div>
  <input class="notes" placeholder="notes (shooter location, intake style...)"
         value="{html.escape(notes)}">
</div>''')
    page = f'''<!doctype html><html><head><meta charset="utf-8">
<title>CAD review — {html.escape(event)}</title>
<style>
body {{ font: 13px system-ui; margin: 12px; background: #111; color: #eee }}
h1 {{ font-size: 18px }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, 300px);
        gap: 10px }}
.card {{ border: 1px solid #444; border-radius: 6px; padding: 8px }}
.card.done {{ border-color: #4a4 }}
.hd {{ display: flex; gap: 8px; margin-bottom: 4px }}
.links a {{ color: #7af; margin-right: 10px }}
input {{ width: 100%; box-sizing: border-box; margin: 3px 0;
        background: #1c1c1c; color: #eee; border: 1px solid #333 }}
.mechs {{ display: grid; grid-template-columns: 1fr 1fr; margin: 4px 0 }}
.mechs label {{ white-space: nowrap }}
button {{ font-size: 14px; padding: 8px 16px }}
#export {{ position: fixed; top: 10px; right: 14px }}
</style></head><body>
<h1>{html.escape(event)} — mechanism review</h1>
<p>Tag each team's mechanisms, paste their CAD link, then Export.
Import the downloaded file with <code>frc-scout registry import
&lt;file&gt;</code>.</p>
<button id="export">Export JSON</button>
<div class="grid">{''.join(cards)}</div>
<script>
document.getElementById('export').onclick = () => {{
  const out = {{}};
  for (const card of document.querySelectorAll('.card')) {{
    const team = card.dataset.team;
    const mechs = [...card.querySelectorAll('.mech:checked')]
      .map(c => ({{type: c.value, params: {{}}}}));
    const e = {{}};
    if (mechs.length) e.mechanisms = mechs;
    const cad = card.querySelector('.cad').value.trim();
    if (cad) e.cad_url = cad;
    const rn = card.querySelector('.rname').value.trim();
    if (rn) e.robot_name = rn;
    const nt = card.querySelector('.notes').value.trim();
    if (nt) e.notes = nt;
    if (Object.keys(e).length) out[team] = e;
  }}
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(
    [JSON.stringify(out, null, 2)], {{type: 'application/json'}}));
  a.download = 'mechanisms_export.json';
  a.click();
}};
// mark cards with any data as done
for (const c of document.querySelectorAll('.card')) {{
  const upd = () => c.classList.toggle('done',
    c.querySelector('.mech:checked') ||
    c.querySelector('.cad').value || c.querySelector('.notes').value);
  c.addEventListener('input', upd); upd();
}}
</script></body></html>'''
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return out
