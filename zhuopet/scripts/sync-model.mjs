#!/usr/bin/env node
/** Copy the canonical model package from src/ into public/ so it can be downloaded at runtime. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const outDir = path.join(root, 'public/models/xiaoxun');
fs.mkdirSync(outDir, { recursive: true });
fs.copyFileSync(path.join(root, 'src/assets/character.svg'), path.join(outDir, 'character.svg'));
fs.copyFileSync(path.join(root, 'src/model/xiaoxun.model.json'), path.join(outDir, 'model.json'));
fs.copyFileSync(path.join(root, 'src/model/palettes.json'), path.join(outDir, 'palettes.json'));
console.log('synced model package to public/models/xiaoxun');
