import { useEffect, useState } from 'react';
import { Brain, Maximize2, MessageCircle, ScanLine, Settings, Sparkles, Volume2, VolumeX } from 'lucide-react';
import { usePetStore } from '../store/usePetStore';
import { affectionTitle, getCharacter } from '../data/characters';
import { EXPRESSIONS } from '../model/types';

export function TopBar() {
  const characterId = usePetStore((s) => s.characterId);
  const character = getCharacter(characterId);
  const emotion = usePetStore((s) => s.emotion);
  const affection = usePetStore((s) => s.affection);
  const chatOpen = usePetStore((s) => s.chatOpen);
  const memoryOpen = usePetStore((s) => s.memoryOpen);
  const toggleChat = usePetStore((s) => s.toggleChat);
  const setMemoryOpen = usePetStore((s) => s.setMemoryOpen);
  const setStudioOpen = usePetStore((s) => s.setStudioOpen);
  const setSettingsOpen = usePetStore((s) => s.setSettingsOpen);
  const setImmersive = usePetStore((s) => s.setImmersive);
  const voiceEnabled = usePetStore((s) => s.settings.voiceEnabled);
  const updateSettings = usePetStore((s) => s.updateSettings);
  const cloud = usePetStore((s) => s.settings.cloud);
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 20000);
    return () => clearInterval(timer);
  }, []);

  const cloudActive = cloud.enabled && cloud.apiKey.trim().length > 0;
  const mood = EXPRESSIONS[emotion] ?? EXPRESSIONS.neutral;

  return (
    <header className="topbar">
      <div className="brand">
        <div className="logo-mark">
          <Sparkles size={20} />
        </div>
        <div>
          <div className="brand-name">ZhuoPet</div>
          <div className="brand-sub">你的 AI 桌宠</div>
        </div>
      </div>

      <div className="status-pill">
        <span className={`status-dot ${cloudActive ? 'cloud' : ''}`} />
        <span>{cloudActive ? `云端 · ${cloud.model}` : '本地大脑'}</span>
        <span className="status-sep" />
        <span>
          {character.name} · {mood.label}
        </span>
        <span className="status-sep hide-sm" />
        <span className="hide-sm">♥ {affectionTitle(affection)}</span>
      </div>

      <div className="top-spacer" />

      <div className="top-actions">
        <span className="clock">
          {now.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })} {now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
        </span>
        <button
          className={`icon-btn ${chatOpen ? 'active' : ''}`}
          title="和她说话"
          onClick={() => toggleChat()}
        >
          <MessageCircle size={18} />
        </button>
        <button
          className={`icon-btn ${memoryOpen ? 'active' : ''}`}
          title="记忆"
          onClick={() => setMemoryOpen(true)}
        >
          <Brain size={18} />
        </button>
        <button className="icon-btn" title="模型工坊" onClick={() => setStudioOpen(true)}>
          <ScanLine size={18} />
        </button>
        <button className="icon-btn" title="设置" onClick={() => setSettingsOpen(true)}>
          <Settings size={18} />
        </button>
        <button
          className="icon-btn"
          title={voiceEnabled ? '关闭语音' : '打开语音'}
          onClick={() => updateSettings({ voiceEnabled: !voiceEnabled })}
        >
          {voiceEnabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
        </button>
        <button className="icon-btn" title="沉浸模式" onClick={() => setImmersive(true)}>
          <Maximize2 size={18} />
        </button>
      </div>
    </header>
  );
}
