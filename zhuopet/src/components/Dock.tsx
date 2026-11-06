import { Brain, CakeSlice, Hand, Heart, Maximize2, MessageCircle, Settings, Shirt, Sparkles, X } from 'lucide-react';
import { usePetStore } from '../store/usePetStore';
import { getCharacter } from '../data/characters';
import model from '../model/xiaoxun.model.json';

export function Dock() {
  const character = getCharacter(usePetStore((s) => s.characterId));
  const form = usePetStore((s) => s.form);
  const hairstyle = usePetStore((s) => s.hairstyle);
  const outfit = usePetStore((s) => s.outfit);
  const accessory = usePetStore((s) => s.accessory);
  const scale = usePetStore((s) => s.scale);
  const dressupOpen = usePetStore((s) => s.dressupOpen);
  const chatOpen = usePetStore((s) => s.chatOpen);
  const setForm = usePetStore((s) => s.setForm);
  const setHairstyle = usePetStore((s) => s.setHairstyle);
  const setOutfit = usePetStore((s) => s.setOutfit);
  const setAccessory = usePetStore((s) => s.setAccessory);
  const setScale = usePetStore((s) => s.setScale);
  const setDressupOpen = usePetStore((s) => s.setDressupOpen);
  const toggleChat = usePetStore((s) => s.toggleChat);
  const setMemoryOpen = usePetStore((s) => s.setMemoryOpen);
  const setSettingsOpen = usePetStore((s) => s.setSettingsOpen);
  const setImmersive = usePetStore((s) => s.setImmersive);
  const interact = usePetStore((s) => s.interact);

  return (
    <div className="dock-wrap">
      {dressupOpen && (
        <div className="dressup">
          <div className="dressup-row">
            <span className="dressup-label">形态</span>
            <div className="chip-row">
              <button className={`chip ${form === 'chibi' ? 'active' : ''}`} onClick={() => setForm('chibi')}>
                Q 版
              </button>
              <button className={`chip ${form === 'teen' ? 'active' : ''}`} onClick={() => setForm('teen')}>
                少女
              </button>
            </div>
            <span className="dressup-label" style={{ marginLeft: 8 }}>大小</span>
            <input
              className="mini-range"
              type="range"
              min={0.7}
              max={1.3}
              step={0.01}
              value={scale}
              onChange={(e) => setScale(Number(e.target.value))}
            />
            <button className="chip" onClick={() => setDressupOpen(false)} style={{ marginLeft: 'auto' }}>
              <X size={12} /> 收起
            </button>
          </div>
          <div className="dressup-row">
            <span className="dressup-label">发型</span>
            <div className="chip-row">
              {model.hairstyles.map((h) => (
                <button key={h.id} className={`chip ${hairstyle === h.id ? 'active' : ''}`} onClick={() => setHairstyle(h.id as typeof hairstyle)} title={h.description}>
                  {h.label}
                </button>
              ))}
            </div>
          </div>
          <div className="dressup-row">
            <span className="dressup-label">服装</span>
            <div className="chip-row">
              {model.outfits.map((o) => (
                <button
                  key={o.id}
                  className={`chip ${outfit === o.id ? 'active' : ''}`}
                  onClick={() => setOutfit(o.id as typeof outfit)}
                  title={o.description}
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
          <div className="dressup-row">
            <span className="dressup-label">配饰</span>
            <div className="chip-row">
              {model.accessories.map((a) => (
                <button key={a.id} className={`chip ${accessory === a.id ? 'active' : ''}`} onClick={() => setAccessory(a.id as typeof accessory)} title={a.description}>
                  {a.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="dock">
        <button className={`dock-btn ${chatOpen ? 'active' : ''}`} onClick={() => toggleChat()} title="和她说话">
          <MessageCircle />
          <span>说话</span>
        </button>
        <button className="dock-btn" onClick={() => interact('headpat')} title="摸摸头">
          <Heart />
          <span>摸摸</span>
        </button>
        <button className="dock-btn" onClick={() => interact('wave')} title="挥挥手">
          <Hand />
          <span>挥手</span>
        </button>
        <button className="dock-btn" onClick={() => interact('feed')} title="投喂">
          <CakeSlice />
          <span>投喂</span>
        </button>
        <div className="dock-sep" />
        <button className={`dock-btn ${dressupOpen ? 'active' : ''}`} onClick={() => setDressupOpen(!dressupOpen)} title="换个样子">
          <Shirt />
          <span>换装</span>
        </button>
        <button className="dock-btn" onClick={() => setMemoryOpen(true)} title="记忆">
          <Brain />
          <span>记忆</span>
        </button>
        <button className="dock-btn" onClick={() => setSettingsOpen(true)} title="设置">
          <Settings />
          <span>设置</span>
        </button>
        <div className="dock-sep" />
        <button className="dock-btn" onClick={() => setImmersive(true)} title="沉浸模式">
          <Maximize2 />
          <span>沉浸</span>
        </button>
        <button className="dock-btn" onClick={() => interact('dance')} title="转圈圈">
          <Sparkles />
          <span>转圈</span>
        </button>
      </div>
    </div>
  );
}
