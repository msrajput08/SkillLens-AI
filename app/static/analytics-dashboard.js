/* SkillLens admin-only aggregate analytics presentation. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const count = n => Number(n || 0).toLocaleString('en-IN');
function renderBars(target, values) {
  target.replaceChildren();
  const sorted = Object.entries(values || {}).sort((a,b)=>b[1]-a[1]);
  if (!sorted.length) { target.textContent='No events counted yet.'; return; }
  const largest = Math.max(1, ...sorted.map(x=>x[1]));
  for (const [key, value] of sorted) {
    const row=document.createElement('div'); row.className='bar-row';
    const label=document.createElement('span'); label.className='label'; label.textContent=key;
    const track=document.createElement('div'); track.className='bar-track';
    const fill=document.createElement('div'); fill.className='bar-fill';
    fill.style.width=Math.max(2,100*value/largest)+'%'; track.append(fill);
    const n=document.createElement('strong'); n.className='bar-number'; n.textContent=count(value);
    row.append(label,track,n); target.append(row);
  }
}
function renderTrend(values) {
  const parent=$('trend'); parent.replaceChildren();
  const sorted=Object.entries(values || {}).sort(([a],[b])=>a.localeCompare(b));
  if(!sorted.length){parent.textContent='No daily data yet.';return;}
  const maximum=Math.max(1,...sorted.map(([,v])=>Number(v.page_view||0)));
  for(const [day,events] of sorted){
    const element=document.createElement('div');element.className='day';element.tabIndex=0;
    const value=Number(events.page_view||0);
    element.title=day+': '+count(value)+' page views';
    element.setAttribute('aria-label',element.title);
    const bar=document.createElement('div');bar.className='bar';
    bar.style.height=Math.max(2, Math.round(164*value/maximum))+'px';
    element.append(bar);parent.append(element);
  }
}
async function load() {
  $('status').textContent='Loading aggregate metrics…';
  try {
    const response=await fetch('/api/analytics/summary?days='+encodeURIComponent($('period').value),
      {credentials:'same-origin', cache:'no-store'});
    if(!response.ok)throw Error(response.status===401?'Sign in to view your private metrics.':'Metrics access unavailable. Check the administrator email configuration.');
    const data=await response.json();
    for(const [id,event] of Object.entries({views:'page_view',previews:'preview_completed',
      analyses:'analysis_completed',upgrades:'upgrade_cta_clicked',checkouts:'checkout_started',
      signups:'signup_submitted'}))$(id).textContent=count(data.event_counts?.[event]);
    renderBars($('channels'),data.acquisition_channels);
    renderBars($('pages'),data.page_views);
    renderTrend(data.daily_events);
    $('status').textContent='Since '+data.since_utc+' (UTC). Counts are aggregated, not unique people.';
  }catch(err){$('status').textContent=err.message||'Metrics unavailable.';}
}
$('period').addEventListener('change',load);
load();
})();
