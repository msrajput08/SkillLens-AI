import { mkdir, copyFile } from 'node:fs/promises';
import path from 'node:path';
const out = process.argv[2] || path.join(process.cwd(), 'vendor');
await mkdir(out, { recursive: true });
for (const [src,name] of [
  ['node_modules/pdfjs-dist/build/pdf.mjs','pdf.mjs'],
  ['node_modules/pdfjs-dist/build/pdf.worker.mjs','pdf.worker.mjs'],
  ['node_modules/mammoth/mammoth.browser.min.js','mammoth.browser.min.js']
]) { await copyFile(src,path.join(out,name)); }
console.log('Browser PDF/DOCX parsers installed as local static assets.');
