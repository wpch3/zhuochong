import { useEffect, useRef } from 'react';
import rawSvg from '../assets/character.svg?raw';
import { applyCharacterStyle, applyPose } from '../model/applyPose';
import type { Pose } from '../model/types';

interface CharacterSvgProps {
  svgRef?: React.MutableRefObject<SVGSVGElement | null>;
  pose?: Pose;
  form?: 'chibi' | 'teen';
  palette: Record<string, string>;
  hairstyle: string;
  accessory: string;
  showBuddy: boolean;
  className?: string;
  onReady?: (svg: SVGSVGElement) => void;
}

/**
 * Renders the layered character SVG once, then mutates transforms/opacity
 * imperatively. This keeps 60fps animation out of React's render loop.
 */
export function CharacterSvg({
  svgRef,
  pose,
  form = 'chibi',
  palette,
  hairstyle,
  accessory,
  showBuddy,
  className,
  onReady,
}: CharacterSvgProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const localRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = hostRef.current?.querySelector('svg') ?? null;
    if (!svg) return;
    localRef.current = svg;
    if (svgRef) svgRef.current = svg;
    applyCharacterStyle(svg, { palette, hairstyle, accessory, showBuddy });
    onReady?.(svg);
    return () => {
      if (svgRef && svgRef.current === svg) svgRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (localRef.current) {
      applyCharacterStyle(localRef.current, { palette, hairstyle, accessory, showBuddy });
    }
  }, [palette, hairstyle, accessory, showBuddy]);

  useEffect(() => {
    if (pose && localRef.current) applyPose(localRef.current, pose, form);
  }, [pose, form]);

  return <div ref={hostRef} className={className} dangerouslySetInnerHTML={{ __html: rawSvg }} />;
}
