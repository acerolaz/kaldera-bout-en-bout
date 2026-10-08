"""Génère les pièces factices et leur vérité terrain (dossier 2.7) : PDF reportlab, photos Pillow.

Déterministe : même scénario + même graine ⇒ mêmes octets ⇒ même sha256 (le cache VLM sert).
Usage : uv run python tools/generer_pieces.py --seed 42
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from kaldera import regles

rl_config.invariant = 1  # ni date ni identifiant aléatoire dans le PDF ⇒ sha256 stable
LARGEUR, HAUTEUR = (int(x) for x in A4)
RACINE = Path(__file__).resolve().parents[1]
SCENARIOS = RACINE / "eval/scenarios.jsonl"
INGESTION = RACINE / "eval/scenarios_ingestion.jsonl"
FIXTURES = RACINE / "fixtures/pieces"
EXECUTABLE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00 programme renomme en .pdf (ING-05)"
GESTION = ("numero", "statut", "cotisations_a_jour")  # état du contrat, système de gestion


def _police(taille: int) -> Any:
    return ImageFont.load_default(size=taille)  # police livrée avec Pillow, sans chemin système


def _page_texte(titre: str, lignes: list[str]) -> Image.Image:
    """Page A4 rendue en image : sert aux variantes scannée et floue."""
    img = Image.new("RGB", (LARGEUR, HAUTEUR), "white")
    dessin = ImageDraw.Draw(img)
    dessin.text((50, 50), titre, fill="black", font=_police(22))
    for i, ligne in enumerate(lignes):
        dessin.text((50, 110 + i * 28), ligne, fill="black", font=_police(15))
    return img


def _degrader(img: Image.Image, variante: str, rng: random.Random) -> Image.Image:
    if variante == "scannee":  # lisible : légère rotation, grain
        img = img.rotate(rng.uniform(-2.5, 2.5), expand=True, fillcolor="white")
        return img.filter(ImageFilter.GaussianBlur(0.6))
    if variante in ("floue", "scannee_floue"):  # illisible : sous-échantillonnage + flou fort
        petit = img.resize((img.width // 12, img.height // 12))
        return petit.resize(img.size).filter(ImageFilter.GaussianBlur(6))
    return img


def _pdf(titre: str, lignes: list[str], variante: str, rng: random.Random) -> bytes:
    tampon = io.BytesIO()
    page = canvas.Canvas(tampon, pagesize=A4)
    if variante == "nette":  # PDF natif : couche texte présente
        page.setFont("Helvetica-Bold", 16)
        page.drawString(50, HAUTEUR - 60, titre)
        page.setFont("Helvetica", 11)
        for i, ligne in enumerate(lignes):
            page.drawString(50, HAUTEUR - 100 - i * 18, ligne)
    else:  # PDF image seule : comme un scan, sans couche texte
        image = _degrader(_page_texte(titre, lignes), variante, rng)
        page.drawImage(ImageReader(image), 0, 0, LARGEUR, HAUTEUR)
    page.showPage()
    page.save()
    return tampon.getvalue()


DECORS = {  # type de sinistre → dessin
    "degat_des_eaux": lambda d, rng: [
        d.ellipse((x, y, x + rng.randint(80, 200), y + rng.randint(40, 120)), fill=(110, 140, 190))
        for x, y in [(rng.randint(50, 600), rng.randint(60, 250)) for _ in range(4)]
    ],
    "incendie": lambda d, rng: [
        d.polygon(
            [(x, 420), (x + 40, rng.randint(150, 300)), (x + 80, 420)],
            fill=rng.choice([(40, 30, 30), (230, 120, 30)]),
        )
        for x in range(80, 700, 70)
    ],
    "vol": lambda d, rng: [
        d.line(
            (400, 120, 400 + rng.randint(-150, 150), 120 + rng.randint(50, 250)),
            fill="black",
            width=3,
        )
        for _ in range(6)
    ],
}


def _photo(type_sinistre: str, variante: str, rng: random.Random) -> bytes:
    img = Image.new("RGB", (800, 600), (225, 215, 195))  # mur
    dessin = ImageDraw.Draw(img)
    dessin.rectangle((0, 420, 800, 600), fill=(150, 110, 80))  # sol
    dessin.rectangle((300, 100, 500, 300), outline="gray", width=6)  # fenêtre
    DECORS.get(type_sinistre, DECORS["vol"])(dessin, rng)
    img = _degrader(img, variante, rng)
    if variante == "floue":  # photo illisible : en plus, sous-exposée
        img = ImageEnhance.Brightness(img).enhance(0.12)
    tampon = io.BytesIO()
    img.save(tampon, format="PNG", optimize=False)
    return tampon.getvalue()


def _variante(lisible: bool, rng: random.Random) -> str:
    return rng.choice(["nette", "scannee"]) if lisible else "floue"


def _piece(
    p: dict[str, Any], d: dict[str, Any], rng: random.Random, extra: str | None
) -> tuple[bytes, str, str]:
    v = "nette" if extra else _variante(p.get("lisible", True), rng)  # ING-03 : texte à lire
    ref, sinistre = d["reference"], d["sinistre"]
    if p["type"] == "photo":
        return _photo(sinistre["type"], v, rng), "png", v
    if p["type"] == "facture":
        lignes = [
            f"Dossier : {ref}",
            f"Prestation : réparation {sinistre['type']}",
            f"Montant TTC : {p.get('montant') or 0:.2f} €",
        ]
        if extra:
            lignes.append(extra)  # ING-03 : un texte qui donne des ordres
        return _pdf("FACTURE", lignes, v, rng), "pdf", v
    lignes = [f"Dossier : {ref}", f"Faits du {sinistre['date_survenance']}"]
    return _pdf("RÉCÉPISSÉ DE DÉPÔT DE PLAINTE", lignes, v, rng), "pdf", v


def _contrat(
    d: dict[str, Any], variante: str | None, rng: random.Random
) -> tuple[bytes, dict[str, Any], str]:
    c, bareme = d["contrat"], regles.FORMULES[d["contrat"]["formule"]]
    attendu = {  # termes IMPRIMÉS : la vérité terrain de la lecture
        "numero": c["numero"],
        "formule": c["formule"],
        "date_souscription": c["date_souscription"],
        "franchise": bareme["franchise"] * (10 if variante == "franchise_faussee" else 1),
        "plafond": bareme["plafond"],
    }
    lignes = [
        f"Contrat n° {attendu['numero']}",
        f"Formule : {attendu['formule']}",
        f"Franchise : {attendu['franchise']:.2f} €",
        f"Plafond de garantie : {attendu['plafond']:.2f} €",
        f"Date de souscription : {attendu['date_souscription']}",
    ]
    rendu = "scannee_floue" if variante == "scannee_floue" else "nette"
    return _pdf("CONTRAT D'ASSURANCE HABITATION", lignes, rendu, rng), attendu, rendu


def demandes(scenarios: Path, ingestion: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(demande, variante) : les 34 demandes fournies, puis les ING dérivées de leur base."""
    fournis = [json.loads(x) for x in scenarios.read_text("utf-8").splitlines() if x.strip()]
    par_id = {s["id"]: s for s in fournis}
    sortie: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (d, {}) for s in fournis for d in s["demandes"]
    ]
    for ligne in ingestion.read_text("utf-8").splitlines():
        if not ligne.strip():
            continue
        ing = json.loads(ligne)
        d = copy.deepcopy(par_id[ing["base"]]["demandes"][0])
        d["reference"] = ing["reference"]
        d["contrat"]["numero"] = ing["contrat_numero"]  # son propre contrat
        sortie.append((d, ing["variante"]))
    return sortie


def _ecrire(sortie: Path, fichier: str, octets: bytes) -> str:
    chemin = sortie / fichier
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(octets)
    return hashlib.sha256(octets).hexdigest()


def generer(scenarios: Path, ingestion: Path, sortie: Path, seed: int) -> list[dict[str, Any]]:
    """Écrit les fichiers et ``manifeste.jsonl`` ; renvoie les lignes du manifeste."""
    manifeste: list[dict[str, Any]] = []

    def fichier(
        ref: str,
        nom: str,
        octets: bytes,
        role: str,
        relance: int | None,
        type_: str,
        lisible: bool,
        variante: str,
        montant: float | None,
        attendu: dict[str, Any],
        http: int,
    ) -> dict[str, Any]:
        ligne = {
            "reference": ref,
            "fichier": f"{ref}/{nom}",
            "role": role,
            "relance": relance,
            "type": type_,
            "lisible": lisible,
            "variante": variante,
            "montant": montant,
            "attendu": attendu,
            "http": http,
            "sha256": _ecrire(sortie, f"{ref}/{nom}", octets),
        }
        manifeste.append(ligne)
        return ligne

    for d, variante in demandes(scenarios, ingestion):
        ref = d["reference"]
        rng = random.Random(f"{seed}:{ref}")  # une graine par dossier : ordre indifférent
        json_demande = {k: v for k, v in d.items() if k not in ("pieces", "espace_assure")}
        json_demande["contrat"] = {k: d["contrat"][k] for k in GESTION}
        manifeste.append({"reference": ref, "role": "demande", "json": json_demande})
        octets, attendu, rendu = _contrat(d, variante.get("contrat"), rng)
        fichier(
            ref,
            "contrat.pdf",
            octets,
            "contrat",
            None,
            "contrat",
            rendu == "nette",
            rendu,
            None,
            attendu,
            202,
        )
        groupes = [("initiale", None, d.get("pieces", []))] + [
            ("depot", k, [p])
            for k, p in enumerate(d.get("espace_assure", {}).get("depots", []), start=1)
        ]
        for role, relance, pieces in groupes:
            for i, p in enumerate(pieces, start=1):
                extra = variante.get("facture_extra") if p["type"] == "facture" else None
                octets, ext, v = _piece(p, d, rng, extra)
                ligne = fichier(
                    ref,
                    f"{role}{relance or ''}_{i:02d}_{p['type']}.{ext}",
                    octets,
                    role,
                    relance,
                    p["type"],
                    p.get("lisible", True),
                    v,
                    p.get("montant"),
                    {},
                    202,
                )
                if variante.get("doublon") and p["type"] == "facture":
                    manifeste.append({**ligne, "http": 200})  # ING-04 : même fichier, 2e dépôt
        if variante.get("executable"):
            fichier(
                ref,
                "facture.pdf",
                EXECUTABLE,
                "initiale",
                None,
                "facture",
                False,
                "executable",
                None,
                {},
                415,
            )  # ING-05
    (sortie / "manifeste.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in manifeste), "utf-8"
    )
    return manifeste


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--seed", type=int, default=42)
    args.add_argument("--sortie", type=Path, default=FIXTURES)
    a = args.parse_args()
    lignes = generer(SCENARIOS, INGESTION, a.sortie, a.seed)
    print(f"{sum(1 for x in lignes if 'sha256' in x)} fichiers générés dans {a.sortie}")


if __name__ == "__main__":
    main()
