"""Unitaires — métriques par agent et d'équipe (C2b, C2-Q15) sur des fiches fabriquées."""

from __future__ import annotations

from typing import Any

import kaldera
from kaldera.partenaire import NATURES


def _etape(agent: str, duree: float = 10.0, **champs: Any) -> dict[str, Any]:
    return {"agent": agent, "statut": "ok", "duree_ms": duree, "appels_externes": 0, **champs}


def _fiche(
    trace: list[dict[str, Any]],
    issue: str = "decision",
    file: str | None = None,
    mode_degrade: bool = False,
    arret: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "reference": "KAL-26-0001",
        "issue": issue,
        "file": file,
        "mode_degrade": mode_degrade,
        "arret": arret,
        "trace": trace,
    }


def test_natures_de_l_agent_antifraude() -> None:
    fiches = [
        _fiche([_etape("antifraude", nature="ok", appels_externes=1)]),
        _fiche([_etape("antifraude", nature="timeout", appels_externes=1, statut="echec")]),
        _fiche([_etape("antifraude", nature="non_envoye", statut="echec")]),
        _fiche([_etape("antifraude", nature="non_requis")]),
    ]
    m = kaldera.metriques_par_agent(fiches)["antifraude"]
    assert m["natures"] == {
        "ok": 1,
        "timeout": 1,
        "invalide": 0,
        "erreur": 0,
        "non_envoye": 1,
        "non_requis": 1,
    }
    assert set(m["natures"]) == set(NATURES)
    assert m["appels_externes"] == 2 and m["echecs"] == 2


def test_agent_sans_nature_sans_cle_natures() -> None:
    m = kaldera.metriques_par_agent([_fiche([_etape("pieces")])])["pieces"]
    assert "natures" not in m


def test_equipe() -> None:
    fiches = [_fiche([_etape("pieces", duree=float(i)) for _ in range(3)]) for i in range(1, 21)]
    fiches.append(
        _fiche(
            [_etape("decision", duree=500.0, statut="echec", erreur="ErreurEcriture")],
            issue="escalade",
            file="cellule_fraude",
            mode_degrade=True,
            arret={"borne": "relances_pieces_max", "valeur": 1, "etape": 4},
        )
    )
    e = kaldera.metriques_equipe(fiches)
    assert e["demandes"] == 21
    assert e["etapes"] == {"max": 3, "moyenne": round(61 / 21, 2)}
    assert e["arrets"] == {"relances_pieces_max": 1}
    assert e["issues"] == {"decision": 20, "escalade": 1}
    assert e["escalades_par_file"] == {"cellule_fraude": 1}
    assert e["mode_degrade"] == {"n": 1, "taux": round(1 / 21, 4)}
    # durées par fiche : 3, 6, …, 60 (20 fiches) puis 500 ; rang 95 % : ceil(0,95×21) = 20
    assert e["duree_ms"] == {"p95": 60.0, "max": 500.0}
    assert e["ecritures_rejetees"] == 1


def test_equipe_lot_vide() -> None:
    """Review Focus 3."""
    e = kaldera.metriques_equipe([])
    assert e["demandes"] == 0
    assert e["etapes"] == {"max": 0, "moyenne": 0.0}
    assert e["mode_degrade"] == {"n": 0, "taux": 0.0}
    assert e["duree_ms"] == {"p95": 0.0, "max": 0.0}
    assert e["issues"] == {"decision": 0, "escalade": 0}


def test_traiter_lot_renvoie_equipe() -> None:
    import copy
    import json
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    nom = json.loads((racine / "eval/scenarios.jsonl").read_text("utf-8").splitlines()[0])
    resultat = kaldera.traiter_lot(copy.deepcopy(nom["demandes"]))
    assert set(resultat) == {"fiches", "metriques", "equipe"}
    assert resultat["equipe"]["demandes"] == len(nom["demandes"])
    assert "equipe" not in resultat["metriques"]


def test_equipe_fiche_sans_issue_sans_keyerror() -> None:
    e = kaldera.metriques_equipe([{"reference": "KAL-26-0001", "trace": []}])
    assert e["issues"] == {"decision": 0, "escalade": 0} and e["escalades_par_file"] == {}
