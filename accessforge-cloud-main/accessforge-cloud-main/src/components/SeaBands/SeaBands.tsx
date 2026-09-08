/**
 * SeaBands — four layered wave bands anchored to the bottom of the hero.
 *
 * Stacked back-to-front sand → coral → navy → turquoise, echoing the order of
 * the strokes in the REDSEA mark. Each band scrolls horizontally at its own
 * speed and direction, so the layers separate into parallax rather than moving
 * as one sheet.
 *
 * Seamlessness: every band is a 600px tile whose sine completes a whole number
 * of periods across that tile, repeated with `mask-repeat: repeat-x`. The layer
 * is then 600px wider than the viewport and translated by exactly -600px, so
 * the loop point is invisible at any width.
 *
 * The SVG is used as a MASK, not as a background image — the shape comes from
 * the tile and the colour from a CSS custom property, so the bands re-tint with
 * the theme without regenerating any data URI.
 */

const TILE = 600;

type Band = {
  token: string;
  /** must divide TILE exactly, or the tile seam becomes visible */
  wavelength: number;
  amplitude: number;
  /** band height in px */
  height: number;
  /** seconds for one full 600px traversal */
  duration: number;
  reverse: boolean;
};

// Back to front. Durations lengthen toward the back so distant layers drift
// slower, which is what reads as depth.
const BANDS: ReadonlyArray<Band> = [
  { token: "--wave-sand", wavelength: 600, amplitude: 30, height: 190, duration: 30, reverse: false },
  { token: "--wave-coral", wavelength: 300, amplitude: 26, height: 155, duration: 22, reverse: true },
  { token: "--wave-navy", wavelength: 600, amplitude: 22, height: 120, duration: 15, reverse: false },
  { token: "--wave-teal", wavelength: 300, amplitude: 18, height: 78, duration: 10, reverse: true },
];

/**
 * One tile as an alpha mask: an opaque sine-topped block on transparency.
 * Sampled rather than approximated with beziers — it is computed once at module
 * load, so the extra points cost nothing and the curve is exact.
 */
function tileMask(wavelength: number, amplitude: number, height: number) {
  const mid = amplitude + 2;
  const pts: string[] = [];
  for (let x = 0; x <= TILE; x += 6) {
    const y = mid - amplitude * Math.sin((2 * Math.PI * x) / wavelength);
    pts.push(`${x},${y.toFixed(2)}`);
  }
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${TILE}" height="${height}" ` +
    `viewBox="0 0 ${TILE} ${height}" preserveAspectRatio="none">` +
    `<path d="M ${pts.join(" L ")} L ${TILE},${height} L 0,${height} Z" fill="#000"/></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

export function SeaBands({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute inset-x-0 bottom-0 z-0 overflow-hidden ${className}`}
      style={{ height: BANDS[0].height }}
    >
      {BANDS.map((band) => {
        const mask = tileMask(band.wavelength, band.amplitude, band.height);
        return (
          <div
            key={band.token}
            className="seaband absolute bottom-0 left-0"
            style={{
              height: band.height,
              // 600px of overhang gives the -600px translate somewhere to go.
              width: `calc(100% + ${TILE}px)`,
              backgroundColor: `var(${band.token})`,
              maskImage: mask,
              WebkitMaskImage: mask,
              maskRepeat: "repeat-x",
              WebkitMaskRepeat: "repeat-x",
              maskSize: `${TILE}px 100%`,
              WebkitMaskSize: `${TILE}px 100%`,
              animationName: "seaband-drift",
              animationDuration: `${band.duration}s`,
              animationTimingFunction: "linear",
              animationIterationCount: "infinite",
              animationDirection: band.reverse ? "reverse" : "normal",
            }}
          />
        );
      })}
    </div>
  );
}
