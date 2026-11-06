import { useEffect, useRef } from 'react';
import { Brain, EyeOff, Hand, Heart, LogOut, MessageCircle, Settings, Shirt, Sparkles, UserRound } from 'lucide-react';
import { usePetStore } from '../store/usePetStore';
import { getCharacter } from '../data/characters';

export function ContextMenu() {
  const menu = usePetStore((s) => s.contextMenu);
  const setContextMenu = usePetStore((s) => s.setContextMenu);
  const character = getCharacter(usePetStore((s) => s.characterId));
  const toggleChat = usePetStore((s) => s.toggleChat);
  const interact = usePetStore((s) => s.interact);
  const setDressupOpen = usePetStore((s) => s.setDressupOpen);
  const setMemoryOpen = usePetStore((s) => s.setMemoryOpen);
  const setSettingsOpen = usePetStore((s) => s.setSettingsOpen);
  const setHidden = usePetStore((s) => s.setHidden);
  const setToast = usePetStore((s) => s.setToast);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const onDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setContextMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setContextMenu(null);
    };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [menu, setContextMenu]);

  if (!menu) return null;
  const x = Math.min(menu.x, window.innerWidth - 236);
  const y = Math.min(menu.y, window.innerHeight - 360);
  const close = () => setContextMenu(null);

  return (
    <div ref={ref} className="context-menu" style={{ left: x, top: y }} role="menu">
      <div className="context-label">
        {character.name} · {character.title}
      </div>
      <button
        className="context-item"
        onClick={() => {
          toggleChat(true);
          close();
        }}
      >
        <MessageCircle size={15} /> 跟她说话
      </button>
      <button
        className="context-item"
        onClick={() => {
          interact('headpat');
          close();
        }}
      >
        <Heart size={15} /> 摸摸头
      </button>
      <button
        className="context-item"
        onClick={() => {
          interact('wave');
          close();
        }}
      >
        <Hand size={15} /> 挥挥手
      </button>
      <button
        className="context-item"
        onClick={() => {
          setDressupOpen(true);
          close();
        }}
      >
        <Shirt size={15} /> 换个样子
      </button>
      <button
        className="context-item"
        onClick={() => {
          setSettingsOpen(true, 'persona');
          close();
        }}
      >
        <UserRound size={15} /> 她的性格
      </button>
      <button
        className="context-item"
        onClick={() => {
          setMemoryOpen(true);
          close();
        }}
      >
        <Brain size={15} /> 记忆
      </button>
      <div className="context-sep" />
      <button
        className="context-item"
        onClick={() => {
          setSettingsOpen(true);
          close();
        }}
      >
        <Settings size={15} /> 设置
      </button>
      <button
        className="context-item"
        onClick={() => {
          setHidden(true);
          close();
        }}
      >
        <EyeOff size={15} /> 暂时隐藏
      </button>
      <button
        className="context-item"
        onClick={() => {
          setSettingsOpen(true, 'about');
          close();
        }}
      >
        <Sparkles size={15} /> 关于
      </button>
      <div className="context-sep" />
      <button
        className="context-item danger"
        onClick={() => {
          if (window.zhuopet?.quit) window.zhuopet.quit();
          else {
            setToast('浏览器版请直接关闭标签页。');
            close();
          }
        }}
      >
        <LogOut size={15} /> 退出
      </button>
    </div>
  );
}
