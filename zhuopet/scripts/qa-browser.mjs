#!/usr/bin/env node
/**
 * Headless layout + render QA. Uses a Chromium binary bundled in npm so it works
 * in restricted sandboxes. Requires the dev server on :5173.
 */
import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const outDir = path.join(root, 'docs/qa');
fs.mkdirSync(outDir, { recursive: true });
const URL = process.env.QA_URL || 'http://localhost:5173/';

const executablePath = await chromium.executablePath();
// @sparticuz/chromium ships its shared libraries separately; unpack them for glibc systems.
const libDir = '/tmp/al2023/lib';
if (!fs.existsSync(path.join(libDir, 'libnspr4.so'))) {
  const pkgBin = path.resolve(process.cwd(), 'node_modules/@sparticuz/chromium/bin/al2023.tar.br');
  if (fs.existsSync(pkgBin)) {
    fs.mkdirSync('/tmp/al2023', { recursive: true });
    fs.writeFileSync('/tmp/al2023.tar', zlib.brotliDecompressSync(fs.readFileSync(pkgBin)));
    require('node:child_process').execFileSync('tar', ['-xf', '/tmp/al2023.tar', '-C', '/tmp/al2023']);
  }
}
const browser = await puppeteer.launch({
  executablePath,
  args: [...chromium.args, '--no-sandbox', '--disable-setuid-sandbox', '--font-render-hinting=none'],
  headless: 'shell',
  env: { ...process.env, LD_LIBRARY_PATH: `${libDir}:${process.env.LD_LIBRARY_PATH ?? ''}` },
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 1 },
});

const errors = [];
const page = await browser.newPage();
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(`console: ${msg.text()}`);
});
page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));

await page.goto(URL, { waitUntil: 'networkidle0', timeout: 60000 });
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: 'networkidle0' });
await new Promise((r) => setTimeout(r, 1200));

const report = {};

report.onboardingVisible = await page.evaluate(() => !!document.querySelector('.onboarding'));
await page.screenshot({ path: path.join(outDir, 'qa_onboarding.png') });

// complete onboarding
await page.evaluate(() => {
  const input = document.querySelector('.onboarding input');
  if (input) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, '阿宁');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
});
await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll('.onboarding button'));
  const start = buttons.find((b) => b.textContent.includes('开始和'));
  start?.click();
});
await new Promise((r) => setTimeout(r, 900));
report.onboardingClosed = await page.evaluate(() => !document.querySelector('.onboarding'));

report.desktop = await page.evaluate(() => {
  const pet = document.querySelector('.pet-wrap');
  const svg = document.querySelector('.pet-svg svg');
  const topbar = document.querySelector('.topbar');
  const dock = document.querySelector('.dock');
  const rect = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  };
  return {
    pet: rect(pet),
    svg: rect(svg),
    topbar: rect(topbar),
    dock: rect(dock),
    parts: svg ? svg.querySelectorAll('[data-part]').length : 0,
    bodyScrollWidth: document.body.scrollWidth,
    innerWidth: window.innerWidth,
    bodyScrollHeight: document.body.scrollHeight,
    innerHeight: window.innerHeight,
    svgBBox: (() => {
      try {
        const b = svg.getBBox();
        return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) };
      } catch {
        return null;
      }
    })(),
    starBuddy: (() => {
      const el = document.querySelector('[data-part="starBuddy"]');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    })(),
    background: getComputedStyle(document.querySelector('.wallpaper')).backgroundImage.slice(0, 80),
  };
});
await page.screenshot({ path: path.join(outDir, 'qa_desktop.png') });
const petEl = await page.$('.pet-wrap');
if (petEl) await petEl.screenshot({ path: path.join(outDir, 'qa_pet.png') });

// chat
await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll('.dock button'));
  buttons.find((b) => b.textContent.includes('说话'))?.click();
});
await new Promise((r) => setTimeout(r, 500));
report.chatOpen = await page.evaluate(() => !!document.querySelector('.chat-panel'));
report.chatRect = await page.evaluate(() => {
  const el = document.querySelector('.chat-panel');
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
});
await page.screenshot({ path: path.join(outDir, 'qa_chat.png') });

// send a message
await page.evaluate(() => {
  const textarea = document.querySelector('.chat-input');
  if (textarea) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(textarea, '你好呀，今天过得怎么样？');
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }
});
await new Promise((r) => setTimeout(r, 200));
await page.evaluate(() => document.querySelector('.send-btn')?.click());
await new Promise((r) => setTimeout(r, 2200));
report.messages = await page.evaluate(() => document.querySelectorAll('.msg').length);
report.petMessages = await page.evaluate(() => document.querySelectorAll('.msg.pet').length);
await page.screenshot({ path: path.join(outDir, 'qa_chat_reply.png') });

// dressup
await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll('.dock button'));
  buttons.find((b) => b.textContent.includes('换装'))?.click();
});
await new Promise((r) => setTimeout(r, 400));
report.dressupOpen = await page.evaluate(() => !!document.querySelector('.dressup'));
await page.screenshot({ path: path.join(outDir, 'qa_dressup.png') });

// settings
await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll('.topbar button'));
  buttons.find((b) => b.title === '设置')?.click();
});
await new Promise((r) => setTimeout(r, 400));
report.settingsOpen = await page.evaluate(() => !!document.querySelector('.modal'));
report.settingsRect = await page.evaluate(() => {
  const el = document.querySelector('.modal');
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
});
await page.screenshot({ path: path.join(outDir, 'qa_settings.png') });
await page.keyboard.press('Escape');
await new Promise((r) => setTimeout(r, 300));

// studio
await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll('.topbar button'));
  buttons.find((b) => b.title === '模型工坊')?.click();
});
await new Promise((r) => setTimeout(r, 600));
report.studioOpen = await page.evaluate(() => !!document.querySelector('.studio'));
report.studioSvg = await page.evaluate(() => {
  const svg = document.querySelector('.studio-svg svg');
  if (!svg) return null;
  const r = svg.getBoundingClientRect();
  return { w: Math.round(r.width), h: Math.round(r.height) };
});
await page.screenshot({ path: path.join(outDir, 'qa_studio.png') });
await page.keyboard.press('Escape');

// mobile layout
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
await new Promise((r) => setTimeout(r, 500));
report.mobile = await page.evaluate(() => {
  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  };
  return {
    pet: rect('.pet-wrap'),
    topbar: rect('.topbar'),
    dock: rect('.dock'),
    scrollWidth: document.body.scrollWidth,
    innerWidth: window.innerWidth,
  };
});
await page.screenshot({ path: path.join(outDir, 'qa_mobile.png') });

report.errors = errors;
console.log(JSON.stringify(report, null, 2));
await browser.close();
