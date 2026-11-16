"use client";

import { useEffect, useRef } from "react";

/** Minimal 3D backdrop — perspective plane + a few quiet depth pieces. */
export function AuthAtmosphere() {
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const fine = window.matchMedia("(pointer: fine)").matches;
    if (reduce || !fine) return;

    let frame = 0;
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;

    const onMove = (e: PointerEvent) => {
      targetX = (e.clientX / window.innerWidth - 0.5) * 2;
      targetY = (e.clientY / window.innerHeight - 0.5) * 2;
    };

    const tick = () => {
      currentX += (targetX - currentX) * 0.05;
      currentY += (targetY - currentY) * 0.05;
      stage.style.setProperty("--auth-px", currentX.toFixed(4));
      stage.style.setProperty("--auth-py", currentY.toFixed(4));
      frame = requestAnimationFrame(tick);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    frame = requestAnimationFrame(tick);
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div aria-hidden className="auth-3d pointer-events-none absolute inset-0 overflow-hidden">
      <div className="auth-3d-base" />
      <div className="auth-3d-vignette" />
      <div ref={stageRef} className="auth-3d-stage">
        <div className="auth-3d-world">
          <div className="auth-3d-floor" />
          <div className="auth-3d-orb" />
          <div className="auth-3d-slab auth-3d-slab-a" />
          <div className="auth-3d-slab auth-3d-slab-b" />
        </div>
      </div>
    </div>
  );
}
