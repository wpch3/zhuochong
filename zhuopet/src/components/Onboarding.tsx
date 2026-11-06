import { useState } from 'react';
import { ArrowRight, ShieldCheck, Sparkles } from 'lucide-react';
import { usePetStore } from '../store/usePetStore';
import { CHARACTER_LIST, getCharacter } from '../data/characters';

export function Onboarding() {
  const onboarded = usePetStore((s) => s.onboarded);
  const characterId = usePetStore((s) => s.characterId);
  const setCharacter = usePetStore((s) => s.setCharacter);
  const completeOnboarding = usePetStore((s) => s.completeOnboarding);
  const [name, setName] = useState('');
  const character = getCharacter(characterId);

  if (onboarded) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal onboarding" role="dialog" aria-label="初次见面">
        <div className="onboard-hero">
          <div className="onboard-eyebrow">ZhuoPet · 初次见面</div>
          <div className="onboard-title">你好，我是{character.name}。</div>
          <div className="onboard-sub">
            {character.title} · {character.tagline}
            <br />
            我会住在他的桌面上，陪你聊天、记住你说过的话，也会在你累的时候提醒你休息。
          </div>
        </div>
        <div className="onboard-body">
          <div className="onboard-greeting">「{character.greeting[0]}」</div>

          <div className="onboard-label">先选一个你喜欢的桌宠</div>
          <div className="character-grid" style={{ marginBottom: 16 }}>
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

          <div className="onboard-label">我该怎么称呼你？</div>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="你的名字或昵称（可以留空）"
            maxLength={20}
            onKeyDown={(e) => {
              if (e.key === 'Enter') completeOnboarding(name);
            }}
          />

          <div className="privacy-note" style={{ marginTop: 12 }}>
            <ShieldCheck size={15} />
            <span>没有账号，没有上传。你的聊天和记忆只保存在这台设备上。</span>
          </div>

          <div className="onboard-actions">
            <button className="btn" onClick={() => completeOnboarding('')}>
              先随便看看
            </button>
            <button className="btn primary" onClick={() => completeOnboarding(name)}>
              开始和{character.name}一起生活 <ArrowRight size={14} style={{ display: 'inline', verticalAlign: '-2px' }} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
