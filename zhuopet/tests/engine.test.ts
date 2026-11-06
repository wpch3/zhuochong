import { describe, expect, it } from 'vitest';
import { PetEngine, Spring, clamp } from '../src/model/engine';
import type { EngineInput } from '../src/model/types';

const input = (patch: Partial<EngineInput> = {}): EngineInput => ({
  pointer: null,
  emotion: 'neutral',
  energy: 1,
  sleeping: false,
  dragging: false,
  talking: false,
  reducedMotion: false,
  form: 'chibi',
  ...patch,
});

describe('Spring', () => {
  it('converges to its target without exploding', () => {
    const spring = new Spring(60, 6, 30);
    spring.target = 10;
    for (let i = 0; i < 600; i++) spring.update(1 / 60);
    expect(spring.value).toBeCloseTo(10, 1);
    expect(Math.abs(spring.velocity)).toBeLessThan(1);
  });

  it('is bounded by max', () => {
    const spring = new Spring(60, 6, 5);
    spring.impulse(1000);
    for (let i = 0; i < 120; i++) spring.update(1 / 60);
    expect(Math.abs(spring.value)).toBeLessThanOrEqual(5.0001);
  });
});

describe('PetEngine', () => {
  it('produces finite, bounded poses', () => {
    const engine = new PetEngine();
    for (let i = 0; i < 240; i++) {
      const pose = engine.update(1 / 60, input({ pointer: { x: 0.5, y: -0.3 } }));
      expect(Number.isFinite(pose.head.rot)).toBe(true);
      expect(Number.isFinite(pose.twinL1)).toBe(true);
      expect(pose.eyeOpen).toBeGreaterThanOrEqual(0);
      expect(pose.eyeOpen).toBeLessThanOrEqual(1.25);
      expect(pose.mouthOpen).toBeGreaterThanOrEqual(0);
      expect(pose.mouthOpen).toBeLessThanOrEqual(1);
      expect(Math.abs(pose.armR)).toBeLessThanOrEqual(150);
    }
  });

  it('blinks within a few seconds', () => {
    const engine = new PetEngine();
    let minEye = 1;
    for (let i = 0; i < 60 * 8; i++) {
      const pose = engine.update(1 / 60, input());
      minEye = Math.min(minEye, pose.eyeOpen);
    }
    expect(minEye).toBeLessThan(0.4);
  });

  it('closes its eyes while sleeping', () => {
    const engine = new PetEngine();
    for (let i = 0; i < 120; i++) engine.update(1 / 60, input({ sleeping: true }));
    const pose = engine.update(1 / 60, input({ sleeping: true }));
    expect(pose.eyeOpen).toBeLessThan(0.2);
    expect(pose.zzz).toBeGreaterThan(0.5);
  });

  it('waves with the right arm', () => {
    const engine = new PetEngine();
    engine.trigger('wave');
    for (let i = 0; i < 30; i++) engine.update(1 / 60, input());
    const pose = engine.update(1 / 60, input());
    expect(pose.armR).toBeLessThan(-40);
  });

  it('opens the mouth while talking', () => {
    const engine = new PetEngine();
    let maxMouth = 0;
    for (let i = 0; i < 60; i++) {
      const pose = engine.update(1 / 60, input({ talking: true }));
      maxMouth = Math.max(maxMouth, pose.mouthOpen);
    }
    expect(maxMouth).toBeGreaterThan(0.4);
  });

  it('dampens motion when reduced motion is on', () => {
    const still = new PetEngine();
    const reduced = new PetEngine();
    for (let i = 0; i < 120; i++) {
      still.update(1 / 60, input());
      reduced.update(1 / 60, input({ reducedMotion: true }));
    }
    const a = still.update(1 / 60, input());
    const b = reduced.update(1 / 60, input({ reducedMotion: true }));
    expect(Math.abs(b.twinL1)).toBeLessThan(Math.abs(a.twinL1) + 4);
  });
});

describe('clamp', () => {
  it('clamps both ends', () => {
    expect(clamp(5, 0, 1)).toBe(1);
    expect(clamp(-5, 0, 1)).toBe(0);
    expect(clamp(0.5, 0, 1)).toBe(0.5);
  });
});
