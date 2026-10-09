import { describe, expect, it } from "vitest";
import { duree, euros } from "./format";

describe("format", () => {
  it("euros à la française", () => {
    expect(euros(1700)).toMatch(/^1\s700,00\s€$/);
  });
  it("durées lisibles", () => {
    expect(duree(5)).toBe("5 s");
    expect(duree(125)).toBe("2 min 05 s");
  });
});
