let cachedVoices: SpeechSynthesisVoice[] = [];

export function speechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

export function refreshVoices(): SpeechSynthesisVoice[] {
  if (!speechSupported()) return [];
  cachedVoices = window.speechSynthesis.getVoices();
  return cachedVoices;
}

export function chineseVoices(): SpeechSynthesisVoice[] {
  const voices = cachedVoices.length ? cachedVoices : refreshVoices();
  return voices.filter((v) => /zh|cmn|chinese/i.test(v.lang) || /chinese|中文|普通话/i.test(v.name));
}

export function pickVoice(uri?: string): SpeechSynthesisVoice | undefined {
  const voices = chineseVoices();
  if (uri) {
    const found = voices.find((v) => v.voiceURI === uri);
    if (found) return found;
  }
  return (
    voices.find((v) => /Xiaoxiao|Yaoyao|Huihui|Tingting|Meijia|female|女/i.test(v.name)) ??
    voices[0]
  );
}

export interface SpeakOptions {
  pitch?: number;
  rate?: number;
  volume?: number;
  voiceURI?: string;
  onStart?: () => void;
  onEnd?: () => void;
}

export function speak(text: string, opts: SpeakOptions = {}): boolean {
  if (!speechSupported() || !text.trim()) return false;
  const synth = window.speechSynthesis;
  synth.cancel();
  const utter = new SpeechSynthesisUtterance(text.replace(/（[^）]*）/g, '').replace(/\*[^*]*\*/g, ''));
  const voice = pickVoice(opts.voiceURI);
  if (voice) utter.voice = voice;
  utter.lang = voice?.lang ?? 'zh-CN';
  utter.pitch = opts.pitch ?? 1.25;
  utter.rate = opts.rate ?? 1;
  utter.volume = opts.volume ?? 1;
  utter.onstart = () => opts.onStart?.();
  utter.onend = () => opts.onEnd?.();
  utter.onerror = () => opts.onEnd?.();
  synth.speak(utter);
  return true;
}

export function stopSpeaking() {
  if (speechSupported()) window.speechSynthesis.cancel();
}

export function estimateSpeechMs(text: string, rate = 1): number {
  const chars = text.replace(/\s/g, '').length;
  return Math.min(30000, Math.max(1200, (chars / 4.2) * 1000 / rate));
}
