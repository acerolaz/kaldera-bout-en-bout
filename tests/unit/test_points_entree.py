"""Unitaires — les points d'entrée du paquet (docs/interface.md)."""

from __future__ import annotations

import json
from pathlib import Path

import kaldera

RACINE = Path(__file__).resolve().parents[2]
NOMINAUX = [
    d
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
    if s["categorie"] == "nominal"
    for d in s["demandes"]
]


def test_bornes_exposees() -> None:
    bornes = kaldera.bornes()
    assert bornes["etapes_max"] == 12 and 0 < bornes["duree_max_s"] <= 10
    assert {"relances_pieces_max", "delai_partenaire_s"} <= set(bornes)


def test_lot_rend_les_fiches_dans_l_ordre() -> None:
    resultat = kaldera.traiter_lot(NOMINAUX)
    assert [f["reference"] for f in resultat["fiches"]] == [d["reference"] for d in NOMINAUX]


def test_metriques_par_agent_calculees_sur_les_traces() -> None:
    resultat = kaldera.traiter_lot(NOMINAUX)
    etapes = [e for f in resultat["fiches"] for e in f["trace"]]
    metriques = resultat["metriques"]
    assert set(metriques) == {e["agent"] for e in etapes}
    for agent, m in metriques.items():
        siennes = [e for e in etapes if e["agent"] == agent]
        assert m["appels"] == len(siennes)
        assert m["echecs"] == sum(e["statut"] == "echec" for e in siennes)
        assert m["appels_externes"] == sum(e["appels_externes"] for e in siennes)
        assert isinstance(m["latence_ms"], float) and m["latence_ms"] >= 0
