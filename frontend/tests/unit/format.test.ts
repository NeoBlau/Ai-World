import { clockLabel, eventGlyph, timeAgo, untilLabel } from "@/lib/format";

describe("format helpers", () => {
  const now = new Date("2026-01-01T12:00:00Z").getTime();
  it("formats relative times", () => {
    expect(timeAgo("2026-01-01T11:59:58Z", now)).toBe("just now");
    expect(timeAgo("2026-01-01T11:59:00Z", now)).toBe("1m ago");
    expect(timeAgo("2026-01-01T11:00:00Z", now)).toBe("1h ago");
    expect(untilLabel("2026-01-01T12:05:00Z", now)).toBe("in 5 min");
    expect(untilLabel("2026-01-01T11:00:00Z", now)).toBe("now");
  });
  it("formats clock and glyphs", () => {
    expect(clockLabel(7, 5)).toBe("07:05");
    expect(eventGlyph("message.created")).toBe("💬");
    expect(eventGlyph("game.move")).toBe("♟");
  });
});
