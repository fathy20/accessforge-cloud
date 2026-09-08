/**
 * WaveEmblem — the REDSEA mark: two crossing wave ribbons.
 *
 * The mark is two blades, not four shapes. Each carries two of the brand's
 * colours along its length, which is why sampling the logo returns four hues at
 * roughly equal share (navy #0e4670, coral #ee5446, teal #38b6b6, sand #eed2a8):
 *
 *   upper blade   coral  →  sand
 *   lower blade   navy   →  teal
 *
 * Each blade is a tapered outline rather than a stroke — pointed at both tips,
 * fattest through the belly — generated from two sampled functions:
 *
 *   spine(t)     one full wave period, so the blade rises and falls once
 *   halfWidth(t) sin(pi*t)^0.6, which fattens the belly and sharpens the tips
 *                more than a plain sine taper does
 *
 * Colours come from CSS custom properties, so the mark re-tints with the theme.
 */

type Ribbon = {
  id: string;
  x0: number;
  x1: number;
  midY: number;
  amp: number;
  maxW: number;
  /** shifts where the crest falls along the blade */
  phase: number;
  /** the two colours carried along the blade, start → end */
  from: string;
  to: string;
  className: string;
};

// Lower blade first so the upper one crosses over it, as in the mark.
const RIBBONS: ReadonlyArray<Ribbon> = [
  {
    id: "rs-lower",
    x0: 4,
    x1: 96,
    midY: 38,
    amp: 12.5,
    maxW: 7.6,
    phase: 0.0,
    from: "var(--hero-navy)",
    to: "var(--hero-teal)",
    className: "wavemark-ribbon wavemark-ribbon--back",
  },
  {
    id: "rs-upper",
    x0: 10,
    x1: 102,
    midY: 26,
    amp: 12.5,
    maxW: 7.6,
    phase: 0.0,
    from: "var(--hero-coral)",
    to: "var(--hero-sandwave)",
    className: "wavemark-ribbon wavemark-ribbon--front",
  },
];

function ribbonPath({ x0, x1, midY, amp, maxW, phase }: Ribbon) {
  const STEPS = 80;
  const span = x1 - x0;
  const top: string[] = [];
  const bottom: string[] = [];

  for (let i = 0; i <= STEPS; i++) {
    const t = i / STEPS;
    const x = x0 + span * t;
    const y = midY - amp * Math.sin(2 * Math.PI * t + phase * Math.PI);
    const w = maxW * Math.pow(Math.sin(Math.PI * t), 0.6);
    top.push(`${x.toFixed(2)},${(y - w).toFixed(2)}`);
    bottom.push(`${x.toFixed(2)},${(y + w).toFixed(2)}`);
  }

  return `M ${top.join(" L ")} L ${bottom.reverse().join(" L ")} Z`;
}

const PATHS = RIBBONS.map((r) => ({ ...r, d: ribbonPath(r) }));

export function WaveEmblem({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 106 58"
      role="img"
      aria-label="REDSEA"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        {PATHS.map((r) => (
          // gradientUnits userSpaceOnUse so the hand-off lands at a fixed point
          // along the blade rather than inside its bounding box.
          <linearGradient
            key={r.id}
            id={r.id}
            gradientUnits="userSpaceOnUse"
            x1={r.x0}
            y1="0"
            x2={r.x1}
            y2="0"
          >
            {/* held flat at each end so both colours read as themselves, with a
                short hand-off across the middle rather than a long muddy blend */}
            <stop offset="0%" stopColor={r.from} />
            <stop offset="38%" stopColor={r.from} />
            <stop offset="64%" stopColor={r.to} />
            <stop offset="100%" stopColor={r.to} />
          </linearGradient>
        ))}
      </defs>

      {PATHS.map((r) => (
        <path key={r.id} className={r.className} d={r.d} fill={`url(#${r.id})`} />
      ))}
    </svg>
  );
}
