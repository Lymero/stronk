import { describe, expect, it } from "vitest";
import { elo, games, name, phase, region, role, runePage } from "./labels.ts";

describe("labels", () => {
  it("spells out champion-select phases, known or not", () => {
    expect(phase("BAN_PICK")).toBe("Bans and picks");
    expect(phase("PLANNING")).toBe("Declaring picks");
    expect(phase("SOMETHING_NEW")).toBe("Something new");
    expect(phase("")).toBe("Champion select");
  });

  it("names roles as players do", () => {
    expect(role("MIDDLE")).toBe("Mid");
    expect(role("UTILITY")).toBe("Support");
  });

  it("falls back to the id without a name", () => {
    expect(name(null, "items", 6692)).toBe("6692");
    const names = { champions: {}, rune_styles: {}, runes: {}, spells: { "4": "Flash" }, items: {} };
    expect(name(names, "spells", 4)).toBe("Flash");
    expect(name(names, "spells", 99)).toBe("99");
  });

  it("splits a rune page into trees and shards", () => {
    const page = { primary_style: 8000, sub_style: 8300, perks: [1, 2, 3, 4, 5, 6, 7, 8, 9] };
    expect(runePage(null, page)).toEqual([
      { title: "8000", runes: ["1", "2", "3", "4"] },
      { title: "8300", runes: ["5", "6"] },
      { title: "Shards", runes: ["7", "8", "9"] },
    ]);
  });

  it("names elo brackets and regions", () => {
    expect(elo("master_plus")).toBe("Master+");
    expect(elo("diamond_plus")).toBe("Diamond+");
    expect(elo("emerald")).toBe("Emerald");
    expect(elo("all")).toBe("All ranks");
    expect(region("all")).toBe("All regions");
    expect(region("euw1")).toBe("EUW1");
  });

  it("counts games", () => {
    expect(games(1)).toBe("1 game");
    expect(games(1840)).toBe("1,840 games");
  });
});
