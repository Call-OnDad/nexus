// Capture mobile-viewport screenshot of the new radial layout.
const { chromium, devices } = require('playwright');
const path = require('path'), fs = require('fs');
const URL = 'http://100.71.24.81:5000/app-native.html';
const OUT = path.join(__dirname, '..', 'test-results', 'phase3');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices['Pixel 7'] });
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: 'load', timeout: 30000 });
  await page.waitForTimeout(2000); // let drift settle

  const layout = await page.evaluate(() => {
    const orbRect = document.querySelector('.orb-btn').getBoundingClientRect();
    const bubbles = [...document.querySelectorAll('.dept-constellation .bubble')].map(b => {
      const r = b.getBoundingClientRect();
      return { id: b.id, cx: Math.round(r.left + r.width/2), cy: Math.round(r.top + r.height/2) };
    });
    return {
      orb: { cx: Math.round(orbRect.left + orbRect.width/2), cy: Math.round(orbRect.top + orbRect.height/2) },
      bubbles,
      lines: document.querySelectorAll('#orb-links line').length,
    };
  });
  console.log('Orb centre:', layout.orb);
  console.log('Lines drawn:', layout.lines);
  console.log('Bubble positions:');
  layout.bubbles.forEach(b => {
    const dx = b.cx - layout.orb.cx, dy = b.cy - layout.orb.cy;
    const dist = Math.round(Math.sqrt(dx*dx + dy*dy));
    const angle = Math.round(Math.atan2(dy, dx) * 180 / Math.PI);
    console.log(`  ${b.id.padEnd(15)}  centre+(${dx},${dy})  dist=${dist}  angle=${angle}°`);
  });

  await page.screenshot({ path: path.join(OUT, 'radial-pixel7.png'), fullPage: false, animations: 'disabled', timeout: 10000 });
  console.log('\nScreenshot: pwa/test-results/phase3/radial-pixel7.png');
  await browser.close();
})();
