import { useEffect, useMemo, useRef, useState } from 'react';
import { Heart, X } from 'lucide-react';
import { CharacterSvg } from './CharacterSvg';
import { usePetStore, petBus } from '../store/usePetStore';
import { getCharacter, affectionTitle } from '../data/characters';
import { PetEngine, clamp } from '../model/engine';
import { applyPose } from '../model/applyPose';
import { EXPRESSIONS, type Pose } from '../model/types';
import model from '../model/xiaoxun.model.json';

const HEAD_PARTS = new Set([
  'face',
  'hairFront',
  'hairBack',
  'hairBackRig',
  'headRig',
  'eyeL',
  'eyeR',
  'browL',
  'browR',
  'mouth',
  'blush',
  'catEarL',
  'catEarR',
  'ahoge',
  'accessory',
  'twinL1',
  'twinR1',
  'hairTieL',
  'hairTieR',
]);

const EFFECT_EMOJI: Record<string, string> = {
  heart: '💗',
  sparkle: '✨',
  zzz: '💤',
  sweat: '💦',
  question: '❓',
  note: '🎵',
};

export function PetStage() {
  const characterId = usePetStore((s) => s.characterId);
  const character = getCharacter(characterId);
  const form = usePetStore((s) => s.form);
  const hairstyle = usePetStore((s) => s.hairstyle);
  const accessory = usePetStore((s) => s.accessory);
  const outfit = usePetStore((s) => s.outfit);
  const scale = usePetStore((s) => s.scale);
  const position = usePetStore((s) => s.position);
  const emotion = usePetStore((s) => s.emotion);
  const sleeping = usePetStore((s) => s.sleeping);
  const bubble = usePetStore((s) => s.bubble);
  const effects = usePetStore((s) => s.effects);
  const showBuddy = usePetStore((s) => s.settings.showBuddy);
  const showNameplate = usePetStore((s) => s.settings.showNameplate);
  const immersive = usePetStore((s) => s.immersive);
  const hidden = usePetStore((s) => s.hidden);
  const affection = usePetStore((s) => s.affection);
  const setPosition = usePetStore((s) => s.setPosition);
  const interact = usePetStore((s) => s.interact);
  const toggleChat = usePetStore((s) => s.toggleChat);
  const setContextMenu = usePetStore((s) => s.setContextMenu);
  const clearBubble = usePetStore((s) => s.clearBubble);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<PetEngine | null>(null);
  if (!engineRef.current) engineRef.current = new PetEngine();
  const pointerRef = useRef<{ x: number; y: number } | null>(null);
  const draggingRef = useRef(false);
  const [dragging, setDragging] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const dragInfo = useRef({ down: false, moved: false, startX: 0, startY: 0, offsetX: 0, offsetY: 0, part: '' });

  const palette = useMemo(() => {
    const outfitDef = model.outfits.find((o) => o.id === outfit);
    return { ...character.palette, ...((outfitDef?.palette ?? {}) as Record<string, string>) };
  }, [character, outfit]);

  useEffect(() => {
    const unsub = petBus.on((action) => engineRef.current?.trigger(action));
    return () => {
      unsub();
    };
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setShowHint(true), 900);
    const hide = setTimeout(() => setShowHint(false), 8200);
    return () => {
      clearTimeout(timer);
      clearTimeout(hide);
    };
  }, []);

  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      const s = usePetStore.getState();
      const engine = engineRef.current!;
      const pose: Pose = engine.update(dt, {
        pointer: pointerRef.current,
        emotion: s.emotion,
        energy: s.energy,
        sleeping: s.sleeping,
        dragging: draggingRef.current,
        talking: s.talking,
        reducedMotion: s.settings.reduceMotion,
        form: s.form,
      });
      if (svgRef.current) applyPose(svgRef.current, pose, s.form);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const handlePointerMove = (e: React.PointerEvent) => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const rect = wrap.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height * 0.3;
    pointerRef.current = {
      x: clamp((e.clientX - cx) / (rect.width * 0.8), -1, 1),
      y: clamp((e.clientY - cy) / (rect.height * 0.65), -1, 1),
    };
    const info = dragInfo.current;
    if (!info.down) return;
    const dx = e.clientX - info.startX;
    const dy = e.clientY - info.startY;
    if (!info.moved && Math.hypot(dx, dy) > 5) {
      info.moved = true;
      draggingRef.current = true;
      setDragging(true);
    }
    if (info.moved) {
      const host = wrap.parentElement?.parentElement;
      if (!host) return;
      const hostRect = host.getBoundingClientRect();
      const x = ((e.clientX - info.offsetX - hostRect.left) / hostRect.width) * 100;
      const y = ((e.clientY - info.offsetY - hostRect.top) / hostRect.height) * 100;
      setPosition({ x, y });
    }
  };

  const handlePointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const wrap = wrapRef.current;
    if (!wrap) return;
    const rect = wrap.getBoundingClientRect();
    const part = (e.target as Element).closest('[data-part]')?.getAttribute('data-part') ?? '';
    dragInfo.current = {
      down: true,
      moved: false,
      startX: e.clientX,
      startY: e.clientY,
      offsetX: e.clientX - (rect.left + rect.width / 2),
      offsetY: e.clientY - (rect.top + rect.height / 2),
      part,
    };
    wrap.setPointerCapture(e.pointerId);
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    const info = dragInfo.current;
    if (!info.down) return;
    info.down = false;
    if (wrapRef.current?.hasPointerCapture(e.pointerId)) wrapRef.current.releasePointerCapture(e.pointerId);
    if (!info.moved) {
      if (HEAD_PARTS.has(info.part)) interact('headpat');
      else interact('poke');
    }
    draggingRef.current = false;
    setDragging(false);
  };

  const mood = EXPRESSIONS[emotion] ?? EXPRESSIONS.neutral;

  return (
    <div
      className="pet-layer"
      onPointerMove={handlePointerMove}
      onPointerLeave={() => {
        pointerRef.current = null;
      }}
    >
      <div
        ref={wrapRef}
        className={`pet-wrap ${dragging ? 'dragging' : ''} ${hidden ? 'hidden' : ''}`}
        style={{ left: `${position.x}%`, top: `${position.y}%`, ['--pet-scale' as string]: scale }}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onDoubleClick={(e) => {
          e.preventDefault();
          toggleChat(true);
        }}
        onContextMenu={(e) => {
          e.preventDefault();
          setContextMenu({ x: e.clientX, y: e.clientY });
        }}
      >
        <div className="pet-glow" />
        <CharacterSvg
          svgRef={svgRef}
          form={form}
          palette={palette}
          hairstyle={hairstyle}
          accessory={accessory}
          showBuddy={showBuddy}
          className="pet-svg"
        />

        {sleeping && (
          <div className="sleep-zzz" aria-hidden>
            <span>Z</span>
            <span>z</span>
            <span>z</span>
          </div>
        )}

        {effects.map((effect) => (
          <span
            key={effect.id}
            className="effect"
            style={{
              left: `${effect.x}%`,
              top: `${effect.y}%`,
              ['--drift' as string]: `${effect.drift}px`,
            }}
          >
            {EFFECT_EMOJI[effect.type] ?? '✨'}
          </span>
        ))}

        {bubble && !hidden && (
          <div className="speech-bubble" role="status" onPointerDown={(e) => e.stopPropagation()} onPointerUp={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
            <button className="bubble-close" onClick={clearBubble} aria-label="关闭气泡">
              <X size={11} />
            </button>
            {bubble.text}
          </div>
        )}

        {showHint && !immersive && (
          <div className="hint-bubble">点点我的头 · 双击聊天 · 右键有菜单</div>
        )}

        {showNameplate && !immersive && (
          <div className="nameplate" onPointerDown={(e) => e.stopPropagation()} onPointerUp={(e) => e.stopPropagation()}>
            <strong>{character.name}</strong>
            <span className="mood">
              {mood.label} · {affectionTitle(affection)}
            </span>
            <span className="affection">
              <Heart size={10} fill="currentColor" /> {Math.round(affection)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
