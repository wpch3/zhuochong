import type { Pose } from './types';
import { clamp } from './engine';

type PartMap = Map<string, Element>;

const partCache = new WeakMap<SVGSVGElement, PartMap>();
const lastTransform = new WeakMap<Element, string>();

function parts(root: SVGSVGElement): PartMap {
  let map = partCache.get(root);
  if (!map) {
    map = new Map();
    root.querySelectorAll<SVGElement>('[data-part]').forEach((el) => {
      map!.set(el.getAttribute('data-part')!, el);
    });
    partCache.set(root, map);
  }
  return map;
}

function setTransform(root: SVGSVGElement, id: string, transform: string) {
  const el = parts(root).get(id);
  if (!el) return;
  if (lastTransform.get(el) === transform) return;
  lastTransform.set(el, transform);
  el.setAttribute('transform', transform);
}

function setOpacity(root: SVGSVGElement, selector: string, value: number) {
  const el = root.querySelector<SVGElement>(selector);
  if (el) el.setAttribute('opacity', value.toFixed(3));
}

const rot = (deg: number, cx: number, cy: number) => `rotate(${deg.toFixed(2)} ${cx} ${cy})`;

export interface FormScale {
  head: number;
  body: number;
  worldX: number;
  worldY: number;
}

export const FORM_SCALE: Record<'chibi' | 'teen', FormScale> = {
  chibi: { head: 1, body: 1, worldX: 1, worldY: 1 },
  teen: { head: 0.9, body: 1.04, worldX: 0.97, worldY: 1.05 },
};

export function applyPose(root: SVGSVGElement, pose: Pose, form: 'chibi' | 'teen' = 'chibi') {
  const f = FORM_SCALE[form];
  const headTransform =
    `translate(${pose.head.x.toFixed(2)} ${pose.head.y.toFixed(2)}) ` +
    rot(pose.head.rot, 300, 400) +
    ` translate(300 400) scale(${f.head}) translate(-300 -400)`;
  const bodyTransform =
    `translate(${pose.body.x.toFixed(2)} ${pose.body.y.toFixed(2)}) ` +
    rot(pose.body.rot, 300, 600) +
    ` translate(300 600) scale(1 ${f.body}) translate(-300 -600)`;

  setTransform(
    root,
    'world',
    `translate(300 780) scale(${f.worldX} ${f.worldY}) translate(-300 -780) ` +
      `translate(${pose.world.x.toFixed(2)} ${pose.world.y.toFixed(2)}) ` +
      rot(pose.world.rot, 300, 780) +
      ` translate(300 780) scale(${pose.world.scaleX.toFixed(4)} ${pose.world.scaleY.toFixed(4)}) translate(-300 -780)`,
  );
  setTransform(root, 'shadow', `translate(300 780) scale(${pose.shadow.scale.toFixed(3)}) translate(-300 -780)`);
  const shadow = parts(root).get('shadow');
  if (shadow) shadow.setAttribute('opacity', pose.shadow.opacity.toFixed(3));

  setTransform(root, 'bodyRig', bodyTransform);
  setTransform(root, 'headRig', headTransform);
  setTransform(root, 'hairBackRig', `${bodyTransform} ${headTransform}`);

  setTransform(root, 'twinL1', rot(pose.twinL1, 172, 218));
  setTransform(root, 'twinL2', rot(pose.twinL2, 96, 414));
  setTransform(root, 'twinR1', rot(pose.twinR1, 428, 218));
  setTransform(root, 'twinR2', rot(pose.twinR2, 504, 414));
  setTransform(root, 'ahoge', rot(pose.ahoge, 305, 100));
  setTransform(root, 'catEarL', rot(pose.earL, 212, 152));
  setTransform(root, 'catEarR', rot(pose.earR, 388, 152));
  setTransform(root, 'armL', rot(pose.armL, 215, 450));
  setTransform(root, 'armR', rot(pose.armR, 385, 450));
  setTransform(root, 'tail1', rot(pose.tail1, 366, 596));
  setTransform(root, 'tail2', rot(pose.tail2, 452, 506));
  setTransform(root, 'legL', rot(pose.legL, 270, 646));
  setTransform(root, 'legR', rot(pose.legR, 330, 646));

  const eye = clamp(pose.eyeOpen, 0, 1);
  setOpacity(root, '[data-part="eyeL"] [data-eye="open"]', eye);
  setOpacity(root, '[data-part="eyeL"] [data-eye="closed"]', 1 - eye);
  setOpacity(root, '[data-part="eyeR"] [data-eye="open"]', eye);
  setOpacity(root, '[data-part="eyeR"] [data-eye="closed"]', 1 - eye);
  const gaze = `translate(${(pose.gazeX * 4.5).toFixed(2)} ${(pose.gazeY * 3.6).toFixed(2)})`;
  const eyeballL = root.querySelector('[data-eyeball="L"]');
  const eyeballR = root.querySelector('[data-eyeball="R"]');
  if (eyeballL) eyeballL.setAttribute('transform', gaze);
  // the right eye lives in a mirrored group, so invert X to keep both eyes looking the same way
  if (eyeballR) eyeballR.setAttribute('transform', `translate(${(-pose.gazeX * 4.5).toFixed(2)} ${(pose.gazeY * 3.6).toFixed(2)})`);

  setTransform(root, 'browL', `translate(0 ${(-pose.brow * 4).toFixed(2)})`);
  setTransform(root, 'browR', `translate(0 ${(-pose.brow * 4).toFixed(2)})`);

  const open = pose.mouthOpen;
  setOpacity(root, '[data-mouth="open"]', open);
  const shapes = ['neutral', 'smile', 'cat', 'surprised'];
  for (const shape of shapes) {
    const active = pose.mouthShape === shape ? 1 : 0;
    setOpacity(root, `[data-mouth="${shape}"]`, active * (1 - open));
  }
  setOpacity(root, '[data-part="blush"]', 0.15 + pose.blush * 0.85);

  setTransform(
    root,
    'starBuddy',
    `translate(${pose.star.x.toFixed(2)} ${pose.star.y.toFixed(2)}) ` +
      rot(pose.star.rot, 470, 300) +
      ` translate(470 300) scale(${pose.star.scale.toFixed(3)}) translate(-470 -300)`,
  );
}

export interface CharacterStyle {
  palette: Record<string, string>;
  hairstyle: string;
  accessory: string;
  showBuddy: boolean;
  showCatTail?: boolean;
}

export function applyCharacterStyle(root: SVGSVGElement, style: CharacterStyle) {
  for (const [key, value] of Object.entries(style.palette)) {
    root.style.setProperty(`--${key}`, value);
  }
  root.querySelectorAll<SVGElement>('[data-hairstyle]').forEach((el) => {
    const groups = el.getAttribute('data-hairstyle')!.split(',');
    const active = groups.includes(style.hairstyle);
    el.style.display = active ? '' : 'none';
    if (el.getAttribute('data-hairstyle') === 'long' || el.getAttribute('data-hairstyle') === 'pony') {
      el.setAttribute('opacity', active ? '1' : '0');
    }
  });
  const catEars = style.accessory === 'cat';
  for (const id of ['catEarL', 'catEarR']) {
    const el = root.querySelector<SVGElement>(`[data-part="${id}"]`);
    if (el) el.style.display = catEars ? '' : 'none';
  }
  const star = style.accessory === 'star' || style.accessory === 'cat';
  const clip = root.querySelector<SVGElement>('[data-part="accessory"]');
  if (clip) clip.style.display = star ? '' : 'none';
  const buddy = root.querySelector<SVGElement>('[data-part="starBuddy"]');
  if (buddy) buddy.style.display = style.showBuddy ? '' : 'none';
  const tail = root.querySelector<SVGElement>('[data-part="tail1"]');
  if (tail) tail.style.display = style.showCatTail === false ? 'none' : '';
}

/** Serialize the live SVG with palette inlined, for PNG export / model packaging. */
export function serializeSvg(root: SVGSVGElement, palette: Record<string, string>): string {
  const clone = root.cloneNode(true) as SVGSVGElement;
  clone.querySelectorAll('*').forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      if (attr.value.includes('var(--')) {
        el.setAttribute(
          attr.name,
          attr.value.replace(/var\(--([a-z0-9-]+)\)/g, (_, key) => palette[key] ?? '#000'),
        );
      }
    }
  });
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  return new XMLSerializer().serializeToString(clone);
}

export function downloadBlob(content: BlobPart, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function exportPosePng(root: SVGSVGElement, palette: Record<string, string>, filename: string) {
  const svg = serializeSvg(root, palette);
  const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = 1200;
    canvas.height = 1640;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const png = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (png) downloadBlob(png, filename, 'image/png');
  } finally {
    URL.revokeObjectURL(url);
  }
}
