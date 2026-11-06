import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { affectionLevel, affectionTitle, getCharacter, type CharacterId } from '../data/characters';
import { buildSystemPrompt, generateReply, proactiveLine, type Fact } from '../ai/brain';
import { DEFAULT_CLOUD, streamChat, type CloudConfig } from '../ai/provider';
import type { Emotion } from '../model/types';
import { sfx } from '../utils/sound';
import { estimateSpeechMs, speak, stopSpeaking } from '../utils/speech';

export type Form = 'chibi' | 'teen';
export type Hairstyle = 'twin' | 'long' | 'pony' | 'short';
export type Outfit = 'cream' | 'midnight' | 'sakura' | 'mint';
export type Accessory = 'star' | 'cat' | 'none';
export type Theme = 'twilight' | 'day' | 'sakura';
export type SettingsTab = 'appearance' | 'persona' | 'voice' | 'cloud' | 'advanced' | 'about';
export type EffectType = 'heart' | 'sparkle' | 'zzz' | 'sweat' | 'question' | 'note';
export type PetAction = 'headpat' | 'poke' | 'wave' | 'feed' | 'scared' | 'dance' | 'greet' | 'sleep' | 'wake';

export interface Message {
  id: string;
  role: 'user' | 'pet';
  text: string;
  at: number;
  emotion?: Emotion;
  source?: 'local' | 'cloud';
}

export interface Moment {
  id: string;
  text: string;
  at: number;
  kind: 'meet' | 'level' | 'promise' | 'note';
}

export interface Effect {
  id: string;
  type: EffectType;
  x: number;
  y: number;
  drift: number;
}

export interface Settings {
  voiceEnabled: boolean;
  voiceURI: string;
  voiceRate: number;
  voicePitch: number;
  volume: number;
  soundEnabled: boolean;
  reduceMotion: boolean;
  sleepAfterMin: number;
  proactive: boolean;
  cloud: CloudConfig;
  theme: Theme;
  showBuddy: boolean;
  showNameplate: boolean;
  nickname: string;
}

export interface Bubble {
  text: string;
  at: number;
  tone: 'normal' | 'happy' | 'shy' | 'sad';
}

interface PetState {
  characterId: CharacterId;
  form: Form;
  hairstyle: Hairstyle;
  outfit: Outfit;
  accessory: Accessory;
  scale: number;
  position: { x: number; y: number };
  emotion: Emotion;
  affection: number;
  energy: number;
  sleeping: boolean;
  talking: boolean;
  messages: Message[];
  facts: Fact[];
  moments: Moment[];
  userName: string;
  onboarded: boolean;
  lastInteractionAt: number;
  bubble: Bubble | null;
  effects: Effect[];
  isReplying: boolean;
  streamingText: string;
  cloudError: string | null;
  chatOpen: boolean;
  settingsOpen: boolean;
  settingsTab: SettingsTab;
  studioOpen: boolean;
  memoryOpen: boolean;
  dressupOpen: boolean;
  immersive: boolean;
  hidden: boolean;
  contextMenu: { x: number; y: number } | null;
  settings: Settings;
  toast: string | null;

  init: () => void;
  tick: () => void;
  interact: (action: PetAction) => void;
  sendMessage: (text: string) => Promise<void>;
  receiveProactive: () => void;
  setCharacter: (id: CharacterId) => void;
  setForm: (form: Form) => void;
  setHairstyle: (h: Hairstyle) => void;
  setOutfit: (o: Outfit) => void;
  setAccessory: (a: Accessory) => void;
  setScale: (s: number) => void;
  setPosition: (p: { x: number; y: number }) => void;
  setEmotion: (e: Emotion) => void;
  addEffect: (type: EffectType, x?: number, y?: number) => void;
  setBubble: (text: string, tone?: Bubble['tone']) => void;
  clearBubble: () => void;
  setTalking: (v: boolean) => void;
  setSleeping: (v: boolean) => void;
  toggleChat: (v?: boolean) => void;
  setSettingsOpen: (v: boolean, tab?: SettingsTab) => void;
  setStudioOpen: (v: boolean) => void;
  setMemoryOpen: (v: boolean) => void;
  setDressupOpen: (v: boolean) => void;
  setImmersive: (v: boolean) => void;
  setHidden: (v: boolean) => void;
  setContextMenu: (p: { x: number; y: number } | null) => void;
  updateSettings: (patch: Partial<Settings>) => void;
  updateCloud: (patch: Partial<CloudConfig>) => void;
  addFact: (text: string, kind?: Fact['kind']) => void;
  removeFact: (id: string) => void;
  clearFacts: () => void;
  addMoment: (text: string, kind?: Moment['kind']) => void;
  setUserName: (name: string) => void;
  completeOnboarding: (name: string) => void;
  setToast: (text: string | null) => void;
  resetAll: () => void;
  exportData: () => void;
  importData: (json: string) => boolean;
}

const uid = () => Math.random().toString(36).slice(2, 10);
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

const DEFAULT_SETTINGS: Settings = {
  voiceEnabled: true,
  voiceURI: '',
  voiceRate: 1,
  voicePitch: 1.25,
  volume: 1,
  soundEnabled: true,
  reduceMotion: false,
  sleepAfterMin: 5,
  proactive: true,
  cloud: { ...DEFAULT_CLOUD },
  theme: 'twilight',
  showBuddy: true,
  showNameplate: true,
  nickname: '',
};

let bubbleTimer: ReturnType<typeof setTimeout> | null = null;
let speechTimer: ReturnType<typeof setTimeout> | null = null;
let lastProactiveAt = 0;
let lastTickAt = Date.now();

const petListeners = new Set<(action: PetAction) => void>();
export const petBus = {
  on(fn: (action: PetAction) => void) {
    petListeners.add(fn);
    return () => petListeners.delete(fn);
  },
  emit(action: PetAction) {
    petListeners.forEach((fn) => fn(action));
  },
};

function mergeFacts(existing: Fact[], incoming: Fact[]): Fact[] {
  const map = new Map(existing.map((f) => [f.text, f]));
  for (const f of incoming) if (!map.has(f.text)) map.set(f.text, f);
  return Array.from(map.values()).slice(-80);
}

function pick<T>(list: T[]): T {
  return list[Math.floor(Math.random() * list.length)];
}

const interactionLines: Record<string, string[]> = {
  headpat: ['唔……再摸一下。', '哼，手法还行。', '喵……好舒服。', '只准摸三下哦。'],
  poke: ['呀！你干嘛。', '戳我干嘛啦。', '哼，不理你了。', '再戳我就要咬人了。'],
  wave: ['看这里！我挥得好看吗？', '嘿！我在这里！', '喵～你好呀。'],
  feed: ['呜哇！好吃！', '这个味道……我记住了！', '还有吗？就一口。'],
  scared: ['！……你吓死我了。', '呜哇！', '我、我才没有叫。'],
  dance: ['转圈圈～', '看我跳得好看吗！', '嘿嘿，开心！'],
  greet: ['你来啦。', '今天也辛苦啦。'],
  sleep: ['呼……我先睡一会儿。', '晚安……'],
  wake: ['唔……我醒了。', '你回来啦。'],
};

export const usePetStore = create<PetState>()(
  persist(
    (set, get) => ({
      characterId: 'xiaoxun',
      form: 'chibi',
      hairstyle: 'twin',
      outfit: 'cream',
      accessory: 'star',
      scale: 1,
      position: { x: 50, y: 54 },
      emotion: 'neutral',
      affection: 24,
      energy: 0.86,
      sleeping: false,
      talking: false,
      messages: [],
      facts: [],
      moments: [],
      userName: '',
      onboarded: false,
      lastInteractionAt: Date.now(),
      bubble: null,
      effects: [],
      isReplying: false,
      streamingText: '',
      cloudError: null,
      chatOpen: false,
      settingsOpen: false,
      settingsTab: 'appearance',
      studioOpen: false,
      memoryOpen: false,
      dressupOpen: false,
      immersive: false,
      hidden: false,
      contextMenu: null,
      settings: DEFAULT_SETTINGS,
      toast: null,

      init: () => {
        const s = get();
        set({ lastInteractionAt: Date.now() });
        if (s.onboarded && s.messages.length === 0) {
          const character = getCharacter(s.characterId);
          const greeting = character.greeting[0];
          set({
            messages: [{ id: uid(), role: 'pet', text: greeting, at: Date.now(), emotion: 'happy', source: 'local' }],
            bubble: { text: greeting, at: Date.now(), tone: 'happy' },
          });
        }
      },

      tick: () => {
        const now = Date.now();
        const dt = Math.min(5, (now - lastTickAt) / 1000);
        lastTickAt = now;
        const s = get();
        const idleMs = now - s.lastInteractionAt;
        const sleepAfter = Math.max(1, s.settings.sleepAfterMin) * 60_000;

        let energy = s.energy;
        if (s.sleeping) energy = clamp(energy + dt * 0.0025, 0, 1);
        else energy = clamp(energy - dt * 0.0009, 0, 1);

        if (!s.sleeping && idleMs > sleepAfter) {
          set({ sleeping: true, energy, emotion: 'sleepy', bubble: { text: '呼……我先睡一会儿。你忙完记得叫我。', at: now, tone: 'normal' } });
          petBus.emit('sleep');
          get().addEffect('zzz');
          return;
        }

        if (s.sleeping && idleMs < 1500) {
          set({ sleeping: false, emotion: 'neutral' });
          petBus.emit('wake');
        }

        if (!s.sleeping && s.settings.proactive && !s.isReplying && idleMs > 60_000 && now - lastProactiveAt > 150_000) {
          const line = proactiveLine(s.characterId, {
            idleMinutes: idleMs / 60_000,
            affection: s.affection,
            energy,
          });
          if (line) {
            lastProactiveAt = now;
            get().receiveProactive();
          }
        }

        if (!s.sleeping && idleMs > 45_000 && (s.emotion === 'excited' || s.emotion === 'love' || s.emotion === 'surprised')) {
          set({ emotion: 'neutral' });
        }

        set({ energy });
      },

      interact: (action) => {
        const s = get();
        const character = getCharacter(s.characterId);
        const wasSleeping = s.sleeping;
        const now = Date.now();
        const affectionDelta: Record<string, number> = {
          headpat: 2,
          poke: 0.4,
          wave: 1,
          feed: 2.2,
          scared: 0.3,
          dance: 1.4,
          greet: 1,
          sleep: 0,
          wake: 0.5,
        };
        const emotion: Record<string, Emotion> = {
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
        const prevLevel = affectionLevel(s.affection);
        const nextAffection = clamp(s.affection + (affectionDelta[action] ?? 0.5), 0, 100);
        const nextLevel = affectionLevel(nextAffection);
        const lines = interactionLines[action] ?? character.lines.happy;
        const text = pick(lines);

        set({
          sleeping: false,
          emotion: emotion[action] ?? 'happy',
          affection: nextAffection,
          energy: clamp(s.energy + 0.05, 0, 1),
          lastInteractionAt: now,
          bubble: { text, at: now, tone: action === 'poke' || action === 'scared' ? 'shy' : 'happy' },
        });
        petBus.emit(action);
        if (action === 'headpat' || action === 'feed') {
          for (let i = 0; i < 3; i++) get().addEffect(action === 'feed' ? 'sparkle' : 'heart', 50 + (Math.random() - 0.5) * 18, 30 + (Math.random() - 0.5) * 10);
          sfx.heart(s.settings.soundEnabled);
        } else if (action === 'poke' || action === 'scared') {
          get().addEffect('sweat', 62, 26);
          sfx.pop(s.settings.soundEnabled);
        } else if (action === 'dance') {
          for (let i = 0; i < 4; i++) get().addEffect('note', 50 + (Math.random() - 0.5) * 30, 34 + (Math.random() - 0.5) * 14);
          sfx.chime(s.settings.soundEnabled);
        } else {
          get().addEffect('sparkle', 58, 28);
          sfx.pop(s.settings.soundEnabled);
        }
        if (nextLevel > prevLevel) {
          get().addMoment(`我们的关系升到了「${affectionTitle(nextAffection)}」。`, 'level');
          get().setToast(`亲密度提升：${affectionTitle(nextAffection)}`);
          sfx.chime(s.settings.soundEnabled);
        }
        if (wasSleeping) {
          set({ bubble: { text: '唔……你回来啦。', at: now, tone: 'happy' } });
        }
        if (bubbleTimer) clearTimeout(bubbleTimer);
        bubbleTimer = setTimeout(() => {
          if (get().bubble && Date.now() - get().bubble!.at > 5000) set({ bubble: null });
        }, 6500);
      },

      sendMessage: async (raw) => {
        const text = raw.trim();
        if (!text) return;
        const s = get();
        if (s.isReplying) return;
        const character = getCharacter(s.characterId);
        const now = Date.now();
        const userMessage: Message = { id: uid(), role: 'user', text, at: now };
        set({
          messages: [...s.messages, userMessage].slice(-80),
          isReplying: true,
          streamingText: '',
          cloudError: null,
          lastInteractionAt: now,
          sleeping: false,
          chatOpen: true,
        });

        const local = generateReply(text, {
          characterId: s.characterId,
          userName: s.userName,
          affection: s.affection,
          facts: s.facts,
        });

        let reply = local.text;
        let source: 'local' | 'cloud' = 'local';
        let emotion = local.emotion;
        let delta = local.affectionDelta;
        let facts = local.facts;
        let name = local.name;
        let forget = local.forget;

        const cloud = s.settings.cloud;
        if (cloud.enabled && cloud.apiKey.trim()) {
          try {
            const system = buildSystemPrompt(s.characterId, { characterId: s.characterId, userName: s.userName, affection: s.affection, facts: s.facts }, emotion);
            const history = s.messages
              .slice(-12)
              .map((m) => ({ role: m.role === 'user' ? ('user' as const) : ('assistant' as const), content: m.text }));
            const stream = streamChat(
              [{ role: 'system', content: system }, ...history, { role: 'user', content: text }],
              cloud,
            );
            let full = '';
            for await (const chunk of stream) {
              full += chunk;
              set({ streamingText: full });
            }
            if (full.trim().length > 0) {
              reply = full.trim();
              source = 'cloud';
              delta = 1.2;
            } else {
              throw new Error('云端没有返回内容');
            }
          } catch (err) {
            const message = err instanceof Error ? err.message : '云端连接失败';
            set({ cloudError: message, toast: `云端不可用，已切回本地大脑：${message}` });
          }
        } else {
          await delay(420 + Math.random() * 520);
        }

        const petMessage: Message = {
          id: uid(),
          role: 'pet',
          text: reply,
          at: Date.now(),
          emotion,
          source,
        };

        const prevLevel = affectionLevel(get().affection);
        const nextAffection = clamp(get().affection + delta, 0, 100);
        const nextLevel = affectionLevel(nextAffection);
        const nextFacts = mergeFacts(get().facts, facts);
        const finalName = name ?? get().userName;

        set((state) => ({
          messages: [...state.messages, petMessage].slice(-80),
          isReplying: false,
          streamingText: '',
          emotion,
          affection: nextAffection,
          facts: nextFacts,
          userName: finalName,
          bubble: { text: reply, at: Date.now(), tone: emotion === 'sad' ? 'sad' : emotion === 'shy' || emotion === 'love' ? 'shy' : 'happy' },
          moments:
            nextLevel > prevLevel
              ? [...state.moments, { id: uid(), text: `我们的关系升到了「${affectionTitle(nextAffection)}」。`, at: Date.now(), kind: 'level' as const }].slice(-30)
              : state.moments,
        }));

        if (forget) {
          set((state) => ({ facts: state.facts.filter((f) => !f.text.includes(forget!) && !forget!.includes(f.text)) }));
        }

        if (nextLevel > prevLevel) {
          get().setToast(`亲密度提升：${affectionTitle(nextAffection)}`);
          sfx.chime(get().settings.soundEnabled);
        }

        if (bubbleTimer) clearTimeout(bubbleTimer);
        bubbleTimer = setTimeout(() => {
          if (get().bubble && Date.now() - get().bubble!.at > 5000) set({ bubble: null });
        }, 7000);

        const settings = get().settings;
        if (settings.voiceEnabled) {
          const pitch = character.voice.pitch * settings.voicePitch;
          const rate = character.voice.rate * settings.voiceRate;
          const started = speak(reply, {
            pitch,
            rate,
            volume: settings.volume,
            voiceURI: settings.voiceURI,
            onStart: () => set({ talking: true }),
            onEnd: () => set({ talking: false }),
          });
          if (started) {
            if (speechTimer) clearTimeout(speechTimer);
            speechTimer = setTimeout(() => set({ talking: false }), estimateSpeechMs(reply, rate) + 800);
          }
        }
      },

      receiveProactive: () => {
        const s = get();
        if (s.isReplying || s.sleeping) return;
        const line = proactiveLine(s.characterId, {
          idleMinutes: (Date.now() - s.lastInteractionAt) / 60_000,
          affection: s.affection,
          energy: s.energy,
        });
        if (!line) return;
        const message: Message = { id: uid(), role: 'pet', text: line, at: Date.now(), emotion: 'neutral', source: 'local' };
        set({
          messages: [...s.messages, message].slice(-80),
          bubble: { text: line, at: Date.now(), tone: 'normal' },
          emotion: 'neutral',
        });
        if (s.settings.voiceEnabled) {
          speak(line, {
            pitch: getCharacter(s.characterId).voice.pitch * s.settings.voicePitch,
            rate: getCharacter(s.characterId).voice.rate * s.settings.voiceRate,
            volume: s.settings.volume,
            voiceURI: s.settings.voiceURI,
            onStart: () => set({ talking: true }),
            onEnd: () => set({ talking: false }),
          });
        }
      },

      setCharacter: (id) => {
        const character = getCharacter(id);
        set({
          characterId: id,
          emotion: 'happy',
          bubble: { text: character.greeting[0], at: Date.now(), tone: 'happy' },
          messages: [
            ...get().messages,
            { id: uid(), role: 'pet' as const, text: `我是${character.name}。${character.tagline}。`, at: Date.now(), emotion: 'happy' as const, source: 'local' as const },
          ].slice(-80),
        });
        petBus.emit('greet');
        sfx.chime(get().settings.soundEnabled);
      },

      setForm: (form) => set({ form }),
      setHairstyle: (hairstyle) => set({ hairstyle }),
      setOutfit: (outfit) => set({ outfit }),
      setAccessory: (accessory) => set({ accessory }),
      setScale: (scale) => set({ scale: clamp(scale, 0.65, 1.35) }),
      setPosition: (position) =>
        set({ position: { x: clamp(position.x, 12, 88), y: clamp(position.y, 24, 82) } }),
      setEmotion: (emotion) => set({ emotion }),
      addEffect: (type, x = 50, y = 30) => {
        const effect: Effect = { id: uid(), type, x, y, drift: (Math.random() - 0.5) * 40 };
        set((s) => ({ effects: [...s.effects.slice(-14), effect] }));
        setTimeout(() => {
          set((s) => ({ effects: s.effects.filter((e) => e.id !== effect.id) }));
        }, 1800);
      },
      setBubble: (text, tone = 'normal') => set({ bubble: { text, at: Date.now(), tone } }),
      clearBubble: () => set({ bubble: null }),
      setTalking: (talking) => set({ talking }),
      setSleeping: (sleeping) => set({ sleeping, emotion: sleeping ? 'sleepy' : 'neutral' }),
      toggleChat: (v) => set((s) => ({ chatOpen: v ?? !s.chatOpen, memoryOpen: false })),
      setSettingsOpen: (settingsOpen, tab) => set({ settingsOpen, ...(tab ? { settingsTab: tab } : {}) }),
      setStudioOpen: (studioOpen) => set({ studioOpen }),
      setMemoryOpen: (memoryOpen) => set({ memoryOpen, chatOpen: memoryOpen ? true : get().chatOpen }),
      setDressupOpen: (dressupOpen) => set({ dressupOpen }),
      setImmersive: (immersive) => set({ immersive, chatOpen: false, settingsOpen: false, studioOpen: false, memoryOpen: false }),
      setHidden: (hidden) => set({ hidden }),
      setContextMenu: (contextMenu) => set({ contextMenu }),
      updateSettings: (patch) => set((s) => ({ settings: { ...s.settings, ...patch } })),
      updateCloud: (patch) =>
        set((s) => ({ settings: { ...s.settings, cloud: { ...s.settings.cloud, ...patch } } })),
      addFact: (text, kind = 'other') => {
        const clean = text.trim().slice(0, 60);
        if (!clean) return;
        set((s) => ({ facts: mergeFacts(s.facts, [{ id: uid(), kind, text: clean, createdAt: Date.now() }]) }));
      },
      removeFact: (id) => set((s) => ({ facts: s.facts.filter((f) => f.id !== id) })),
      clearFacts: () => set({ facts: [] }),
      addMoment: (text, kind = 'note') =>
        set((s) => ({ moments: [...s.moments, { id: uid(), text, at: Date.now(), kind }].slice(-30) })),
      setUserName: (userName) => set({ userName: userName.trim().slice(0, 20) }),
      completeOnboarding: (name) => {
        const character = getCharacter(get().characterId);
        const greeting = character.greeting[0];
        set((s) => ({
          onboarded: true,
          userName: name.trim().slice(0, 20),
          messages: [
            ...s.messages,
            { id: uid(), role: 'pet', text: greeting, at: Date.now(), emotion: 'happy', source: 'local' as const },
          ],
          bubble: { text: greeting, at: Date.now(), tone: 'happy' },
          moments: [{ id: uid(), text: `和${character.name}第一次见面。`, at: Date.now(), kind: 'meet' as const }],
        }));
        petBus.emit('greet');
      },
      setToast: (toast) => {
        set({ toast });
        if (toast) setTimeout(() => set((s) => (s.toast === toast ? { toast: null } : s)), 4200);
      },
      resetAll: () => {
        stopSpeaking();
        localStorage.removeItem('zhuopet-save-v1');
        window.location.reload();
      },
      exportData: () => {
        const s = get();
        const data = {
          app: 'ZhuoPet',
          version: 1,
          exportedAt: new Date().toISOString(),
          characterId: s.characterId,
          userName: s.userName,
          affection: s.affection,
          facts: s.facts,
          moments: s.moments,
          messages: s.messages,
          settings: { ...s.settings, cloud: { ...s.settings.cloud, apiKey: '' } },
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `zhuopet-backup-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
      importData: (json) => {
        try {
          const data = JSON.parse(json);
          set({
            characterId: data.characterId ?? get().characterId,
            userName: data.userName ?? get().userName,
            affection: typeof data.affection === 'number' ? data.affection : get().affection,
            facts: Array.isArray(data.facts) ? data.facts : get().facts,
            moments: Array.isArray(data.moments) ? data.moments : get().moments,
            messages: Array.isArray(data.messages) ? data.messages : get().messages,
            settings: data.settings ? { ...get().settings, ...data.settings, cloud: { ...get().settings.cloud, ...data.settings.cloud, apiKey: '' } } : get().settings,
          });
          get().setToast('数据导入成功');
          return true;
        } catch {
          get().setToast('导入失败：文件格式不对');
          return false;
        }
      },
    }),
    {
      name: 'zhuopet-save-v1',
      version: 1,
      partialize: (s) => ({
        characterId: s.characterId,
        form: s.form,
        hairstyle: s.hairstyle,
        outfit: s.outfit,
        accessory: s.accessory,
        scale: s.scale,
        position: s.position,
        affection: s.affection,
        energy: s.energy,
        messages: s.messages.slice(-60),
        facts: s.facts,
        moments: s.moments,
        userName: s.userName,
        onboarded: s.onboarded,
        settings: s.settings,
      }),
    },
  ),
);

export const useCharacter = () => getCharacter(usePetStore((s) => s.characterId));
