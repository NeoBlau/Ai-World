"use client";

import clsx from "clsx";

const GLYPH: Record<string, string> = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙", k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };

/** Expand the piece-placement field of a FEN string into an 8x8 grid. */
export function fenToGrid(fen: string): (string | null)[][] {
  const rows = fen.split(" ")[0].split("/");
  return rows.map((row) => {
    const out: (string | null)[] = [];
    for (const ch of row) {
      if (/\d/.test(ch)) for (let i = 0; i < Number(ch); i++) out.push(null);
      else out.push(ch);
    }
    return out;
  });
}

export function ChessBoard({ fen, size = "full" }: { fen: string; size?: "full" | "mini" }) {
  const grid = fenToGrid(fen);
  return (
    <div className={clsx("grid grid-cols-8 overflow-hidden rounded-xl border border-white/10", size === "mini" ? "w-40" : "w-full max-w-[520px]")} role="img" aria-label="Chess board">
      {grid.flatMap((row, r) =>
        row.map((p, c) => (
          <div key={`${r}-${c}`} className={clsx("flex aspect-square items-center justify-center", (r + c) % 2 === 0 ? "bg-[#1f2536]" : "bg-[#141926]")}>
            {p && (
              <span className={clsx(size === "mini" ? "text-sm" : "text-[clamp(18px,5vw,40px)]", p === p.toUpperCase() ? "text-[#eef1f8]" : "text-[#9aa7ff]")} style={{ textShadow: "0 2px 8px rgba(0,0,0,.6)" }}>
                {GLYPH[p]}
              </span>
            )}
          </div>
        )),
      )}
    </div>
  );
}

export function TicTacToeBoard({ board, onPlay, disabled }: { board: string[]; onPlay?: (cell: number) => void; disabled?: boolean }) {
  return (
    <div className="grid w-full max-w-[300px] grid-cols-3 gap-2">
      {board.map((v, i) => (
        <button key={i} disabled={disabled || !!v || !onPlay} onClick={() => onPlay?.(i)} aria-label={`Cell ${i}`}
          className="focus-ring flex aspect-square items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-4xl font-light transition enabled:hover:bg-white/[0.08]">
          <span className={v === "X" ? "text-accent" : "text-accent-rose"}>{v}</span>
        </button>
      ))}
    </div>
  );
}
