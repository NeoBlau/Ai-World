import type { Creation } from "@/types/world";

function rng(seed: number) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 10000) / 10000;
  };
}

/** Renders an agent's generative artwork deterministically from its recipe. */
export function ArtPiece({ data, title }: { data: Creation["data"]; title: string }) {
  const r = rng(data.seed ?? 1);
  const pal = data.palette?.length ? data.palette : ["#8b9cff", "#b18cff", "#5ee6f0"];
  const n = data.density ?? 16;
  const pick = () => pal[Math.floor(r() * pal.length)];
  const shapes = Array.from({ length: n }, (_, i) => {
    const x = r() * 100, y = r() * 100, s = 6 + r() * 30, c = pick(), o = 0.25 + r() * 0.55;
    switch (data.shapes) {
      case "polygons":
        return <polygon key={i} points={`${x},${y} ${x + s},${y + r() * s} ${x + r() * s},${y + s}`} fill={c} opacity={o} />;
      case "grid":
        return <rect key={i} x={Math.floor(x / 10) * 10} y={Math.floor(y / 10) * 10} width={10} height={10} fill={c} opacity={o} />;
      case "strokes":
        return <path key={i} d={`M${x},${y} q${s},${-s} ${s * 2},0`} stroke={c} strokeWidth={0.6 + r() * 2} fill="none" opacity={o} strokeLinecap="round" />;
      case "lines":
        return <line key={i} x1={0} y1={y} x2={100} y2={y + (r() - 0.5) * 20} stroke={c} strokeWidth={0.4} opacity={o} />;
      case "blobs":
        return <ellipse key={i} cx={x} cy={y} rx={s} ry={s * (0.5 + r())} fill={c} opacity={o * 0.6} />;
      default:
        return <circle key={i} cx={50} cy={50} r={s + i * 1.5} fill="none" stroke={c} strokeWidth={0.5 + r()} opacity={o} strokeDasharray={`${r() * 20} ${r() * 10}`} />;
    }
  });
  return (
    <svg viewBox="0 0 100 100" className="aspect-square w-full bg-ink-950" role="img" aria-label={title}>
      <defs><filter id={`b${data.seed}`}><feGaussianBlur stdDeviation={data.shapes === "blobs" ? 2 : 0.2} /></filter></defs>
      <g filter={`url(#b${data.seed})`}>{shapes}</g>
    </svg>
  );
}
