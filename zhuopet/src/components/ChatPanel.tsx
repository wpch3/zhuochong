import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Brain, Mic, Plus, Settings, Sparkles, Trash2, X } from 'lucide-react';
import { usePetStore } from '../store/usePetStore';
import { affectionTitle, getCharacter } from '../data/characters';
import { EXPRESSIONS } from '../model/types';
import type { Fact } from '../ai/brain';

const FACT_LABEL: Record<Fact['kind'], string> = {
  like: '喜欢',
  dislike: '讨厌',
  name: '名字',
  identity: '身份',
  other: '其他',
};

const QUICK_CHIPS = ['今天好累', '讲个笑话', '你喜欢什么？', '摸摸头'];

function timeLabel(at: number) {
  return new Date(at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export function ChatPanel() {
  const character = getCharacter(usePetStore((s) => s.characterId));
  const messages = usePetStore((s) => s.messages);
  const isReplying = usePetStore((s) => s.isReplying);
  const streamingText = usePetStore((s) => s.streamingText);
  const emotion = usePetStore((s) => s.emotion);
  const affection = usePetStore((s) => s.affection);
  const userName = usePetStore((s) => s.userName);
  const facts = usePetStore((s) => s.facts);
  const moments = usePetStore((s) => s.moments);
  const memoryOpen = usePetStore((s) => s.memoryOpen);
  const cloud = usePetStore((s) => s.settings.cloud);
  const voiceEnabled = usePetStore((s) => s.settings.voiceEnabled);
  const sendMessage = usePetStore((s) => s.sendMessage);
  const toggleChat = usePetStore((s) => s.toggleChat);
  const setMemoryOpen = usePetStore((s) => s.setMemoryOpen);
  const setSettingsOpen = usePetStore((s) => s.setSettingsOpen);
  const setToast = usePetStore((s) => s.setToast);
  const addFact = usePetStore((s) => s.addFact);
  const removeFact = usePetStore((s) => s.removeFact);
  const clearFacts = usePetStore((s) => s.clearFacts);
  const interact = usePetStore((s) => s.interact);

  const [tab, setTab] = useState<'chat' | 'memory'>('chat');
  const [input, setInput] = useState('');
  const [listening, setListening] = useState(false);
  const [factInput, setFactInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    if (memoryOpen) setTab('memory');
  }, [memoryOpen]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, isReplying, streamingText, tab]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') toggleChat(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [toggleChat]);

  const submit = () => {
    const text = input.trim();
    if (!text || isReplying) return;
    void sendMessage(text);
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  };

  const startListening = () => {
    const Ctor = window.webkitSpeechRecognition;
    if (!Ctor) {
      setToast('这个浏览器不支持语音输入，建议使用 Chrome 或 Edge。');
      return;
    }
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const rec = new Ctor();
    rec.lang = 'zh-CN';
    rec.continuous = false;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript ?? '';
      if (transcript) {
        setInput(transcript);
        inputRef.current?.focus();
      }
    };
    rec.onerror = () => {
      setListening(false);
      setToast('没听清，再试一次吧。');
    };
    rec.onend = () => setListening(false);
    try {
      rec.start();
      setListening(true);
      recognitionRef.current = rec;
    } catch {
      setToast('语音输入启动失败。');
    }
  };

  const mood = EXPRESSIONS[emotion] ?? EXPRESSIONS.neutral;
  const cloudActive = cloud.enabled && cloud.apiKey.trim().length > 0;
  const grouped = facts.reduce<Record<string, Fact[]>>((acc, fact) => {
    (acc[fact.kind] ??= []).push(fact);
    return acc;
  }, {});

  return (
    <aside className="chat-panel" aria-label="和桌宠聊天">
      <div className="chat-head">
        <div className="chat-head-row">
          <div className="avatar-dot" style={{ background: character.gradient }}>
            {character.name.slice(0, 1)}
          </div>
          <div style={{ minWidth: 0 }}>
            <div className="chat-name">
              {character.name}
              <span className="mood-chip">{mood.label}</span>
            </div>
            <div className="chat-title">
              {character.title} · {character.tagline}
            </div>
          </div>
          <button className="icon-btn chat-close" onClick={() => toggleChat(false)} title="关闭">
            <X size={17} />
          </button>
        </div>
        <div className="affection-row">
          <span>♥ {affectionTitle(affection)}</span>
          <div className="affection-bar">
            <div className="affection-fill" style={{ width: `${Math.round(affection)}%` }} />
          </div>
          <span>{Math.round(affection)}/100</span>
        </div>
        <div className="chat-tabs">
          <button className={`chat-tab ${tab === 'chat' ? 'active' : ''}`} onClick={() => setTab('chat')}>
            聊天
          </button>
          <button
            className={`chat-tab ${tab === 'memory' ? 'active' : ''}`}
            onClick={() => {
              setTab('memory');
              setMemoryOpen(true);
            }}
          >
            记忆 · {facts.length}
          </button>
        </div>
      </div>

      {tab === 'chat' ? (
        <>
          <div className="chat-body">
            {messages.length === 0 && (
              <div className="empty-note">
                和{character.name}说点什么吧。她会记得你说过的话。
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`msg ${m.role}`}>
                <div
                  className="msg-avatar"
                  style={{
                    background:
                      m.role === 'pet'
                        ? character.gradient
                        : 'linear-gradient(135deg,#b9c6ff,#8fa8e8)',
                  }}
                >
                  {m.role === 'pet' ? character.name.slice(0, 1) : (userName || '你').slice(0, 1)}
                </div>
                <div>
                  <div className="msg-bubble">{m.text}</div>
                  <div className="msg-meta">
                    {m.role === 'pet' && (
                      <>
                        <span className={`source-dot ${m.source === 'cloud' ? 'cloud' : ''}`} />
                        <span>{m.source === 'cloud' ? '云端' : '本地'}</span>
                      </>
                    )}
                    <span>{timeLabel(m.at)}</span>
                  </div>
                </div>
              </div>
            ))}
            {isReplying && !streamingText && (
              <div className="msg pet">
                <div className="msg-avatar" style={{ background: character.gradient }}>
                  {character.name.slice(0, 1)}
                </div>
                <div className="typing">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
            {streamingText && (
              <div className="msg pet">
                <div className="msg-avatar" style={{ background: character.gradient }}>
                  {character.name.slice(0, 1)}
                </div>
                <div>
                  <div className="msg-bubble streaming">{streamingText}</div>
                  <div className="msg-meta">
                    <span className="source-dot cloud" />
                    <span>云端</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <div className="quick-chips">
            {QUICK_CHIPS.map((chip) => (
              <button
                key={chip}
                className="quick-chip"
                onClick={() => {
                  if (chip === '摸摸头') interact('headpat');
                  else void sendMessage(chip);
                }}
              >
                {chip}
              </button>
            ))}
          </div>

          <div className="chat-input-wrap">
            <div className="chat-input-box">
              <textarea
                ref={inputRef}
                className="chat-input"
                rows={1}
                placeholder={`和${character.name}说点什么…（Enter 发送）`}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  const el = e.target;
                  el.style.height = 'auto';
                  el.style.height = `${Math.min(110, el.scrollHeight)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
              />
              <button
                className={`mic-btn ${listening ? 'listening' : ''}`}
                onClick={startListening}
                title={listening ? '停止录音' : '语音输入'}
              >
                <Mic size={16} />
              </button>
              <button className="send-btn" onClick={submit} disabled={!input.trim() || isReplying} title="发送">
                <ArrowUp size={16} />
              </button>
            </div>
          </div>
          <div className="chat-foot">
            <span className="model-state">
              <span className={`source-dot ${cloudActive ? 'cloud' : ''}`} />
              {cloudActive ? `云端 · ${cloud.model}` : '本地大脑 · 无需联网'}
            </span>
            <button
              className="context-item"
              style={{ width: 'auto', padding: '2px 6px', fontSize: 10 }}
              onClick={() => setSettingsOpen(true, 'cloud')}
            >
              <Settings size={11} /> 模型设置
            </button>
          </div>
        </>
      ) : (
        <div className="chat-body">
          <div className="memory-section-title">她记得的事</div>
          {facts.length === 0 ? (
            <div className="empty-note">她还什么都不知道。试着说「记住，我喜欢草莓牛奶」。</div>
          ) : (
            <div className="memory-list">
              {(Object.keys(grouped) as Fact['kind'][]).map((kind) => (
                <div key={kind}>
                  <div className="memory-section-title">{FACT_LABEL[kind]}</div>
                  {grouped[kind].map((fact) => (
                    <div className="fact-item" key={fact.id}>
                      <span className="fact-kind">{FACT_LABEL[fact.kind]}</span>
                      <span className="fact-text">{fact.text}</span>
                      <button className="fact-del" onClick={() => removeFact(fact.id)} title="删除">
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
          <div className="add-fact-row">
            <input
              className="add-fact-input"
              placeholder="手动添加一条记忆…"
              value={factInput}
              onChange={(e) => setFactInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  addFact(factInput);
                  setFactInput('');
                }
              }}
            />
            <button
              className="btn"
              onClick={() => {
                addFact(factInput);
                setFactInput('');
              }}
            >
              <Plus size={13} />
            </button>
          </div>
          <div className="btn-row" style={{ marginTop: 8 }}>
            <button
              className="btn danger"
              onClick={() => {
                if (window.confirm('确定清空她记住的所有事吗？')) clearFacts();
              }}
            >
              <Trash2 size={13} /> 清空记忆
            </button>
          </div>

          <div className="memory-section-title" style={{ marginTop: 14 }}>
            一起经历的时刻
          </div>
          {moments.length === 0 ? (
            <div className="empty-note">还没有特别的时刻。去摸摸她的头吧。</div>
          ) : (
            <div className="memory-list">
              {[...moments].reverse().map((moment) => (
                <div className="fact-item" key={moment.id}>
                  <Sparkles size={12} color="#8b7be8" />
                  <span className="fact-text">{moment.text}</span>
                  <span style={{ fontSize: 9, color: 'var(--ink-faint)' }}>{timeLabel(moment.at)}</span>
                </div>
              ))}
            </div>
          )}

          <div className="privacy-note" style={{ marginTop: 14 }}>
            <Brain size={15} />
            <span>记忆只保存在这台设备的浏览器里。你可以随时删除，或导出备份。</span>
          </div>
        </div>
      )}
    </aside>
  );
}
