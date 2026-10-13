'use strict';
const $=id=>document.getElementById(id);
const keys=['fullName','jobTitle','email','phone','city','links','summary','skills','experience','projects','education','certifications'];
let csrf='',currentDraftId=null;
const status=(msg,error=false)=>{$('builderStatus').textContent=msg;$('builderStatus').classList.toggle('error',error);};
const val=id=>$(id).value.trim();
function renderText(){
  const parts=[];if(val('fullName'))parts.push(val('fullName').toUpperCase());
  if(val('jobTitle'))parts.push(val('jobTitle'));
  const contact=['email','phone','city','links'].map(val).filter(Boolean).join(' | ');
  if(contact)parts.push(contact);
  for(const [key,title] of [['summary','PROFESSIONAL SUMMARY'],['skills','SKILLS'],['experience','EXPERIENCE'],['projects','PROJECTS'],['education','EDUCATION'],['certifications','CERTIFICATIONS & ACHIEVEMENTS']]){
    if(val(key))parts.push(title+'\n'+val(key));
  }
  return parts.join('\n\n');
}
function sync(){$('preview').textContent=renderText()||'Your resume will appear here as you type…';}
$('builderForm').addEventListener('input',sync);sync();
function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);}
$('downloadTxt').onclick=()=>download(new Blob([renderText()],{type:'text/plain;charset=utf-8'}),'skilllens-resume.txt');
$('printPdf').onclick=()=>window.print();
async function initAuth(){
  try{const r=await fetch('/api/auth/me',{credentials:'same-origin'});if(!r.ok)throw Error('Signed out');const d=await r.json();csrf=d.csrf;$('accountStatus').textContent=d.user.email;}
  catch{$('accountStatus').textContent='Sign in on homepage to save';}
}
async function api(url,options={}){
  const r=await fetch(url,{credentials:'same-origin',...options,headers:{...(options.headers||{}),...(options.method&&options.method!=='GET'?{'x-csrf-token':csrf}:{})}});
  const ct=r.headers.get('content-type')||'';const attachment=(r.headers.get('content-disposition')||'').toLowerCase().includes('attachment');
  const data=attachment?await r.blob():ct.includes('json')?await r.json():await r.blob();
  if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Sign in on the main page and try again.');
  return data;
}
$('downloadDocx').onclick=async()=>{
  try{
    const text=renderText();if(text.length<100)throw Error('Add more resume content before exporting.');
    const blob=await api('/api/export/docx',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({draft:text})});
    download(blob,'skilllens-professional-resume.docx');status('DOCX downloaded.');
  }catch(e){status(e.message,true);}
};
async function saveDraft(){
  const text=renderText();if(text.length<100)throw Error('Add at least 100 characters before saving.');
  if(!val('fullName'))throw Error('Enter your name first.');
  const body={title:val('fullName')+' — '+(val('jobTitle')||'Resume'),text,fields:Object.fromEntries(keys.map(k=>[k,val(k)]))};
  const data=await api(currentDraftId?'/api/drafts/'+currentDraftId:'/api/drafts',{method:currentDraftId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  currentDraftId=data.id;status('Encrypted resume saved for up to 90 days.');return data.id;
}
$('saveDraft').onclick=async()=>{try{await saveDraft();await listDrafts();}catch(e){status(e.message,true);}};
$('sendToAnalyzer').onclick=async()=>{try{const id=await saveDraft();location.href='/?draft='+encodeURIComponent(id);}catch(e){status(e.message,true);}};
async function listDrafts(){
  const data=await api('/api/drafts');const root=$('savedDrafts');root.replaceChildren();
  if(!data.length){root.textContent='No saved drafts yet.';return;}
  for(const item of data){
    const row=document.createElement('div');row.className='saved-row';
    const btn=document.createElement('button');btn.className='secondary';btn.textContent=item.title;btn.onclick=async()=>{
      try{const d=await api('/api/drafts/'+encodeURIComponent(item.id));const text=d.text;
        if(d.fields && Object.keys(d.fields).length){for(const k of keys)$(k).value=d.fields[k]||'';currentDraftId=item.id;sync();status('Saved draft loaded.');return;}
        // Import formatted plaintext into the editable sections, without silently inventing data.
        const map={'PROFESSIONAL SUMMARY':'summary','SKILLS':'skills','EXPERIENCE':'experience','PROJECTS':'projects','EDUCATION':'education','CERTIFICATIONS & ACHIEVEMENTS':'certifications'};
        for(const k of keys)$(k).value='';
        const chunks=text.split(/\n\n(?=[A-Z][A-Z &]+\n)/);
        const front=chunks.shift()||'';const lines=front.split('\n');$('fullName').value=lines[0]||'';$('jobTitle').value=lines[1]||'';
        const contact=lines[2]||'';const segments=contact.split(' | ');
        $('email').value=segments[0]||'';$('phone').value=segments[1]||'';$('city').value=segments[2]||'';$('links').value=segments[3]||'';
        for(const chunk of chunks){const idx=chunk.indexOf('\n');const key=map[chunk.slice(0,idx)];if(key)$(key).value=chunk.slice(idx+1);}
        currentDraftId=item.id;sync();status('Saved draft loaded. Review formatting before export.');
      }catch(e){status(e.message,true);}
    };
    const del=document.createElement('button');del.className='danger';del.textContent='Delete';del.onclick=async()=>{
      if(!confirm('Permanently delete this encrypted draft?'))return;
      try{await api('/api/drafts/'+encodeURIComponent(item.id),{method:'DELETE'});if(currentDraftId===item.id)currentDraftId=null;await listDrafts();}catch(e){status(e.message,true);}
    };
    row.append(btn,del);root.append(row);
  }
}
$('loadDrafts').onclick=async()=>{try{await listDrafts();}catch(e){status(e.message,true);}};
$('exportData').onclick=async()=>{
  try{const blob=await api('/api/account/export',{headers:{'x-csrf-token':csrf}});download(blob,'skilllens-my-data.json');status('Your private account data was exported. Store it securely.');}
  catch(e){status(e.message,true);}
};
initAuth();

// Cover letter drafting is extractive/deterministic: no external AI requests.
const coverMessage=(msg,error=false)=>{const n=$('coverMessage');n.textContent=msg;n.classList.toggle('error',error);};
$('generateCover').onclick=async()=>{
  try{
    const body={full_name:val('fullName'),company:val('coverCompany'),role:val('coverRole'),resume_text:renderText(),job_description:val('coverJob')};
    if(body.resume_text.length<100||body.job_description.length<80)throw Error('Complete your resume and paste a job description (80+ characters).');
    const result=await api('/api/cover-letter',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    $('coverDraft').value=result.draft;coverMessage('Template created. Check all claims and customize your letter before sending.');
  }catch(e){coverMessage(e.message,true)}
};
$('coverTxt').onclick=()=>download(new Blob([$('coverDraft').value],{type:'text/plain;charset=utf-8'}),'skilllens-cover-letter.txt');
$('coverDocx').onclick=async()=>{
  try{const blob=await api('/api/export/docx',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({draft:$('coverDraft').value})});download(blob,'skilllens-cover-letter.docx');}
  catch(e){coverMessage(e.message,true)}
};
