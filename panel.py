"""HTML panel for spend per thread. threadeyes.py calls it with the numbers already computed.

One single page. The data and the chart library are both written INSIDE the file, so the page
makes no network request at all: nothing leaves your computer, and it works offline.
The chart library is read from vendor/chart.umd.min.js next to this file. If it is missing the
tables still work and the page says so.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CHART_JS = os.path.join(HERE, 'vendor', 'chart.umd.min.js')

TEMPLATE = r"""<!doctype html>
<html lang="__LANG__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ThreadEyes</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--txt:#1d2330;--sub:#5d6677;--line:#e3e6ec;--acc:#2f6fdb;--warn:#c2410c;--ok:#15803d}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2128;--txt:#e7eaf0;--sub:#9aa3b2;--line:#2c323c;--acc:#6ea0ff;--warn:#fb923c;--ok:#4ade80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1280px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0 0 10px}
.sub{color:var(--sub);font-size:13px}.grid{display:grid;gap:14px}.kpis{grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}.kpi b{display:block;font-size:26px;margin-top:2px}
.dos{grid-template-columns:1fr 1fr}@media(max-width:900px){.dos{grid-template-columns:1fr}}
.chart{position:relative;height:280px}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{background:var(--card);cursor:pointer;user-select:none}th:hover{color:var(--acc)}th.asc:after{content:" \25B2"}th.desc:after{content:" \25BC"}
td.n{text-align:right;font-variant-numeric:tabular-nums}tr:hover td{background:color-mix(in srgb,var(--acc) 7%,transparent)}
.tag{display:inline-block;padding:1px 7px;border-radius:9px;font-size:12px;border:1px solid var(--line)}.cambiar{color:var(--warn);border-color:var(--warn)}
.ok{color:var(--ok)}.bar{display:inline-block;height:8px;background:var(--acc);border-radius:4px;vertical-align:middle}
.ctrl{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}select,input{padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--txt);font:inherit}
.spark{width:120px;height:26px}
.btn{padding:7px 14px;border-radius:7px;border:1px solid var(--acc);background:var(--acc);color:#fff;font:inherit;cursor:pointer}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;padding:16px;z-index:9}.modal[hidden]{display:none}
.modal-c{width:min(820px,100%)}
nav{position:sticky;top:0;z-index:5;background:var(--bg);display:flex;gap:6px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--line);margin-bottom:14px}
nav button{padding:8px 16px;border-radius:20px;border:1px solid var(--line);background:var(--card);color:var(--txt);font:inherit;cursor:pointer}
nav button.on{background:var(--acc);border-color:var(--acc);color:#fff}
section[hidden]{display:none}.scroll{overflow-x:auto}
table{--colw:220px}td:first-child,th:first-child{white-space:normal;width:var(--colw);min-width:var(--colw);max-width:var(--colw);position:relative}
.grip{position:absolute;top:0;right:-4px;width:9px;height:100%;cursor:col-resize;z-index:2}
.grip:after{content:"";position:absolute;left:4px;top:20%;height:60%;border-left:2px solid var(--sub)}.grip:hover:after{border-color:var(--acc)}
tr.clic{cursor:pointer}.d-div{color:var(--warn);font-weight:600}.d-cam{color:var(--acc);font-weight:600}
.warnbox{border:1px solid var(--warn);color:var(--warn);border-radius:8px;padding:8px 12px;margin:10px 0}
</style></head><body><main>
<h1 id="h1"></h1>
<div class="sub" id="periodo"></div>
<div class="grid kpis" id="kpis"></div>
<div class="warnbox" id="nochart" hidden></div>
<nav id="menu"></nav>

<section data-tab="tiempo">
<div class="grid dos">
 <div class="card"><h2 id="t1"></h2><div class="sub" id="s1"></div><div class="chart"><canvas id="cSem"></canvas></div></div>
 <div class="card"><h2 id="t2"></h2><div class="sub" id="s2"></div><div class="chart"><canvas id="cDia"></canvas></div></div>
</div>
<div class="card" style="margin-top:14px"><h2 id="t3"></h2><div class="sub" id="s3"></div><div class="chart" style="height:320px"><canvas id="cHilos"></canvas></div></div>
</section>

<section data-tab="ahorro" hidden>
<div class="card"><h2 id="t4"></h2>
 <div class="ctrl" style="align-items:center;justify-content:space-between"><div class="sub" id="s4"></div>
 <button id="aplicar" class="btn"></button></div>
 <div id="copiado" class="sub" style="display:none;margin-bottom:8px"></div>
 <div class="scroll"><table id="tRecos"><thead></thead><tbody></tbody></table></div>
 <div class="sub" style="margin-top:6px" id="diagHelp"></div>
</div>
<div id="modal" class="modal" hidden><div class="card modal-c"><div style="display:flex;justify-content:space-between;align-items:center"><h2 id="mTit" style="margin:0"></h2><button class="btn" id="cerrar"></button></div>
 <div class="sub" id="mSub" style="margin:6px 0 10px"></div><div class="chart" style="height:340px"><canvas id="cRel"></canvas></div>
 <div class="sub" style="margin-top:8px" id="mHelp"></div></div></div>
</section>

<section data-tab="hilos" hidden>
<div class="card"><h2 id="t5"></h2>
 <div class="ctrl"><select id="fSec"></select><input id="fTxt"><label class="sub"><input type="checkbox" id="fCamb"> <span id="lCamb"></span></label></div>
 <div class="scroll"><table id="tHilos"><thead></thead><tbody></tbody></table></div>
 <div class="sub" style="margin-top:6px" id="hHelp"></div>
</div>
</section>

<section data-tab="secciones" hidden>
<div class="card"><h2 id="t6"></h2><div class="scroll"><table id="tSec"><thead></thead><tbody></tbody></table></div></div>
</section>

<p class="sub" style="margin-top:18px" id="pie"></p>
</main>
<script>__CHARTJS__</script>
<script>
const D = __DATA__;
const T = __TEXTS__;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (s, o) => s.replace(/\{(\w+)\}/g, (m, k) => (k in o ? o[k] : m));
const HAS_CHART = typeof Chart !== 'undefined';
if (!HAS_CHART) { $('nochart').hidden = false; $('nochart').textContent = T.p_no_charts; }
const chart = (el, cfg) => HAS_CHART ? new Chart(el, cfg) : null;

document.title = 'ThreadEyes · ' + T.p_title;
$('h1').textContent = T.p_title;
$('periodo').textContent = fmt(T.p_period, {start: D.since, end: D.today, threads: D.rows.length, weeks: D.weeks.length});
$('menu').innerHTML = [['tiempo', T.p_tab_time], ['ahorro', T.p_tab_saving], ['hilos', T.p_tab_threads], ['secciones', T.p_tab_sections]]
  .map((x, i) => `<button data-t="${x[0]}"${i ? '' : ' class="on"'}>${esc(x[1])}</button>`).join('');
[['t1','p_weeks_title'],['s1','p_weeks_sub'],['t2','p_days_title'],['s2','p_days_sub'],['t3','p_top_title'],['s3','p_top_sub'],
 ['t4','p_saving_title'],['s4','p_saving_sub'],['aplicar','p_copy_btn'],['cerrar','p_modal_close'],['mHelp','p_modal_help'],
 ['t5','p_threads_title'],['lCamb','p_only_change'],['hHelp','p_threads_help'],['t6','p_sections_title'],['pie','p_footer']]
  .forEach(([id, k]) => $(id).textContent = T[k]);
$('diagHelp').innerHTML = T.p_diag_help;
$('fTxt').placeholder = T.p_search;
$('fSec').innerHTML = `<option value="">${esc(T.p_all_sections)}</option>` + D.sections.map(s => `<option>${esc(s.name)}</option>`).join('');

document.querySelectorAll('#menu button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#menu button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('section[data-tab]').forEach(sc => sc.hidden = sc.dataset.tab !== b.dataset.t);
  window.scrollTo({top: 0});
});

const C = ['#2f6fdb','#e8590c','#2b8a3e','#ae3ec9','#1098ad','#f08c00','#c92a2a','#5c7cfa','#868e96','#94d82d','#e64980','#0ca678'];
const pct = v => (100 * v / D.total).toFixed(1) + '%';
const topRow = D.rows[0];
$('kpis').innerHTML = [
  [T.p_kpi_saving, D.saving.toFixed(0) + '%', T.p_kpi_saving_sub],
  [T.p_kpi_now, D.wkNow.toFixed(0) + '%', fmt(T.p_kpi_now_sub, {days: D.daysNow})],
  [T.p_kpi_last, D.wkLast.toFixed(0) + '%', T.p_kpi_last_sub],
  [T.p_kpi_top, topRow ? esc(topRow.name) : '-', topRow ? pct(topRow.total) + ' ' + T.p_kpi_top_sub : '']
].map(x => `<div class="card kpi"><span class="sub">${x[0]}</span><b>${x[1]}</b><span class="sub">${x[2]}</span></div>`).join('');

const opts = (stack, unit) => ({responsive: true, maintainAspectRatio: false, interaction: {mode: 'index', intersect: false},
  scales: {x: {stacked: stack}, y: {stacked: stack, ticks: {callback: v => v + unit}}},
  plugins: {tooltip: {callbacks: {label: c => c.dataset.label + ': ' + c.parsed.y.toFixed(0) + unit}}}});
chart($('cSem'), {type: 'bar', data: {labels: D.weeks, datasets: D.sections.map((s, i) => ({label: s.name, data: s.wkNorm, backgroundColor: C[i % C.length]}))}, options: opts(true, '%')});
chart($('cDia'), {type: 'bar', data: {labels: D.days.map(d => d[0]), datasets: [{label: T.p_day_label, data: D.days.map(d => d[1]), backgroundColor: D.days.map(d => d[1] > 150 ? '#e8590c' : '#2f6fdb')}]}, options: opts(false, '%')});
chart($('cHilos'), {type: 'line', data: {labels: D.weeks, datasets: D.rows.slice(0, 10).map((f, i) => ({label: f.name, data: f.wkNorm, borderColor: C[i % C.length], backgroundColor: C[i % C.length], tension: .3, pointRadius: 3}))}, options: opts(false, '%')});

function table(id, cols, rows) {
  const t = $(id); let order = {k: null, dir: -1};
  t.querySelector('thead').innerHTML = '<tr>' + cols.map(c => `<th data-k="${c.k}">${esc(c.t)}</th>`).join('') + '</tr>';
  const th0 = t.querySelector('th'); const g = document.createElement('span'); g.className = 'grip'; g.title = T.p_grip; th0.appendChild(g);
  g.onclick = e => e.stopPropagation();
  g.onmousedown = e => { e.preventDefault(); e.stopPropagation(); const x0 = e.clientX, w0 = th0.getBoundingClientRect().width;
    const mv = ev => { t.style.setProperty('--colw', Math.max(90, Math.min(600, w0 + ev.clientX - x0)) + 'px'); };
    const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); };
    document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up); };
  const paint = () => { let rs = rows(); if (order.k) { rs = [...rs].sort((a, b) => { const x = a[order.k], y = b[order.k]; return (typeof x === 'number' ? x - y : String(x).localeCompare(String(y))) * order.dir; }); }
    t.querySelector('tbody').innerHTML = rs.map(f => `<tr data-id="${f.id === undefined ? '' : f.id}">` + cols.map(c => `<td class="${c.n ? 'n' : ''}">${c.f ? c.f(f) : esc(f[c.k])}</td>`).join('') + '</tr>').join(''); };
  t.querySelectorAll('th').forEach(th => th.onclick = () => { const kk = th.dataset.k; order.dir = order.k === kk ? -order.dir : -1; order.k = kk;
    t.querySelectorAll('th').forEach(h => h.className = ''); th.className = order.dir > 0 ? 'asc' : 'desc'; paint(); });
  return paint;
}

const spark = a => { const m = Math.max(...a, 1); const w = 120, h = 26, st = w / Math.max(a.length - 1, 1);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="currentColor" stroke-width="2" points="${a.map((v, i) => (i * st).toFixed(1) + ',' + (h - 2 - (h - 4) * v / m).toFixed(1)).join(' ')}"/></svg>`; };
const mm = v => v >= 0.5 ? v.toFixed(0) + '%' : '·';
const maxTotal = D.rows.length ? D.rows[0].total : 1;
const cols = [
  {k: 'name', t: T.p_col_thread}, {k: 'section', t: T.p_col_section},
  {k: 'total', t: T.p_col_share, n: 1, f: f => `<span class="bar" style="width:${Math.max(2, 60 * f.total / maxTotal)}px"></span> ${pct(f.total)}`},
  {k: 'ult', t: T.p_col_timeline, f: f => spark(f.wkNorm)},
  {k: 'relays', t: T.p_col_relays, n: 1}, {k: 'last', t: T.p_col_last}, {k: 'type', t: T.p_col_type},
  {k: 'build', t: T.p_col_build, n: 1, f: f => f.build + '%'}, {k: 'test', t: T.p_col_test, n: 1, f: f => f.test + '%'},
  {k: 'read', t: T.p_col_read, n: 1, f: f => f.read + '%'}, {k: 'coord', t: T.p_col_coord, n: 1, f: f => f.coord + '%'},
  {k: 'fable', t: 'Fable', n: 1, f: f => mm(f.fable)}, {k: 'opus', t: 'Opus', n: 1, f: f => mm(f.opus)},
  {k: 'sonnet', t: 'Sonnet', n: 1, f: f => mm(f.sonnet)}, {k: 'haiku', t: 'Haiku', n: 1, f: f => mm(f.haiku)},
  {k: 'reco', t: T.p_col_reco, f: f => f.saving > 0 ? `<span class="tag cambiar">${esc(f.reco)} · ${esc(T.p_change)}</span>` : `<span class="tag ok">${esc(f.reco)}</span>`},
  {k: 'saving', t: T.p_col_saving, n: 1, f: f => f.saving > 0 ? f.saving.toFixed(1) + '%' : '—'}];
const filter = () => D.rows.filter(f => (!$('fSec').value || f.section === $('fSec').value) && (!$('fTxt').value || f.name.toLowerCase().includes($('fTxt').value.toLowerCase())) && (!$('fCamb').checked || f.saving > 0));
const pH = table('tHilos', cols, filter); pH(); ['fSec', 'fTxt', 'fCamb'].forEach(i => $(i).oninput = pH);

const MC = {fable: '#ae3ec9', opus: '#2f6fdb', sonnet: '#2b8a3e', haiku: '#f08c00'};
const FAMS = ['fable', 'opus', 'sonnet', 'haiku'];
const mix = f => FAMS.filter(m => f[m] >= 5).map(m => m + ' ' + f[m].toFixed(0) + '%').join(' · ');
D.rows.forEach(f => { f.mixText = mix(f); });
const dcls = k => k === 'split' ? 'd-div' : (k === 'switch' ? 'd-cam' : 'ok');
const recos = D.rows.filter(f => f.saving >= 0.1 || f.diagKey !== 'ok');
const pR = table('tRecos', [{k: 'name', t: T.p_col_thread}, {k: 'section', t: T.p_col_section}, {k: 'now', t: T.p_col_now},
  {k: 'mixText', t: T.p_col_mix, f: mix}, {k: 'reco', t: T.p_col_reco, f: f => `<b>${esc(f.reco)}</b>`},
  {k: 'saving', t: T.p_col_saving, n: 1, f: f => f.saving > 0 ? f.saving.toFixed(1) + '%' : '—'},
  {k: 'diag', t: T.p_col_diag, f: f => `<span class="${dcls(f.diagKey)}">${esc(f.diag)}</span>`}, {k: 'type', t: T.p_col_type}], () => recos.slice().sort((a, b) => b.saving - a.saving));
pR();

let cRel = null;
function open_(f) {
  $('mTit').textContent = f.name;
  $('mSub').textContent = fmt(T.p_modal_sub, {n: f.rel.length, now: f.now, reco: f.reco, diag: f.diag});
  $('modal').hidden = false;
  if (cRel) { cRel.destroy(); cRel = null; }
  if (!HAS_CHART) return;
  const ds = FAMS.map(m => ({label: m, backgroundColor: MC[m] + 'cc', borderColor: MC[m],
    data: f.rel.filter(r => r.fam === m).map(r => ({x: r.bt, y: r.read, r: Math.max(4, Math.min(26, 4 + 60 * Math.sqrt(r.cost / (f.total / D.total * 100 || 1)))), date: r.date, cost: r.cost}))})).filter(d => d.data.length);
  cRel = new Chart($('cRel'), {type: 'bubble', data: {datasets: ds}, options: {animation: false, responsive: true, maintainAspectRatio: false,
    scales: {x: {min: 0, max: 100, title: {display: true, text: T.p_axis_x}}, y: {min: 0, max: 100, title: {display: true, text: T.p_axis_y}}},
    plugins: {tooltip: {callbacks: {label: c => fmt(T.p_tip, {model: c.dataset.label, date: c.raw.date, pct: c.raw.cost.toFixed(2)})}}}}});
}
const close_ = () => { $('modal').hidden = true; };
$('cerrar').onclick = close_;
$('modal').onclick = e => { if (e.target.id === 'modal') close_(); };
const clickable = id => { $(id).querySelector('tbody').onclick = e => { const tr = e.target.closest('tr'); if (!tr) return; const f = D.rows.find(x => String(x.id) === tr.dataset.id); if (f && f.rel.length) open_(f); }; };
clickable('tRecos'); clickable('tHilos');
new MutationObserver(() => { document.querySelectorAll('#tRecos tbody tr,#tHilos tbody tr').forEach(tr => tr.classList.add('clic')); }).observe(document.body, {subtree: true, childList: true});
document.querySelectorAll('#tRecos tbody tr,#tHilos tbody tr').forEach(tr => tr.classList.add('clic'));

$('aplicar').onclick = async () => {
  const list = recos.filter(f => f.saving > 0).sort((a, b) => b.saving - a.saving).map(f => `- ${f.name} (${f.section}): ${f.reco}${f.diagKey === 'split' ? T.p_copy_split : ''}`).join('\n');
  const txt = fmt(T.p_copy_text, {date: D.today, list: list});
  try { await navigator.clipboard.writeText(txt); $('copiado').textContent = T.p_copied; }
  catch (e) { $('copiado').innerHTML = esc(T.p_copy_fail) + '<br><textarea style="width:100%;height:120px">' + esc(txt) + '</textarea>'; }
  $('copiado').style.display = 'block';
};
table('tSec', [{k: 'name', t: T.p_col_section}, {k: 'total', t: T.p_col_share, n: 1, f: s => pct(s.total)}, {k: 'threads', t: T.p_col_threads, n: 1},
  {k: 'ult', t: T.p_col_timeline, f: s => spark(s.wkNorm)}, {k: 'saving', t: T.p_col_saving_possible, n: 1, f: s => s.saving.toFixed(1) + '%'}], () => D.sections)();
</script></body></html>"""


def _chart_js():
    try:
        with open(CHART_JS, encoding='utf-8') as f:
            return f.read().replace('</script', '<\\/script')
    except OSError:
        return ''


def write(path, data, texts, lang):
    """Write the panel to `path`. `data` and `texts` are plain dicts."""
    def js(obj):
        return json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')
    parts = {'LANG': lang, 'CHARTJS': _chart_js(), 'DATA': js(data), 'TEXTS': js(texts)}
    # One single pass, so a thread called "__DATA__" cannot be substituted twice.
    page = re.sub(r'__(LANG|CHARTJS|DATA|TEXTS)__', lambda m: parts[m.group(1)], TEMPLATE)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(page)
