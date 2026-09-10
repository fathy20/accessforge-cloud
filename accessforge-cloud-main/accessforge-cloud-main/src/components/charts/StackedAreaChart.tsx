import { useId, useState } from "react";

export interface AreaSeries {
  key: string;
  label: string;
  /** Any CSS colour, including `var(--token)`. */
  color: string;
}

export interface AreaPoint {
  label: string;
  values: Record<string, number>;
}

interface StackedAreaChartProps {
  series: AreaSeries[];
  points: AreaPoint[];
  height?: number;
  className?: string;
}

const PAD = { top: 12, right: 12, bottom: 24, left: 28 };
const WIDTH = 600;

/**
 * Dependency-free time-series area chart: two or three thin lines with soft
 * fills, a recessive grid, a legend, and a crosshair tooltip. Replaces the
 * recharts bundle (~400 KB) that the dashboard alone used to pull in.
 */
export function StackedAreaChart({
  series,
  points,
  height = 220,
  className,
}: StackedAreaChartProps) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const plotW = WIDTH - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const maxValue = Math.max(
    1,
    ...points.flatMap((point) => series.map((s) => point.values[s.key] ?? 0)),
  );
  const yTicks = niceTicks(maxValue);
  const yMax = yTicks[yTicks.length - 1] || 1;

  const x = (index: number) =>
    PAD.left + (points.length <= 1 ? plotW / 2 : (index / (points.length - 1)) * plotW);
  const y = (value: number) => PAD.top + plotH - (value / yMax) * plotH;

  const linePath = (key: string) =>
    points
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.values[key] ?? 0).toFixed(1)}`)
      .join(" ");
  const areaPath = (key: string) =>
    points.length === 0
      ? ""
      : `${linePath(key)} L${x(points.length - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`;

  const onMove = (event: React.MouseEvent<SVGSVGElement>) => {
    if (points.length === 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * WIDTH;
    const ratio = Math.min(1, Math.max(0, (px - PAD.left) / plotW));
    setHover(Math.round(ratio * (points.length - 1)));
  };

  const hovered = hover !== null ? points[hover] : null;
  const labelEvery = Math.max(1, Math.ceil(points.length / 7));

  return (
    <figure className={className}>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="h-auto w-full select-none"
        role="img"
        aria-label={series.map((s) => s.label).join(", ")}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`${gradientId}-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={s.color} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>

        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--border)"
              strokeDasharray="3 3"
            />
            <text
              x={PAD.left - 6}
              y={y(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-fg-muted"
              fontSize="10"
            >
              {tick}
            </text>
          </g>
        ))}

        {points.map((point, index) =>
          index % labelEvery === 0 || index === points.length - 1 ? (
            <text
              key={point.label}
              x={x(index)}
              y={height - 6}
              textAnchor="middle"
              className="fill-fg-muted"
              fontSize="10"
            >
              {point.label}
            </text>
          ) : null,
        )}

        {series.map((s) => (
          <g key={s.key}>
            <path d={areaPath(s.key)} fill={`url(#${gradientId}-${s.key})`} />
            <path
              d={linePath(s.key)}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </g>
        ))}

        {hovered && hover !== null && (
          <g pointerEvents="none">
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD.top}
              y2={PAD.top + plotH}
              stroke="var(--fg-muted)"
              strokeWidth={1}
            />
            {series.map((s) => (
              <circle
                key={s.key}
                cx={x(hover)}
                cy={y(hovered.values[s.key] ?? 0)}
                r={4}
                fill={s.color}
                stroke="var(--card)"
                strokeWidth={2}
              />
            ))}
          </g>
        )}
      </svg>

      <figcaption className="mt-2 flex flex-wrap items-center justify-between gap-2 text-caption text-fg-muted">
        <ul className="flex flex-wrap gap-3" aria-label="Legend">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span
                className="size-2 rounded-full"
                style={{ background: s.color }}
                aria-hidden="true"
              />
              {s.label}
            </li>
          ))}
        </ul>
        <span className="numeric-tabular min-h-4 text-fg-secondary" aria-live="polite">
          {hovered
            ? `${hovered.label} · ${series.map((s) => `${s.label} ${hovered.values[s.key] ?? 0}`).join(" · ")}`
            : ""}
        </span>
      </figcaption>
    </figure>
  );
}

/** Integer axis ticks (the series are counts, so a 0.5 tick is meaningless). */
function niceTicks(max: number): number[] {
  const rawStep = Math.max(1, max / 4);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= top; value += step) ticks.push(value);
  return ticks;
}
