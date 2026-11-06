import { describe, expect, it } from 'vitest';
import {
  buildSystemPrompt,
  detectIntent,
  extractFacts,
  generateReply,
  proactiveLine,
  sentimentOf,
  timeOfDay,
} from '../src/ai/brain';
import type { BrainState, Fact } from '../src/ai/brain';

const baseState = (patch: Partial<BrainState> = {}): BrainState => ({
  characterId: 'xiaoxun',
  userName: '小明',
  affection: 30,
  facts: [],
  time: new Date('2026-11-06T21:30:00'),
  ...patch,
});

const fact = (kind: Fact['kind'], text: string): Fact => ({
  id: Math.random().toString(36),
  kind,
  text,
  createdAt: Date.now(),
});

describe('intent detection', () => {
  it('recognises common intents', () => {
    expect(detectIntent('你好呀')).toBe('greeting');
    expect(detectIntent('我今天好累')).toBe('sad');
    expect(detectIntent('我爱你')).toBe('love');
    expect(detectIntent('我想你了')).toBe('miss');
    expect(detectIntent('讲个笑话')).toBe('joke');
    expect(detectIntent('今天天气怎么样')).toBe('weather');
    expect(detectIntent('你能做什么')).toBe('help');
    expect(detectIntent('你是谁')).toBe('whoAreYou');
    expect(detectIntent('在写代码，有个 bug')).toBe('work');
    expect(detectIntent('晚上吃什么')).toBe('food');
  });

  it('does not treat "我喜欢你" as a like fact', () => {
    const { facts } = extractFacts('我喜欢你', []);
    expect(facts).toHaveLength(0);
  });
});

describe('memory extraction', () => {
  it('extracts a name', () => {
    const result = extractFacts('我叫小明', []);
    expect(result.name).toBe('小明');
    expect(result.facts[0].kind).toBe('name');
  });

  it('extracts likes and dislikes', () => {
    const likes = extractFacts('我最喜欢草莓牛奶', []);
    expect(likes.facts[0].kind).toBe('like');
    expect(likes.facts[0].text).toBe('草莓牛奶');

    const dislikes = extractFacts('我讨厌香菜', []);
    expect(dislikes.facts[0].kind).toBe('dislike');
    expect(dislikes.facts[0].text).toBe('香菜');
  });

  it('extracts a "记住" fact', () => {
    const result = extractFacts('记住，我的猫叫年糕', []);
    expect(result.facts[0].text).toContain('年糕');
  });

  it('deduplicates against existing facts', () => {
    const existing = [fact('like', '草莓牛奶')];
    const result = extractFacts('我喜欢草莓牛奶', existing);
    expect(result.facts).toHaveLength(0);
  });

  it('detects forgetting', () => {
    const result = extractFacts('忘掉我喜欢草莓牛奶', []);
    expect(result.forget).toContain('草莓牛奶');
  });
});

describe('generateReply', () => {
  it('confirms a new fact and returns it', () => {
    const result = generateReply('记住，我喜欢草莓牛奶', baseState());
    expect(result.facts).toHaveLength(1);
    expect(result.text).toContain('草莓牛奶');
    expect(result.affectionDelta).toBeGreaterThan(0);
  });

  it('returns the extracted name', () => {
    const result = generateReply('我叫阿寻', baseState());
    expect(result.name).toBe('阿寻');
  });

  it('recalls stored facts', () => {
    const state = baseState({ facts: [fact('name', '小明'), fact('like', '草莓牛奶')] });
    const result = generateReply('你还记得我吗', state);
    expect(result.text).toContain('小明');
    expect(result.text).toContain('草莓牛奶');
  });

  it('says it knows nothing when recall is empty', () => {
    const result = generateReply('你还记得什么', baseState({ userName: '' }));
    expect(result.text).toContain('还没告诉过我');
  });

  it('comforts when the user is sad', () => {
    const result = generateReply('今天工作好累，我有点撑不住', baseState());
    expect(result.emotion).toBe('sad');
    expect(result.text.length).toBeGreaterThan(4);
  });

  it('is a little hurt by insults', () => {
    const result = generateReply('你真笨', baseState());
    expect(result.emotion).toBe('angry');
    expect(result.affectionDelta).toBeLessThan(0);
  });

  it('answers identity questions in character', () => {
    const result = generateReply('你是谁', baseState());
    expect(result.intent).toBe('whoAreYou');
    expect(result.text.length).toBeGreaterThan(4);
  });

  it('gives a time-aware answer', () => {
    const result = generateReply('现在几点', baseState());
    expect(result.text).toContain('21:30');
  });

  it('handles very short input gracefully', () => {
    const result = generateReply('嗯', baseState());
    expect(result.text.length).toBeGreaterThan(2);
  });

  it('fills the user name into templates', () => {
    const result = generateReply('谢谢你', baseState({ userName: '阿宁' }));
    expect(result.text).not.toContain('{name}');
  });
});

describe('sentiment and time', () => {
  it('detects positive and negative sentiment', () => {
    expect(sentimentOf('今天好开心').emotion).toBe('happy');
    expect(sentimentOf('我很难过').emotion).toBe('sad');
    expect(sentimentOf('我爱你').emotion).toBe('love');
    expect(sentimentOf('今天天气不错').emotion).toBe('neutral');
  });

  it('maps time of day', () => {
    expect(timeOfDay(new Date('2026-11-06T03:00:00'))).toBe('night');
    expect(timeOfDay(new Date('2026-11-06T09:00:00'))).toBe('morning');
    expect(timeOfDay(new Date('2026-11-06T15:00:00'))).toBe('afternoon');
    expect(timeOfDay(new Date('2026-11-06T21:00:00'))).toBe('evening');
  });
});

describe('proactive lines and prompt', () => {
  it('returns a line when idle for a long time', () => {
    const line = proactiveLine('xiaoxun', { idleMinutes: 30, affection: 40, energy: 0.8 });
    expect(typeof line).toBe('string');
    expect(line!.length).toBeGreaterThan(2);
  });

  it('returns null when the user is active', () => {
    const line = proactiveLine('xiaoxun', { idleMinutes: 0.1, affection: 40, energy: 0.9 });
    expect(line).toBeNull();
  });

  it('builds a system prompt with persona and facts', () => {
    const prompt = buildSystemPrompt('xiaoxun', baseState({ facts: [fact('like', '草莓牛奶')] }), 'happy');
    expect(prompt).toContain('小寻');
    expect(prompt).toContain('草莓牛奶');
    expect(prompt).toContain('小明');
    expect(prompt).toContain('21:30');
  });
});
