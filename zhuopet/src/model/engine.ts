import {
  ACTION_DURATION,
  ACTION_EMOTION,
  EXPRESSIONS,
  type Emotion,
  type EngineInput,
  type Expression,
  type MouthShape,
  type Pose,
} from './types';

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const rand = (a: number, b: number) => a + Math.random() * (b - a);

/** Damped spring, integrated with fixed sub-steps so it stays stable at any frame rate. */
export class Spring {
  value = 0;
  velocity = 0;
  target = 0;
  constructor(
    public stiffness = 60,
    public damping = 6,
    public max = 30,
  ) {}

  update(dt: number) {
    const steps = Math.max(1, Math.ceil(dt / 0.008));
    const h = dt / steps;
    for (let i = 0; i < steps; i++) {
      const accel = -this.stiffness * (this.value - this.target) - this.damping * this.velocity;
      this.velocity += accel * h;
      this.value += this.velocity * h;
    }
    this.value = clamp(this.value, -this.max, this.max);
  }

  impulse(v: number) {
    this.velocity += v;
  }

  snap(v: number) {
    this.value = v;
    this.target = v;
    this.velocity = 0;
  }
}

interface BlinkState {
  phase: 0 | 1 | 2 | 3;
  timer: number;
  nextAt: number;
  doubleAt: number;
}

export class PetEngine {
  t = 0;
  private twinL1 = new Spring(52, 5.2, 26);
  private twinL2 = new Spring(34, 4.2, 30);
  private twinR1 = new Spring(52, 5.2, 26);
  private twinR2 = new Spring(34, 4.2, 30);
  private ahoge = new Spring(70, 4.4, 32);
  private tail1 = new Spring(40, 4.6, 24);
  private tail2 = new Spring(30, 3.8, 28);
  private earL = new Spring(90, 8, 14);
  private earR = new Spring(90, 8, 14);
  private armL = new Spring(90, 9, 150);
  private armR = new Spring(90, 9, 150);
  private bounce = new Spring(120, 10, 1.6);
  private gazeX = new Spring(120, 14, 1);
  private gazeY = new Spring(120, 14, 1);
  private headX = new Spring(110, 13, 10);
  private headY = new Spring(110, 13, 10);
  private bodySway = new Spring(60, 7, 8);
  private expr: Expression = { ...EXPRESSIONS.neutral };
  private blink: BlinkState = { phase: 0, timer: 0, nextAt: 2.5, doubleAt: 0 };
  private action: { name: string; until: number } | null = null;
  private lastInput: EngineInput | null = null;
  private glance = { x: 0, y: 0, nextAt: 4, until: 0 };
  private sleepBlend = 0;

  setEmotion(_emotion: Emotion) {
    /* expression is driven by input each frame; kept for API symmetry */
  }

  trigger(name: string) {
    const duration = ACTION_DURATION[name] ?? 1.5;
    this.action = { name, until: this.t + duration };
    if (name === 'headpat' || name === 'feed' || name === 'dance') {
      this.bounce.impulse(1.4);
      this.ahoge.impulse(rand(-90, 90));
      this.twinL1.impulse(rand(-40, 40));
      this.twinR1.impulse(rand(-40, 40));
      this.tail1.impulse(rand(-30, 30));
    }
    if (name === 'poke' || name === 'scared') {
      this.bounce.impulse(2.2);
      this.ahoge.impulse(rand(-140, 140));
      this.twinL1.impulse(rand(-70, 70));
      this.twinR1.impulse(rand(-70, 70));
      this.earL.impulse(rand(-60, 60));
      this.earR.impulse(rand(-60, 60));
    }
    if (name === 'wave' || name === 'greet') {
      this.armR.impulse(-60);
    }
    if (name === 'dance') {
      this.armL.impulse(-50);
      this.armR.impulse(-50);
    }
  }

  get currentAction() {
    return this.action?.name ?? null;
  }

  update(dtRaw: number, input: EngineInput): Pose {
    const dt = clamp(dtRaw, 0.001, 0.05);
    this.t += dt;
    this.lastInput = input;
    const t = this.t;
    const reduced = input.reducedMotion;

    if (this.action && t > this.action.until) this.action = null;
    const actionName = this.action?.name ?? null;
    const actionEmotion = actionName ? ACTION_EMOTION[actionName] : null;
    const targetEmotion: Emotion = input.sleeping ? 'sleepy' : actionEmotion ?? input.emotion;
    const target = EXPRESSIONS[targetEmotion];

    // smooth expression blend
    const k = 1 - Math.exp(-dt * 7);
    this.expr = {
      label: target.label,
      eyeOpen: lerp(this.expr.eyeOpen, target.eyeOpen, k),
      mouth: target.mouth,
      mouthOpen: lerp(this.expr.mouthOpen, target.mouthOpen, k),
      brow: lerp(this.expr.brow, target.brow, k),
      blush: lerp(this.expr.blush, target.blush, k),
      headTilt: lerp(this.expr.headTilt, target.headTilt, k),
      headY: lerp(this.expr.headY, target.headY, k),
    };

    // ---- blink state machine ----
    let blinkMul = 1;
    if (input.sleeping) {
      blinkMul = 0.06;
    } else {
      const b = this.blink;
      if (b.phase === 0 && t >= b.nextAt) {
        b.phase = 1;
        b.timer = 0;
      }
      if (b.phase === 1) {
        b.timer += dt;
        blinkMul = 1 - clamp(b.timer / 0.07, 0, 1);
        if (b.timer >= 0.07) {
          b.phase = 2;
          b.timer = 0;
        }
      } else if (b.phase === 2) {
        blinkMul = 0;
        b.timer += dt;
        if (b.timer >= 0.05) {
          b.phase = 3;
          b.timer = 0;
        }
      } else if (b.phase === 3) {
        b.timer += dt;
        blinkMul = clamp(b.timer / 0.13, 0, 1);
        if (b.timer >= 0.13) {
          b.phase = 0;
          b.nextAt = t + rand(2.2, 5.5);
          if (Math.random() < 0.18) b.nextAt = t + 0.28;
        }
      }
    }

    // ---- gaze ----
    if (t > this.glance.nextAt) {
      this.glance.x = rand(-0.7, 0.7);
      this.glance.y = rand(-0.35, 0.35);
      this.glance.until = t + rand(0.8, 2.2);
      this.glance.nextAt = t + rand(3.5, 7);
    }
    const glanceActive = t < this.glance.until;
    let gx = input.pointer ? clamp(input.pointer.x, -1, 1) : glanceActive ? this.glance.x : Math.sin(t * 0.37) * 0.22;
    let gy = input.pointer ? clamp(input.pointer.y, -1, 1) : glanceActive ? this.glance.y : Math.cos(t * 0.29) * 0.12;
    if (actionName === 'shy' || targetEmotion === 'shy') gx = -0.55;
    if (input.sleeping) {
      gx = 0;
      gy = 0.3;
    }
    this.gazeX.target = gx;
    this.gazeY.target = gy;
    this.gazeX.update(dt);
    this.gazeY.update(dt);

    // ---- head + body ----
    const headRotTarget =
      this.gazeX.value * 7 + this.expr.headTilt + Math.sin(t * 0.53) * (reduced ? 0 : 0.9);
    this.headX.target = this.gazeX.value * 5;
    this.headY.target = this.gazeY.value * 3.2 + this.expr.headY + Math.sin(t * 1.6) * 0.6;
    this.headX.update(dt);
    this.headY.update(dt);
    this.bodySway.target = Math.sin(t * 0.72) * (reduced ? 0 : 0.9) + this.expr.headTilt * 0.18;
    this.bodySway.update(dt);

    const breath = reduced ? 0 : Math.sin(t * 1.55) * 0.5 + 0.5;
    const bounceTarget = actionName === 'dance' ? Math.abs(Math.sin(t * 7)) * 0.9 : 0;
    this.bounce.target = bounceTarget;
    this.bounce.update(dt);

    // ---- arms ----
    let armLTarget = 0;
    let armRTarget = 0;
    if (actionName === 'wave' || actionName === 'greet') {
      armRTarget = -122 + Math.sin(t * 11) * 16;
      armLTarget = -6;
    } else if (actionName === 'dance') {
      armLTarget = -62 + Math.sin(t * 7) * 18;
      armRTarget = -62 + Math.cos(t * 7) * 18;
    } else if (actionName === 'headpat') {
      armLTarget = -10;
      armRTarget = 10;
    } else if (actionName === 'feed') {
      armLTarget = -34;
      armRTarget = -34;
    } else if (actionName === 'scared') {
      armLTarget = -48;
      armRTarget = -48;
    } else if (input.sleeping) {
      armLTarget = 2;
      armRTarget = -2;
    }
    this.armL.target = armLTarget;
    this.armR.target = armRTarget;
    this.armL.update(dt);
    this.armR.update(dt);

    // ---- hair / tail / ears springs ----
    const sway = reduced ? 0 : Math.sin(t * 1.15);
    this.twinL1.target = -headRotTarget * 0.45 + sway * 2.4 + this.bodySway.value * 0.4;
    this.twinL2.target = this.twinL1.value * 0.55 + Math.sin(t * 1.5 + 1.2) * 3.4;
    this.twinR1.target = -headRotTarget * 0.45 - sway * 2.4 + this.bodySway.value * 0.4;
    this.twinR2.target = this.twinR1.value * 0.55 + Math.sin(t * 1.5 + 2.4) * 3.4;
    this.ahoge.target = Math.sin(t * 2.2) * 4.5 + headRotTarget * 0.9 + this.bounce.value * 6;
    this.tail1.target = Math.sin(t * 1.7) * 7 + this.bodySway.value * 0.8;
    this.tail2.target = this.tail1.value * 0.6 + Math.sin(t * 2.1 + 0.8) * 8;
    this.earL.target = headRotTarget * 0.25 + Math.sin(t * 1.9) * 1.6;
    this.earR.target = headRotTarget * 0.25 - Math.sin(t * 1.9) * 1.6;
    for (const s of [this.twinL1, this.twinL2, this.twinR1, this.twinR2, this.ahoge, this.tail1, this.tail2, this.earL, this.earR]) {
      s.update(dt);
    }

    // ---- legs ----
    const legSwing = input.dragging ? Math.sin(t * 9) * 13 : 0;

    // ---- mouth ----
    let mouthOpen = this.expr.mouthOpen;
    let mouthShape: MouthShape = this.expr.mouth;
    if (input.talking && !input.sleeping) {
      mouthShape = 'open';
      mouthOpen = 0.3 + Math.abs(Math.sin(t * 13.5)) * 0.55 + Math.abs(Math.sin(t * 7.1)) * 0.15;
    }
    if (input.sleeping) {
      mouthShape = 'neutral';
      mouthOpen = 0;
    }

    // ---- star buddy ----
    const happy = targetEmotion === 'happy' || targetEmotion === 'excited' || targetEmotion === 'love';
    const star = {
      x: Math.sin(t * 0.9) * 12 + (happy ? Math.sin(t * 3) * 3 : 0),
      y: Math.cos(t * 1.3) * 8 - 4 + (happy ? -4 : 0),
      rot: Math.sin(t * 0.7) * 9,
      scale: 1 + (happy ? 0.08 : 0) + Math.sin(t * 2.1) * 0.02,
    };

    this.sleepBlend = lerp(this.sleepBlend, input.sleeping ? 1 : 0, 1 - Math.exp(-dt * 3));

    return {
      world: {
        x: 0,
        y: this.bounce.value * 4,
        rot: this.bodySway.value * 0.35,
        scaleX: 1 + breath * 0.004,
        scaleY: 1 - breath * 0.006 + this.bounce.value * 0.01,
      },
      shadow: {
        scale: 1 - this.bounce.value * 0.06,
        opacity: 0.2 - this.bounce.value * 0.03,
      },
      body: { x: 0, y: 0, rot: this.bodySway.value },
      head: { x: this.headX.value, y: this.headY.value, rot: headRotTarget },
      twinL1: this.twinL1.value,
      twinL2: this.twinL2.value,
      twinR1: this.twinR1.value,
      twinR2: this.twinR2.value,
      ahoge: this.ahoge.value,
      earL: this.earL.value,
      earR: this.earR.value,
      armL: this.armL.value,
      armR: this.armR.value,
      tail1: this.tail1.value,
      tail2: this.tail2.value,
      legL: legSwing,
      legR: -legSwing,
      eyeOpen: clamp(blinkMul * this.expr.eyeOpen, 0, 1.25),
      gazeX: this.gazeX.value,
      gazeY: this.gazeY.value,
      brow: this.expr.brow,
      blush: this.expr.blush,
      mouthShape,
      mouthOpen: clamp(mouthOpen, 0, 1),
      star,
      zzz: this.sleepBlend,
      breath,
    };
  }
}

export const neutralPose = (): Pose => ({
  world: { x: 0, y: 0, rot: 0, scaleX: 1, scaleY: 1 },
  shadow: { scale: 1, opacity: 0.2 },
  body: { x: 0, y: 0, rot: 0 },
  head: { x: 0, y: 0, rot: 0 },
  twinL1: 0,
  twinL2: 0,
  twinR1: 0,
  twinR2: 0,
  ahoge: 0,
  earL: 0,
  earR: 0,
  armL: 0,
  armR: 0,
  tail1: 0,
  tail2: 0,
  legL: 0,
  legR: 0,
  eyeOpen: 1,
  gazeX: 0,
  gazeY: 0,
  brow: 0,
  blush: 0.18,
  mouthShape: 'neutral',
  mouthOpen: 0,
  star: { x: 0, y: 0, rot: 0, scale: 1 },
  zzz: 0,
  breath: 0.5,
});
