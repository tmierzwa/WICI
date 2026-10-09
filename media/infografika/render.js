// Renders infografika.html to PNG: node render.js  (needs playwright)
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const FORMATS = [
  { name: 'post', height: 1350, pad: 16, file: lang => `WICI-infografika-${lang}.png` },
  { name: 'story', height: 1920, pad: 300, file: lang => `WICI-stories-${lang}.png` },
];
(async () => {
  const dir = __dirname;
  const logo = fs.readFileSync(path.join(dir, '../logo/WICI-na-ciemnym.svg'), 'utf8')
    .replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
  const browser = await chromium.launch();
  for (const f of FORMATS) {
    const page = await browser.newPage({ viewport: { width: 1080, height: f.height }, deviceScaleFactor: 2 });
    for (const lang of ['pl', 'en']) {
      await page.goto('file://' + path.join(dir, 'infografika.html') + `?lang=${lang}&format=${f.name}`);
      await page.evaluate(l => { document.getElementById('logo').innerHTML = l; }, logo);
      await page.evaluate(() => document.fonts.ready);
      const h = await page.evaluate(() => [...document.querySelectorAll('.page > :not(.deco)')].map(e => e.getBoundingClientRect().bottom).reduce((a, b) => Math.max(a, b)));
      if (h > f.height - f.pad) console.warn(f.name, lang, 'content bottom at', Math.round(h), 'limit', f.height - f.pad);
      await page.screenshot({ path: path.join(dir, f.file(lang)) });
    }
    await page.close();
  }
  await browser.close();
})();
