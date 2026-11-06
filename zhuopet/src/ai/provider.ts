export interface CloudConfig {
  enabled: boolean;
  baseUrl: string;
  apiKey: string;
  model: string;
}

export const DEFAULT_CLOUD: CloudConfig = {
  enabled: false,
  baseUrl: 'https://api.openai.com/v1',
  apiKey: '',
  model: 'gpt-4o-mini',
};

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

function endpoint(baseUrl: string) {
  const base = baseUrl.trim().replace(/\/+$/, '');
  if (!base) throw new Error('请先填写 API 地址');
  if (/\/chat\/completions$/.test(base)) return base;
  return `${base}/chat/completions`;
}

export async function* streamChat(
  messages: ChatMessage[],
  config: CloudConfig,
  signal?: AbortSignal,
): AsyncGenerator<string> {
  if (!config.apiKey.trim()) throw new Error('还没有填写 API Key');
  const res = await fetch(endpoint(config.baseUrl), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${config.apiKey.trim()}`,
    },
    body: JSON.stringify({
      model: config.model.trim() || 'gpt-4o-mini',
      messages,
      stream: true,
      temperature: 0.85,
      max_tokens: 220,
    }),
    signal,
  });

  if (!res.ok) {
    let detail = '';
    try {
      const data = await res.json();
      detail = data?.error?.message ?? data?.message ?? '';
    } catch {
      detail = await res.text().catch(() => '');
    }
    if (res.status === 401) throw new Error('API Key 无效或已过期（401）');
    if (res.status === 404) throw new Error('接口地址或模型名不对（404）');
    if (res.status === 429) throw new Error('请求太频繁或额度不足（429）');
    throw new Error(`云端接口返回 ${res.status}${detail ? `：${detail.slice(0, 120)}` : ''}`);
  }

  if (!res.body) throw new Error('云端没有返回内容');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data:')) continue;
      const payload = trimmed.slice(5).trim();
      if (payload === '[DONE]') return;
      try {
        const json = JSON.parse(payload);
        const delta = json.choices?.[0]?.delta?.content ?? json.choices?.[0]?.message?.content ?? '';
        if (delta) yield delta as string;
      } catch {
        // ignore malformed keep-alive chunks
      }
    }
  }
}

export async function testConnection(config: CloudConfig): Promise<{ ok: boolean; message: string }> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    const res = await fetch(endpoint(config.baseUrl), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.apiKey.trim()}`,
      },
      body: JSON.stringify({
        model: config.model.trim() || 'gpt-4o-mini',
        messages: [{ role: 'user', content: '只回复两个字：你好' }],
        max_tokens: 12,
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) {
      if (res.status === 401) return { ok: false, message: 'API Key 无效（401）' };
      if (res.status === 404) return { ok: false, message: '地址或模型名不对（404）' };
      return { ok: false, message: `接口返回 ${res.status}` };
    }
    const data = await res.json();
    const text = data?.choices?.[0]?.message?.content ?? '';
    return { ok: true, message: text ? `连接成功，模型回复：${String(text).slice(0, 30)}` : '连接成功' };
  } catch (err) {
    const message = err instanceof Error ? err.message : '连接失败';
    return { ok: false, message: message.includes('abort') ? '连接超时' : message };
  }
}
