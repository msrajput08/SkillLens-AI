'use strict';
// Browser importer regression tests; no browser or extra npm dependencies required.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..');
const importerCode = fs.readFileSync(path.join(ROOT, 'app/static/importer.js'), 'utf8');

function harness() {
  const els = new Map();
  const winListeners = new Map();
  const classes = new Set();
  class Element {
    constructor(id) {
      this.id = id;
      this.value = '';
      this.textContent = '';
      this.disabled = false;
      this.files = [];
      this.listeners = new Map();
      this.classes = new Set();
      this.classList = {
        add: name => this.classes.add(name),
        remove: name => this.classes.delete(name),
        toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name),
        contains: name => this.classes.has(name),
      };
      this.clickCount = 0;
    }
    addEventListener(type, callback) {
      if (!this.listeners.has(type)) this.listeners.set(type, []);
      this.listeners.get(type).push(callback);
    }
    dispatchEvent(event) {
      for (const handler of this.listeners.get(event.type) || []) handler(event);
    }
    click() { this.clickCount++; this.dispatchEvent({type:'click'}); }
    focus() { this.focused = true; }
  }
  const get = id => {
    if (!els.has(id)) els.set(id, new Element(id));
    return els.get(id);
  };
  const document = {getElementById:get, createElement:()=>new Element('script'), head:{append:()=>{}}};
  const window = {
    addEventListener: (type, cb) => winListeners.set(type, cb),
    mammoth: {extractRawText: async () => ({value: 'DOCX: ' + 'Verified background '.repeat(10)})},
  };
  const context = vm.createContext({
    document, window, TextDecoder, Uint8Array, console,
    Event: class {constructor(type, options) {this.type=type;this.bubbles=!!options?.bubbles;}}
  });
  vm.runInContext(importerCode, context, {filename:'importer.js'});
  return {get, window, fireWindow:(type)=>winListeners.get(type)?.(), classes};
}
const tick = () => new Promise(resolve => setTimeout(resolve, 10));
function sample(name, bytes) {
  return {name,size:bytes.byteLength,arrayBuffer: async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset + bytes.byteLength)};
}

test('visible upload picker is wired to local import, never raw API upload', () => {
  const html=fs.readFileSync(path.join(ROOT, 'app/static/index.html'),'utf8');
  const app=fs.readFileSync(path.join(ROOT, 'app/static/app.js'),'utf8');
  assert.match(html, /id="uploadTab" class="tab">Upload PDF \/ DOCX \/ TXT/);
  assert.match(html, /id="uploadStatus"/);
  assert.match(importerCode, /uploadInput\.addEventListener\('change'/);
  assert.doesNotMatch(app, /payload\.append\('resume_file'/);
  assert.doesNotMatch(app, /fd\.append\('resume_file'/);
  assert.match(app, /payload\.append\('resume_text'/);
});

test('primary upload picker extracts TXT locally and switches to review tab', async () => {
  const {get,window}=harness();
  const raw = new TextEncoder().encode('Experienced Python developer working with APIs. '.repeat(5));
  get('resumeFile').dispatchEvent({type:'change',target:{files:[sample('my_cv.txt',raw)]}});
  assert.equal(window.skilllensImporting,true);
  await tick();
  assert.equal(window.skilllensImporting,false);
  assert.match(get('resumeText').value,/Python developer/);
  assert.equal(get('pasteTab').clickCount,1);
  assert.match(get('uploadStatus').textContent,/Imported my_cv\.txt/);
  assert.match(get('importStatus').textContent,/Imported my_cv\.txt/);
  assert.equal(get('fileTitle').textContent,'my_cv.txt');
  assert.equal(get('resumeFile').value,'');
});

test('DOCX importer uses local parser and does not call the network', async () => {
  const {get}=harness();
  const bytes = Uint8Array.from([0x50,0x4b,0x03,0x04,0,0,0,0]);
  get('importTextButton').click();
  assert.equal(get('importTextFile').clickCount,1);
  get('importTextFile').dispatchEvent({type:'change',target:{files:[sample('resume.docx',bytes)]}});
  await tick();
  assert.match(get('resumeText').value,/Verified background/);
  assert.equal(get('pasteTab').clickCount,1);
});

test('main upload zone drag/drop actually imports files', async () => {
  const {get}=harness();
  const text = new TextEncoder().encode('Java SQL projects and education. '.repeat(6));
  let prevented=false;
  get('dropzone').dispatchEvent({type:'drop',preventDefault:()=>{prevented=true;},
    dataTransfer:{files:[sample('resume.txt',text)]}});
  await tick();
  assert.equal(prevented,true);
  assert.match(get('resumeText').value,/Java SQL/);
});

test('bad files show an actionable error instead of a false success', async () => {
  const {get}=harness();
  const bytes = new TextEncoder().encode('not a pdf!'.repeat(20));
  get('resumeFile').dispatchEvent({type:'change',target:{files:[sample('fake.pdf',bytes)]}});
  await tick();
  assert.equal(get('resumeText').value,'');
  assert.match(get('uploadStatus').textContent,/not a valid PDF/);
  assert.ok(get('uploadStatus').classList.contains('error'));
});

test('clearing the form ignores a previously selected, still-parsing file', async () => {
  const {get,fireWindow}=harness();
  let finish;
  const pending = new Promise(resolve => {finish=resolve;});
  get('resumeFile').dispatchEvent({type:'change',target:{files:[{
    name:'slow.txt', size:250, arrayBuffer:()=>pending
  }]}});
  fireWindow('skilllens:clear');
  const bytes = new TextEncoder().encode('Python developer resume details '.repeat(9));
  finish(bytes.buffer);
  await tick();
  assert.equal(get('resumeText').value,'');
  assert.equal(get('pasteTab').clickCount,0);
});
