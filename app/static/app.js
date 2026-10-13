'use strict';
const $ = (id) => document.getElementById(id);
const form = $('analyzerForm');
let method = 'paste';
let currentReport = null;
let lastFile = null;
const demoResume = `Alex Example\nalex@example.com | linkedin.com/in/alexexample | github.com/alexexample\n\nPROFESSIONAL SUMMARY\nComputer Engineering graduate interested in scalable Java backend engineering.\n\nTECHNICAL SKILLS\nJava, Spring Boot, Spring Security, PostgreSQL, SQL, REST APIs, JWT, Git, Docker, Python, React, HTML, CSS, Unit Testing.\n\nPROJECTS\nTaskFlow — Built a Java Spring Boot backend API for a task manager with JWT access control, PostgreSQL data persistence and JUnit unit tests. Used Git to track changes and Docker to package the service.\n\nEDUCATION\nBachelor of Engineering in Computer Engineering, Example University, 2026.`;
const demoJD = `Junior Java Backend Software Engineer\n\nRequirements:\n- Build backend services with Java, Spring Boot and REST APIs.\n- Work with relational data using SQL and PostgreSQL.\n- Use Git, write unit tests and maintain testable code.\n- Familiarity with Docker, CI/CD and secure APIs with OAuth.\n\nNice-to-have:\n- AWS and Kubernetes cloud deployment.\n- React, microservices and system design experience.\n\nYou will build reliable product features with your team, review code, and improve service quality.`;
function elem(tag, className = '', text = '') { const el = document.createElement(tag); if(className) el.className=className; el.textContent=text; return el; }
function switchInput(to) {
  method = to;
  $('uploadContent').hidden = to !== 'upload';
  $('pasteContent').hidden = to !== 'paste';
  for (const tab of ['upload','paste']) {
    const selected = tab === to;
    $(tab+'Tab').classList.toggle('active',selected);
    $(tab+'Tab').setAttribute('aria-selected',String(selected));
  }
  hideError();
}
$('uploadTab').addEventListener('click',()=>switchInput('upload'));
$('pasteTab').addEventListener('click',()=>switchInput('paste'));
function setFile(file) {
  if(!file) return;
  lastFile = file;
  $('fileTitle').textContent = file.name;
  $('fileSubtitle').textContent = `${(file.size/(1024*1024)).toFixed(2)} MB · Ready to analyze`;
  $('dropzone').classList.add('selected');
  hideError();
}
$('resumeFile').addEventListener('change', e => setFile(e.target.files[0]));
const dz = $('dropzone');
for(const eventName of ['dragenter','dragover']) dz.addEventListener(eventName,e=>{e.preventDefault();dz.classList.add('dragover')});
for(const eventName of ['dragleave','drop']) dz.addEventListener(eventName,e=>{e.preventDefault();dz.classList.remove('dragover')});
dz.addEventListener('drop', e=>{ const file = e.dataTransfer?.files?.[0]; if(file) { if(typeof DataTransfer!=='undefined'){const d=new DataTransfer();d.items.add(file);$('resumeFile').files=d.files;}setFile(file); }});
$('jobDescription').addEventListener('input', e => $('jdCount').textContent = `${e.target.value.length.toLocaleString()} characters`);
$('resumeText').addEventListener('input', e => $('resumeCount').textContent = `${e.target.value.length.toLocaleString()} characters`);
function showError(msg){$('formError').hidden=false;$('formError').textContent=msg;}
function hideError(){$('formError').hidden=true;$('formError').textContent='';}
function showState(s){$('emptyState').hidden=s!=='empty';$('loadingState').hidden=s!=='loading';$('resultState').hidden=s!=='result';}
$('trySample').addEventListener('click',()=>{
  $('roleTitle').value='Junior Java Backend Software Engineer';
  $('jobDescription').value=demoJD;
  $('resumeText').value=demoResume;
  $('jobDescription').dispatchEvent(new Event('input'));
  $('resumeText').dispatchEvent(new Event('input'));
  switchInput('paste');
  showState('empty');
  $('jobDescription').focus();
});
function clearAll() {
  form.reset(); lastFile=null;currentReport=null;
  $('fileTitle').textContent='Drop your resume here';
  $('fileSubtitle').textContent='or browse files from your device';
  $('jdCount').textContent='0 characters';$('resumeCount').textContent='0 characters';
  switchInput('paste');hideError();showState('empty');
}
$('clearButton').addEventListener('click',clearAll);
$('newAnalysis').addEventListener('click',()=>{showState('empty');$('jobDescription').focus();$('workspace').scrollIntoView({behavior:'smooth',block:'start'});});
form.addEventListener('submit',async (e)=>{
  e.preventDefault();hideError();
  const jd=$('jobDescription').value.trim();
  if(jd.length<80){showError('Please paste a job description with at least 80 characters.');return;}
  if(method==='upload'&&!lastFile){showError('Please upload a resume, or choose “Paste text” instead.');return;}
  if(method==='upload'&&lastFile.size>6*1024*1024){showError('Resume file must be 6 MB or smaller.');return;}
  if(method==='paste'&&$('resumeText').value.trim().length<100){showError('Please paste at least 100 characters of readable resume text.');return;}
  const payload=new FormData();
  payload.append('job_description',jd);payload.append('target_role',$('roleTitle').value);
  if(method==='upload') payload.append('resume_file',lastFile,lastFile.name);
  else payload.append('resume_text',$('resumeText').value);
  payload.append('semantic_mode',$('semanticMode').value);
  payload.append('use_custom_model',String($('customEvidence').checked));
  const button=$('analyzeButton');button.disabled=true;$('analyzeText').textContent='Analyzing…';
  showState('loading');
  try {
    const response=await apiFetch('/api/analyze',{method:'POST',body:payload});
    let data;try{data=await response.json()}catch{throw new Error('The server returned an unreadable response.');}
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'The analysis could not be completed.');
    currentReport=data;renderReport(data);showState('result');
  }catch(error){showState('empty');showError(error.message||'Analysis failed. Please try again.');}
  finally{button.disabled=false;$('analyzeText').textContent='Analyze my resume';}
});
const short=(arr,empty)=>arr?.length?arr.join(', '):empty;
function fillChips(id,arr,missing){const parent=$(id);parent.replaceChildren(); if(!arr.length){parent.append(elem('span','none-msg',missing?'No documented gaps in the detected category.':'None detected.'));return;} for(const item of arr){parent.append(elem('span','chip'+(missing?' missing':''),item));}}
function renderReport(r){
  $('reportTitle').textContent=r.role==='this role'?'Your application analysis':r.role;
  $('scoreRing').style.setProperty('--progress', `${r.score}%`);
  $('scoreValue').textContent=r.score;
  $('verdict').textContent=r.verdict;
  $('reportSummary').textContent=r.summary;
  $('coreStat').textContent=`${r.required.matched.length}/${r.required.total}`;
  $('preferredStat').textContent=`${r.preferred.matched.length}/${r.preferred.total}`;
  $('structureStat').textContent=`${r.sections.filter(x=>x.present).length}/${r.sections.length}`;
  $('reportNotes').textContent=r.notes;
  const breakdown=$('breakdown');breakdown.replaceChildren();
  for(const item of r.breakdown){
    if(item.weight===0)continue;
    const row=elem('div','breakdown-row');const label=elem('div','breakdown-label');
    label.append(elem('span','',`${item.label} · ${item.weight}% weight`),elem('strong','',`${item.score}%`));
    const track=elem('div','bar-track');const fill=elem('div','bar-fill');fill.style.width=`${Math.max(0,Math.min(100,item.score))}%`;track.append(fill);row.append(label,track);breakdown.append(row);
  }
  fillChips('matchedSkills',r.required.matched,false);
  fillChips('missingSkills',r.required.not_found,true);
  const evidence=$('evidenceList');evidence.replaceChildren();
  if(!r.evidence.length)evidence.append(elem('p','section-caption','No direct examples found for detected job-description skills.'));
  for(const ev of r.evidence){const card=elem('article','evidence-item');card.append(elem('strong','',ev.skill),elem('p','',ev.evidence));evidence.append(card);}
  const checks=$('sectionChecks');checks.replaceChildren();
  for(const s of r.sections){const card=elem('div','check-item');card.append(elem('b',s.present?'pass':'fail',s.present?'✓':'○'),elem('span','',s.name));checks.append(card);}
  const improvements=$('improvementList');improvements.replaceChildren();
  for(const tip of r.improvements){const card=elem('article','improvement-item');const title=elem('div');title.append(elem('span','priority '+tip.priority.toLowerCase(),tip.priority),elem('strong','',tip.title));card.append(title,elem('p','',tip.detail));improvements.append(card);}
  const interviews=$('interviewList');interviews.replaceChildren();
  r.interview_questions.forEach((q,index)=>{const card=elem('div','interview-item');card.append(elem('b','',String(index+1).padStart(2,'0')),elem('span','',q));interviews.append(card);});
  const sem=document.getElementById('semanticEvidence');if(sem)sem.remove();
  if(r.semantic&&r.semantic.matches?.length){
    const holder=elem('div');holder.id='semanticEvidence';holder.append(elem('h4','minor-head','Semantic passage matches'));
    for(const match of r.semantic.matches){
      const card=elem('div','semantic-card');card.append(elem('strong','',`Similarity ${Math.round(match.similarity*100)}% · ${match.requirement}`),elem('p','',`Resume text: ${match.resume_evidence}`));holder.append(card);
    }
    $('evidenceSection').append(holder);
  }
  const custom=document.getElementById('customEvidenceView');if(custom)custom.remove();
  if(r.custom_evidence?.length){
    const holder=elem('div');holder.id='customEvidenceView';holder.append(elem('h4','minor-head','Experimental trained classifier'));
    for(const x of r.custom_evidence)holder.append(elem('p','section-caption',`${x.skill}: ${Math.round(x.confidence*100)}% model confidence on a snippet — NOT an ATS/hiring probability.`));
    $('evidenceSection').append(holder);
  }
  $('rewriteContent').hidden=true;$('rewriteInfo').textContent='';$('rewriteError').hidden=true;
  activateResultTab('matchSection');
}
function activateResultTab(section){
  for(const btn of document.querySelectorAll('.results-tab')){
    const active=btn.dataset.target===section;btn.classList.toggle('selected',active);btn.setAttribute('aria-selected',String(active));
    $(btn.dataset.target).hidden=!active;$(btn.dataset.target).classList.toggle('active',active);
  }
}
for(const b of document.querySelectorAll('.results-tab'))b.addEventListener('click',()=>activateResultTab(b.dataset.target));
function reportMarkdown(r){
  const lines=[`# SkillLens analysis: ${r.role}`,`\n**Document-alignment estimate:** ${r.score}/100 — ${r.verdict}`,`\n${r.summary}`,`\n> ${r.methodology}`,`\n## Score components`];
  for(const b of r.breakdown)if(b.weight)lines.push(`- ${b.label}: ${b.score}% (${b.weight}% weight)`);
  lines.push(`\n## Detected skills`,`- Required, documented: ${short(r.required.matched,'none')}`,`- Required, not found: ${short(r.required.not_found,'none')}`,`- Preferred, documented: ${short(r.preferred.matched,'none')}`,`- Preferred, not found: ${short(r.preferred.not_found,'none')}`,`\n## Resume essentials`);
  for(const s of r.sections) lines.push(`- ${s.present?'Present':'Not detected'}: ${s.name}`);
  lines.push(`\n## Evidence`);
  for(const e of r.evidence)lines.push(`- ${e.skill}: ${e.evidence}`);
  lines.push(`\n## Suggested improvements`);
  for(const t of r.improvements)lines.push(`- [${t.priority}] ${t.title}: ${t.detail}`);
  lines.push(`\n## Interview practice`);
  for(const q of r.interview_questions)lines.push(`- ${q}`);
  lines.push(`\n## Limitations`,`This is NOT a real employer ATS score. No employer ATS integration. Listed skills are not independently verified.`,r.notes);
  return lines.join('\n')+'\n';
}
$('exportButton').addEventListener('click',()=>{
  if(!currentReport)return;
  const blob=new Blob([reportMarkdown(currentReport)],{type:'text/markdown;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');anchor.href=url;anchor.download='skilllens-report.md';anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
});
$('saveReportButton').addEventListener('click',async()=>{
  if(!currentReport)return;
  try{
    const res=await apiFetch('/api/reports',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:currentReport.role || 'Analysis report',report:currentReport})});
    const data=await res.json();if(!res.ok)throw Error(data.detail || 'Cannot save report');
    $('saveReportButton').textContent='Saved securely ✓';setTimeout(()=>$('saveReportButton').textContent='☷ Save encrypted report',2200);
  }catch(e){showError(e.message);window.openAccount?.();}
});
$('printReport').addEventListener('click',()=>{if(currentReport)window.print()});

// ----- Local-first AI capabilities, model-assisted evidence and rewrite studio -----
let capabilities = null;
async function fetchCapabilities(){
  try{
    const response=await apiFetch('/api/capabilities');
    if(!response.ok)throw Error('Could not load model status');
    capabilities=await response.json();
    $('embeddingBadge').textContent=capabilities.embedding.available?'Configured (loads on demand)':'Not configured';
    $('modelBadge').textContent=capabilities.custom_model.available?'Experimental model available':'Training required';
    $('llmBadge').textContent=capabilities.llm.available?`${capabilities.llm.provider}: ${capabilities.llm.model}`:'Safe-only until configured';
    $('engineStatus').textContent=capabilities.embedding.available||capabilities.custom_model.available?'Advanced options available':'Classic NLP enabled';
    $('engineHelp').textContent='Embeddings require an optional local model. The custom classifier should be used for research only, not hiring decisions.';
    $('semanticMode').querySelector('[value="embeddings"]').disabled=!capabilities.embedding.available;
    $('customEvidence').disabled=!capabilities.custom_model.available;
    $('rewriteMode').querySelector('[value="llm"]').disabled=!capabilities.llm.available;
    if(!capabilities.embedding.available)$('semanticMode').value='classic';
  }catch{
    $('engineStatus').textContent='Engine status unavailable';
    $('engineHelp').textContent='The basic analyzer remains available.';
  }
}
fetchCapabilities();
function jobPayload(){
  const fd=new FormData();fd.append('job_description',$('jobDescription').value.trim());
  fd.append('target_role',$('roleTitle').value.trim());
  if(method==='upload'&&lastFile)fd.append('resume_file',lastFile,lastFile.name);
  else fd.append('resume_text',$('resumeText').value);
  return fd;
}
function rewriteAlert(message){$('rewriteError').hidden=false;$('rewriteError').textContent=message;}
function insertSuggestion(s){
  const draft=$('resumeDraft');
  const lines=draft.value.split('\n');
  const i=Number(s.id.slice(1))-1;
  // Apply only if draft has the original unchanged source on the claimed line.
  if(i>=0&&i<lines.length&&lines[i].trim().replace(/^[\s\-•*]+/,'').replace(/\s+/g,' ')===s.original){
    const prefix=lines[i].match(/^[\s\-•*]*/)?.[0]||'';
    lines[i]=prefix+s.suggested;draft.value=lines.join('\n');return true;
  }
  // The user may have edited the draft; never overwrite an unrelated line.
  return false;
}
function displayRewrites(data){
  $('rewriteInfo').textContent=`${data.message} ${data.privacy}`;
  $('draftDisclaimer').textContent=data.warning;
  $('resumeDraft').value=data.draft;
  const list=$('suggestionList');list.replaceChildren();
  if(!data.suggestions.length)list.append(elem('p','section-caption','No eligible evidence lines identified. Edit the source draft directly.'));
  for(const s of data.suggestions){
    const card=elem('div','suggestion-item');
    card.append(elem('div','source',`SOURCE ${s.id}: ${s.original}`),elem('div','proposal',s.suggested),
      elem('span','verification',s.verification+(s.review_required?' · Human verification required':'')));
    const btn=elem('button','','Apply to draft');btn.type='button';btn.disabled=s.suggested===s.original;
    btn.addEventListener('click',()=>{
      if(insertSuggestion(s)){btn.disabled=true;btn.textContent='Applied ✓';}
      else rewriteAlert('The corresponding draft line has changed. Review the suggestion and edit it manually to avoid overwriting your work.');
    });
    card.append(btn);list.append(card);
  }
  $('rewriteContent').hidden=false;
}
$('rewriteButton').addEventListener('click',async ()=>{
  $('rewriteError').hidden=true;$('rewriteInfo').textContent='';
  if($('jobDescription').value.trim().length<80)return rewriteAlert('Add a job description before rewriting.');
  if(method==='upload'&&!lastFile)return rewriteAlert('Select a resume file before rewriting.');
  if(method==='paste'&&$('resumeText').value.trim().length<100)return rewriteAlert('Paste your full resume text before rewriting.');
  const btn=$('rewriteButton');btn.disabled=true;btn.textContent='Preparing your draft…';
  try{
    const data=jobPayload();data.append('mode',$('rewriteMode').value);data.append('consent_external_ai',String($('aiConsent').checked));
    const response=await apiFetch('/api/rewrite',{method:'POST',body:data});
    const body=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Rewrite failed.');
    displayRewrites(body);
  }catch(error){rewriteAlert(error.message||'Unable to generate a draft.');}
  finally{btn.disabled=false;btn.textContent='Generate tailored draft ↗';}
});
function downloadText(text,filename,type='text/plain;charset=utf-8'){
  const file=new Blob([text],{type});const url=URL.createObjectURL(file);const a=document.createElement('a');
  a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('draftTxt').addEventListener('click',()=>downloadText($('resumeDraft').value,'skilllens-tailored-resume.txt'));
$('draftCopy').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText($('resumeDraft').value);$('draftCopy').textContent='Copied ✓';}
  catch{rewriteAlert('Clipboard unavailable. Select and copy the draft text manually.');}
});
$('draftDocx').addEventListener('click',async()=>{
  const draft=$('resumeDraft').value;
  if(draft.length<20)return rewriteAlert('Resume draft is too short.');
  const btn=$('draftDocx');btn.disabled=true;btn.textContent='Generating DOCX…';
  try{
    const response=await apiFetch('/api/export/docx',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({draft})});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw Error(data.detail||'Could not export DOCX.');}
    const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');
    a.download='skilllens-tailored-resume.docx';a.href=url;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
  }catch(error){rewriteAlert(error.message||'Could not export DOCX.');}
  finally{btn.disabled=false;btn.textContent='Download DOCX';}
});

window.addEventListener('skilllens:report', e => { currentReport=e.detail; renderReport(currentReport); showState('result'); $('workspace').scrollIntoView({behavior:'smooth'}); });
