"""Épreuve de l'équipe (dossier 4.1, 4.2 ; C2b) : rejoue les 28 scénarios contre le partenaire
simulé, rend un verdict par exigence, la couverture des transitions et les seuils.

Usage : uv run python -m tools.epreuve (ou make epreuve)
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import uvicorn

import kaldera
from kaldera.etat import BORNES, PROPRIETAIRES, Bornes
from kaldera.machine import TRANSITIONS
from kaldera.memoire import RegistreA2AEnMemoire, SnapshotsEnMemoire
from kaldera.orchestrateur import Orchestrateur

RAPPORTS = Path(__file__).resolve().parents[1] / "eval/rapports"
CHAMPS_CONTRAT = frozenset(
    {
        "reference_dossier",
        "type_sinistre",
        "montant_declare",
        "date_survenance",
        "anciennete_contrat_jours",
        "sinistres_12_mois",
        "departement",
    }
)
HORS_SCENARIOS = {"T0": "ING-01 / ING-02 (make eval-ingestion)"}  # garde d'entrée : niveau 1
# catégorie de scénarios → exigence qui ne s'évalue que sur elle
EXIGENCE_PAR_CATEGORIE = {"invalide": "EX-04", "panne": "EX-05", "boucle": "EX-06"}
SCENARIOS = Path(__file__).resolve().parents[1] / "eval/scenarios.jsonl"
JETON_RECETTE = "jeton-recette"


def valeurs_personnelles(demande: dict[str, Any]) -> list[str]:
    """Données qui ne doivent jamais partir chez le partenaire (contrat §2)."""
    assure = demande.get("assure", {})
    champs = ("id_client", "nom", "prenom", "email", "telephone", "iban", "adresse", "code_postal")
    valeurs = [assure.get(c) for c in champs]
    valeurs += [
        demande.get("contrat", {}).get("numero"),
        demande.get("sinistre", {}).get("description"),
    ]
    return [v for v in valeurs if isinstance(v, str) and v]


def _corps_lisible(brut: str) -> str:
    """Corps JSON réécrit en UTF-8 : une valeur échappée (``\\u00e9``) reste détectable."""
    try:
        return json.dumps(json.loads(brut), ensure_ascii=False)
    except (ValueError, RecursionError):
        return brut


def _par_reference(rejeu: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f.get("reference"): f for f in rejeu["fiches"]}


def _ecarts_attendu(fiche: dict[str, Any], attendu: dict[str, Any]) -> list[str]:
    ref, ecarts = attendu["reference"], []
    for champ in ("issue", "decision", "file"):
        if champ in attendu and fiche.get(champ) != attendu[champ]:
            ecarts.append(f"{ref} : {champ} = {fiche.get(champ)!r}, attendu {attendu[champ]!r}")
    if "montant_rembourse" in attendu:
        obtenu, prevu = fiche.get("montant_rembourse"), attendu["montant_rembourse"]
        if (prevu is None) != (obtenu is None) or (
            prevu is not None and obtenu is not None and abs(obtenu - prevu) >= 0.01
        ):
            ecarts.append(f"{ref} : montant {obtenu!r}, attendu {prevu!r}")
    if "mode_degrade" in attendu and bool(fiche.get("mode_degrade")) is not attendu["mode_degrade"]:
        ecarts.append(f"{ref} : mode_degrade = {fiche.get('mode_degrade')!r}")
    if "avis_fraude" in attendu:
        avis = fiche.get("avis_fraude")
        niveau = avis.get("niveau") if isinstance(avis, dict) else None
        if niveau != attendu["avis_fraude"]:
            ecarts.append(f"{ref} : avis {niveau!r}, attendu {attendu['avis_fraude']!r}")
    if attendu.get("arret") and not fiche.get("arret"):
        ecarts.append(f"{ref} : arrêt non signalé")
    return ecarts


def verdicts(rejeux: list[dict[str, Any]], bornes: Bornes) -> dict[str, list[str]]:
    """Écarts par exigence (dossier 4.1, C2-Q14) ; une liste vide vaut ✅."""
    v: dict[str, list[str]] = {
        k: [] for k in ("EX-01", "EX-02", "EX-03", "EX-04", "EX-05", "EX-06")
    }
    v["attendu"] = []
    vues: dict[str, bool] = {}  # catégorie → au moins une fiche évaluée
    for rejeu in rejeux:
        scenario, fiches = rejeu["scenario"], _par_reference(rejeu)
        categorie = scenario["categorie"]
        # toutes les demandes du scénario : une référence illisible ne dispense de rien
        personnelles = [v for d in scenario["demandes"] for v in valeurs_personnelles(d)]
        vues[categorie] = vues.get(categorie, False) or bool(fiches)
        for ref, fiche in fiches.items():
            motif = fiche.get("motif")
            if fiche.get("issue") not in ("decision", "escalade") or not (
                isinstance(motif, str) and motif.strip()
            ):
                v["EX-01"].append(f"{ref} : issue non motivée")
            for etape in fiche.get("trace", []):
                for section in etape.get("ecrit", []):
                    if PROPRIETAIRES.get(section) != etape["agent"]:
                        v["EX-02"].append(f"{ref} : section {section} écrite par {etape['agent']}")
                if etape.get("erreur") == "ErreurEcriture":
                    v["EX-02"].append(f"{ref} : écriture rejetée ({etape['agent']})")
            if categorie == "invalide" and fiche.get("avis_fraude") is not None:
                v["EX-04"].append(f"{ref} : réponse non conforme propagée dans la fiche")
            if categorie == "boucle":
                arret = fiche.get("arret") or {}
                if arret.get("borne") != "relances_pieces_max":
                    v["EX-06"].append(f"{ref} : arrêt {arret.get('borne')!r}")
                if len(fiche.get("trace", [])) > bornes.etapes_max:
                    n = len(fiche["trace"])
                    v["EX-06"].append(f"{ref} : {n} étapes > {bornes.etapes_max}")
        for entree in rejeu["journal"]:
            ref = entree.get("reference")
            # 401 / 503 : le simulateur répond avant de lire le corps (champs vides) — seul le
            # corps brut est alors contrôlé
            lu = entree.get("statut_http") not in (401, 503)
            if lu and set(entree.get("champs", [])) != CHAMPS_CONTRAT:
                v["EX-03"].append(f"{ref} : champs envoyés ≠ les 7 du contrat")
            corps = _corps_lisible(entree.get("corps_brut") or "")
            if any(val in corps for val in personnelles):
                # jamais la valeur elle-même dans le rapport
                v["EX-03"].append(f"{ref} : donnée personnelle dans la requête")
        for attendu in scenario["attendu"]:
            produite = fiches.get(attendu["reference"])
            if produite is None:
                v["attendu"].append(f"{attendu['reference']} : aucune fiche produite")
                continue
            ecarts = _ecarts_attendu(produite, attendu)
            v["attendu"] += ecarts
            if categorie == "panne":
                v["EX-05"] += [e for e in ecarts if "mode_degrade" in e or "file" in e]
    for categorie, exigence in EXIGENCE_PAR_CATEGORIE.items():
        if vues.get(categorie) is False:  # scénario présent, aucune fiche évaluée
            v[exigence].append(f"aucune fiche {categorie} évaluée")
    return v


def couverture(rejeux: list[dict[str, Any]]) -> dict[str, Any]:
    """Transitions T1 … T11 empruntées par les scénarios (dossier 4.2) ; T0 : ingestion."""
    gardes = {e.get("garde") for r in rejeux for f in r["fiches"] for e in f.get("trace", [])}
    toutes = [f"T{i}" for i in range(1, len(TRANSITIONS) + 1)]
    return {
        "empruntees": [t for t in toutes if t in gardes],
        "manquantes": [t for t in toutes if t not in gardes],
        "hors_scenarios": dict(HORS_SCENARIOS),
    }


def seuils(
    rejeux: list[dict[str, Any]], equipe: dict[str, Any], bornes: Bornes
) -> list[dict[str, Any]]:
    """Seuils de l'équipe (spec C2b §4.3) : mesure, seuil lisible, verdict."""
    hors_relance = sum(n for b, n in equipe["arrets"].items() if b != "relances_pieces_max")
    appels = max(
        (n for r in rejeux for n in Counter(e.get("reference") for e in r["journal"]).values()),
        default=0,
    )
    duree_max_ms = bornes.duree_max_s * 1000
    return [
        {
            "nom": "durée p95 (ms)",
            "mesure": equipe["duree_ms"]["p95"],
            "seuil": f"< {duree_max_ms:g}",
            "ok": equipe["duree_ms"]["p95"] < duree_max_ms,
        },
        {
            "nom": "durée max (ms)",
            "mesure": equipe["duree_ms"]["max"],
            "seuil": "< 10000",
            "ok": equipe["duree_ms"]["max"] < 10_000,
        },
        {
            "nom": "écritures rejetées",
            "mesure": equipe["ecritures_rejetees"],
            "seuil": "= 0",
            "ok": equipe["ecritures_rejetees"] == 0,
        },
        {
            "nom": "étapes max",
            "mesure": equipe["etapes"]["max"],
            "seuil": f"≤ {bornes.etapes_max}",
            "ok": equipe["etapes"]["max"] <= bornes.etapes_max,
        },
        {
            "nom": "arrêts hors relances_pieces_max",
            "mesure": hors_relance,
            "seuil": "= 0",
            "ok": hors_relance == 0,
        },
        {
            "nom": "appels partenaire par référence",
            "mesure": appels,
            "seuil": "≤ 1",
            "ok": appels <= 1,
        },
    ]


def bornes_observees(
    rejeux: list[dict[str, Any]], equipe: dict[str, Any], bornes: Bornes
) -> list[dict[str, Any]]:
    """Bornes provisoires en vigueur ↔ valeurs observées pendant l'épreuve."""
    antifraude_ms = max(
        (
            e["duree_ms"]
            for r in rejeux
            for f in r["fiches"]
            for e in f.get("trace", [])
            if e.get("agent") == "antifraude"
        ),
        default=0.0,
    )
    return [
        {"borne": "etapes_max", "valeur": bornes.etapes_max, "observe": equipe["etapes"]["max"]},
        {
            "borne": "duree_max_s",
            "valeur": bornes.duree_max_s,
            "observe": round(equipe["duree_ms"]["max"] / 1000, 2),
        },
        {
            "borne": "relances_pieces_max",
            "valeur": bornes.relances_pieces_max,
            "observe": equipe["arrets"].get("relances_pieces_max", 0),
        },
        {
            "borne": "delai_partenaire_s",
            "valeur": bornes.delai_partenaire_s,
            "observe": round(antifraude_ms / 1000, 2),
        },
    ]


def _ok(valeur: bool) -> str:
    return "✅" if valeur else "❌"


def ecrire_rapport(rapport: dict[str, Any], dossier: Path = RAPPORTS) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"epreuve-{rapport['date']}.md"
    chemin.with_suffix(".json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2, default=str), "utf-8"
    )
    couv, modes = rapport["couverture"], rapport.get("modes", {})
    lignes = [
        f"# Épreuve de l'équipe — {rapport['date']}",
        "",
        f"**Résultat : {'réussie' if rapport['reussi'] else 'en échec'}** · mode : "
        + f"llm {modes.get('llm', 0)} / repli {modes.get('repli', 0)} · modèles : "
        + (", ".join(rapport["modeles"]) or "aucun")
        + f" · durée : {rapport['duree_s']} s",
        "",
        "## Seuils",
        "",
        "| Mesure | Résultat | Seuil | |",
        "|---|---|---|---|",
        *(
            f"| {s['nom']} | {s['mesure']} | {s['seuil']} | {_ok(s['ok'])} |"
            for s in rapport["seuils"]
        ),
        "",
        "## Exigences",
        "",
        "| Exigence | Verdict | Écarts |",
        "|---|---|---|",
        *(
            f"| {k} | {_ok(not e)} | {'<br>'.join(e) or '—'} |"
            for k, e in rapport["verdicts"].items()
        ),
        "",
        "## Couverture des transitions",
        "",
        f"Empruntées : {', '.join(couv['empruntees']) or '—'}  ",
        f"Non empruntées : {', '.join(couv['manquantes']) or 'aucune'}  ",
        *(f"{t} : couverte par {ou}  " for t, ou in couv["hors_scenarios"].items()),
        "",
        "## Scénarios",
        "",
        "| Scénario | Verdict | Écarts |",
        "|---|---|---|",
        *(
            f"| {s['id']} | {_ok(s['ok'])} | {'<br>'.join(s['ecarts']) or '—'} |"
            for s in rapport["scenarios"]
        ),
        "",
        "## Bornes",
        "",
        "| Borne | En vigueur | Observé |",
        "|---|---|---|",
        *(f"| {b['borne']} | {b['valeur']} | {b['observe']} |" for b in rapport["bornes"]),
        "",
        "## Métriques",
        "",
        "```json",
        json.dumps(
            {"agents": rapport["metriques"], "equipe": rapport["equipe"]},
            ensure_ascii=False,
            indent=2,
        ),
        "```",
    ]
    chemin.write_text("\n".join(lignes) + "\n", "utf-8")
    return chemin


@contextmanager
def partenaire_simule() -> Iterator[str]:
    """Partenaire simulé (``external_agent``) dans le processus, sur un port libre."""
    avant = os.environ.get("PARTENAIRE_JETON")
    if not avant:  # absent ou vide (.env exporté par make) : même jeton client et simulateur
        os.environ["PARTENAIRE_JETON"] = JETON_RECETTE
    from external_agent.app import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", ws="none")
    serveur = uvicorn.Server(config)
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    limite = time.monotonic() + 10
    while not serveur.started:
        if time.monotonic() > limite or not fil.is_alive():
            serveur.should_exit = True
            raise RuntimeError("le partenaire simulé n'a pas démarré")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        serveur.should_exit = True
        fil.join(5)
        if not avant:  # environnement du processus rendu tel quel
            if avant is None:
                os.environ.pop("PARTENAIRE_JETON", None)
            else:
                os.environ["PARTENAIRE_JETON"] = avant


def orchestrateur(url: str) -> Orchestrateur:
    """Snapshots et registre en mémoire : une épreuve ne dépend d'aucune base et se rejoue."""
    return Orchestrateur(url, snapshots=SnapshotsEnMemoire(), registre=RegistreA2AEnMemoire())


def rejouer(url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(base_url=url, timeout=5) as sim:
        sim.post("/_sim/reset").raise_for_status()
        sim.post("/_sim/mode", json=scenario["partenaire"]).raise_for_status()
        orch = orchestrateur(url)
        # en parallèle, comme traiter_lot (§12)
        with ThreadPoolExecutor() as pool:
            fiches = list(pool.map(orch.traiter, scenario["demandes"]))
        journal = sim.get("/_sim/journal").json()
    return {"scenario": scenario, "fiches": fiches, "journal": journal}


def evaluer(scenarios: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if scenarios is None:
        lignes = SCENARIOS.read_text("utf-8").splitlines()
        scenarios = [json.loads(ligne) for ligne in lignes if ligne.strip()]
    debut = time.monotonic()
    with partenaire_simule() as url:
        rejeux = [rejouer(url, s) for s in scenarios]
    fiches = [f for r in rejeux for f in r["fiches"]]
    equipe = kaldera.metriques_equipe(fiches)
    v = verdicts(rejeux, BORNES)
    couv = couverture(rejeux)
    s = seuils(rejeux, equipe, BORNES)
    par_scenario = []
    for r in rejeux:
        ecarts = verdicts([r], BORNES)
        tous = [e for liste in ecarts.values() for e in liste]
        par_scenario.append({"id": r["scenario"]["id"], "ok": not tous, "ecarts": tous})
    modeles = sorted(
        {e.get("modele") or "aucun" for f in fiches for e in f["trace"] if "mode" in e}
    )
    # mode réel de chaque étape LLM : un modèle configuré mais toujours en repli n'est pas éprouvé
    modes = dict(Counter(e["mode"] for f in fiches for e in f["trace"] if "mode" in e))
    reussi = all(not e for e in v.values()) and not couv["manquantes"]
    return {
        "date": date.today().isoformat(),
        "reussi": reussi and all(x["ok"] for x in s),
        "modeles": modeles,
        "modes": modes,
        "duree_s": round(time.monotonic() - debut, 1),
        "seuils": s,
        "verdicts": v,
        "couverture": couv,
        "scenarios": par_scenario,
        "metriques": kaldera.metriques_par_agent(fiches),
        "equipe": equipe,
        "bornes": bornes_observees(rejeux, equipe, BORNES),
    }


def main() -> None:
    rapport = evaluer()
    chemin = ecrire_rapport(rapport)
    print(chemin.read_text("utf-8"))
    if not rapport["reussi"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
