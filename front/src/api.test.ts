import { afterEach, describe, expect, it, vi } from "vitest";
import { ErreurApi, lire } from "./api";

const repondre = (corps: unknown, statut = 200) =>
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(corps), { status: statut })));

afterEach(() => vi.unstubAllGlobals());

describe("lire", () => {
  it("préfixe /api et renvoie le JSON", async () => {
    repondre([{ reference: "KAL-26-0101" }]);
    await expect(lire("/demandes")).resolves.toEqual([{ reference: "KAL-26-0101" }]);
    expect(fetch).toHaveBeenCalledWith("/api/demandes");
  });

  it("lève ErreurApi avec le statut et le détail", async () => {
    repondre({ detail: "demande inconnue" }, 404);
    await expect(lire("/demandes/KAL-26-9999")).rejects.toMatchObject({
      name: "ErreurApi",
      statut: 404,
      message: "demande inconnue",
    });
  });

  it("corps illisible (proxy sans API) : message générique", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 502 })));
    const erreur = await lire("/demandes").catch((e: unknown) => e);
    expect(erreur).toBeInstanceOf(ErreurApi);
    expect((erreur as ErreurApi).message).toBe("Erreur 502");
  });
});
