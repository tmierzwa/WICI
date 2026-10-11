// Renders stacja.html to PNG: npm install --no-save three@0.160.0 playwright && node render.js
// three.js requests to the CDN are served from the local node_modules when present.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const VIEWS = [
  { view: 'front', file: 'stacja-front.png' },
  { view: 'zlacza', file: 'stacja-zlacza.png' },
];
const CDN = 'https://cdn.jsdelivr.net/npm/three@0.160.0/';
(async () => {
  const dir = __dirname;
  const uklad = JSON.parse(fs.readFileSync(path.join(dir, 'uklad.json'), 'utf8'));
  const logo = fs.readFileSync(path.join(dir, '../../../media/logo/WICI-na-jasnym.svg'), 'utf8');
  let threeDir = null;
  try { threeDir = path.dirname(path.dirname(require.resolve('three', { paths: [process.cwd(), dir] }))); } catch { }
  if (!threeDir) console.warn('three.js not installed locally; loading it from', CDN);
  const browser = await chromium.launch({ args: ['--allow-file-access-from-files', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  for (const v of VIEWS) {
    const page = await browser.newPage({ viewport: { width: 1800, height: 1250 } });
    page.on('pageerror', e => { console.error(e); process.exitCode = 1; });
    if (threeDir) await page.route(CDN + '**', route => {
      const file = path.join(threeDir, route.request().url().slice(CDN.length));
      route.fulfill({ path: file, contentType: 'text/javascript' });
    });
    await page.addInitScript(([u, l]) => { window.UKLAD = u; window.LOGO = l; }, [uklad, logo]);
    await page.goto('file://' + path.join(dir, 'stacja.html') + `?view=${v.view}`);
    await page.waitForFunction(() => window.RENDER_DONE === true, null, { timeout: 120000 });
    await page.screenshot({ path: path.join(dir, v.file) });
    await page.close();
  }
  await browser.close();
})();
