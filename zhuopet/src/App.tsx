import { useEffect } from 'react';
import { Eye, Sparkles } from 'lucide-react';
import { TopBar } from './components/TopBar';
import { Dock } from './components/Dock';
import { PetStage } from './components/PetStage';
import { ChatPanel } from './components/ChatPanel';
import { SettingsModal } from './components/SettingsModal';
import { ModelStudio } from './components/ModelStudio';
import { Onboarding } from './components/Onboarding';
import { ContextMenu } from './components/ContextMenu';
import { usePetStore } from './store/usePetStore';
import { refreshVoices } from './utils/speech';

const params = new URLSearchParams(window.location.search);
const PET_MODE = params.get('mode') === 'pet';

export default function App() {
  const theme = usePetStore((s) => s.settings.theme);
  const chatOpen = usePetStore((s) => s.chatOpen);
  const settingsOpen = usePetStore((s) => s.settingsOpen);
  const studioOpen = usePetStore((s) => s.studioOpen);
  const immersive = usePetStore((s) => s.immersive);
  const hidden = usePetStore((s) => s.hidden);
  const toast = usePetStore((s) => s.toast);
  const init = usePetStore((s) => s.init);
  const tick = usePetStore((s) => s.tick);
  const toggleChat = usePetStore((s) => s.toggleChat);
  const setImmersive = usePetStore((s) => s.setImmersive);
  const setHidden = usePetStore((s) => s.setHidden);
  const setContextMenu = usePetStore((s) => s.setContextMenu);
  const setSettingsOpen = usePetStore((s) => s.setSettingsOpen);
  const setStudioOpen = usePetStore((s) => s.setStudioOpen);

  useEffect(() => {
    init();
    refreshVoices();
    const t = setInterval(() => tick(), 1000);
    return () => clearInterval(t);
  }, [init, tick]);

  useEffect(() => {
    const api = window.zhuopet;
    if (!api) return;
    const unsubs = [
      api.onOpenChat?.(() => toggleChat(true)),
      api.onOpenSettings?.(() => setSettingsOpen(true)),
      api.onOpenStudio?.(() => setStudioOpen(true)),
      api.onClickThrough?.((value: boolean) => usePetStore.getState().setToast(value ? '鼠标穿透已开启：点击空白处会穿过去' : '鼠标穿透已关闭')),
    ].filter(Boolean) as (() => void)[];
    return () => unsubs.forEach((fn) => fn());
  }, [toggleChat, setSettingsOpen, setStudioOpen]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        toggleChat();
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        setImmersive(true);
      }
      if (e.key === 'Escape') {
        setContextMenu(null);
        setSettingsOpen(false);
        setStudioOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggleChat, setImmersive, setContextMenu, setSettingsOpen, setStudioOpen]);

  return (
    <div className={`app theme-${theme} ${PET_MODE ? 'pet-mode' : ''}`}>
      <div className={`wallpaper ${theme}`} aria-hidden>
        <div className="stars" />
        <div className="moon" />
        <div className="orb a" />
        <div className="orb b" />
        <div className="orb c" />
        <div className="grid" />
        <div className="vignette" />
      </div>

      {!PET_MODE && !immersive && <TopBar />}

      <main className="desktop">
        <PetStage />
      </main>

      {!PET_MODE && !immersive && <Dock />}
      {chatOpen && <ChatPanel />}
      {settingsOpen && <SettingsModal />}
      {studioOpen && <ModelStudio />}
      <Onboarding />
      <ContextMenu />

      {toast && <div className="toast">{toast}</div>}

      {immersive && (
        <button className="immersive-exit" onClick={() => setImmersive(false)}>
          <Eye size={13} /> 退出沉浸
        </button>
      )}

      {hidden && (
        <button
          className="btn primary"
          style={{ position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)', zIndex: 90 }}
          onClick={() => setHidden(false)}
        >
          <Sparkles size={14} style={{ display: 'inline', verticalAlign: '-2px' }} /> 显示桌宠
        </button>
      )}
    </div>
  );
}
