// Build NOVU_MASTER_PRODUCT_BOOK.pdf from the Markdown master.
// Markdown -> HTML (marked) with Mermaid blocks preserved -> headless Chrome -> PDF.
import { readFileSync, writeFileSync } from 'node:fs';
import { marked } from 'marked';
import puppeteer from 'puppeteer-core';

const ROOT = 'd:/Novu_Hub/Novu_Builder';
const MD_PATH = `${ROOT}/NOVU_MASTER_PRODUCT_BOOK.md`;
const PDF_PATH = `${ROOT}/NOVU_MASTER_PRODUCT_BOOK.pdf`;
const HTML_PATH = `${ROOT}/.pdfbuild/book.html`;
const MERMAID_JS = readFileSync(`${ROOT}/node_modules/mermaid/dist/mermaid.min.js`, 'utf8');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// Mermaid code blocks -> <pre class="mermaid">; \newpage -> page break div.
marked.use({
  renderer: {
    code(token) {
      if ((token.lang || '').trim() === 'mermaid') {
        return `<div class="mermaid-wrap"><pre class="mermaid">${esc(token.text)}</pre></div>`;
      }
      return false;
    },
  },
});

let md = readFileSync(MD_PATH, 'utf8');
md = md.replace(/^\\newpage\s*$/gm, '\n<div class="page-break"></div>\n');

let body = marked.parse(md);
// Convert fenced mermaid code blocks into mermaid render targets.
body = body.replace(
  /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g,
  (_m, code) => `<div class="mermaid-wrap"><pre class="mermaid">${code}</pre></div>`,
);

const html = `<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<style>
  :root { --ink:#1a2230; --muted:#5b6b85; --line:#d8dee9; --accent:#1565c0; --accent2:#0d3a6b; --soft:#f5f7fb; }
  * { box-sizing: border-box; }
  html, body { margin:0; padding:0; }
  body {
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
    color: var(--ink); font-size: 10.8pt; line-height: 1.55;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .content { padding: 0 4pt; }
  h1 {
    font-size: 21pt; color: var(--accent2); margin: 6pt 0 10pt;
    padding-bottom: 6pt; border-bottom: 3px solid var(--accent);
    page-break-after: avoid; line-height: 1.2;
  }
  h2 { font-size: 15pt; color: var(--accent2); margin: 18pt 0 7pt; page-break-after: avoid; }
  h3 { font-size: 12.2pt; color: var(--accent); margin: 13pt 0 5pt; page-break-after: avoid; }
  h4 { font-size: 11pt; color: var(--ink); margin: 10pt 0 4pt; page-break-after: avoid; }
  p { margin: 0 0 7pt; }
  a { color: var(--accent); text-decoration: none; }
  ul, ol { margin: 0 0 8pt; padding-left: 20pt; }
  li { margin: 2pt 0; }
  strong { color: var(--accent2); }
  hr { border: none; border-top: 1px solid var(--line); margin: 14pt 0; }
  blockquote {
    margin: 10pt 0; padding: 8pt 14pt; background: var(--soft);
    border-left: 4px solid var(--accent); color: var(--ink); border-radius: 3px;
  }
  blockquote p:last-child { margin-bottom: 0; }
  code { font-family: "Consolas","JetBrains Mono",monospace; font-size: 9.4pt;
         background: #eef2f8; padding: 1px 4px; border-radius: 3px; }
  table {
    border-collapse: collapse; width: 100%; margin: 8pt 0 12pt;
    font-size: 9.4pt; page-break-inside: auto;
  }
  th { background: var(--accent2); color: #fff; text-align: left; padding: 5pt 7pt; font-weight: 600; }
  td { border: 1px solid var(--line); padding: 4pt 7pt; vertical-align: top; }
  tr:nth-child(even) td { background: #f7f9fc; }
  tr { page-break-inside: avoid; }
  .mermaid-wrap { text-align: center; margin: 10pt 0 14pt; page-break-inside: avoid; }
  .mermaid { display: inline-block; }
  .mermaid svg { max-width: 100%; height: auto; }
  .page-break { page-break-before: always; }
  /* Title block */
  div[align="center"] { text-align: center; }
  div[align="center"] h1 { border: none; color: var(--accent2); font-size: 30pt; }
  div[align="center"] h2 { color: var(--accent); font-size: 16pt; margin-top: 2pt; }
</style>
</head>
<body>
<div class="content">
${body}
</div>
<script>${MERMAID_JS}</script>
<script>
  const __ns = window.__esbuild_esm_mermaid_nm.mermaid;
  const mermaid = (__ns && typeof __ns.initialize === 'function') ? __ns : (__ns.default || __ns.mermaid || __ns);
  window.__diag = { version: (mermaid && mermaid.version) || 'n/a', count: 0, errors: [] };
  window.__mermaidReady = (async () => {
    mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose',
      flowchart: { htmlLabels: true, useMaxWidth: true },
      themeVariables: { fontSize: '14px', primaryColor: '#e3f0fb', primaryBorderColor: '#1565c0',
                        lineColor: '#5b6b85', fontFamily: 'Segoe UI, Arial, sans-serif' } });
    const nodes = Array.from(document.querySelectorAll('.mermaid'));
    window.__diag.count = nodes.length;
    for (let i = 0; i < nodes.length; i++) {
      const el = nodes[i];
      const src = el.textContent;
      try {
        const { svg } = await mermaid.render('mmd-' + i, src);
        el.innerHTML = svg;
      } catch (e) {
        window.__diag.errors.push({ i, msg: String(e && e.message || e).slice(0, 200), head: src.slice(0, 40) });
      }
    }
    return true;
  })();
</script>
</body>
</html>`;

writeFileSync(HTML_PATH, html, 'utf8');
console.log('HTML written:', HTML_PATH, `(${(html.length/1024).toFixed(0)} KB)`);

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--font-render-hinting=none'],
});
const page = await browser.newPage();
const fileUrl = 'file:///' + HTML_PATH.replace(/\\/g, '/');
page.on('console', (m) => { if (m.type() === 'error') console.log('  [page]', m.text()); });
await page.goto(fileUrl, { waitUntil: 'load', timeout: 120000 });
await page.waitForFunction(() => typeof window.__mermaidReady !== 'undefined', { timeout: 60000 });
await page.evaluate(async () => { await window.__mermaidReady; });
// settle layout/fonts
await new Promise((r) => setTimeout(r, 1500));

const diag = await page.evaluate(() => window.__diag);
const svgCount = await page.evaluate(() => document.querySelectorAll('.mermaid svg').length);
console.log('Mermaid version:', diag.version, '| blocks:', diag.count, '| SVGs:', svgCount, '| errors:', diag.errors.length);
if (diag.errors.length) console.log(JSON.stringify(diag.errors.slice(0, 6), null, 2));

await page.pdf({
  path: PDF_PATH,
  format: 'A4',
  printBackground: true,
  margin: { top: '16mm', bottom: '18mm', left: '15mm', right: '15mm' },
  displayHeaderFooter: true,
  headerTemplate: '<div></div>',
  footerTemplate:
    '<div style="width:100%; font-size:8px; color:#8a97ad; padding:0 15mm; font-family:Segoe UI,Arial;">' +
    '<span style="float:left;">NOVU Builder — Master Product Book · v1.0</span>' +
    '<span style="float:right;">Strana <span class="pageNumber"></span> / <span class="totalPages"></span></span>' +
    '</div>',
});

await browser.close();
console.log('PDF written:', PDF_PATH);
