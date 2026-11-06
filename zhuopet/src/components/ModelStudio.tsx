import { useEffect, useMemo, useRef, useState } from 'react';
import { Bone, Download, Grid3x3, Image as ImageIcon, RotateCcw, ScanLine, X } from 'lucide-react';
import { CharacterSvg } from './CharacterSvg';
import { usePetStore } from '../store/usePetStore';
import { getCharacter } from '../data/characters';
import model from '../model/xiaoxun.model.json';
import { neutralPose } from '../model/engine';
import { EXPRESSIONS, type Emotion, type MouthShape, type Pose } from '../model/types';
import { downloadBlob, exportPosePng, serializeSvg } from '../model/applyPose';

type ParamValues = Record<string, number>;

const defaultParams = (): ParamValues =>
  Object.fromEntries(model.parameters.map((p) => [p.id, p.default]));

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
}

export function ModelStudio() {
  const character = getCharacter(usePetStore((s) => s.characterId));
  const palette = useMemo(() => ({ ...character.palette }), [character]);
  const setStudioOpen = usePetStore((s) => s.setStudioOpen);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [params, setParams] = useState<ParamValues>(defaultParams);
  const [expr, setExpr] = useState<Emotion>('neutral');
  const [showBones, setShowBones] = useState(false);
  const [showWire, setShowWire] = useState(false);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [highlight, setHighlight] = useState<string | null>(null);

  const pose: Pose = useMemo(() => {
    const base = neutralPose();
    const p = params;
    const mouthOpen = p.ParamMouthOpen ?? 0;
    const expression = EXPRESSIONS[expr] ?? EXPRESSIONS.neutral;
    const mouthShape: MouthShape = mouthOpen > 0.08 ? 'open' : expression.mouth;
    return {
      ...base,
      head: { x: (p.ParamAngleX ?? 0) * 0.5, y: (p.ParamAngleY ?? 0) * 0.4, rot: p.ParamAngleZ ?? 0 },
      eyeOpen: p.ParamEyeOpen ?? 1,
      mouthOpen,
      mouthShape,
      brow: p.ParamBrow ?? 0,
      blush: p.ParamBlush ?? 0.2,
      gazeX: p.ParamGazeX ?? 0,
      gazeY: p.ParamGazeY ?? 0,
      armL: p.ParamArmLA ?? 0,
      armR: p.ParamArmRA ?? 0,
      twinL1: p.ParamTwinL ?? 0,
      twinR1: p.ParamTwinR ?? 0,
      ahoge: p.ParamAhoge ?? 0,
      body: { x: 0, y: 0, rot: p.ParamBodySway ?? 0 },
      world: { ...base.world, scaleY: 1 + (p.ParamBreath ?? 0) * 0.012 },
    };
  }, [params, expr]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setStudioOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [setStudioOpen]);

  useEffect(() => {
    if (!showWire) {
      setBoxes([]);
      return;
    }
    const raf = requestAnimationFrame(() => {
      const svg = svgRef.current;
      if (!svg) return;
      const result: Box[] = [];
      svg.querySelectorAll<SVGGraphicsElement>('[data-part]').forEach((el) => {
        try {
          const b = el.getBBox();
          const ctm = el.getCTM();
          if (!ctm || b.width === 0) return;
          const pts = [
            [b.x, b.y],
            [b.x + b.width, b.y],
            [b.x + b.width, b.y + b.height],
            [b.x, b.y + b.height],
          ].map(([x, y]) => {
            const pt = new DOMPoint(x, y).matrixTransform(ctm);
            return [pt.x, pt.y];
          });
          const xs = pts.map((p) => p[0]);
          const ys = pts.map((p) => p[1]);
          result.push({
            x: Math.min(...xs),
            y: Math.min(...ys),
            w: Math.max(...xs) - Math.min(...xs),
            h: Math.max(...ys) - Math.min(...ys),
            label: el.getAttribute('data-part') ?? '',
          });
        } catch {
          /* ignore hidden parts */
        }
      });
      setBoxes(result);
    });
    return () => cancelAnimationFrame(raf);
  }, [showWire, pose]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    svg.querySelectorAll<SVGElement>('[data-part]').forEach((el) => {
      el.style.filter = el.getAttribute('data-part') === highlight ? 'drop-shadow(0 0 7px #a78bfa)' : '';
    });
  }, [highlight]);

  const bones = useMemo(() => {
    const rad = (deg: number) => (deg * Math.PI) / 180;
    const rotate = (x: number, y: number, cx: number, cy: number, a: number): [number, number] => [
      cx + (x - cx) * Math.cos(a) - (y - cy) * Math.sin(a),
      cy + (x - cx) * Math.sin(a) + (y - cy) * Math.cos(a),
    ];
    const body = (x: number, y: number): [number, number] => {
      const [rx, ry] = rotate(x, y, 300, 600, rad(pose.body.rot));
      return [rx + pose.body.x, ry + pose.body.y];
    };
    const head = (x: number, y: number): [number, number] => {
      const [rx, ry] = rotate(x, y, 300, 400, rad(pose.head.rot));
      return body(rx + pose.head.x, ry + pose.head.y);
    };
    const neck = body(300, 400);
    const headCenter = head(300, 250);
    const hip = body(300, 600);
    const shoulderL = body(215, 450);
    const shoulderR = body(385, 450);
    const elbowL = body(185, 540);
    const elbowR = body(415, 540);
    const handL = body(180, 580);
    const handR = body(420, 580);
    const kneeL = body(270, 700);
    const kneeR = body(330, 700);
    const footL = body(270, 780);
    const footR = body(330, 780);
    return {
      joints: [neck, headCenter, hip, shoulderL, shoulderR, elbowL, elbowR, handL, handR, kneeL, kneeR, footL, footR],
      lines: [
        [neck, headCenter],
        [neck, hip],
        [neck, shoulderL],
        [neck, shoulderR],
        [shoulderL, elbowL],
        [elbowL, handL],
        [shoulderR, elbowR],
        [elbowR, handR],
        [hip, kneeL],
        [kneeL, footL],
        [hip, kneeR],
        [kneeR, footR],
      ] as [number, number][][],
    };
  }, [pose]);

  const applyExpression = (id: Emotion) => {
    const e = EXPRESSIONS[id];
    setExpr(id);
    setParams((prev) => ({
      ...prev,
      ParamEyeOpen: e.eyeOpen,
      ParamMouthOpen: e.mouthOpen,
      ParamBrow: e.brow,
      ParamBlush: e.blush,
      ParamAngleZ: e.headTilt,
      ParamAngleY: e.headY,
    }));
  };

  const reset = () => {
    setParams(defaultParams());
    setExpr('neutral');
  };

  return (
    <div className="studio-backdrop" onPointerDown={(e) => e.target === e.currentTarget && setStudioOpen(false)}>
      <div className="studio" role="dialog" aria-label="模型工坊">
        <div className="studio-col left">
          <div className="studio-head">
            <ScanLine size={17} color="#a78bfa" />
            <div>
              <div className="studio-title">模型工坊</div>
              <div className="studio-sub">
                {model.name} · {model.format} v{model.formatVersion}
              </div>
            </div>
            <button className="studio-tool" style={{ marginLeft: 'auto' }} onClick={() => setStudioOpen(false)}>
              <X size={13} style={{ display: 'inline', verticalAlign: '-2px' }} /> 关闭
            </button>
          </div>
          <div className="studio-body">
            <div className="studio-note" style={{ marginBottom: 12 }}>
              拖动参数，实时查看骨骼、网格与物理。这里的参数命名与 Live2D Cubism 的 Param* 约定保持一致。
            </div>
            {model.parameters.map((param) => (
              <div className="param-row" key={param.id}>
                <div className="param-top">
                  <span>
                    {param.label} <code>{param.id}</code>
                  </span>
                  <span>{(params[param.id] ?? 0).toFixed(2)}</span>
                </div>
                <input
                  className="param-range"
                  type="range"
                  min={param.min}
                  max={param.max}
                  step={0.01}
                  value={params[param.id] ?? param.default}
                  onChange={(e) => setParams((prev) => ({ ...prev, [param.id]: Number(e.target.value) }))}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="studio-preview">
          <div className="studio-toolbar">
            <button className={`studio-tool ${showBones ? 'active' : ''}`} onClick={() => setShowBones(!showBones)}>
              <Bone size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> 骨骼
            </button>
            <button className={`studio-tool ${showWire ? 'active' : ''}`} onClick={() => setShowWire(!showWire)}>
              <Grid3x3 size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> 网格
            </button>
            <button className="studio-tool" onClick={reset}>
              <RotateCcw size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> 重置
            </button>
            <button
              className="studio-tool"
              onClick={() => {
                if (svgRef.current) void exportPosePng(svgRef.current, palette, `zhuopet-${character.id}-pose.png`);
              }}
            >
              <ImageIcon size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> 导出 PNG
            </button>
          </div>
          <div className="studio-svg">
            <CharacterSvg
              svgRef={svgRef}
              pose={pose}
              palette={palette}
              hairstyle="twin"
              accessory="cat"
              showBuddy
            />
            {(showBones || showWire) && (
              <svg className="overlay-svg" viewBox="0 0 600 820" preserveAspectRatio="xMidYMid meet">
                {showWire &&
                  boxes.map((box, i) => (
                    <rect
                      key={`${box.label}-${i}`}
                      x={box.x}
                      y={box.y}
                      width={box.w}
                      height={box.h}
                      fill="rgba(124,245,212,0.04)"
                      stroke="rgba(124,245,212,0.45)"
                      strokeWidth="1"
                    />
                  ))}
                {showBones && (
                  <>
                    {bones.lines.map(([a, b], i) => (
                      <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="rgba(255,158,196,0.85)" strokeWidth="2.5" strokeLinecap="round" />
                    ))}
                    {bones.joints.map((joint, i) => (
                      <circle key={i} cx={joint[0]} cy={joint[1]} r="5" fill="#1b1733" stroke="#7cf5d4" strokeWidth="2.5" />
                    ))}
                  </>
                )}
              </svg>
            )}
          </div>
          <div className="studio-badge">
            {model.canvas.width}×{model.canvas.height} · {model.parts.length} parts · {model.parameters.length} params
          </div>
          <div className="studio-mobile-note" style={{ position: 'absolute', bottom: 44, left: 12, right: 12, zIndex: 5 }}>
            <div className="studio-note">桌面端可查看完整参数与部件列表。</div>
          </div>
        </div>

        <div className="studio-col right">
          <div className="studio-head">
            <div>
              <div className="studio-title">表情 / 部件</div>
              <div className="studio-sub">点击部件可在预览中高亮</div>
            </div>
          </div>
          <div className="studio-body">
            <div className="studio-note" style={{ marginBottom: 8 }}>
              表情预设
            </div>
            <div className="expr-grid">
              {(Object.keys(EXPRESSIONS) as Emotion[]).map((id) => (
                <button key={id} className={`expr-btn ${expr === id ? 'active' : ''}`} onClick={() => applyExpression(id)}>
                  {EXPRESSIONS[id].label}
                </button>
              ))}
            </div>

            <div className="studio-note" style={{ margin: '14px 0 8px' }}>
              部件层级（z-order）
            </div>
            {[...model.parts]
              .sort((a, b) => a.z - b.z)
              .map((part) => (
                <button
                  key={part.id}
                  className="part-item"
                  style={{ width: '100%', border: 'none', background: 'transparent', textAlign: 'left' }}
                  onClick={() => setHighlight(highlight === part.id ? null : part.id)}
                >
                  <span className="z">{part.z}</span>
                  <span className="plabel">{part.label}</span>
                  <span className="pid">{part.id}</span>
                </button>
              ))}

            <div className="studio-note" style={{ margin: '14px 0 8px' }}>
              导出
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <button
                className="studio-tool"
                onClick={() =>
                  downloadBlob(
                    JSON.stringify({ ...model, palette, exportedPose: pose }, null, 2),
                    `${character.id}.model.json`,
                    'application/json',
                  )
                }
              >
                <Download size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> 下载模型 JSON
              </button>
              <button
                className="studio-tool"
                onClick={() => {
                  if (svgRef.current) downloadBlob(serializeSvg(svgRef.current, palette), `${character.id}.character.svg`, 'image/svg+xml');
                }}
              >
                <Download size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> 下载 SVG 模型
              </button>
            </div>

            <div className="studio-note" style={{ marginTop: 14 }}>
              这是一个原创的分层 Live2D 风格模型：{model.parts.length} 个可动部件、{model.parameters.length} 组参数、物理发梢与表情差分。
              它不是 Live2D 官方 .moc3 格式，但参数命名与 Cubism 对齐，方便迁移。
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
