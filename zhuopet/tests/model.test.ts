import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const model = JSON.parse(fs.readFileSync(path.join(root, 'src/model/xiaoxun.model.json'), 'utf8'));
const svg = fs.readFileSync(path.join(root, 'src/assets/character.svg'), 'utf8');
const palettes = JSON.parse(fs.readFileSync(path.join(root, 'src/model/palettes.json'), 'utf8'));

const partIds = new Set(Array.from(svg.matchAll(/data-part="([^"]+)"/g)).map((m) => m[1]));
const usedVars = new Set(Array.from(svg.matchAll(/var\(--([a-z0-9-]+)\)/g)).map((m) => m[1]));

describe('model package integrity', () => {
  it('has a valid format and canvas', () => {
    expect(model.format).toBe('zhuopet-layer-rig');
    expect(model.canvas.width).toBe(600);
    expect(model.canvas.height).toBe(820);
    expect(svg).toContain('viewBox="0 0 600 820"');
  });

  it('declares every part that exists in the SVG', () => {
    for (const part of model.parts) {
      expect(partIds.has(part.id), `missing SVG part: ${part.id}`).toBe(true);
    }
  });

  it('has pivots inside the canvas', () => {
    for (const part of model.parts) {
      const [x, y] = part.pivot;
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(model.canvas.width);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(model.canvas.height);
    }
  });

  it('has unique part ids and z-order', () => {
    const ids = model.parts.map((p: { id: string }) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const part of model.parts) expect(typeof part.z).toBe('number');
  });

  it('has parameters with sane ranges', () => {
    for (const param of model.parameters) {
      expect(param.min).toBeLessThan(param.max);
      expect(param.default).toBeGreaterThanOrEqual(param.min);
      expect(param.default).toBeLessThanOrEqual(param.max);
    }
  });

  it('has valid expressions', () => {
    const mouths = ['neutral', 'smile', 'cat', 'open', 'surprised'];
    for (const [id, expression] of Object.entries(model.expressions) as [string, { mouth: string }][]) {
      expect(mouths.includes(expression.mouth), `bad mouth in ${id}`).toBe(true);
    }
  });

  it('has valid hairstyle groups', () => {
    const styles = new Set(Array.from(svg.matchAll(/data-hairstyle="([^"]+)"/g)).map((m) => m[1]));
    for (const style of model.hairstyles) {
      for (const group of style.groups) {
        expect(styles.has(group), `missing hairstyle group ${group}`).toBe(true);
      }
    }
  });

  it('covers every CSS variable used by the SVG in every palette', () => {
    for (const [name, palette] of Object.entries(palettes) as [string, Record<string, string>][]) {
      for (const key of usedVars) {
        expect(palette[key], `${name} is missing --${key}`).toBeTruthy();
      }
    }
  });

  it('has outfit palettes that only override known variables', () => {
    for (const outfit of model.outfits) {
      for (const key of Object.keys(outfit.palette)) {
        expect(usedVars.has(key), `outfit ${outfit.id} overrides unknown --${key}`).toBe(true);
      }
    }
  });

  it('has no broken values in the SVG', () => {
    expect(svg).not.toContain('NaN');
    expect(svg).not.toContain('undefined');
    expect(svg).toContain('<defs>');
    expect(svg).toContain('data-eyeball="L"');
    expect(svg).toContain('data-eyeball="R"');
  });

  it('has a non-trivial rig', () => {
    expect(model.parts.length).toBeGreaterThanOrEqual(25);
    expect(model.parameters.length).toBeGreaterThanOrEqual(12);
    expect(Object.keys(model.expressions).length).toBeGreaterThanOrEqual(8);
    expect(Object.keys(model.motions).length).toBeGreaterThanOrEqual(8);
  });
});
