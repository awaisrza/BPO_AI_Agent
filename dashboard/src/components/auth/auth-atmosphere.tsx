"use client";

import { useEffect, useRef } from "react";

/** Minimal CSS 3D backdrop — scales motion/size with the viewport. */
export function AuthAtmosphere() {
  const rootRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    const stage = stageRef.current;
    if (!root || !stage) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    const fine = window.matchMedia("(pointer: fine)");

    const syncScale = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      // 0 → narrow phone, 1 → wide desktop
      const scale = Math.min(1, Math.max(0, (w - 360) / (1280 - 360)));
      root.style.setProperty("--auth-vw-scale", scale.toFixed(3));
      root.style.setProperty("--auth-vh", `${h}px`);
    };

    syncScale();
    window.addEventListener("resize", syncScale, { passive: true });

    let frame = 0;
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;

    const onMove = (e: PointerEvent) => {
      if (reduce.matches || !fine.matches) return;
      targetX = e.clientX / window.innerWidth - 0.5;
      targetY = e.clientY / window.innerHeight - 0.5;
    };

    const tick = () => {
      if (!reduce.matches && fine.matches) {
        currentX += (targetX * 2 - currentX) * 0.05;
        currentY += (targetY * 2 - currentY) * 0.05;
        stage.style.setProperty("--auth-px", currentX.toFixed(4));
        stage.style.setProperty("--auth-py", currentY.toFixed(4));
      }
      frame = requestAnimationFrame(tick);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    frame = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("resize", syncScale);
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div
      ref={rootRef}
      aria-hidden
      className="auth-3d pointer-events-none absolute inset-0 overflow-hidden"
    >
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
