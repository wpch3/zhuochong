import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import zlib from 'node:zlib';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const libDir = '/tmp/al2023/lib';
if (!fs.existsSync(path.join(libDir, 'libnspr4.so'))) {
  const pkgBin = path.resolve(process.cwd(), 'node_modules/@sparticuz/chromium/bin/al2023.tar.br');
  fs.mkdirSync('/tmp/al2023', { recursive: true });
  fs.writeFileSync('/tmp/al2023.tar', zlib.brotliDecompressSync(fs.readFileSync(pkgBin)));
  execFileSync('tar', ['-xf', '/tmp/al2023.tar', '-C', '/tmp/al2023']);
}
const browser = await puppeteer.launch({
  executablePath: await chromium.executablePath(),
  args: [...chromium.args, '--no-sandbox', '--disable-setuid-sandbox'],
  headless: 'shell',
  env: { ...process.env, LD_LIBRARY_PATH: `${libDir}:${process.env.LD_LIBRARY_PATH ?? ''}` },
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto('http://localhost:5173/', { waitUntil: 'networkidle0' });
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: 'networkidle0' });
await new Promise((r) => setTimeout(r, 700));
await page.evaluate(() => {
  const input = document.querySelector('.onboarding input');
  if (input) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, '阿宁');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
  Array.from(document.querySelectorAll('.onboarding button')).find((b) => b.textContent.includes('开始和'))?.click();
});
await new Promise((r) => setTimeout(r, 1000));
// hide chrome for a clean pet shot
await page.addStyleTag({ content: '.topbar,.dock-wrap,.nameplate,.speech-bubble,.hint-bubble,.sleep-zzz{display:none!important}' });
const pet = await page.$('.pet-wrap');
await pet.screenshot({ path: 'docs/qa/visual_pet.png' });
await page.addStyleTag({ content: '.pet-svg{visibility:hidden!important}' });
await pet.screenshot({ path: 'docs/qa/visual_bg.png' });
const info = await page.evaluate(() => {
  const r = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) };
  };
  const svg = document.querySelector('.pet-svg svg');
  let bbox = null;
  try { const b = svg.getBBox(); bbox = { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) }; } catch {}
  return { pet: r('.pet-wrap'), star: r('[data-part="starBuddy"]'), svgBBox: bbox, errors: [] };
});
console.log(JSON.stringify({ ...info, errors }, null, 2));
await browser.close();
