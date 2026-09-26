import clsx from "clsx";

import { ACTIVITY_COLOR } from "@/lib/format";
import type { ActivityKind, Avatar } from "@/types/world";

/** Soft generative orb avatar built from the agent's palette. */
export function AgentAvatar({ avatar, name, size = 40, activity, className, ring = true }: {
  avatar: Avatar; name: string; size?: number; activity?: ActivityKind | null; className?: string; ring?: boolean;
}) {
  const [a = "#8b9cff", b = "#b18cff", c = "#5ee6f0"] = avatar?.palette ?? [];
  const glyph = (avatar?.glyph ?? name.slice(0, 1)).slice(0, 2);
  const id = `g-${name.replace(/\W/g, "")}-${size}`;
  return (
    <span className={clsx("relative inline-flex shrink-0", className)} style={{ width: size, height: size }} title={name}>
      <svg viewBox="0 0 40 40" width={size} height={size} aria-hidden>
        <defs>
          <radialGradient id={id} cx="30%" cy="28%" r="80%">
            <stop offset="0%" stopColor="#fff" stopOpacity="0.85" />
            <stop offset="22%" stopColor={a} />
            <stop offset="62%" stopColor={b} />
            <stop offset="100%" stopColor={c} />
          </radialGradient>
        </defs>
        <circle cx="20" cy="20" r="19" fill={`url(#${id})`} />
        <circle cx="20" cy="20" r="19" fill="none" stroke="rgba(255,255,255,0.18)" />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-semibold text-ink-950/80" style={{ fontSize: size * 0.36 }}>
        {glyph}
      </span>
      {ring && activity && (
        <span
          className={clsx("absolute -bottom-0.5 -right-0.5 rounded-full border-2 border-ink-900", activity !== "resting" && activity !== "idle" && "animate-pulse2")}
          style={{ width: Math.max(8, size * 0.28), height: Math.max(8, size * 0.28), background: ACTIVITY_COLOR[activity] }}
        />
      )}
    </span>
  );
}
