// Rend le dossier de conception : pages/*.html (ordre des noms) → PDF A4 paysage, via Chromium.
// Usage (depuis la racine du dépôt, après `cd front && npm install`) :
//   node docs/conception/rendre.cjs                       → docs/conception/dossier-conception.pdf
//   node docs/conception/rendre.cjs --sortie autre.pdf
//   node docs/conception/rendre.cjs --png /tmp/apercu --seulement 13,14   (aperçu de quelques pages)
// Signale toute page dont le contenu déborde sur le pied de page.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require(require.resolve("playwright", {
  paths: [path.join(__dirname, "..", "..", "front")],
}));

const ICI = __dirname;
const args = process.argv.slice(2);
const opt = (nom) => (args.includes(nom) ? args[args.indexOf(nom) + 1] : undefined);
const sortie = path.resolve(opt("--sortie") || path.join(ICI, "dossier-conception.pdf"));
const png = opt("--png");
const seulement = (opt("--seulement") || "").split(",").filter(Boolean);
const PIED = "Kaldera · Dossier de conception · Acerola";

const fichiers = fs.readdirSync(path.join(ICI, "pages"))
  .filter((f) => f.endsWith(".html"))
  .filter((f) => !seulement.length || seulement.some((p) => f.startsWith(p)))
  .sort();
if (!fichiers.length) throw new Error("aucune page à rendre");

const corps = fichiers
  .map((f) => `<!-- ${f} -->\n${fs.readFileSync(path.join(ICI, "pages", f), "utf-8")}`)
  .join("\n");
const html = `<!doctype html><html lang="fr"><head><meta charset="utf-8">
<base href="file://${ICI}/"><link rel="stylesheet" href="style.css">
<title>Kaldera — Dossier de conception</title></head><body>${corps}</body></html>`;
const temp = path.join(os.tmpdir(), `dossier-conception-${process.pid}.html`);
fs.writeFileSync(temp, html);

(async () => {
  const navigateur = await chromium.launch();
  const page = await navigateur.newPage({ viewport: { width: 1123, height: 794 }, deviceScaleFactor: 1.5 });
  await page.goto(`file://${temp}`);
  await page.evaluate(() => document.fonts.ready);
  const alertes = await page.evaluate((pied) => {
    const pages = [...document.querySelectorAll("section.page")];
    const alertes = [];
    pages.forEach((p, i) => {
      if (!p.querySelector(".pied")) {
        p.insertAdjacentHTML("beforeend",
          `<footer class="pied"><span>${pied}</span><span>${i + 1} / ${pages.length}</span></footer>`);
      }
      const limite = p.getBoundingClientRect().bottom - 46;   // zone du pied (≈ 12 mm)
      const droite = p.getBoundingClientRect().right - 40;
      for (const el of p.querySelectorAll(":scope > *:not(.pied)")) {
        const r = el.getBoundingClientRect();
        if (r.bottom > limite + 1) alertes.push(`page ${i + 1} (${p.id || "?"}) : déborde en bas de ${Math.round(r.bottom - limite)} px`);
        if (r.right > droite + 1) alertes.push(`page ${i + 1} (${p.id || "?"}) : déborde à droite de ${Math.round(r.right - droite)} px`);
      }
    });
    return alertes;
  }, PIED);
  alertes.forEach((a) => console.warn("⚠️ ", a));

  if (png) {
    fs.mkdirSync(png, { recursive: true });
    const pages = await page.$$("section.page");
    for (const [i, p] of pages.entries()) {
      const id = (await p.getAttribute("id")) || "page";
      await p.screenshot({ path: path.join(png, `${String(i + 1).padStart(2, "0")}-${id}.png`) });
    }
    console.log(`${pages.length} aperçus dans ${png}`);
  } else {
    await page.pdf({ path: sortie, width: "297mm", height: "210mm", printBackground: true });
    console.log(`${fichiers.length} fragments → ${sortie}`);
  }
  await navigateur.close();
  fs.unlinkSync(temp);
  process.exitCode = alertes.length ? 1 : 0;
})();
