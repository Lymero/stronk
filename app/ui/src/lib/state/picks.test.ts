import { describe, expect, it } from "vitest";
import { samePage } from "./picks.ts";

describe("samePage", () => {
  const page = { primary_style: 8000, sub_style: 8300, perks: [8010, 9111, 9104, 8014, 8347, 8304, 5005, 5008, 5001] };

  it("reads the two secondary runes as one choice, in either order", () => {
    // The data gives Cosmic Insight then Magical Footwear; the app keeps them in row order.
    const reordered = { ...page, perks: [8010, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001] };
    expect(samePage(page, reordered)).toBe(true);
  });

  it("tells pages apart by any rune, shard or tree", () => {
    expect(samePage(page, { ...page, perks: [8010, 9111, 9104, 8014, 8347, 8304, 5005, 5008, 5011] })).toBe(false);
    expect(samePage(page, { ...page, perks: [8010, 9111, 9104, 8017, 8347, 8304, 5005, 5008, 5001] })).toBe(false);
    expect(samePage(page, { ...page, sub_style: 8100 })).toBe(false);
    // Shards are in their rows, so their order counts.
    expect(samePage(page, { ...page, perks: [8010, 9111, 9104, 8014, 8347, 8304, 5008, 5005, 5001] })).toBe(false);
  });
});
