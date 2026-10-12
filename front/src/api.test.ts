import { afterEach, describe, expect, it, vi } from "vitest";
import { ErreurApi, lire } from "./api";
import { json, simulerApi } from "./test/rendre";

afterEach(() => vi.unstubAllGlobals());

describe("lire", () => {
  it("préfixe /api et renvoie le JSON", async () => {
    simulerApi(() => json([{ reference: "KAL-26-0101" }]));
    await expect(lire("/demandes")).resolves.toEqual([{ reference: "KAL-26-0101" }]);
    expect(fetch).toHaveBeenCalledWith("/api/demandes");
  });

  it("lève ErreurApi avec le statut et le détail", async () => {
    simulerApi(() => json({ detail: "demande inconnue" }, 404));
    await expect(lire("/demandes/KAL-26-9999")).rejects.toMatchObject({
      name: "ErreurApi",
      statut: 404,
      message: "demande inconnue",
    });
  });

  it("corps illisible (proxy sans API) : message générique", async () => {
    simulerApi(() => new Response("<html>", { status: 502 }));
    const erreur = await lire("/demandes").catch((e: unknown) => e);
    expect(erreur).toBeInstanceOf(ErreurApi);
    expect((erreur as ErreurApi).message).toBe("Erreur 502");
  });
});
