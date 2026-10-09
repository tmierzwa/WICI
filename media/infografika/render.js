// Renders infografika.html to PNG: node render.js  (needs playwright)
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const dir = __dirname;
  const logo = fs.readFileSync(path.join(dir, '../logo/WICI-na-ciemnym.svg'), 'utf8')
    .replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 2 });
  for (const lang of ['pl', 'en']) {
    await page.goto('file://' + path.join(dir, 'infografika.html') + '?lang=' + lang);
    await page.evaluate(l => { document.getElementById('logo').innerHTML = l; }, logo);
    await page.evaluate(() => document.fonts.ready);
    const h = await page.evaluate(() => [...document.querySelectorAll('.page > *')].map(e => e.getBoundingClientRect().bottom).reduce((a, b) => Math.max(a, b)));
    if (h > 1350 - 40) console.warn(lang, 'content bottom at', h);
    await page.screenshot({ path: path.join(dir, `WICI-infografika-${lang}.png`) });
  }
  await browser.close();
})();
