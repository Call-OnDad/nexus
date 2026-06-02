// PWA installability probe — checks manifest, icons, SW registration.
const { chromium, devices } = require('playwright');
const path = require('path'), fs = require('fs');
const URL = 'http://100.71.24.81:5000/app-native.html';
const OUT = path.join(__dirname, '..', 'test-results', 'phase3');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices['Pixel 7'] });
  const page = await ctx.newPage();
  const errs = [], warns = [];
  page.on('console',  m => { if (m.type() === 'error') errs.push(m.text()); if (m.type() === 'warning') warns.push(m.text()); });
  page.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
  page.on('response',  r => { if (r.status() >= 400) errs.push(`HTTP ${r.status()} ${r.url()}`); });

  await page.goto(URL, { waitUntil: 'load', timeout: 30000 });
  // Wait for SW to register
  const swState = await page.waitForFunction(async () => {
    if (!('serviceWorker' in navigator)) return 'no-sw-support';
    const r = await navigator.serviceWorker.getRegistration();
    if (!r) return 'no-registration';
    return r.active ? 'active' : (r.installing ? 'installing' : 'waiting');
  }, { timeout: 10000 }).then(h => h.jsonValue()).catch(e => 'timeout: ' + e.message);

  const manifest = await page.evaluate(async () => {
    const link = document.querySelector('link[rel=manifest]');
    if (!link) return { ok: false, reason: 'no link tag' };
    const r = await fetch(link.href);
    if (!r.ok) return { ok: false, reason: 'HTTP ' + r.status };
    const j = await r.json();
    return { ok: true, name: j.name, start_url: j.start_url, icons: j.icons.length };
  });

  console.log('SW state:        ', swState);
  console.log('Manifest:        ', JSON.stringify(manifest));
  console.log('Console errors:  ', errs.length === 0 ? '(none)' : errs);
  console.log('Console warnings:', warns.length === 0 ? '(none)' : warns.slice(0, 5));

  await browser.close();
})();
