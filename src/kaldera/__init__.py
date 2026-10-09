"""Kaldera — traitement des demandes de remboursement d'assurance."""

from __future__ import annotations

import math
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .etat import BORNES
from .orchestrateur import Orchestrateur
from .partenaire import NATURES

__all__ = ["bornes", "metriques_equipe", "metriques_par_agent", "traiter_demande", "traiter_lot"]


def bornes() -> dict[str, Any]:
    """Bornes d'exécution en vigueur."""
    return BORNES.model_dump()


def traiter_demande(
    demande: dict[str, Any], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite une demande et retourne sa fiche de décision."""
    return Orchestrateur(partenaire_url).traiter(demande)


def traiter_lot(
    demandes: list[dict[str, Any]], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite un lot de demandes en parallèle (§12) ; fiches dans l'ordre, métriques par agent."""
    orchestrateur = Orchestrateur(partenaire_url)  # config lue et clients construits une fois
    # un EtatDemande par demande : l'orchestrateur et les agents partagés ne gardent aucun état
    # ponytail: pool par défaut ; borne explicite si le partenaire ou Azure limitent le débit
    with ThreadPoolExecutor() as pool:
        fiches = list(pool.map(orchestrateur.traiter, demandes))
    return {
        "fiches": fiches,
        "metriques": metriques_par_agent(fiches),
        "equipe": metriques_equipe(fiches),
    }


LLM_SOMMES = ("tours_llm", "jetons", "latence_llm_ms")


def metriques_par_agent(fiches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Métriques par agent (EX-D14, C2-Q15) : clés de `docs/interface.md`."""
    metriques: dict[str, dict[str, Any]] = {}
    for etape in (e for f in fiches for e in f["trace"]):
        m = metriques.setdefault(
            etape["agent"], {"appels": 0, "echecs": 0, "duree_ms": 0.0, "appels_externes": 0}
        )
        m["appels"] += 1
        m["echecs"] += int(etape["statut"] == "echec")
        m["duree_ms"] += etape["duree_ms"]
        m["appels_externes"] += etape["appels_externes"]
        if "nature" in etape:  # agent antifraude (C2b)
            natures = m.setdefault("natures", dict.fromkeys(NATURES, 0))
            natures[etape["nature"]] += 1
        if "mode" in etape:  # agent LLM (EX-D14)
            for cle in LLM_SOMMES:
                m[cle] = m.get(cle, 0) + etape[cle]
            m["replis"] = m.get("replis", 0) + int(etape["mode"] == "repli")
            m["sorties_rejetees"] = m.get("sorties_rejetees", 0) + int(etape["sortie_rejetee"])
            modeles = m.setdefault("modeles", {})
            modele = etape["modele"] or "aucun"
            modeles[modele] = modeles.get(modele, 0) + 1
    for m in metriques.values():
        m["latence_ms"] = round(m.pop("duree_ms") / m["appels"], 2)
        if "latence_llm_ms" in m:
            m["latence_llm_ms"] = round(m["latence_llm_ms"] / m["appels"], 2)
    return metriques


def metriques_equipe(fiches: list[dict[str, Any]]) -> dict[str, Any]:
    """Métriques de l'équipe sur un lot (C2-Q15) ; un lot vide donne des zéros."""
    n = len(fiches)
    etapes = [len(f["trace"]) for f in fiches]
    durees = sorted(sum(e["duree_ms"] for e in f["trace"]) for f in fiches)
    degrades = sum(bool(f.get("mode_degrade")) for f in fiches)
    issues = Counter(f["issue"] for f in fiches)
    return {
        "demandes": n,
        "etapes": {
            "max": max(etapes, default=0),
            "moyenne": round(sum(etapes) / n, 2) if n else 0.0,
        },
        "arrets": dict(Counter(f["arret"]["borne"] for f in fiches if f.get("arret"))),
        "issues": {"decision": issues["decision"], "escalade": issues["escalade"]},
        "escalades_par_file": dict(Counter(f["file"] for f in fiches if f["issue"] == "escalade")),
        "mode_degrade": {"n": degrades, "taux": round(degrades / n, 4) if n else 0.0},
        "duree_ms": {
            # centile au rang le plus proche : une durée réellement observée
            "p95": round(durees[math.ceil(0.95 * n) - 1], 2) if n else 0.0,
            "max": round(durees[-1], 2) if n else 0.0,
        },
        "ecritures_rejetees": sum(
            e.get("erreur") == "ErreurEcriture" for f in fiches for e in f["trace"]
        ),
    }
