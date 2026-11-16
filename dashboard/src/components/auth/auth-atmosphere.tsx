"use client";

import { useEffect, useRef } from "react";

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
      const { innerWidth, innerHeight } = window;
      targetX = ((e.clientX / innerWidth) - 0.5) * 2;
      targetY = ((e.clientY / innerHeight) - 0.5) * 2;
    };

    const tick = () => {
      currentX += (targetX - currentX) * 0.06;
      currentY += (targetY - currentY) * 0.06;
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
          <div className="auth-3d-horizon" />

          <div className="auth-3d-orb auth-3d-orb-core">
            <span className="auth-3d-orb-shine" />
            <span className="auth-3d-orb-rim" />
          </div>
          <div className="auth-3d-orb auth-3d-orb-sat-a">
            <span className="auth-3d-orb-shine" />
          </div>
          <div className="auth-3d-orb auth-3d-orb-sat-b">
            <span className="auth-3d-orb-shine" />
          </div>

          <div className="auth-3d-panel auth-3d-panel-a" />
          <div className="auth-3d-panel auth-3d-panel-b" />
          <div className="auth-3d-panel auth-3d-panel-c" />
          <div className="auth-3d-panel auth-3d-panel-d" />

          <div className="auth-3d-beam auth-3d-beam-a" />
          <div className="auth-3d-beam auth-3d-beam-b" />
        </div>
      </div>
    </div>
  );
}
