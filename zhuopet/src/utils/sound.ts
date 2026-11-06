let ctx: AudioContext | null = null;

function audio(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  if (!ctx) ctx = new Ctor();
  if (ctx.state === 'suspended') void ctx.resume();
  return ctx;
}

function tone(freq: number, duration: number, type: OscillatorType, gainValue: number, delay = 0) {
  const ac = audio();
  if (!ac) return;
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  const start = ac.currentTime + delay;
  osc.type = type;
  osc.frequency.setValueAtTime(freq, start);
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(gainValue, start + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  osc.connect(gain);
  gain.connect(ac.destination);
  osc.start(start);
  osc.stop(start + duration + 0.02);
}

export const sfx = {
  pop(enabled = true) {
    if (!enabled) return;
    tone(660, 0.09, 'sine', 0.05);
    tone(990, 0.07, 'sine', 0.03, 0.03);
  },
  heart(enabled = true) {
    if (!enabled) return;
    tone(523, 0.12, 'triangle', 0.045);
    tone(659, 0.12, 'triangle', 0.04, 0.07);
    tone(784, 0.16, 'triangle', 0.035, 0.14);
  },
  chime(enabled = true) {
    if (!enabled) return;
    tone(880, 0.18, 'sine', 0.04);
    tone(1174, 0.22, 'sine', 0.03, 0.08);
  },
  error(enabled = true) {
    if (!enabled) return;
    tone(220, 0.12, 'sine', 0.04);
    tone(180, 0.16, 'sine', 0.035, 0.08);
  },
  meow(enabled = true) {
    if (!enabled) return;
    tone(720, 0.1, 'sine', 0.04);
    tone(880, 0.12, 'sine', 0.035, 0.08);
    tone(620, 0.16, 'sine', 0.03, 0.17);
  },
};
