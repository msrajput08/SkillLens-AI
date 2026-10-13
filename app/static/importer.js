/* Private, in-browser resume text extraction. Original file bytes never leave the browser. */
'use strict';
const fileInput = document.getElementById('importTextFile');
const trigger = document.getElementById('importTextButton');
const target = document.getElementById('resumeText');
const limitBytes = 6 * 1024 * 1024;
let importing = false;
function notify(text, error=false) {
  const element = document.getElementById('importStatus');
  if (element) { element.textContent = text; element.classList.toggle('error',error); }
}
function loadScript(src) {
  return new Promise((resolve,reject)=> {
    const script=document.createElement('script'); script.src=src;
    script.onload=resolve; script.onerror=()=>reject(Error('DOCX parser is unavailable. Install browser parser assets.'));
    document.head.append(script);
  });
}
async function pdfText(bytes) {
  let pdfjs;
  try { pdfjs=await import('/assets/vendor/pdf.mjs'); }
  catch {throw Error('PDF parser is unavailable on this deployment. The server must include the browser parser assets.');}
  pdfjs.GlobalWorkerOptions.workerSrc='/assets/vendor/pdf.worker.mjs';
  const loading=pdfjs.getDocument({data:bytes,isEvalSupported:false,enableXfa:false});
  let pdf;
  try {
    pdf=await loading.promise;
    if(pdf.numPages>35)throw Error('PDF exceeds the 35-page import limit.');
    const result=[];
    for(let i=1;i<=pdf.numPages;i++) {
      const page=await pdf.getPage(i);
      const content=await page.getTextContent();
      const lines=[];let line='';
      for(const item of content.items) {
        if(typeof item.str!=='string')continue;
        line+=item.str+(item.hasEOL?'\n':' ');
      }
      lines.push(line.trim()); result.push(lines.join('\n'));
      page.cleanup();
      if(result.join('\n').length>60000)throw Error('PDF contains too much text.');
    }
    return result.join('\n\n');
  } finally { try { await loading.destroy(); } catch { /* cleanup */ } }
}
async function docxText(buffer){
  if(!window.mammoth) await loadScript('/assets/vendor/mammoth.browser.min.js');
  const result=await window.mammoth.extractRawText({arrayBuffer:buffer});
  return result.value;
}
async function extract(file){
  if(!file || file.size>limitBytes)throw Error('Choose a file no larger than 6 MB.');
  if(!/\.(txt|pdf|docx)$/i.test(file.name))throw Error('Only .txt, .pdf and .docx files are supported.');
  const buffer=await file.arrayBuffer();
  const lower=file.name.toLowerCase();
  if(lower.endsWith('.txt')) return new TextDecoder('utf-8',{fatal:true}).decode(buffer).replace(/^\uFEFF/,'');
  if(lower.endsWith('.pdf')) {
    if(new TextDecoder().decode(buffer.slice(0,5))!=='%PDF-')throw Error('The selected file is not a valid PDF.');
    return pdfText(new Uint8Array(buffer));
  }
  const head=new Uint8Array(buffer.slice(0,4));
  if(head[0]!==0x50 || head[1]!==0x4b)throw Error('The selected file is not a valid DOCX.');
  return docxText(buffer);
}
async function handleImport(file){
  if(importing||!file)return;
  importing=true;trigger.disabled=true;notify('Extracting text locally…');
  try{
    const text=await extract(file);
    if(text.trim().length<100)throw Error('This file has too little readable text. Scanned PDFs need OCR before analysis.');
    if(text.length>55000)throw Error('Extracted resume exceeds the 55,000-character limit.');
    target.value=text;
    target.dispatchEvent(new Event('input',{bubbles:true}));
    document.getElementById('pasteTab').click();
    notify(`Imported ${file.name}. Original file stayed on your device; submit analysis to send extracted text.`);
    target.focus();
  }catch(error){notify(error?.message||'Unable to read this file.',true);}
  finally{importing=false;trigger.disabled=false;fileInput.value='';}
}
trigger.addEventListener('click',()=>fileInput.click());
fileInput.addEventListener('change',event=>handleImport(event.target.files?.[0]));
const dropzone=document.getElementById('importDropzone');
if(dropzone){
  dropzone.addEventListener('dragover',e=>{e.preventDefault();dropzone.classList.add('dragover');});
  dropzone.addEventListener('dragleave',()=>dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop',e=>{e.preventDefault();dropzone.classList.remove('dragover');handleImport(e.dataTransfer?.files?.[0]);});
}
