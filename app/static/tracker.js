'use strict';
const $=id=>document.getElementById(id);
let csrf='',items=[],editId=null;
const fields=['company','role','status','location','url','notes','next_step'];
function message(text,error=false){$('statusMessage').textContent=text;$('statusMessage').classList.toggle('error',error)}
function safeURL(s){try{const u=new URL(s);if(!['https:','http:'].includes(u.protocol)||u.username||u.password)return null;return u.href}catch{return null}}
async function api(path,options={}){
  const r=await fetch('/api/'+path,{credentials:'same-origin',...options,headers:{...(options.headers||{}),...(options.method&&options.method!=='GET'?{'x-csrf-token':csrf}:{})}});
  const body=await r.json().catch(()=>({}));if(!r.ok)throw Error(body.detail||'Action failed. Sign in and try again.');return body;
}
async function init(){
  try{const data=await api('auth/me');csrf=data.csrf;$('accountStatus').textContent=data.user.email;await refresh();message('Your applications are private and encrypted.');}
  catch(e){$('accountStatus').textContent='Sign in required';$('jobs').textContent='Please sign in from the main SkillLens page first.';message(e.message,true)}
}
function current(){const result={};for(const k of fields)result[k]=$(k).value.trim();return result}
function reset(){editId=null;$('jobForm').reset();$('formHeading').textContent='Add application';$('saveApplication').textContent='Save application';}
$('resetForm').onclick=reset;
$('jobForm').addEventListener('submit',async e=>{
  e.preventDefault();try{
    const body=current(),method=editId?'PUT':'POST',path=editId?'applications/'+encodeURIComponent(editId):'applications';
    await api(path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    reset();await refresh();message('Application securely saved.');
  }catch(err){message(err.message,true)}
});
function el(tag,cls,text){const element=document.createElement(tag);if(cls)element.className=cls;element.textContent=text||'';return element;}
function edit(item){for(const k of fields)$(k).value=item[k]||'';editId=item.id;$('formHeading').textContent='Edit application';$('saveApplication').textContent='Update application';$('company').focus();scrollTo({top:0,behavior:'smooth'});}
async function remove(item){if(!confirm('Delete this application permanently?'))return;try{await api('applications/'+encodeURIComponent(item.id),{method:'DELETE'});if(editId===item.id)reset();await refresh();message('Application deleted.')}catch(e){message(e.message,true)}}
function render(){
  const query=$('search').value.toLowerCase().trim(),filter=$('filter').value;
  const data=items.filter(x=>(!filter||x.status===filter)&&(!query||[x.company,x.role,x.location,x.notes].some(y=>(y||'').toLowerCase().includes(query))));
  const root=$('jobs');root.replaceChildren();
  if(!data.length){root.append(el('p','subtle',items.length?'No matching applications.':'No applications yet. Add your first on the left.'));return;}
  for(const item of data){
    const card=el('article','job');card.setAttribute('role','listitem');
    const details=el('div');details.append(el('strong','',item.role+' · '+item.company));
    const row=el('p');row.append(el('span','status-tag',item.status.toUpperCase()));row.append(document.createTextNode('  '+(item.location||'Location not set')));details.append(row);
    if(item.next_step)details.append(el('p','',`Next: ${item.next_step}`));
    if(item.notes)details.append(el('p','',item.notes.length>220?item.notes.slice(0,220)+'…':item.notes));
    if(item.url){const link=safeURL(item.url);if(link){const a=el('a','','View official application ↗');a.href=link;a.rel='noopener noreferrer';a.target='_blank';details.append(a)}}
    const actions=el('div','actions');const editBtn=el('button','secondary','Edit');editBtn.onclick=()=>edit(item);
    const delBtn=el('button','danger','Delete');delBtn.onclick=()=>remove(item);actions.append(editBtn,delBtn);
    card.append(details,actions);root.append(card);
  }
}
async function refresh(){items=await api('applications');$('totalCount').textContent=items.length;
  $('appliedCount').textContent=items.filter(x=>x.status==='applied').length;
  $('interviewCount').textContent=items.filter(x=>x.status==='interview').length;
  $('offerCount').textContent=items.filter(x=>x.status==='offer').length;render();}
$('refresh').onclick=async()=>{try{await refresh();message('Up to date.')}catch(e){message(e.message,true)}};
$('search').addEventListener('input',render);$('filter').addEventListener('change',render);
function download(blob,filename){const url=URL.createObjectURL(blob),a=document.createElement('a');a.download=filename;a.href=url;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
$('downloadCsv').onclick=()=>{
  const cols=['company','role','status','location','url','next_step','notes'];
  const escape=value=>'"'+String(value||'').replace(/^[=+@\-]/,"'$&").replaceAll('"','""')+'"';
  // Prefix dangerous spreadsheet formulas, even if the exported values are user-entered.
  const csv='\uFEFF'+[cols.join(','),...items.map(x=>cols.map(k=>escape(x[k])).join(','))].join('\r\n');
  download(new Blob([csv],{type:'text/csv;charset=utf-8'}),'skilllens-applications.csv');
};
$('exportData').onclick=async()=>{
  try{const r=await fetch('/api/account/export',{credentials:'same-origin',headers:{'x-csrf-token':csrf}});if(!r.ok){const e=await r.json();throw Error(e.detail||'Export failed')}
    download(await r.blob(),'skilllens-my-data.json');message('Account data exported. Keep it private.');
  }catch(e){message(e.message,true)}
};
init();
