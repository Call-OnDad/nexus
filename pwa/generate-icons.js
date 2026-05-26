// Run once to generate PNG icons for the PWA manifest and Capacitor
// Usage: node generate-icons.js
// Requires: npm install sharp

const sharp = require('sharp');
const path  = require('path');

const svg = Buffer.from(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="112" fill="#07070F"/>
  <circle cx="256" cy="256" r="200" fill="none" stroke="#00d4ff" stroke-width="8" opacity="0.3"/>
  <circle cx="256" cy="256" r="160" fill="#0d1f3c" opacity="0.8"/>
  <text
    x="256" y="300"
    text-anchor="middle"
    font-family="sans-serif"
    font-size="160"
    font-weight="200"
    fill="#00d4ff"
    letter-spacing="8"
  >N</text>
</svg>`);

async function generate() {
  await sharp(svg).resize(192, 192).png().toFile(path.join(__dirname, 'icons', 'icon-192.png'));
  console.log('icon-192.png created');
  await sharp(svg).resize(512, 512).png().toFile(path.join(__dirname, 'icons', 'icon-512.png'));
  console.log('icon-512.png created');
}

generate().catch(console.error);
