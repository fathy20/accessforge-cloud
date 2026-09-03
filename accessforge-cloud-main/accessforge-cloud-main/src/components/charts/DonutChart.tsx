import { useState } from "react";

export interface DonutSlice {
  key: string;
  label: string;
  value: number;
  color: string;
}

interface DonutChartProps {
  slices: DonutSlice[];
  /** Text shown in the centre; defaults to the total. */
  centerLabel?: string;
  className?: string;
}

const SIZE = 160;
const RADIUS = 64;
const STROKE = 18;
const GAP_DEGREES = 2;

/** Dependency-free donut with a 2° surface gap between slices and a legend that doubles as the data table. */
export function DonutChart({ slices, centerLabel, className }: DonutChartProps) {
  const [hover, setHover] = useState<string | null>(null);
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  const circumference = 2 * Math.PI * RADIUS;

  let cursor = -90;
  const arcs = slices
    .filter((slice) => slice.value > 0)
    .map((slice) => {
      const sweep = (slice.value / total) * 360;
      const start = cursor;
      cursor += sweep;
      const visible = Math.max(0, sweep - (slices.length > 1 ? GAP_DEGREES : 0));
      return { ...slice, start, dash: (visible / 360) * circumference };
    });

  const hovered = arcs.find((arc) => arc.key === hover);

  return (
    <figure className={`flex flex-wrap items-center justify-center gap-6 ${className ?? ""}`}>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="size-40 shrink-0"
        role="img"
        aria-label={centerLabel}
      >
        {arcs.map((arc) => (
          <circle
            key={arc.key}
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={arc.color}
            strokeWidth={hover === arc.key ? STROKE + 4 : STROKE}
            strokeDasharray={`${arc.dash} ${circumference - arc.dash}`}
            transform={`rotate(${arc.start + GAP_DEGREES / 2} ${SIZE / 2} ${SIZE / 2})`}
            className="transition-[stroke-width] duration-150"
            onMouseEnter={() => setHover(arc.key)}
            onMouseLeave={() => setHover(null)}
          >
            <title>{`${arc.label}: ${arc.value}`}</title>
          </circle>
        ))}
        <text
          x={SIZE / 2}
          y={SIZE / 2 - 4}
          textAnchor="middle"
          className="fill-fg-primary"
          fontSize="22"
          fontWeight="700"
        >
          {hovered ? hovered.value : total}
        </text>
        <text
          x={SIZE / 2}
          y={SIZE / 2 + 14}
          textAnchor="middle"
          className="fill-fg-muted"
          fontSize="10"
        >
          {hovered ? hovered.label : centerLabel}
        </text>
      </svg>
      <figcaption>
        <ul className="space-y-1.5 text-body" aria-label="Legend">
          {slices.map((slice) => (
            <li
              key={slice.key}
              className="flex items-center gap-2"
              onMouseEnter={() => setHover(slice.key)}
              onMouseLeave={() => setHover(null)}
            >
              <span
                className="size-2.5 rounded-full"
                style={{ background: slice.color }}
                aria-hidden="true"
              />
              <span className="text-fg-secondary">{slice.label}</span>
              <span className="numeric-tabular ms-auto ps-4 text-fg-primary">{slice.value}</span>
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}
