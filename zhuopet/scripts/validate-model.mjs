#!/usr/bin/env node
/**
 * Validate the ZhuoPet model package without a browser.
 * Exits 1 with a readable report if anything is inconsistent.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const modelPath = path.join(root, 'src/model/xiaoxun.model.json');
const svgPath = path.join(root, 'src/assets/character.svg');
const palettePath = path.join(root, 'src/model/palettes.json');

const errors = [];
const warnings = [];
const ok = (condition, message) => {
  if (!condition) errors.push(message);
};

const model = JSON.parse(fs.readFileSync(modelPath, 'utf8'));
const svg = fs.readFileSync(svgPath, 'utf8');
const palettes = JSON.parse(fs.readFileSync(palettePath, 'utf8'));

ok(model.format === 'zhuopet-layer-rig', 'format must be zhuopet-layer-rig');
ok(model.canvas?.width === 600 && model.canvas?.height === 820, 'canvas must be 600x820');
ok(svg.includes('viewBox="0 0 600 820"'), 'SVG viewBox must be 0 0 600 820');

const partIds = new Set(Array.from(svg.matchAll(/data-part="([^"]+)"/g)).map((m) => m[1]));
for (const part of model.parts) {
  ok(partIds.has(part.id), `part "${part.id}" is declared but missing from the SVG`);
  ok(Array.isArray(part.pivot) && part.pivot.length === 2, `part "${part.id}" needs a [x,y] pivot`);
  if (Array.isArray(part.pivot)) {
    ok(part.pivot[0] >= 0 && part.pivot[0] <= model.canvas.width, `part "${part.id}" pivot x out of canvas`);
    ok(part.pivot[1] >= 0 && part.pivot[1] <= model.canvas.height, `part "${part.id}" pivot y out of canvas`);
  }
  ok(typeof part.z === 'number', `part "${part.id}" needs a numeric z`);
}
const ids = model.parts.map((p) => p.id);
ok(new Set(ids).size === ids.length, 'part ids must be unique');

for (const param of model.parameters) {
  ok(param.min < param.max, `parameter ${param.id} has min >= max`);
  ok(param.default >= param.min && param.default <= param.max, `parameter ${param.id} default out of range`);
}

const mouths = ['neutral', 'smile', 'cat', 'open', 'surprised'];
for (const [id, expression] of Object.entries(model.expressions)) {
  ok(mouths.includes(expression.mouth), `expression ${id} has invalid mouth "${expression.mouth}"`);
  ok(expression.eyeOpen >= 0 && expression.eyeOpen <= 1.3, `expression ${id} eyeOpen out of range`);
}

const styleGroups = new Set(Array.from(svg.matchAll(/data-hairstyle="([^"]+)"/g)).map((m) => m[1]));
for (const style of model.hairstyles) {
  for (const group of style.groups) {
    ok(styleGroups.has(group), `hairstyle ${style.id} references missing group "${group}"`);
  }
}

const usedVars = new Set(Array.from(svg.matchAll(/var\(--([a-z0-9-]+)\)/g)).map((m) => m[1]));
for (const [name, palette] of Object.entries(palettes)) {
  for (const key of usedVars) {
    ok(Boolean(palette[key]), `palette ${name} is missing --${key}`);
  }
}
for (const outfit of model.outfits) {
  for (const key of Object.keys(outfit.palette)) {
    ok(usedVars.has(key), `outfit ${outfit.id} overrides unknown variable --${key}`);
  }
}

ok(!svg.includes('NaN'), 'SVG contains NaN');
ok(!svg.includes('undefined'), 'SVG contains undefined');
ok(svg.includes('<defs>'), 'SVG is missing <defs>');
ok(svg.includes('data-eyeball="L"') && svg.includes('data-eyeball="R"'), 'SVG is missing eyeball groups');
ok(model.parts.length >= 25, 'model has too few parts');
ok(model.parameters.length >= 12, 'model has too few parameters');
ok(Object.keys(model.expressions).length >= 8, 'model has too few expressions');
ok(Object.keys(model.motions).length >= 8, 'model has too few motions');

// report
console.log(`ZhuoPet model: ${model.name} v${model.version} (${model.format} v${model.formatVersion})`);
console.log(`  canvas      ${model.canvas.width}x${model.canvas.height}`);
console.log(`  parts       ${model.parts.length}`);
console.log(`  parameters  ${model.parameters.length}`);
console.log(`  expressions ${Object.keys(model.expressions).length}`);
console.log(`  motions     ${Object.keys(model.motions).length}`);
console.log(`  hairstyles  ${model.hairstyles.map((h) => h.id).join(', ')}`);
console.log(`  outfits     ${model.outfits.map((o) => o.id).join(', ')}`);
console.log(`  palettes    ${Object.keys(palettes).join(', ')}`);
if (warnings.length) {
  console.log('\nWarnings:');
  for (const warning of warnings) console.log(`  - ${warning}`);
}
if (errors.length) {
  console.error('\nFAILED:');
  for (const error of errors) console.error(`  - ${error}`);
  process.exit(1);
}
console.log('\nModel package OK.');
