"use client";

import { useEffect, type ReactNode, type RefObject } from "react";

/**
 * Full-bleed canvas the task runner draws the dots onto.
 * Sizes itself to its parent (CSS pixels) and on window resize.
 */
export default function TaskCanvas({
  canvasRef,
  children,
}: {
  canvasRef: RefObject<HTMLCanvasElement>;
  children?: ReactNode;
}) {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [canvasRef]);

  return (
    <div className="task-canvas-wrap">
      <canvas ref={canvasRef} className="task-canvas" />
      {children}
    </div>
  );
}
