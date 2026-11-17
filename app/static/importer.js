/* Client-side resume import. Never POST original file bytes to the application. */
(() => {
'use strict';

const fileInput = document.getElementById('importTextFile');
const uploadInput = document.getElementById('resumeFile');
const trigger = document.getElementById('importTextButton');
const target = document.getElementById('resumeText');
const uploadDropzone = document.getElementById('dropzone');
const inlineDropzone = document.getElementById('importDropzone');
const limitBytes = 6 * 1024 * 1024;
let importing = false;
let generation = 0;
window.skilllensImporting = false;

function notify(text, error = false) {
  for (const id of ['importStatus', 'uploadStatus']) {
    const element = document.getElementById(id);
    if (element) {
      element.textContent = text;
      element.classList.toggle('error', error);
    }
  }
}

function loadParserScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = () => {
      script.remove();
      reject(Error('DOCX parser is unavailable. Refresh the page and try again.'));
    };
    document.head.append(script);
  });
}

async function pdfText(bytes) {
  let pdfjs;
  try {
    pdfjs = await import('/assets/vendor/pdf.mjs');
  } catch {
    throw Error('PDF parser could not load. Refresh the page and try again.');
  }
  pdfjs.GlobalWorkerOptions.workerSrc = '/assets/vendor/pdf.worker.mjs';
  const loading = pdfjs.getDocument({data:bytes, isEvalSupported:false, enableXfa:false});
  let pdf;
  try {
    pdf = await loading.promise;
    if (pdf.numPages > 35) throw Error('PDF exceeds the 35-page import limit.');
    const pages = [];
    let length = 0;
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const content = await page.getTextContent();
      let pageText = '';
      for (const item of content.items) {
        if (typeof item.str !== 'string') continue;
        pageText += item.str + (item.hasEOL ? '\n' : ' ');
      }
      pages.push(pageText.trim());
      length += pageText.length;
      page.cleanup();
      if (length > 60000) throw Error('PDF contains too much text.');
    }
    return pages.join('\n\n');
  } finally {
    try { await loading.destroy(); } catch { /* best-effort cleanup */ }
  }
}

async function docxText(buffer) {
  if (!window.mammoth) await loadParserScript('/assets/vendor/mammoth.browser.min.js');
  const result = await window.mammoth.extractRawText({arrayBuffer:buffer});
  return result.value;
}

async function extract(file) {
  if (!file || !file.size) throw Error('Choose a non-empty PDF, DOCX or TXT file.');
  if (file.size > limitBytes) throw Error('Resume file must be 6 MB or smaller.');
  if (!/\.(txt|pdf|docx)$/i.test(file.name)) throw Error('Supported formats: PDF, DOCX and TXT.');
  const buffer = await file.arrayBuffer();
  const lower = file.name.toLowerCase();
  if (lower.endsWith('.txt')) {
    return new TextDecoder('utf-8',{fatal:true}).decode(buffer).replace(/^\uFEFF/,'');
  }
  if (lower.endsWith('.pdf')) {
    if (new TextDecoder().decode(buffer.slice(0,5)) !== '%PDF-')
      throw Error('The selected file is not a valid PDF.');
    return pdfText(new Uint8Array(buffer));
  }
  const head = new Uint8Array(buffer.slice(0,4));
  if (head[0] !== 0x50 || head[1] !== 0x4b)
    throw Error('The selected file is not a valid DOCX.');
  return docxText(buffer);
}

async function handleImport(file) {
  if (!file) return;
  if (importing) {
    notify('Another resume is being imported. Please let it finish.', true);
    return;
  }
  const thisGeneration = generation;
  importing = true;
  window.skilllensImporting = true;
  trigger.disabled = true;
  notify('Reading resume locally…');
  try {
    const text = await extract(file);
    if (thisGeneration !== generation) return; // User cleared the form mid-import.
    if (text.trim().length < 100)
      throw Error('Not enough readable text. Scanned/image-only PDFs need OCR; try a text-based file.');
    if (text.length > 55000)
      throw Error('Extracted resume exceeds the 55,000-character limit.');
    target.value = text;
    target.dispatchEvent(new Event('input', {bubbles:true}));
    document.getElementById('fileTitle').textContent = file.name;
    document.getElementById('fileSubtitle').textContent =
      'Imported successfully · ' + text.length.toLocaleString() + ' characters';
    uploadDropzone.classList.add('selected');
    document.getElementById('pasteTab').click();
    notify('Imported ' + file.name + '. Review the extracted text, then run your analysis.');
    target.focus();
  } catch (error) {
    if (thisGeneration !== generation) return;
    notify(error?.message || 'Unable to read this file. Try another format.', true);
  } finally {
    importing = false;
    window.skilllensImporting = false;
    trigger.disabled = false;
    fileInput.value = '';
    uploadInput.value = '';
  }
}

trigger.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', event => handleImport(event.target.files?.[0]));
uploadInput.addEventListener('change', event => handleImport(event.target.files?.[0]));
for (const dropzone of [uploadDropzone, inlineDropzone]) {
  if (!dropzone) continue;
  for (const eventName of ['dragenter','dragover']) {
    dropzone.addEventListener(eventName, e => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
  }
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    handleImport(e.dataTransfer?.files?.[0]);
  });
}
window.addEventListener('skilllens:clear', () => {
  generation += 1;
  notify('Only extracted text is sent when you analyze; the original file remains in your browser.');
});
})();
