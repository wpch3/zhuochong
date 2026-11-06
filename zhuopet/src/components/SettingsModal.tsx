import { useEffect, useRef, useState } from 'react';
import {
  Check,
  Cloud,
  Cpu,
  Download,
  Eye,
  EyeOff,
  Heart,
  Info,
  KeyRound,
  Palette,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Upload,
  UserRound,
  Volume2,
  X,
} from 'lucide-react';
import { usePetStore, type SettingsTab } from '../store/usePetStore';
import { CHARACTER_LIST, affectionTitle, getCharacter } from '../data/characters';
import model from '../model/xiaoxun.model.json';
import { testConnection } from '../ai/provider';
import { chineseVoices, refreshVoices, speak } from '../utils/speech';
import { sfx } from '../utils/sound';

const TABS: { id: SettingsTab; label: string; icon: typeof Palette }[] = [
  { id: 'appearance', label: '外观', icon: Palette },
  { id: 'persona', label: '性格', icon: UserRound },
  { id: 'voice', label: '说话', icon: Volume2 },
  { id: 'cloud', label: '模型与隐私', icon: Cloud },
  { id: 'advanced', label: '高级', icon: Cpu },
  { id: 'about', label: '关于', icon: Info },
];

const THEMES = [
  { id: 'twilight', label: '暮色星夜', preview: 'linear-gradient(135deg,#241d45,#4b3a7a 60%,#7a4e86)' },
  { id: 'day', label: '晴日窗边', preview: 'linear-gradient(135deg,#cfe4ff,#fff3e6)' },
  { id: 'sakura', label: '樱花午后', preview: 'linear-gradient(135deg,#ffe6ef,#e8d9f7)' },
] as const;

export function SettingsModal() {
  const character = getCharacter(usePetStore((s) => s.characterId));
  const characterId = usePetStore((s) => s.characterId);
  const form = usePetStore((s) => s.form);
  const hairstyle = usePetStore((s) => s.hairstyle);
  const outfit = usePetStore((s) => s.outfit);
  const accessory = usePetStore((s) => s.accessory);
  const scale = usePetStore((s) => s.scale);
  const affection = usePetStore((s) => s.affection);
  const userName = usePetStore((s) => s.userName);
  const facts = usePetStore((s) => s.facts);
  const moments = usePetStore((s) => s.moments);
  const settings = usePetStore((s) => s.settings);
  const tab = usePetStore((s) => s.settingsTab);
  const setSettingsOpen = usePetStore((s) => s.setSettingsOpen);
  const setCharacter = usePetStore((s) => s.setCharacter);
  const setForm = usePetStore((s) => s.setForm);
  const setHairstyle = usePetStore((s) => s.setHairstyle);
  const setOutfit = usePetStore((s) => s.setOutfit);
  const setAccessory = usePetStore((s) => s.setAccessory);
  const setScale = usePetStore((s) => s.setScale);
  const setUserName = usePetStore((s) => s.setUserName);
  const updateSettings = usePetStore((s) => s.updateSettings);
  const updateCloud = usePetStore((s) => s.updateCloud);
  const exportData = usePetStore((s) => s.exportData);
  const importData = usePetStore((s) => s.importData);
  const resetAll = usePetStore((s) => s.resetAll);
  const setToast = usePetStore((s) => s.setToast);
  const setStudioOpen = usePetStore((s) => s.setStudioOpen);

  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const update = () => setVoices(chineseVoices());
    update();
    refreshVoices();
    const timer = setTimeout(update, 600);
    window.speechSynthesis?.addEventListener?.('voiceschanged', update);
    return () => {
      clearTimeout(timer);
      window.speechSynthesis?.removeEventListener?.('voiceschanged', update);
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSettingsOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [setSettingsOpen]);

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    const result = await testConnection(settings.cloud);
    setTestResult(result);
    setTesting(false);
    if (result.ok) sfx.chime(settings.soundEnabled);
  };

  const testVoice = () => {
    const text = `你好，我是${character.name}。${character.tagline}。今天也请多关照。`;
    const ok = speak(text, {
      pitch: character.voice.pitch * settings.voicePitch,
      rate: character.voice.rate * settings.voiceRate,
      volume: settings.volume,
      voiceURI: settings.voiceURI,
    });
    if (!ok) setToast('当前浏览器没有可用的语音，建议使用 Chrome 或 Edge。');
  };

  return (
    <div className="modal-backdrop" onPointerDown={(e) => e.target === e.currentTarget && setSettingsOpen(false)}>
      <div className="modal" role="dialog" aria-label="设置">
        <div className="modal-head">
          <div>
            <div className="modal-title">设置</div>
            <div className="modal-sub">把桌宠调成你喜欢的样子</div>
          </div>
          <button className="icon-btn modal-close" onClick={() => setSettingsOpen(false)} title="关闭">
            <X size={18} />
          </button>
        </div>
        <div className="tabs">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setSettingsOpen(true, id)}>
              <Icon size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              {label}
            </button>
          ))}
        </div>

        <div className="modal-body">
          {tab === 'appearance' && (
            <>
              <div className="settings-section">
                <div className="settings-section-title">选择你的桌宠</div>
                <div className="character-grid">
                  {CHARACTER_LIST.map((c) => (
                    <button
                      key={c.id}
                      className={`character-card ${characterId === c.id ? 'active' : ''}`}
                      onClick={() => setCharacter(c.id)}
                    >
                      <div className="character-avatar" style={{ background: c.gradient }}>
                        {c.name.slice(0, 1)}
                      </div>
                      <div className="character-name">{c.name}</div>
                      <div className="character-title">{c.title}</div>
                      <div className="character-tagline">{c.tagline}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section-title">样子</div>
                <div className="settings-grid">
                  <div className="field">
                    <label>形态</label>
                    <div className="chip-row">
                      <button className={`chip ${form === 'chibi' ? 'active' : ''}`} onClick={() => setForm('chibi')}>
                        Q 版
                      </button>
                      <button className={`chip ${form === 'teen' ? 'active' : ''}`} onClick={() => setForm('teen')}>
                        少女
                      </button>
                    </div>
                  </div>
                  <div className="field">
                    <label>发型</label>
                    <div className="chip-row">
                      {model.hairstyles.map((h) => (
                        <button
                          key={h.id}
                          className={`chip ${hairstyle === h.id ? 'active' : ''}`}
                          onClick={() => setHairstyle(h.id as typeof hairstyle)}
                        >
                          {h.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="field">
                    <label>服装</label>
                    <div className="chip-row">
                      {model.outfits.map((o) => (
                        <button
                          key={o.id}
                          className={`chip ${outfit === o.id ? 'active' : ''}`}
                          onClick={() => setOutfit(o.id as typeof outfit)}
                        >
                          <span
                            className="swatch"
                            style={{
                              background: `linear-gradient(135deg, ${(o.palette as Record<string, string>)['sleeve-1'] ?? character.palette['sleeve-1']}, ${(o.palette as Record<string, string>)['skirt-1'] ?? character.palette['skirt-1']})`,
                            }}
                          />
                          {o.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="field">
                    <label>配饰</label>
                    <div className="chip-row">
                      {model.accessories.map((a) => (
                        <button
                          key={a.id}
                          className={`chip ${accessory === a.id ? 'active' : ''}`}
                          onClick={() => setAccessory(a.id as typeof accessory)}
                        >
                          {a.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="field">
                    <label>大小：{Math.round(scale * 100)}%</label>
                    <input className="range" type="range" min={0.7} max={1.3} step={0.01} value={scale} onChange={(e) => setScale(Number(e.target.value))} />
                  </div>
                  <div className="field">
                    <label>桌面主题</label>
                    <div className="theme-grid">
                      {THEMES.map((t) => (
                        <button
                          key={t.id}
                          className={`theme-card ${settings.theme === t.id ? 'active' : ''}`}
                          onClick={() => updateSettings({ theme: t.id })}
                        >
                          <div className="theme-preview" style={{ background: t.preview }} />
                          <div className="theme-name">{t.label}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="settings-grid">
                <div className="toggle-row">
                  <div>
                    <div className="t-label">星星伙伴</div>
                    <div className="t-hint">一只会绕着她飞的小星星</div>
                  </div>
                  <button className={`switch ${settings.showBuddy ? 'on' : ''}`} onClick={() => updateSettings({ showBuddy: !settings.showBuddy })} />
                </div>
                <div className="toggle-row">
                  <div>
                    <div className="t-label">显示名字牌</div>
                    <div className="t-hint">在桌宠下方显示名字和心情</div>
                  </div>
                  <button className={`switch ${settings.showNameplate ? 'on' : ''}`} onClick={() => updateSettings({ showNameplate: !settings.showNameplate })} />
                </div>
              </div>
            </>
          )}

          {tab === 'persona' && (
            <>
              <div className="settings-section">
                <div className="settings-section-title">关于你</div>
                <div className="settings-grid">
                  <div className="field">
                    <label>她怎么称呼你</label>
                    <input className="input" value={userName} placeholder="你的名字或昵称" onChange={(e) => setUserName(e.target.value)} />
                    <div className="hint">她会记住这个名字，也会在对话里自然地问起你的事。</div>
                  </div>
                  <div className="field">
                    <label>亲密度</label>
                    <div className="affection-row" style={{ marginTop: 4 }}>
                      <span>♥ {affectionTitle(affection)}</span>
                      <div className="affection-bar">
                        <div className="affection-fill" style={{ width: `${Math.round(affection)}%` }} />
                      </div>
                      <span>{Math.round(affection)}</span>
                    </div>
                    <div className="hint">多聊天、多互动会提升亲密度。每个阶段她的语气都会更亲近一点。</div>
                  </div>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section-title">{character.name}的性格</div>
                <div className="about-hero">
                  <div className="about-logo" style={{ background: character.gradient }}>
                    {character.name.slice(0, 1)}
                  </div>
                  <div>
                    <div className="about-name">
                      {character.name} <span style={{ fontSize: 11, color: 'var(--ink-faint)' }}>{character.title}</span>
                    </div>
                    <div className="about-ver">{character.tagline}</div>
                  </div>
                </div>
                <div className="about-text">{character.persona}</div>
                <div className="settings-grid" style={{ marginTop: 12 }}>
                  <div className="field">
                    <label>喜欢</label>
                    <div className="chip-row">
                      {character.likes.map((like) => (
                        <span key={like} className="chip" style={{ cursor: 'default' }}>
                          <Heart size={10} /> {like}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="field">
                    <label>不喜欢</label>
                    <div className="chip-row">
                      {character.dislikes.map((dislike) => (
                        <span key={dislike} className="chip" style={{ cursor: 'default' }}>
                          {dislike}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="field">
                    <label>生日 / 身高</label>
                    <div className="hint" style={{ fontSize: 12 }}>
                      {character.birthday} · {character.height}
                    </div>
                  </div>
                  <div className="field">
                    <label>说话风格</label>
                    <div className="hint" style={{ fontSize: 12 }}>
                      {character.speech}
                    </div>
                  </div>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section-title">记忆与时刻</div>
                <div className="kv">
                  <span>她记住的事</span>
                  <span>{facts.length} 条</span>
                </div>
                <div className="kv">
                  <span>一起经历的时刻</span>
                  <span>{moments.length} 个</span>
                </div>
                <div className="btn-row" style={{ marginTop: 10 }}>
                  <button className="btn" onClick={() => setSettingsOpen(true, 'appearance')}>
                    <Palette size={13} /> 换个样子
                  </button>
                </div>
              </div>
            </>
          )}

          {tab === 'voice' && (
            <>
              <div className="settings-section">
                <div className="settings-section-title">语音</div>
                <div className="settings-grid">
                  <div className="toggle-row">
                    <div>
                      <div className="t-label">让她说话</div>
                      <div className="t-hint">用浏览器自带的语音合成朗读，不需要联网</div>
                    </div>
                    <button className={`switch ${settings.voiceEnabled ? 'on' : ''}`} onClick={() => updateSettings({ voiceEnabled: !settings.voiceEnabled })} />
                  </div>
                  <div className="toggle-row">
                    <div>
                      <div className="t-label">音效</div>
                      <div className="t-hint">摸摸、投喂时的软软提示音</div>
                    </div>
                    <button className={`switch ${settings.soundEnabled ? 'on' : ''}`} onClick={() => updateSettings({ soundEnabled: !settings.soundEnabled })} />
                  </div>
                  <div className="field">
                    <label>声音</label>
                    <select className="select" value={settings.voiceURI} onChange={(e) => updateSettings({ voiceURI: e.target.value })}>
                      <option value="">自动选择（推荐）</option>
                      {voices.map((v) => (
                        <option key={v.voiceURI} value={v.voiceURI}>
                          {v.name} · {v.lang}
                        </option>
                      ))}
                    </select>
                    <div className="hint">{voices.length === 0 ? '当前浏览器没有中文语音，建议使用 Chrome 或 Edge。' : `找到 ${voices.length} 个中文语音。`}</div>
                  </div>
                  <div className="field">
                    <label>音量：{Math.round(settings.volume * 100)}%</label>
                    <input className="range" type="range" min={0} max={1} step={0.05} value={settings.volume} onChange={(e) => updateSettings({ volume: Number(e.target.value) })} />
                  </div>
                  <div className="field">
                    <label>语速：{settings.voiceRate.toFixed(2)}×</label>
                    <input className="range" type="range" min={0.7} max={1.3} step={0.01} value={settings.voiceRate} onChange={(e) => updateSettings({ voiceRate: Number(e.target.value) })} />
                  </div>
                  <div className="field">
                    <label>音调：{settings.voicePitch.toFixed(2)}</label>
                    <input className="range" type="range" min={0.8} max={1.6} step={0.01} value={settings.voicePitch} onChange={(e) => updateSettings({ voicePitch: Number(e.target.value) })} />
                  </div>
                </div>
                <div className="btn-row" style={{ marginTop: 10 }}>
                  <button className="btn primary" onClick={testVoice}>
                    <Volume2 size={13} /> 试听她的声音
                  </button>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section-title">陪伴节奏</div>
                <div className="settings-grid">
                  <div className="field">
                    <label>发呆多久后睡着：{settings.sleepAfterMin} 分钟</label>
                    <input className="range" type="range" min={1} max={30} step={1} value={settings.sleepAfterMin} onChange={(e) => updateSettings({ sleepAfterMin: Number(e.target.value) })} />
                    <div className="hint">你长时间不理她，她会自己睡着。摸摸她就会醒。</div>
                  </div>
                  <div className="toggle-row">
                    <div>
                      <div className="t-label">主动找你说话</div>
                      <div className="t-hint">安静太久时，她会主动搭话</div>
                    </div>
                    <button className={`switch ${settings.proactive ? 'on' : ''}`} onClick={() => updateSettings({ proactive: !settings.proactive })} />
                  </div>
                  <div className="toggle-row">
                    <div>
                      <div className="t-label">减少动画</div>
                      <div className="t-hint">关闭呼吸、摆动等细微动作</div>
                    </div>
                    <button className={`switch ${settings.reduceMotion ? 'on' : ''}`} onClick={() => updateSettings({ reduceMotion: !settings.reduceMotion })} />
                  </div>
                </div>
              </div>
            </>
          )}

          {tab === 'cloud' && (
            <>
              <div className="settings-section">
                <div className="settings-section-title">大脑</div>
                <div className="toggle-row">
                  <div>
                    <div className="t-label">优先使用云端大模型</div>
                    <div className="t-hint">开启后会调用你填写的 OpenAI 兼容接口；失败时自动切回本地大脑</div>
                  </div>
                  <button className={`switch ${settings.cloud.enabled ? 'on' : ''}`} onClick={() => updateCloud({ enabled: !settings.cloud.enabled })} />
                </div>
                <div className="settings-grid" style={{ marginTop: 10 }}>
                  <div className="field">
                    <label>API 地址（OpenAI 兼容）</label>
                    <input className="input" value={settings.cloud.baseUrl} onChange={(e) => updateCloud({ baseUrl: e.target.value })} placeholder="https://api.openai.com/v1" />
                  </div>
                  <div className="field">
                    <label>模型名</label>
                    <input className="input" value={settings.cloud.model} onChange={(e) => updateCloud({ model: e.target.value })} placeholder="gpt-4o-mini" />
                  </div>
                  <div className="field">
                    <label>API Key</label>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input
                        className="input"
                        type={showKey ? 'text' : 'password'}
                        value={settings.cloud.apiKey}
                        onChange={(e) => updateCloud({ apiKey: e.target.value })}
                        placeholder="sk-..."
                        autoComplete="off"
                      />
                      <button className="btn" onClick={() => setShowKey(!showKey)} title={showKey ? '隐藏' : '显示'}>
                        {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                    <div className="hint">只保存在这台设备的 localStorage，不会上传到任何地方。</div>
                  </div>
                </div>
                <div className="btn-row" style={{ marginTop: 10 }}>
                  <button className="btn primary" onClick={runTest} disabled={testing}>
                    <KeyRound size={13} /> {testing ? '正在连接…' : '测试连接'}
                  </button>
                  {testResult && (
                    <span style={{ fontSize: 11.5, color: testResult.ok ? '#2f9e7f' : '#d05a76' }}>
                      {testResult.ok ? <Check size={12} style={{ display: 'inline' }} /> : <X size={12} style={{ display: 'inline' }} />} {testResult.message}
                    </span>
                  )}
                </div>
              </div>

              <div className="privacy-note">
                <ShieldCheck size={16} />
                <span>
                  本地大脑完全离线，不需要任何 Key。云端是可选的：只有当你填写 Key 并开启开关时才会联网。Key 只存在本机，导出备份时会自动清空。
                </span>
              </div>

              <div className="settings-section" style={{ marginTop: 16 }}>
                <div className="settings-section-title">数据</div>
                <div className="btn-row">
                  <button className="btn" onClick={exportData}>
                    <Download size={13} /> 导出备份
                  </button>
                  <button className="btn" onClick={() => fileRef.current?.click()}>
                    <Upload size={13} /> 导入备份
                  </button>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="application/json"
                    style={{ display: 'none' }}
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      const text = await file.text();
                      importData(text);
                      e.target.value = '';
                    }}
                  />
                  <button
                    className="btn danger"
                    onClick={() => {
                      if (window.confirm('确定要清空所有记忆、聊天和设置，重新开始吗？')) resetAll();
                    }}
                  >
                    <RotateCcw size={13} /> 重新开始
                  </button>
                </div>
              </div>
            </>
          )}

          {tab === 'advanced' && (
            <>
              <div className="settings-section">
                <div className="settings-section-title">模型</div>
                <div className="kv">
                  <span>角色</span>
                  <span>
                    {model.name} · {model.title}
                  </span>
                </div>
                <div className="kv">
                  <span>模型格式</span>
                  <span>
                    {model.format} v{model.formatVersion}
                  </span>
                </div>
                <div className="kv">
                  <span>画布</span>
                  <span>
                    {model.canvas.width} × {model.canvas.height}
                  </span>
                </div>
                <div className="kv">
                  <span>部件 / 参数</span>
                  <span>
                    {model.parts.length} / {model.parameters.length}
                  </span>
                </div>
                <div className="kv">
                  <span>表情 / 动作</span>
                  <span>
                    {Object.keys(model.expressions).length} / {Object.keys(model.motions).length}
                  </span>
                </div>
                <div className="btn-row" style={{ marginTop: 10 }}>
                  <button className="btn primary" onClick={() => setStudioOpen(true)}>
                    <Sparkles size={13} /> 打开模型工坊
                  </button>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section-title">聊天</div>
                <div className="btn-row">
                  <button
                    className="btn danger"
                    onClick={() => {
                      if (window.confirm('清空聊天记录？她的记忆会保留。')) {
                        usePetStore.setState({ messages: [] });
                        setToast('聊天记录已清空');
                      }
                    }}
                  >
                    清空聊天记录
                  </button>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section-title">快捷键</div>
                <div className="kv">
                  <span>打开 / 关闭聊天</span>
                  <span>Ctrl + K</span>
                </div>
                <div className="kv">
                  <span>沉浸模式</span>
                  <span>Ctrl + Shift + F</span>
                </div>
                <div className="kv">
                  <span>关闭弹窗</span>
                  <span>Esc</span>
                </div>
              </div>
            </>
          )}

          {tab === 'about' && (
            <>
              <div className="about-hero">
                <div className="about-logo">
                  <Sparkles size={26} />
                </div>
                <div>
                  <div className="about-name">ZhuoPet · 桌宠</div>
                  <div className="about-ver">v1.0.0 · 一个真正能用的 AI 桌面伴侣</div>
                </div>
              </div>
              <div className="about-text">
                ZhuoPet 是一个从零开始重做的 AI 桌宠。她有一套原创的分层 Live2D 风格模型、物理发梢、会呼吸和眨眼的身体、本地大脑和长期记忆，也可以接入你自己的大模型。
                没有账号、没有订阅、没有云端上传，所有记忆只留在你的设备里。
              </div>
              <div className="settings-grid" style={{ marginTop: 14 }}>
                <div className="kv">
                  <span>角色</span>
                  <span>小寻 / 月见 / 双喜 / 小尘</span>
                </div>
                <div className="kv">
                  <span>模型</span>
                  <span>原创分层 SVG 骨骼模型</span>
                </div>
                <div className="kv">
                  <span>本地大脑</span>
                  <span>意图识别 + 情绪 + 记忆</span>
                </div>
                <div className="kv">
                  <span>云端</span>
                  <span>OpenAI 兼容接口（可选）</span>
                </div>
                <div className="kv">
                  <span>语音</span>
                  <span>浏览器语音合成 + 语音输入</span>
                </div>
                <div className="kv">
                  <span>桌面端</span>
                  <span>Electron 透明窗口 / 托盘</span>
                </div>
              </div>
              <div className="privacy-note" style={{ marginTop: 14 }}>
                <ShieldCheck size={16} />
                <span>本软件不收集任何数据。没有账号系统，没有埋点。你的聊天、记忆和设置都只保存在本机。</span>
              </div>
              <div className="about-text" style={{ marginTop: 14, fontSize: 11, color: 'var(--ink-faint)' }}>
                角色与模型均为原创。模型格式与 Live2D Cubism 参数命名兼容，但不是 Live2D 官方格式；本项目不包含任何 Live2D 官方素材。
              </div>
            </>
          )}
        </div>

        <div style={{ padding: '12px 22px', borderTop: '1px solid var(--line)', display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn primary" onClick={() => setSettingsOpen(false)}>
            完成
          </button>
        </div>
      </div>
    </div>
  );
}
