/**
 * Gradient-ring avatar holding the REDSEA mark.
 *
 * Built as padding on a conic-gradient background with a solid inner circle,
 * rather than a border-image or a mask: the inner element is a real box, so an
 * <img> child sits inside it normally and `object-fit: contain` keeps the logo
 * from stretching. A mask would clip the image to the ring instead.
 */
export function CopilotAvatar({
  size = 34,
  alt,
}: {
  size?: number;
  alt: string;
}) {
  const inner = size - 6;
  return (
    <span
      className="grid shrink-0 place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background:
          "conic-gradient(from 210deg, var(--copilot-accent-1), var(--copilot-accent-2), var(--copilot-accent-3), var(--copilot-accent-1))",
      }}
    >
      <span
        className="grid place-items-center overflow-hidden rounded-full"
        style={{ width: inner, height: inner, background: "var(--copilot-panel)" }}
      >
        <img
          src="/logo.png"
          alt={alt}
          width={inner - 6}
          height={inner - 6}
          className="object-contain"
          style={{ width: inner - 6, height: inner - 6 }}
        />
      </span>
    </span>
  );
}
