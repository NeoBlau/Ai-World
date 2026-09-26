"use client";

import clsx from "clsx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Panel({ className, children, title, action, padded = true }: { className?: string; children: ReactNode; title?: ReactNode; action?: ReactNode; padded?: boolean }) {
  return (
    <section className={clsx("glass flex min-h-0 flex-col", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-5 pt-4">
          <h2 className="label">{title}</h2>
          {action}
        </header>
      )}
      <div className={clsx("min-h-0 flex-1", padded && "p-5 pt-3")}>{children}</div>
    </section>
  );
}

export function Button({ variant = "primary", className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "subtle" }) {
  return (
    <button
      {...rest}
      className={clsx(
        "focus-ring inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition duration-200 disabled:cursor-not-allowed disabled:opacity-40",
        variant === "primary" && "bg-gradient-to-r from-[#8b9cff] to-[#9f8cff] text-ink-950 shadow-glow hover:brightness-110",
        variant === "ghost" && "border border-white/10 bg-white/[0.03] text-mist-100 hover:bg-white/[0.07]",
        variant === "subtle" && "text-mist-300 hover:bg-white/[0.05] hover:text-mist-100",
        variant === "danger" && "border border-rose-400/20 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20",
        className,
      )}
    />
  );
}

export function Badge({ children, color, className }: { children: ReactNode; color?: string; className?: string }) {
  return (
    <span
      className={clsx("inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-0.5 text-[11px] font-medium text-mist-300", className)}
      style={color ? { color, borderColor: `${color}33`, background: `${color}14` } : undefined}
    >
      {children}
    </span>
  );
}

export function Meter({ value, color = "#8b9cff", label }: { value: number; color?: string; label?: string }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className="space-y-1.5">
      {label && (
        <div className="flex justify-between text-xs text-mist-400">
          <span>{label}</span>
          <span className="tabular-nums text-mist-300">{Math.round(v)}</span>
        </div>
      )}
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]" role="meter" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${v}%`, background: `linear-gradient(90deg, ${color}99, ${color})` }} />
      </div>
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="glass p-5">
      <div className="label">{label}</div>
      <div className="mt-2 text-2xl font-semibold tabular-nums tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-xs text-mist-500">{hint}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex h-full min-h-24 items-center justify-center px-4 text-center text-sm text-mist-500">{children}</div>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-xl bg-white/[0.04]", className)} />;
}

const field = "focus-ring w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-2.5 text-sm text-mist-100 placeholder:text-mist-500 transition focus:border-accent/40";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(field, props.className)} />;
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={clsx(field, "resize-none", props.className)} />;
}
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={clsx(field, "appearance-none", props.className)} />;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-mist-400">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-mist-500">{hint}</span>}
    </label>
  );
}

export function PageHeader({ eyebrow, title, subtitle, action }: { eyebrow?: string; title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="animate-fade-up">
        {eyebrow && <div className="label mb-2">{eyebrow}</div>}
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
        {subtitle && <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-mist-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-3.5 py-2.5 text-sm text-rose-200">{children}</div>;
}
