#!/usr/bin/env node
/**
 * ZhuoPet model renderer / QA harness.
 * Renders the layered SVG character with a palette + pose overrides to PNG,
 * so the art can be inspected without a browser. Uses @resvg/resvg-js.
 *
 *   node scripts/render-model.mjs
 *   node scripts/render-model.mjs --state wave --out /tmp/wave.png
 */
import { Resvg } from '@resvg/resvg-js';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const svgPath = path.join(root, 'src/assets/character.svg');
const qaDir = path.join(root, 'docs/qa');
fs.mkdirSync(qaDir, { recursive: true });

export const PALETTES = {
  xiaoxun: {
    'hair-1': '#F1EDFB', 'hair-2': '#D6CDEF', 'hair-3': '#B7A6E2', 'hair-4': '#9A85CE',
    'hair-line': '#6B5A8E', 'hair-shine': '#FFFFFF',
    'skin-1': '#FFF1E7', 'skin-2': '#FFDCCB', 'skin-3': '#F3C3B2', 'skin-line': '#D79C8B',
    'eye-1': '#A8F0FA', 'eye-2': '#5AA6EE', 'eye-3': '#3B3F9E', 'eye-line': '#3A2C55',
    'hoodie-1': '#FFFDF7', 'hoodie-2': '#F4E5CF', 'hoodie-line': '#C7A98A',
    'sleeve-1': '#A6E7DC', 'sleeve-2': '#6FC9BD', 'sleeve-line': '#4E9E94',
    'skirt-1': '#4C5A7C', 'skirt-2': '#333D59', 'skirt-line': '#252D44',
    'sock-1': '#FFFDF8', 'sock-2': '#EFE6DA', 'sock-line': '#C9B8A6',
    'shoe-1': '#8ADBD0', 'shoe-2': '#5FBDB2', 'shoe-line': '#3F8F86',
    'accent-1': '#FFC2DA', 'accent-2': '#FF9EC4', 'accent-3': '#FFD98E', 'accent-line': '#D98BA8',
    'line': '#5B4A70', 'blush': '#FF9FBC',
  },
  yuejian: {
    'hair-1': '#E8ECFA', 'hair-2': '#B9C4E8', 'hair-3': '#8494C9', 'hair-4': '#6474AE',
    'hair-line': '#4A5680', 'hair-shine': '#FFFFFF',
    'skin-1': '#FFF3EC', 'skin-2': '#FFDCCB', 'skin-3': '#F3C3B2', 'skin-line': '#D79C8B',
    'eye-1': '#D8C8FF', 'eye-2': '#9A7BE8', 'eye-3': '#4B3A8F', 'eye-line': '#332A55',
    'hoodie-1': '#F7F5FF', 'hoodie-2': '#DDD8F2', 'hoodie-line': '#A9A0C9',
    'sleeve-1': '#C9C2F0', 'sleeve-2': '#9A8FD6', 'sleeve-line': '#6F63AE',
    'skirt-1': '#3E3A5C', 'skirt-2': '#2A2742', 'skirt-line': '#1E1B30',
    'sock-1': '#FFFDF8', 'sock-2': '#E8E2F2', 'sock-line': '#BDB2CE',
    'shoe-1': '#B9A8E8', 'shoe-2': '#8F7BC9', 'shoe-line': '#6A579E',
    'accent-1': '#D8CCFF', 'accent-2': '#B9A0FF', 'accent-3': '#FFE6A8', 'accent-line': '#9A7BD9',
    'line': '#4A3F66', 'blush': '#FFA8C8',
  },
  shuangxi: {
    'hair-1': '#FFE9D6', 'hair-2': '#FFC9A8', 'hair-3': '#F5A07E', 'hair-4': '#D97C5E',
    'hair-line': '#9A5540', 'hair-shine': '#FFFFFF',
    'skin-1': '#FFF1E7', 'skin-2': '#FFDCCB', 'skin-3': '#F3C3B2', 'skin-line': '#D79C8B',
    'eye-1': '#FFE9A8', 'eye-2': '#FFB45E', 'eye-3': '#C96A2E', 'eye-line': '#5A3A2E',
    'hoodie-1': '#FFF9F0', 'hoodie-2': '#FFE3CC', 'hoodie-line': '#D9A98A',
    'sleeve-1': '#FFD1B0', 'sleeve-2': '#F5A97E', 'sleeve-line': '#C97E55',
    'skirt-1': '#7A4A52', 'skirt-2': '#5A343C', 'skirt-line': '#42242B',
    'sock-1': '#FFFDF8', 'sock-2': '#F6E6DA', 'sock-line': '#D9B8A6',
    'shoe-1': '#FFC49E', 'shoe-2': '#F09A6E', 'shoe-line': '#C4734A',
    'accent-1': '#FFE0A8', 'accent-2': '#FFB86B', 'accent-3': '#FFE9A8', 'accent-line': '#D99A4E',
    'line': '#6B4A3E', 'blush': '#FF9F8E',
  },
  xiaochen: {
    'hair-1': '#E8FAF2', 'hair-2': '#BFEBD8', 'hair-3': '#8FD4BC', 'hair-4': '#6BB49C',
    'hair-line': '#3F7A68', 'hair-shine': '#FFFFFF',
    'skin-1': '#FFF1E7', 'skin-2': '#FFDCCB', 'skin-3': '#F3C3B2', 'skin-line': '#D79C8B',
    'eye-1': '#C8F5E8', 'eye-2': '#5EC9AE', 'eye-3': '#2E7A6A', 'eye-line': '#2E4A44',
    'hoodie-1': '#F8FFFC', 'hoodie-2': '#DDF2E9', 'hoodie-line': '#9CC9B8',
    'sleeve-1': '#B8EBDD', 'sleeve-2': '#7FCBB8', 'sleeve-line': '#4F9A88',
    'skirt-1': '#3E5A54', 'skirt-2': '#2A403B', 'skirt-line': '#1E2E2A',
    'sock-1': '#FFFDF8', 'sock-2': '#E6F2EC', 'sock-line': '#B8CEC4',
    'shoe-1': '#9EE0CE', 'shoe-2': '#6BBFA9', 'shoe-line': '#478F7C',
    'accent-1': '#C8F5E8', 'accent-2': '#8FE0C8', 'accent-3': '#FFE9A8', 'accent-line': '#5EA88F',
    'line': '#3E5A50', 'blush': '#FFA8C0',
  },
};

export function applyPalette(svg, palette) {
  return svg.replace(/var\(--([a-z0-9-]+)\)/g, (m, key) => palette[key] ?? m);
}

export function applyPose(svg, pose = {}) {
  let out = svg;
  if (pose.eyeOpen === 'closed' || pose.sleep) {
    out = out.replace('<g data-eye="open">', '<g data-eye="open" opacity="0">');
    out = out.replace('<g data-eye="closed" opacity="0">', '<g data-eye="closed" opacity="1">');
  }
  if (pose.mouth && pose.mouth !== 'neutral') {
    out = out.replace('<g data-mouth="neutral">', '<g data-mouth="neutral" opacity="0">');
    out = out.replace(`<g data-mouth="${pose.mouth}" opacity="0">`, `<g data-mouth="${pose.mouth}" opacity="1">`);
  }
  if (pose.armR) {
    out = out.replace('<g data-part="armR" transform="translate(0,0)">', `<g data-part="armR" transform="${pose.armR}">`);
  }
  if (pose.armL) {
    out = out.replace('<g data-part="armL" transform="translate(0,0)">', `<g data-part="armL" transform="${pose.armL}">`);
  }
  if (pose.head) {
    out = out.replace('<g data-part="headRig" transform="translate(0,0)">', `<g data-part="headRig" transform="${pose.head}">`);
    out = out.replace('<g data-part="hairBackRig">', `<g data-part="hairBackRig" transform="${pose.head}">`);
  }
  if (pose.twinL) {
    out = out.replace('<g data-part="twinL1" transform="translate(0,0)">', `<g data-part="twinL1" transform="${pose.twinL}">`);
    out = out.replace('<g data-part="twinR1" transform="translate(0,0)">', `<g data-part="twinR1" transform="${pose.twinR}">`);
  }
  if (pose.hide) {
    for (const part of pose.hide) {
      out = out.replace(new RegExp(`<g data-part="${part}"`, 'g'), `<g data-part="${part}" opacity="0"`);
    }
  }
  return out;
}

export function render(svg, width = 600) {
  const r = new Resvg(svg, { fitTo: { mode: 'width', value: width }, background: 'rgba(0,0,0,0)' });
  return r.render().asPng();
}

function montage(inputs, outPath) {
  if (inputs.length === 1) {
    execFileSync('convert', [inputs[0], outPath]);
    return;
  }
  execFileSync('convert', [...inputs, '-background', '#efe9f7', '+append', outPath]);
}

const args = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : fallback;
};

const baseSvg = fs.readFileSync(svgPath, 'utf8');
const state = arg('state', 'base');
const paletteName = arg('palette', 'xiaoxun');
const out = arg('out', path.join(qaDir, `model_${state}_${paletteName}.png`));
const poses = {
  base: {},
  blink: { eyeOpen: 'closed' },
  smile: { mouth: 'smile' },
  wave: { armR: 'rotate(-128 385 450)', mouth: 'smile' },
  sleep: { sleep: true, head: 'rotate(6 300 400)' },
  surprised: { mouth: 'surprised', armR: 'rotate(-40 385 450)', armL: 'rotate(40 215 450)' },
};
const svg = applyPose(applyPalette(baseSvg, PALETTES[paletteName]), poses[state] ?? {});
fs.writeFileSync(out, render(svg, 600));
console.log(`rendered ${out}`);

if (state === 'base' && paletteName === 'xiaoxun' && !arg('single', null)) {
  // contact sheet: expressions
  const states = ['base', 'blink', 'smile', 'wave', 'sleep', 'surprised'];
  const files = states.map((s) => {
    const p = path.join(qaDir, `_sheet_${s}.png`);
    fs.writeFileSync(p, render(applyPose(applyPalette(baseSvg, PALETTES.xiaoxun), poses[s]), 360));
    return p;
  });
  montage(files, path.join(qaDir, 'model_states.png'));
  for (const f of files) fs.unlinkSync(f);
  console.log(`rendered ${path.join(qaDir, 'model_states.png')}`);

  // palette sheet: four companions
  const names = ['xiaoxun', 'yuejian', 'shuangxi', 'xiaochen'];
  const pfiles = names.map((n) => {
    const p = path.join(qaDir, `_pal_${n}.png`);
    fs.writeFileSync(p, render(applyPalette(baseSvg, PALETTES[n]), 360));
    return p;
  });
  montage(pfiles, path.join(qaDir, 'model_palettes.png'));
  for (const f of pfiles) fs.unlinkSync(f);
  console.log(`rendered ${path.join(qaDir, 'model_palettes.png')}`);
}
