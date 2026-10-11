// Renders stacja.html to PNG: npm install --no-save three@0.160.0 playwright && node render.js
// three.js requests to the CDN are served from the local node_modules when present.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const VIEWS = [
  { view: 'front', file: 'stacja-front.png' },
  { view: 'zlacza', file: 'stacja-zlacza.png' },
  // Do materiałów: 3600 × 2400 px, ciasny kadr z krótkim podpisem „wizualizacja koncepcyjna”.
  { view: 'materialy', file: 'stacja-materialy.png', width: 2400, height: 1600, scale: 1.5 },
  // Ten sam kadr dla strony i README: 1800 × 1200 px, JPEG.
  { view: 'materialy', file: 'stacja-materialy-web.jpg', width: 2400, height: 1600, scale: 0.75, quality: 85 },
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
  try {
  for (const v of VIEWS) {
    const page = await browser.newPage({ viewport: { width: v.width || 1800, height: v.height || 1250 }, deviceScaleFactor: v.scale || 1 });
    // Błąd strony albo nieudane żądanie (np. three.js niedostępny) kończy render od razu, zamiast czekać na limit czasu.
    const failed = new Promise((_, reject) => {
      page.on('pageerror', reject);
      page.on('requestfailed', r => reject(new Error(`request failed: ${r.url()} (${r.failure()?.errorText})`)));
    });
    failed.catch(() => {});   // obsłużone w Promise.race niżej; bez tego błąd przed race zabija proces
    if (threeDir) await page.route(CDN + '**', route => {
      const file = path.join(threeDir, route.request().url().slice(CDN.length));
      route.fulfill({ path: file, contentType: 'text/javascript' });
    });
    await page.addInitScript(([u, l]) => { window.UKLAD = u; window.LOGO = l; }, [uklad, logo]);
    await page.goto('file://' + path.join(dir, 'stacja.html') + `?view=${v.view}`);
    await Promise.race([page.waitForFunction(() => window.RENDER_DONE === true, null, { timeout: 120000 }), failed]);
    await page.screenshot({ path: path.join(dir, v.file), ...(v.quality ? { type: 'jpeg', quality: v.quality } : {}) });
    await page.close();
  }
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
