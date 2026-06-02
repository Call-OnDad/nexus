// Phase 3 mobile verification — loads live CT117 URL, taps each dept bubble,
// captures screenshots + console errors. Standalone; not part of test suite.
const { chromium, devices } = require('playwright');
const path = require('path');
const fs   = require('fs');

const URL = 'http://100.71.24.81:5000/app-native.html';
const OUT = path.join(__dirname, '..', 'test-results', 'phase3');
fs.mkdirSync(OUT, { recursive: true });

const DEPTS = ['nexus','infra','marketing','business','community','security','email'];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices['Pixel 7'] });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console',  m => { if (m.type() === 'error') errors.push('[console] ' + m.text()); });
  page.on('pageerror', e => errors.push('[pageerror] ' + e.message));

  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('#bubbles-layer .bubble', { timeout: 10000, state: 'attached' });
  await page.screenshot({ path: path.join(OUT, '00-load.png'), fullPage: false, timeout: 8000, animations: 'disabled' }).catch(e => console.log('screenshot:', e.message));
  console.log('LOAD ok. bubbles:', await page.locator('#bubbles-layer .bubble').count());

  for (const d of DEPTS) {
    try {
      await page.locator(`#node-${d}`).click();
      // wait for detail panel to populate (loader fades out)
      await page.waitForFunction(() => {
        const g = document.getElementById('detail-grid');
        return g && !g.innerHTML.includes('Loading') && g.innerHTML.length > 30;
      }, { timeout: 25000 }).catch(() => {});
      await page.waitForTimeout(600);
      await page.screenshot({ path: path.join(OUT, `${d}.png`), fullPage: false, timeout: 8000, animations: 'disabled' }).catch(e => console.log(`${d} screenshot:`, e.message));
      const gridLen = await page.locator('#detail-grid').evaluate(el => el.innerHTML.length);
      console.log(`${d}: detail rendered, grid=${gridLen} bytes`);
      // close detail
      await page.locator('#detail-back').click();
      await page.waitForTimeout(300);
    } catch (e) {
      console.log(`${d}: FAIL — ${e.message}`);
    }
  }

  if (errors.length) {
    console.log('--- ERRORS ---');
    errors.forEach(e => console.log(e));
  } else {
    console.log('--- no console/page errors ---');
  }
  await browser.close();
})();
