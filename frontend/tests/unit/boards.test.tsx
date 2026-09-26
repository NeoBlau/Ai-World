import { render, screen } from "@testing-library/react";

import { ChessBoard, fenToGrid, TicTacToeBoard } from "@/features/games/boards";

describe("game boards", () => {
  it("parses FEN", () => {
    const grid = fenToGrid("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1");
    expect(grid).toHaveLength(8);
    expect(grid[4][4]).toBe("P");
    expect(grid[0][4]).toBe("k");
    expect(grid[3].every((c) => c === null)).toBe(true);
  });
  it("renders boards", () => {
    render(<ChessBoard fen="8/8/8/8/8/8/8/4K3 w - - 0 1" />);
    expect(screen.getByRole("img", { name: "Chess board" })).toBeInTheDocument();
    render(<TicTacToeBoard board={["X", "", "O", "", "", "", "", "", ""]} />);
    expect(screen.getByLabelText("Cell 0")).toHaveTextContent("X");
  });
});
