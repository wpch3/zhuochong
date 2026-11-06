export type Emotion =
  | 'neutral'
  | 'happy'
  | 'excited'
  | 'shy'
  | 'surprised'
  | 'sad'
  | 'sleepy'
  | 'angry'
  | 'love';

export type MouthShape = 'neutral' | 'smile' | 'cat' | 'open' | 'surprised';

export interface Expression {
  label: string;
  eyeOpen: number;
  mouth: MouthShape;
  mouthOpen: number;
  brow: number;
  blush: number;
  headTilt: number;
  headY: number;
}

export interface Pose {
  world: { x: number; y: number; rot: number; scaleX: number; scaleY: number };
  shadow: { scale: number; opacity: number };
  body: { x: number; y: number; rot: number };
  head: { x: number; y: number; rot: number };
  twinL1: number;
  twinL2: number;
  twinR1: number;
  twinR2: number;
  ahoge: number;
  earL: number;
  earR: number;
  armL: number;
  armR: number;
  tail1: number;
  tail2: number;
  legL: number;
  legR: number;
  eyeOpen: number;
  gazeX: number;
  gazeY: number;
  brow: number;
  blush: number;
  mouthShape: MouthShape;
  mouthOpen: number;
  star: { x: number; y: number; rot: number; scale: number };
  zzz: number;
  breath: number;
}

export interface EngineInput {
  pointer: { x: number; y: number } | null;
  emotion: Emotion;
  energy: number;
  sleeping: boolean;
  dragging: boolean;
  talking: boolean;
  reducedMotion: boolean;
  form: 'chibi' | 'teen';
}

export const EXPRESSIONS: Record<Emotion, Expression> = {
  neutral: { label: '平静', eyeOpen: 1, mouth: 'neutral', mouthOpen: 0, brow: 0, blush: 0.18, headTilt: 0, headY: 0 },
  happy: { label: '开心', eyeOpen: 0.92, mouth: 'smile', mouthOpen: 0, brow: 0.25, blush: 0.45, headTilt: 3, headY: -2 },
  excited: { label: '兴奋', eyeOpen: 1.08, mouth: 'open', mouthOpen: 0.5, brow: 0.45, blush: 0.5, headTilt: -3, headY: -4 },
  shy: { label: '害羞', eyeOpen: 0.72, mouth: 'cat', mouthOpen: 0, brow: -0.1, blush: 0.85, headTilt: 7, headY: 2 },
  surprised: { label: '惊讶', eyeOpen: 1.2, mouth: 'surprised', mouthOpen: 0.65, brow: 0.6, blush: 0.25, headTilt: -2, headY: -3 },
  sad: { label: '难过', eyeOpen: 0.62, mouth: 'neutral', mouthOpen: 0, brow: -0.55, blush: 0.12, headTilt: 2, headY: 4 },
  sleepy: { label: '困困', eyeOpen: 0.12, mouth: 'neutral', mouthOpen: 0, brow: -0.2, blush: 0.2, headTilt: 5, headY: 3 },
  angry: { label: '气鼓鼓', eyeOpen: 0.85, mouth: 'cat', mouthOpen: 0, brow: -0.7, blush: 0.35, headTilt: -4, headY: 1 },
  love: { label: '喜欢', eyeOpen: 0.8, mouth: 'smile', mouthOpen: 0, brow: 0.35, blush: 0.95, headTilt: 8, headY: -1 },
};

export const ACTION_EMOTION: Record<string, Emotion> = {
  headpat: 'happy',
  poke: 'surprised',
  wave: 'happy',
  feed: 'excited',
  scared: 'surprised',
  dance: 'excited',
  greet: 'happy',
  sleep: 'sleepy',
  wake: 'neutral',
};

export const ACTION_DURATION: Record<string, number> = {
  headpat: 1.6,
  poke: 1.2,
  wave: 2.4,
  feed: 2.2,
  scared: 1.4,
  dance: 3.2,
  greet: 2,
  sleep: 999,
  wake: 1,
};
