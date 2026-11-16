"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";

export type PieSlice = {
  label: string;
  value: number;
  color: string;
};

const SIZE = 320;
const CX = SIZE / 2;
const CY = SIZE / 2;
const RADIUS = 118;
const INNER = 68;

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  };
}

function donutSlicePath(
  cx: number,
  cy: number,
  outer: number,
  inner: number,
  startAngle: number,
  endAngle: number,
) {
  const large = endAngle - startAngle > 180 ? 1 : 0;
  const o1 = polar(cx, cy, outer, startAngle);
  const o2 = polar(cx, cy, outer, endAngle);
  const i1 = polar(cx, cy, inner, endAngle);
  const i2 = polar(cx, cy, inner, startAngle);
  return [
    `M ${o1.x} ${o1.y}`,
    `A ${outer} ${outer} 0 ${large} 1 ${o2.x} ${o2.y}`,
    `L ${i1.x} ${i1.y}`,
    `A ${inner} ${inner} 0 ${large} 0 ${i2.x} ${i2.y}`,
    "Z",
  ].join(" ");
}

export function ConversionPieChart({
  slices,
  title = "Conversion",
}: {
  slices: PieSlice[];
  title?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const total = useMemo(
    () => slices.reduce((sum, s) => sum + Math.max(0, s.value), 0),
    [slices],
  );

  const arcs = useMemo(() => {
    if (total <= 0) return [];
    let angle = 0;
    return slices.map((slice, index) => {
      const portion = (Math.max(0, slice.value) / total) * 360;
      // Avoid zero-length arcs that SVG can't render cleanly
      const sweep = Math.max(portion, 0.01);
      const start = angle;
      const end = angle + sweep;
      angle = end;
      return {
        ...slice,
        index,
        start,
        end,
        pct: (slice.value / total) * 100,
        path: donutSlicePath(CX, CY, RADIUS, INNER, start, end - 0.001),
      };
    });
  }, [slices, total]);

  const active = hover !== null ? arcs[hover] : null;
  const centerLabel = active?.label ?? title;
  const centerValue = active
    ? active.value.toLocaleString()
    : total.toLocaleString();
  const centerPct = active ? `${active.pct.toFixed(1)}%` : "100%";

  return (
    <div className="flex w-full flex-col items-center justify-center gap-8 lg:flex-row lg:gap-14">
      <div className="relative h-[320px] w-[320px] shrink-0">
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="h-full w-full overflow-visible"
          role="img"
          aria-label={`${title} pie chart`}
        >
          <circle
            cx={CX}
            cy={CY}
            r={RADIUS + 2}
            fill="none"
            stroke="var(--border-subtle)"
            strokeWidth="1"
          />
          {arcs.map((arc) => {
            const isActive = hover === arc.index;
            const dimmed = hover !== null && !isActive;
            return (
              <path
                key={arc.label}
                d={arc.path}
                fill={arc.color}
                opacity={dimmed ? 0.35 : 1}
                className="cursor-pointer transition-[opacity,transform] duration-150"
                style={{
                  transformOrigin: `${CX}px ${CY}px`,
                  transform: isActive ? "scale(1.03)" : "scale(1)",
                }}
                onMouseEnter={() => setHover(arc.index)}
                onMouseLeave={() => setHover(null)}
              />
            );
          })}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <p className="max-w-[8rem] truncate text-2xs font-semibold uppercase tracking-[0.12em] text-foreground-faint">
            {centerLabel}
          </p>
          <p className="mt-1 text-3xl font-semibold tabular-nums tracking-tight text-foreground">
            {centerValue}
          </p>
          <p className="mt-1 text-body tabular-nums text-foreground-muted">{centerPct}</p>
        </div>
      </div>

      <ul className="w-full max-w-sm space-y-2">
        {arcs.map((arc) => {
          const isActive = hover === arc.index;
          return (
            <li key={arc.label}>
              <button
                type="button"
                onMouseEnter={() => setHover(arc.index)}
                onMouseLeave={() => setHover(null)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors",
                  isActive
                    ? "bg-surface-overlay text-foreground shadow-[inset_2px_0_0_0_var(--brand)]"
                    : "text-foreground-secondary hover:bg-surface-overlay/60",
                )}
              >
                <span
                  className="h-3 w-3 shrink-0 rounded-full"
                  style={{ backgroundColor: arc.color }}
                />
                <span className="min-w-0 flex-1 truncate text-body font-medium">
                  {arc.label}
                </span>
                <span className="tabular-nums text-body text-foreground-faint">
                  {arc.value.toLocaleString()}
                </span>
                <span className="w-14 text-right tabular-nums text-caption text-foreground-faint">
                  {arc.pct.toFixed(0)}%
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
