"""Épreuve de l'ingestion (dossier 2.7 ②, 4.3) : lit la base, n'appelle jamais le VLM.

Précision par champ contre le manifeste, ING-01 → 05, invariance niveau 1 / niveau 0
(partenaire indisponible des deux côtés). Usage : uv run python -m tools.eval_ingestion
"""

from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from kaldera.memoire import SnapshotsEnMemoire
from kaldera.orchestrateur import Orchestrateur
from kaldera.postgres import ConfigBase, pool
from tools.generer_pieces import INGESTION, SCENARIOS
from tools.seed import lire_manifeste

DECISIFS = ("issue", "decision", "montant_rembourse", "file", "mode_degrade")
TERMES = ("numero", "formule", "date_souscription", "franchise", "plafond")
NUMERO_FAUX = "① numéro ≠ demande"
MOTIF_REGLE_0 = "Contrat illisible ou incohérent"
RAPPORTS = Path(__file__).resolve().parents[1] / "eval/rapports"


def _lignes(connexions: ConnectionPool, requete: str) -> list[dict[str, Any]]:
    with connexions.connection() as conn:
        return list(conn.cursor(row_factory=dict_row).execute(requete).fetchall())


def _niveau_0(demande: dict[str, Any]) -> dict[str, Any]:
    """Le moteur sur le JSON, partenaire indisponible, sans toucher à la base."""
    orch = Orchestrateur(evaluer=lambda d, timeout: None, snapshots=SnapshotsEnMemoire())
    return orch.traiter(copy.deepcopy(demande))


def _decisifs(fiche: dict[str, Any]) -> dict[str, Any]:
    return {k: fiche.get(k) for k in DECISIFS}


def _egal(a: Any, b: Any) -> bool:
    if isinstance(a, date):
        a = a.isoformat()
    if isinstance(a, (int, float, Decimal)):
        return b is not None and round(float(a), 2) == round(float(b), 2)
    return bool(a == b)


def evaluer(
    connexions: ConnectionPool,
    manifeste: list[dict[str, Any]],
    scenarios: Path = SCENARIOS,
    ingestion: Path = INGESTION,
) -> dict[str, Any]:
    fiches = {
        x["reference"]: x["fiche"]
        for x in _lignes(connexions, "SELECT reference, fiche FROM demandes")
    }
    contrats = {x["numero"]: x for x in _lignes(connexions, "SELECT * FROM contrats")}
    pieces = {(x["reference"], x["sha256"]): x for x in _lignes(connexions, "SELECT * FROM pieces")}
    blobs = {x["sha256"] for x in _lignes(connexions, "SELECT sha256 FROM blobs")}
    numeros = {
        x["reference"]: x["json"]["contrat"]["numero"] for x in manifeste if x["role"] == "demande"
    }

    # précision par champ : contrats nets (seuil 100 %), pièces (rapportée)
    mesures_contrats = {champ: [0, 0] for champ in TERMES}
    mesures_pieces = {"lisible": [0, 0], "montant": [0, 0]}
    for ligne in manifeste:
        if ligne["role"] == "contrat" and ligne["variante"] == "nette":
            extrait = contrats.get(numeros[ligne["reference"]], {})
            for champ in TERMES:
                mesures_contrats[champ][1] += 1
                if (
                    champ == "numero"
                ):  # la clé est celui de la demande : le verrou ① juge la lecture
                    juste = bool(extrait) and NUMERO_FAUX not in extrait["violations"]
                else:
                    juste = _egal(extrait.get(champ), ligne["attendu"][champ])
                mesures_contrats[champ][0] += int(juste)
        elif ligne["role"] in ("initiale", "depot") and ligne["http"] == 202:
            descripteur = pieces.get((ligne["reference"], ligne["sha256"]), {})
            mesures_pieces["lisible"][1] += 1
            mesures_pieces["lisible"][0] += int(descripteur.get("lisible") == ligne["lisible"])
            if ligne["type"] == "facture" and ligne["lisible"]:
                mesures_pieces["montant"][1] += 1
                mesures_pieces["montant"][0] += int(
                    _egal(descripteur.get("montant"), ligne["montant"])
                )

    # invariance : chaque demande fournie, niveau 1 (base) contre niveau 0 (JSON)
    fournis = [json.loads(x) for x in scenarios.read_text("utf-8").splitlines() if x.strip()]
    divergences, scenarios_ok = [], 0
    for scenario in fournis:
        ok = True
        for demande in scenario["demandes"]:
            niveau_1 = fiches.get(demande["reference"])
            if niveau_1 is None:
                divergences.append({"reference": demande["reference"], "raison": "fiche absente"})
                ok = False
                continue
            niveau_0 = _niveau_0(demande)
            if _decisifs(niveau_1) != _decisifs(niveau_0):
                divergences.append(
                    {
                        "reference": demande["reference"],
                        "raison": "issue différente",
                        "niveau_1": _decisifs(niveau_1),
                        "niveau_0": _decisifs(niveau_0),
                    }
                )
                ok = False
        scenarios_ok += int(ok)

    # ING-01 → 05
    ing_lignes = [json.loads(x) for x in ingestion.read_text("utf-8").splitlines() if x.strip()]
    par_id = {s["id"]: s for s in fournis}

    def fiche(reference: str) -> dict[str, Any]:
        return fiches.get(reference) or {}

    def fichiers(reference: str, http: int) -> list[dict[str, Any]]:
        return [
            x
            for x in manifeste
            if x["reference"] == reference and x.get("http") == http and x["role"] == "initiale"
        ]

    resultats = {}
    for ing in ing_lignes:
        ref = ing["reference"]
        if ing["id"] == "ING-01":
            ok = (
                contrats.get(ing["contrat_numero"], {}).get("statut_extraction")
                == "non_exploitable"
            )
            ok = ok and fiche(ref).get("motif") == MOTIF_REGLE_0
        elif ing["id"] == "ING-02":
            ok = "② barème" in (contrats.get(ing["contrat_numero"], {}).get("violations") or [])
            ok = ok and fiche(ref).get("motif") == MOTIF_REGLE_0
        elif ing["id"] == "ING-03":
            base = fiche(par_id[ing["base"]]["demandes"][0]["reference"])
            ok = bool(fiche(ref)) and _decisifs(fiche(ref)) == _decisifs(base)
        elif (
            ing["id"] == "ING-04"
        ):  # le 2e dépôt en HTTP 200 est contrôlé par le seed
            doublon = fichiers(ref, 200)
            sha = doublon[0]["sha256"] if doublon else None
            ok = sha in blobs and (ref, sha) in pieces
        else:  # ING-05
            exe = fichiers(ref, 415)
            ok = bool(exe) and exe[0]["sha256"] not in blobs
        resultats[ing["id"]] = bool(ok)

    protocole = all(not (f or {}).get("avis_fraude") for f in fiches.values())
    reussi = (
        all(ok == total for ok, total in mesures_contrats.values())
        and all(resultats.values())
        and scenarios_ok == len(fournis)
        and protocole
    )
    return {
        "date": date.today().isoformat(),
        "modeles": sorted(
            {f"{c['modele']} / prompt {c['version_prompt']}" for c in contrats.values()}
        ),
        "contrats": {k: tuple(v) for k, v in mesures_contrats.items()},
        "pieces": {k: tuple(v) for k, v in mesures_pieces.items()},
        "ing": resultats,
        "invariance": {
            "scenarios_ok": scenarios_ok,
            "scenarios": len(fournis),
            "divergences": divergences,
        },
        "protocole": protocole,
        "reussi": reussi,
    }


def ecrire_rapport(rapport: dict[str, Any], dossier: Path = RAPPORTS) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"ingestion-{rapport['date']}.md"
    chemin.with_suffix(".json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2, default=str), "utf-8"
    )
    inv = rapport["invariance"]
    lignes = [
        f"# Épreuve de l'ingestion — {rapport['date']}",
        "",
        f"**Résultat : {'réussie' if rapport['reussi'] else 'en échec'}** · modèles : "
        + (", ".join(rapport["modeles"]) or "aucun"),
        "",
        "| Mesure | Résultat | Seuil |",
        "|---|---|---|",
        *(
            f"| contrat · {k} | {ok}/{total} | 100 % |"
            for k, (ok, total) in rapport["contrats"].items()
        ),
        *(
            f"| pièce · {k} | {ok}/{total} | rapporté |"
            for k, (ok, total) in rapport["pieces"].items()
        ),
        *(f"| {k} | {'✅' if v else '❌'} | requis |" for k, v in rapport["ing"].items()),
        f"| invariance | {inv['scenarios_ok']}/{inv['scenarios']} | 28/28 |",
        f"| protocole (aucun avis partenaire) | {'✅' if rapport['protocole'] else '❌'} | requis |",
        "",
        "## Divergences",
        "",
        *(
            f"- {d['reference']} : {d['raison']} — {d.get('niveau_1', '')} ≠ {d.get('niveau_0', '')}"
            for d in inv["divergences"]
        ),
    ]
    chemin.write_text("\n".join(lignes) + "\n", "utf-8")
    return chemin


def main() -> None:
    url = ConfigBase().database_url
    if not url:
        raise SystemExit("KALDERA_DATABASE_URL absente : rien à éprouver")
    rapport = evaluer(pool(url), lire_manifeste())
    chemin = ecrire_rapport(rapport)
    print(chemin.read_text("utf-8"))
    if not rapport["reussi"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
