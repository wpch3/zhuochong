import { getCharacter, type CharacterDef, type CharacterId, type Intent } from '../data/characters';
import type { Emotion } from '../model/types';

export type FactKind = 'like' | 'dislike' | 'name' | 'identity' | 'other';

export interface Fact {
  id: string;
  kind: FactKind;
  text: string;
  createdAt: number;
}

export interface BrainState {
  characterId: CharacterId;
  userName: string;
  affection: number;
  facts: Fact[];
  time?: Date;
}

export interface BrainResult {
  text: string;
  emotion: Emotion;
  affectionDelta: number;
  facts: Fact[];
  intent: Intent;
  source: 'local';
  name?: string;
  forget?: string;
}

const now = () => Date.now();
const uid = () => Math.random().toString(36).slice(2, 10);

export function timeOfDay(date = new Date()): 'morning' | 'afternoon' | 'evening' | 'night' {
  const h = date.getHours();
  if (h < 5) return 'night';
  if (h < 11) return 'morning';
  if (h < 14) return 'afternoon';
  if (h < 18) return 'afternoon';
  if (h < 23) return 'evening';
  return 'night';
}

export const TIME_LABEL: Record<string, string> = {
  morning: '早上',
  afternoon: '下午',
  evening: '晚上',
  night: '深夜',
};

export function formatTime(date = new Date()) {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

const INTENT_PATTERNS: { intent: Intent; patterns: RegExp[] }[] = [
  { intent: 'insult', patterns: [/笨蛋|笨|蠢|丑|滚开|闭嘴|没用|废物|讨厌你|烦人|走开|白痴|傻/] },
  { intent: 'love', patterns: [/喜欢你|爱你|最喜欢你|心动|做我(女|男)朋友|抱抱|亲亲|贴贴|想抱/] },
  { intent: 'miss', patterns: [/想你|想我了吗|有没有想我|好久不见|想见你/] },
  { intent: 'sad', patterns: [/难过|伤心|想哭|哭了|不开心|失落|委屈|心累|崩溃|焦虑|压力|孤独|寂寞|失眠|难受|心痛|好累|疲惫|撑不住|emo/i] },
  { intent: 'angry', patterns: [/生气|气死|烦死|火大|过分|恶心|讨厌死了|气炸/] },
  { intent: 'happy', patterns: [/开心|高兴|好耶|哈哈|嘿嘿|幸福|满足|成功|升职|加薪|放假|好吃|太棒了|好爽|惊喜|喜欢死/] },
  { intent: 'thanks', patterns: [/谢谢|感谢|谢啦|多谢|thank/i] },
  { intent: 'praise', patterns: [/你真|你好棒|好厉害|可爱|聪明|优秀|温柔|可靠|厉害|漂亮|好看/] },
  { intent: 'food', patterns: [/吃|饿|饭|外卖|火锅|奶茶|蛋糕|零食|早餐|午餐|晚餐|夜宵|甜品/] },
  { intent: 'sleep', patterns: [/睡|困|晚安|熬夜|做梦|起床|打哈欠/] },
  { intent: 'game', patterns: [/游戏|打游戏|上号|开黑|steam|原神|王者|主机|电竞|抽卡|rank/i] },
  { intent: 'work', patterns: [/工作|上班|加班|写代码|代码|bug|项目|老板|同事|学习|考试|作业|论文|ddl|deadline|开会|需求/i] },
  { intent: 'weather', patterns: [/天气|下雨|晴天|下雪|冷|热|风|空气|温度|太阳/] },
  { intent: 'time', patterns: [/几点|时间|日期|今天几号|星期几|礼拜几/] },
  { intent: 'joke', patterns: [/笑话|搞笑|逗我|讲个故事|有趣|无聊/] },
  { intent: 'help', patterns: [/你能做什么|你会什么|帮我|功能|怎么用|帮助|能干嘛/] },
  { intent: 'whoAreYou', patterns: [/你是谁|你叫什么|介绍一下你|你的名字|你是什么|自我介绍/] },
  { intent: 'age', patterns: [/你多大|几岁|年龄|你的生日/] },
  { intent: 'hobby', patterns: [/你喜欢什么|你的爱好|平时做什么|兴趣|喜欢干嘛/] },
  { intent: 'greeting', patterns: [/^(你好|嗨|hi|hello|在吗|早上好|晚上好|早安|午安|哈喽|嗨嗨|哈喽呀)/i] },
  { intent: 'bye', patterns: [/再见|拜拜|走了|下次聊|先这样|回头聊/] },
  { intent: 'howAreYou', patterns: [/你好吗|你怎么样|最近怎么样|在干嘛|干嘛呢|做什么呢|过得好吗/] },
];

export function detectIntent(raw: string): Intent {
  const text = raw.toLowerCase().trim();
  if (!text) return 'default';
  for (const { intent, patterns } of INTENT_PATTERNS) {
    if (patterns.some((p) => p.test(text))) return intent;
  }
  return 'default';
}

const PRONOUNS = /^(你|您|您们|你们|它|他|她|这个|那个|这样|那样|我|自己)$/;

function cleanCapture(raw: string): string {
  return raw
    .replace(/^[\s，,。.!！?？、:：]+/, '')
    .replace(/[\s，,。.!！?？、:：]+$/, '')
    .replace(/^(是|叫|了|在)/, '')
    .trim()
    .slice(0, 40);
}

export function extractFacts(raw: string, existing: Fact[]): { facts: Fact[]; name?: string; forget?: string } {
  const text = raw.trim();
  const facts: Fact[] = [];
  let name: string | undefined;
  let forget: string | undefined;
  const push = (kind: FactKind, value: string) => {
    const clean = cleanCapture(value);
    if (!clean || clean.length < 1 || PRONOUNS.test(clean)) return;
    if (existing.some((f) => f.text === clean)) return;
    if (facts.some((f) => f.text === clean)) return;
    facts.push({ id: uid(), kind, text: clean, createdAt: now() });
  };

  const forgetMatch = text.match(/(?:忘掉|忘记|别记住)(.+)/);
  if (forgetMatch) {
    forget = cleanCapture(forgetMatch[1]);
    return { facts, forget };
  }

  const nameMatch = text.match(/(?:我叫|我的名字(?:是|叫)?|叫我)(.{1,20})/);
  if (nameMatch) {
    const value = cleanCapture(nameMatch[1]);
    if (value && !PRONOUNS.test(value)) {
      name = value;
      push('name', value);
    }
  }

  const rememberMatch = text.match(/(?:请记住|记住|记一下|帮我记)(.+)/);
  if (rememberMatch) {
    if (!nameMatch) push('other', rememberMatch[1]);
    return { facts, name, forget };
  }

  const likeMatch = text.match(/我(?:最|超|很|好|真的)?喜欢(.{1,30})/);
  if (likeMatch && !/^(你|您)/.test(cleanCapture(likeMatch[1]))) push('like', likeMatch[1]);

  const dislikeMatch = text.match(/我(?:最|超|很|好|真的)?(?:讨厌|不喜欢|受不了)(.{1,30})/);
  if (dislikeMatch && !PRONOUNS.test(cleanCapture(dislikeMatch[1]))) push('dislike', dislikeMatch[1]);

  const identityMatch = text.match(/我(?:是|在)(.{1,30}?)(?:工作|上班|上学|读书|住)/);
  if (identityMatch) push('identity', identityMatch[1]);

  const liveMatch = text.match(/我住在(.{1,30})/);
  if (liveMatch) push('other', `住在${cleanCapture(liveMatch[1])}`);

  const birthdayMatch = text.match(/我的生日(?:是)?(.{1,20})/);
  if (birthdayMatch) push('other', `生日是${cleanCapture(birthdayMatch[1])}`);

  return { facts, name, forget };
}

const POSITIVE = /开心|高兴|喜欢|爱|谢谢|棒|好耶|哈哈|嘿嘿|幸福|满足|成功|升职|放假|好吃|可爱|舒服|温暖|惊喜/;
const NEGATIVE = /难过|伤心|累|疲惫|哭|焦虑|压力|烦|生气|讨厌|糟糕|失败|崩溃|孤独|寂寞|失眠|痛|委屈/;
const INSULT = /笨蛋|蠢|丑|滚|闭嘴|没用|废物|白痴|傻|烦人/;

export function sentimentOf(text: string): { emotion: Emotion; delta: number } {
  if (INSULT.test(text)) return { emotion: 'angry', delta: -3 };
  if (/喜欢你|爱你|最喜欢你|抱抱|亲亲|贴贴/.test(text)) return { emotion: 'love', delta: 3 };
  if (NEGATIVE.test(text)) return { emotion: 'sad', delta: 1 };
  if (POSITIVE.test(text)) return { emotion: 'happy', delta: 2 };
  if (/谢谢|感谢/.test(text)) return { emotion: 'happy', delta: 1 };
  return { emotion: 'neutral', delta: 0.5 };
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

function pick<T>(list: T[], seed: number): T {
  return list[seed % list.length];
}

function fill(template: string, vars: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key) => vars[key] ?? '');
}

function topicOf(text: string): string {
  const cleaned = text
    .replace(/[？?！!。，,、~～]/g, '')
    .replace(/^(今天|刚刚|刚才|昨天|明天|最近|我觉得|感觉|其实|就是|然后|所以|但是|而且)/, '')
    .trim();
  return cleaned.length > 18 ? `${cleaned.slice(0, 18)}…` : cleaned || '这件事';
}

function withTic(character: CharacterDef, text: string, seed: number): string {
  if (seed % 100 < 26) return `${text}${character.tics[seed % character.tics.length]}`;
  return text;
}

export function generateReply(raw: string, state: BrainState): BrainResult {
  const character = getCharacter(state.characterId);
  const date = state.time ?? new Date();
  const text = raw.trim();
  const seed = hash(text + state.characterId + Math.floor(now() / 60000));
  const vars = {
    name: state.userName || '你',
    time: formatTime(date),
    topic: topicOf(text),
    character: character.name,
  };

  const extracted = extractFacts(text, state.facts);
  if (extracted.facts.length > 0) {
    const fact = extracted.facts[0];
    const kindText =
      fact.kind === 'like'
        ? `你喜欢${fact.text}`
        : fact.kind === 'dislike'
          ? `你讨厌${fact.text}`
          : fact.kind === 'name'
            ? `你叫${fact.text}`
            : fact.text;
    const confirmations = [
      `记住啦：${kindText}。我会好好收着的。`,
      `嗯，我记下来了——${kindText}。以后不许说我记性差。`,
      `${kindText}，对吧？已经写进我的小本本了。`,
    ];
    return {
      text: withTic(character, pick(confirmations, seed), seed),
      emotion: fact.kind === 'dislike' ? 'neutral' : 'happy',
      affectionDelta: 1.5,
      facts: extracted.facts,
      intent: 'default',
      source: 'local',
      name: extracted.name,
    };
  }

  if (extracted.forget) {
    return {
      text: `好，我把「${extracted.forget}」忘掉了。呼……脑袋轻了一点。`,
      emotion: 'neutral',
      affectionDelta: 0.5,
      facts: [],
      intent: 'default',
      source: 'local',
      forget: extracted.forget,
    };
  }

  const wantsRecall = /记得|还记得|记忆|我是谁|我的名字|我喜欢什么|我讨厌什么/.test(text);
  if (wantsRecall) {
    const nameFact = state.facts.find((f) => f.kind === 'name');
    const likes = state.facts.filter((f) => f.kind === 'like').map((f) => f.text);
    const dislikes = state.facts.filter((f) => f.kind === 'dislike').map((f) => f.text);
    const others = state.facts.filter((f) => f.kind === 'other' || f.kind === 'identity').map((f) => f.text);
    const bits: string[] = [];
    if (nameFact || state.userName) bits.push(`你叫${nameFact?.text ?? state.userName}`);
    if (likes.length) bits.push(`你喜欢${likes.slice(0, 3).join('、')}`);
    if (dislikes.length) bits.push(`你讨厌${dislikes.slice(0, 2).join('、')}`);
    if (others.length) bits.push(others.slice(0, 2).join('，'));
    if (bits.length === 0) {
      return {
        text: '你还没告诉过我什么呢。现在说也不迟，我会认真记的。',
        emotion: 'surprised',
        affectionDelta: 0.5,
        facts: [],
        intent: 'default',
        source: 'local',
      };
    }
    return {
      text: `当然记得。${bits.join('；')}。我都记着呢。`,
      emotion: 'happy',
      affectionDelta: 1,
      facts: [],
      intent: 'default',
      source: 'local',
    };
  }

  const intent = detectIntent(text);
  const sentiment = sentimentOf(text);
  let emotion: Emotion = sentiment.emotion;
  let delta = sentiment.delta;

  if (intent === 'insult') {
    emotion = 'angry';
    delta = -3;
  } else if (intent === 'love') {
    emotion = 'love';
    delta = 3;
  } else if (intent === 'sad') {
    emotion = 'sad';
    delta = 1;
  } else if (intent === 'happy') {
    emotion = 'happy';
    delta = 2;
  } else if (intent === 'thanks' || intent === 'praise') {
    emotion = 'happy';
    delta = 1.5;
  } else if (intent === 'angry') {
    emotion = 'angry';
    delta = 0.5;
  } else if (intent === 'sleep') {
    emotion = 'sleepy';
    delta = 0.5;
  } else if (intent === 'whoAreYou' || intent === 'age' || intent === 'hobby') {
    emotion = 'happy';
    delta = 0.5;
  } else if (intent === 'greeting' || intent === 'bye') {
    emotion = 'happy';
    delta = 1;
  } else if (intent === 'default') {
    emotion = sentiment.emotion === 'neutral' ? 'neutral' : sentiment.emotion;
  }

  const lines = character.lines[intent] ?? character.lines.default;
  let reply = fill(pick(lines, seed), vars);

  if (intent === 'default' && text.length <= 3 && /^(嗯|哦|好|行|可以|没事|不知道|随便|ok|OK)$/.test(text)) {
    reply = pick(
      [
        '嗯？我在听。慢慢说，不着急。',
        '怎么啦，突然这么安静。',
        '好。那你想做点什么？我陪你。',
        '嗯……我在这儿。',
      ],
      seed,
    );
  }

  if (intent === 'time') {
    const h = date.getHours();
    const extra = h >= 23 || h < 5 ? '这个点，真的该睡了。' : h < 11 ? '早上好呀，今天也要慢慢来。' : h < 18 ? '下午容易犯困，记得起来动一动。' : '晚上好，今天辛苦啦。';
    reply = `现在是 ${formatTime(date)}。${reply}${extra}`;
  }

  if (intent === 'default' && seed % 100 < 30) {
    reply = `${reply}${character.questions[seed % character.questions.length]}`;
  }

  reply = withTic(character, reply, seed);
  return { text: reply, emotion, affectionDelta: delta, facts: [], intent, source: 'local' };
}

export function proactiveLine(
  characterId: CharacterId,
  opts: { idleMinutes: number; affection: number; energy: number; time?: Date },
): string | null {
  const character = getCharacter(characterId);
  const date = opts.time ?? new Date();
  const tod = timeOfDay(date);
  if (opts.idleMinutes > 25) {
    return pick(
      [
        '你还在忙吗？……我有点想你了。',
        '桌面好安静。你什么时候回来呀？',
        '我把椅子擦干净了。你回来就能直接坐下。',
      ],
      Math.floor(opts.idleMinutes),
    );
  }
  if (opts.energy < 0.25) {
    return pick(['你看起来有点累。要不要摸摸我，充充电？', '先喝口水吧。我帮你看着时间。'], Math.floor(now() / 60000));
  }
  if (tod === 'night' && opts.idleMinutes > 8) {
    return pick(['夜深了。要不要先睡？我陪你。', '这个点还没睡呀……那我也不睡。'], Math.floor(now() / 60000));
  }
  if (tod === 'morning' && opts.idleMinutes > 12) {
    return pick(['早上好。今天想先做哪一件事？', '醒了吗？先喝口水，再开始今天。'], Math.floor(now() / 60000));
  }
  if (opts.idleMinutes > 6 && Math.random() < 0.5) {
    return character.questions[Math.floor(Math.random() * character.questions.length)];
  }
  return null;
}

export function buildSystemPrompt(characterId: CharacterId, state: BrainState, emotion: Emotion): string {
  const character = getCharacter(characterId);
  const date = state.time ?? new Date();
  const facts = state.facts.length
    ? state.facts.slice(0, 12).map((f) => `- ${f.text}（${f.kind}）`).join('\n')
    : '- 用户还没告诉你什么，保持好奇，自然地问问。';
  return `你是「${character.name}」，${character.title}。${character.persona}

你正在和${state.userName || '你的主人'}说话。你们的关系：${character.tagline}（亲密度 ${Math.round(state.affection)}/100）。
现在是${TIME_LABEL[timeOfDay(date)]}，${formatTime(date)}。你现在的情绪：${emotion}。

你记得关于主人的事：
${facts}

说话风格：${character.speech}
规则：
- 用中文，1~3 句，口语化，像真的在聊天。不要使用列表、Markdown 或 emoji 堆砌。
- 不要自称 AI、助手或模型；你是真实存在的桌宠。
- 自然地记得用户说过的话，但不要每句都复述记忆。
- 用户难过时先安慰，不要急着讲道理；用户开心时陪他一起开心。
- 不主动索要隐私，不讨论政治敏感话题，不生成露骨内容。
- 偶尔可以用括号写一个小动作，但不要每句都用。`;
}

export function makeFact(kind: FactKind, text: string): Fact {
  return { id: uid(), kind, text: text.trim().slice(0, 60), createdAt: now() };
}
