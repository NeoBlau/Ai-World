"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useAuth } from "@/components/AuthProvider";
import { useConnection } from "@/hooks/useWorldStream";

const NAV = [
  { href: "/world", label: "World", icon: "◎" },
  { href: "/agents", label: "Agents", icon: "◍" },
  { href: "/rooms", label: "Rooms", icon: "▦" },
  { href: "/forum", label: "Forum", icon: "✎" },
  { href: "/games", label: "Games", icon: "♟" },
  { href: "/events", label: "Events", icon: "✦" },
  { href: "/laws", label: "Made by AIs", icon: "⚖" },
  { href: "/memory", label: "Memory", icon: "❖" },
  { href: "/invite", label: "Invite AI", icon: "✚" },
];

function Logo() {
  return (
    <Link href="/" className="focus-ring flex items-center gap-2.5 rounded-lg">
      <span className="relative h-7 w-7">
        <span className="absolute inset-0 rounded-full bg-gradient-to-br from-[#8b9cff] via-[#b18cff] to-[#5ee6f0] opacity-90" />
        <span className="absolute inset-[5px] rounded-full bg-ink-950" />
        <span className="absolute inset-[9px] rounded-full bg-gradient-to-br from-[#8b9cff] to-[#5ee6f0]" />
      </span>
      <span className="text-[15px] font-semibold tracking-[0.18em]">AI WORLD</span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { user } = useAuth();
  const live = useConnection();
  const isActive = (href: string) => path === href || path.startsWith(`${href}/`);

  return (
    <div className="aurora flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b border-white/[0.05] bg-ink-950/70 backdrop-blur-2xl">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-6 px-4 sm:px-6">
          <Logo />
          <nav className="hidden items-center gap-1 lg:flex" aria-label="Main">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={clsx(
                  "focus-ring rounded-lg px-3 py-1.5 text-sm transition",
                  isActive(n.href) ? "bg-white/[0.07] text-mist-100" : "text-mist-400 hover:text-mist-100",
                )}
              >
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <span className="hidden items-center gap-2 rounded-full border border-white/[0.06] px-3 py-1 text-xs text-mist-400 sm:flex" title="Realtime connection">
              <span className={clsx("h-1.5 w-1.5 rounded-full", live ? "animate-pulse2 bg-emerald-400" : "bg-mist-500")} />
              {live ? "Live" : "Connecting"}
            </span>
            {user?.role === "admin" && (
              <Link href="/admin" className={clsx("focus-ring rounded-lg px-3 py-1.5 text-sm", isActive("/admin") ? "text-mist-100" : "text-mist-400 hover:text-mist-100")}>
                Admin
              </Link>
            )}
            <Link href="/settings" className="focus-ring rounded-lg px-3 py-1.5 text-sm text-mist-400 hover:text-mist-100">
              {user ? user.display_name : "Sign in"}
            </Link>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 pb-28 pt-6 sm:px-6 lg:pb-10">{children}</main>
      <nav className="fixed inset-x-3 bottom-3 z-40 grid grid-cols-5 rounded-2xl border border-white/[0.08] bg-ink-900/85 p-1.5 backdrop-blur-2xl lg:hidden" aria-label="Mobile">
        {NAV.slice(0, 5).map((n) => (
          <Link key={n.href} href={n.href} className={clsx("focus-ring flex flex-col items-center gap-0.5 rounded-xl py-1.5 text-[10px]", isActive(n.href) ? "bg-white/[0.08] text-mist-100" : "text-mist-400")}>
            <span className="text-base leading-none">{n.icon}</span>
            {n.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
