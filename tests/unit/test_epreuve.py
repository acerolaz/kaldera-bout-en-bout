"""Unitaires — l'outil d'épreuve (C2b) : verdicts, couverture, seuils, rapport."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from kaldera import postgres
from kaldera.etat import Bornes
from kaldera.memoire import SnapshotsEnMemoire
from kaldera.postgres import registre_par_defaut as REGISTRE_PAR_DEFAUT
from kaldera.postgres import snapshots_par_defaut as SNAPSHOTS_PAR_DEFAUT
from tools import epreuve

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}
BORNES = Bornes()


def _etape(agent: str, ecrit: list[str], garde: str = "T1", **champs: Any) -> dict[str, Any]:
    return {
        "agent": agent,
        "ecrit": ecrit,
        "statut": "ok",
        "garde": garde,
        "duree_ms": 5.0,
        "appels_externes": 0,
        **champs,
    }


def _fiche_conforme(attendu: dict[str, Any]) -> dict[str, Any]:
    """Fiche qui respecte son attendu et les règles de rôles."""
    avis = attendu.get("avis_fraude")
    return {
        "reference": attendu["reference"],
        "issue": attendu["issue"],
        "decision": attendu.get("decision"),
        "montant_rembourse": attendu.get("montant_rembourse"),
        "file": attendu.get("file"),
        "mode_degrade": attendu.get("mode_degrade", False),
        "motif": "Motif suffisant",
        "avis_fraude": {"niveau": avis} if avis else None,
        "arret": {"borne": "relances_pieces_max", "valeur": 1, "etape": 4}
        if attendu.get("arret")
        else None,
        "trace": [
            _etape("orchestrateur", ["eligibilite"]),
            _etape("decision", ["issue"], garde="T11"),
        ],
    }


def _rejeu(scenario_id: str) -> dict[str, Any]:
    scenario = copy.deepcopy(SCENARIOS[scenario_id])
    return {
        "scenario": scenario,
        "fiches": [_fiche_conforme(a) for a in scenario["attendu"]],
        "journal": [],
    }


def test_verdicts_tout_conforme() -> None:
    rejeux = [_rejeu(i) for i in ("NOM-01", "INV-01", "PAN-01", "BCL-01")]
    assert all(not e for e in epreuve.verdicts(rejeux, BORNES).values())


def test_ex01_issue_sans_motif() -> None:
    r = _rejeu("NOM-01")
    r["fiches"][0]["motif"] = ""
    assert epreuve.verdicts([r], BORNES)["EX-01"]


def test_ex02_section_ecrite_par_un_autre_agent() -> None:
    r = _rejeu("NOM-01")
    r["fiches"][0]["trace"].append(_etape("pieces", ["issue"]))
    assert epreuve.verdicts([r], BORNES)["EX-02"]


def test_ex02_ecriture_rejetee() -> None:
    r = _rejeu("NOM-01")
    r["fiches"][0]["trace"].append(
        _etape("estimation", [], statut="echec", erreur="ErreurEcriture")
    )
    assert epreuve.verdicts([r], BORNES)["EX-02"]


def test_ex03_champ_hors_contrat_et_donnee_personnelle() -> None:
    r = _rejeu("AF-01")
    demande = r["scenario"]["demandes"][0]
    r["journal"] = [
        {
            "reference": demande["reference"],
            "champs": sorted(epreuve.CHAMPS_CONTRAT | {"iban"}),
            "corps_brut": "{}",
        },
        {
            "reference": demande["reference"],
            "champs": sorted(epreuve.CHAMPS_CONTRAT),
            "corps_brut": json.dumps({"nom": demande["assure"]["nom"]}),
        },
    ]
    ecarts = epreuve.verdicts([r], BORNES)["EX-03"]
    assert len(ecarts) == 2 and all(demande["assure"]["nom"] not in e for e in ecarts)


def test_ex03_requete_conforme() -> None:
    r = _rejeu("AF-01")
    r["journal"] = [
        {
            "reference": r["scenario"]["demandes"][0]["reference"],
            "champs": sorted(epreuve.CHAMPS_CONTRAT),
            "corps_brut": "{}",
        }
    ]
    assert not epreuve.verdicts([r], BORNES)["EX-03"]


def test_ex03_requete_non_lue_en_panne_pas_un_ecart() -> None:
    r = _rejeu("PAN-01")
    r["journal"] = [
        {
            "reference": r["scenario"]["demandes"][0]["reference"],
            "champs": [],
            "statut_http": 503,
            "corps_brut": "{}",
        }
    ]
    assert not epreuve.verdicts([r], BORNES)["EX-03"]


def test_ex04_avis_propage_sur_invalide() -> None:
    r = _rejeu("INV-01")
    r["fiches"][0]["avis_fraude"] = {"niveau": "faible"}
    assert epreuve.verdicts([r], BORNES)["EX-04"]


def test_ex05_panne_mode_degrade_faux() -> None:
    r = _rejeu("PAN-01")
    fiche = next(f for f in r["fiches"] if f["mode_degrade"])
    fiche["mode_degrade"] = False
    assert epreuve.verdicts([r], BORNES)["EX-05"]


def test_ex06_boucle_sans_arret_ou_trop_longue() -> None:
    r = _rejeu("BCL-01")
    r["fiches"][0]["arret"] = None
    assert epreuve.verdicts([r], BORNES)["EX-06"]
    r = _rejeu("BCL-01")
    r["fiches"][0]["trace"] = [_etape("pieces", [])] * (BORNES.etapes_max + 1)
    assert epreuve.verdicts([r], BORNES)["EX-06"]


def test_attendu_ecart_et_fiche_absente() -> None:
    """Review Focus 4 : une référence sans fiche est un écart, pas un KeyError."""
    r = _rejeu("NOM-01")
    r["fiches"][0]["montant_rembourse"] = (r["fiches"][0]["montant_rembourse"] or 0) + 1
    assert epreuve.verdicts([r], BORNES)["attendu"]
    r = _rejeu("NOM-01")
    r["fiches"] = []
    ecarts = epreuve.verdicts([r], BORNES)["attendu"]
    assert ecarts and "aucune fiche" in ecarts[0]


def test_couverture() -> None:
    r = _rejeu("NOM-01")
    r["fiches"][0]["trace"] = [_etape("x", [], garde=f"T{i}") for i in range(1, 11)]
    c = epreuve.couverture([r])
    assert c["manquantes"] == ["T11"] and "T0" in c["hors_scenarios"]
    assert "T0" not in c["manquantes"]


def test_seuils() -> None:
    r = _rejeu("NOM-01")
    reference = r["scenario"]["demandes"][0]["reference"]
    r["journal"] = [{"reference": reference}, {"reference": reference}]
    equipe = {
        "duree_ms": {"p95": 9000.0, "max": 100.0},
        "ecritures_rejetees": 0,
        "etapes": {"max": 5, "moyenne": 5.0},
        "arrets": {"duree_max_s": 1},
    }
    resultat = {s["nom"]: s["ok"] for s in epreuve.seuils([r], equipe, BORNES)}
    assert resultat == {
        "durée p95 (ms)": False,
        "durée max (ms)": True,
        "écritures rejetées": True,
        "étapes max": True,
        "arrêts hors relances_pieces_max": False,
        "appels partenaire par référence": False,
    }


def test_ecrire_rapport(tmp_path: Path) -> None:
    """Review Focus : dossier créé, JSON sérialisable, Markdown lisible."""
    rapport = {
        "date": "2026-10-09",
        "reussi": False,
        "modeles": ["aucun"],
        "modes": {"llm": 0, "repli": 3},
        "duree_s": 9.5,
        "seuils": [{"nom": "étapes max", "mesure": 6, "seuil": "≤ 12", "ok": True}],
        "verdicts": {"EX-01": [], "EX-02": ["KAL-26-0001 : section issue écrite par pieces"]},
        "couverture": {
            "empruntees": ["T1"],
            "manquantes": ["T2"],
            "hors_scenarios": {"T0": "ING-01 / ING-02 (make eval-ingestion)"},
        },
        "scenarios": [{"id": "NOM-01", "ok": True, "ecarts": []}],
        "metriques": {"decision": {"appels": 1}},
        "equipe": {"demandes": 1},
        "bornes": [{"borne": "etapes_max", "valeur": 12, "observe": 6}],
    }
    chemin = epreuve.ecrire_rapport(rapport, tmp_path / "rapports")
    texte = chemin.read_text("utf-8")
    assert chemin.name == "epreuve-2026-10-09.md"
    assert "en échec" in texte and "T2" in texte and "ING-01" in texte and "EX-02" in texte
    assert "llm 0 / repli 3" in texte
    assert json.loads(chemin.with_suffix(".json").read_text("utf-8"))["reussi"] is False


def test_epreuve_rejouable_deux_fois_meme_avec_une_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review Focus 1 : `make` exporte le .env ; sans registre en mémoire, le 2ᵉ passage (ou une
    base injoignable) donnerait « registre … » au lieu de l'avis du partenaire."""
    monkeypatch.setenv("KALDERA_DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    monkeypatch.setattr(postgres, "registre_par_defaut", REGISTRE_PAR_DEFAUT)  # le vrai
    monkeypatch.setattr(postgres, "snapshots_par_defaut", SNAPSHOTS_PAR_DEFAUT)
    scenario = copy.deepcopy(SCENARIOS["AF-01"])
    with epreuve.partenaire_simule() as url:
        for _ in range(2):
            rejeu = epreuve.rejouer(url, scenario)
            assert all(f["avis_fraude"] is not None for f in rejeu["fiches"]), rejeu["fiches"]
    assert isinstance(epreuve.orchestrateur(url).snapshots, SnapshotsEnMemoire)


def test_simulateur_arrete_meme_si_le_rejeu_leve() -> None:
    """Review Focus 2."""
    with pytest.raises(RuntimeError), epreuve.partenaire_simule() as url:
        assert httpx.get(f"{url}/_sim/etat", timeout=2).status_code == 200
        raise RuntimeError("rejeu interrompu")
    with pytest.raises(httpx.HTTPError):
        httpx.get(f"{url}/_sim/etat", timeout=1)


def test_epreuve_complete_reussie(tmp_path: Path) -> None:
    """Fumée : les 28 scénarios rejoués contre le simulateur en processus (≈ 10 s)."""
    rapport = epreuve.evaluer()
    echecs = {k: e for k, e in rapport["verdicts"].items() if e}
    assert rapport["reussi"], (echecs, [s for s in rapport["seuils"] if not s["ok"]])
    assert len(rapport["scenarios"]) == 28
    assert rapport["modes"].get("llm", 0) == 0 and rapport["modes"]["repli"] > 0
    assert rapport["couverture"]["manquantes"] == []
    assert epreuve.ecrire_rapport(rapport, tmp_path).exists()


# ------------------------------------------------------------------ revue finale


def test_ex03_donnee_personnelle_echappee_en_ascii() -> None:
    """httpx < 0.28 échappe le non ASCII : la fuite doit être vue quand même."""
    r = _rejeu("AF-01")
    demande = r["scenario"]["demandes"][0]
    description = demande["sinistre"]["description"]
    corps = json.dumps({"description": description})  # ensure_ascii par défaut
    assert "\\u" in corps
    r["journal"] = [
        {"reference": demande["reference"], "champs": sorted(epreuve.CHAMPS_CONTRAT),
         "corps_brut": corps}
    ]
    ecarts = epreuve.verdicts([r], BORNES)["EX-03"]
    assert ecarts and all(description not in e for e in ecarts)


def test_ex03_reference_illisible_controlee_quand_meme() -> None:
    r = _rejeu("AF-01")
    email = r["scenario"]["demandes"][0]["assure"]["email"]
    r["journal"] = [
        {"reference": None, "champs": [], "statut_http": 503,
         "corps_brut": json.dumps({"x": email})}
    ]
    ecarts = epreuve.verdicts([r], BORNES)["EX-03"]
    assert ecarts and all(email not in e for e in ecarts)


@pytest.mark.parametrize(("scenario_id", "exigence"),
                         [("INV-01", "EX-04"), ("PAN-01", "EX-05"), ("BCL-01", "EX-06")])
def test_categorie_sans_fiche_evaluee_est_un_ecart(scenario_id: str, exigence: str) -> None:
    r = _rejeu(scenario_id)
    r["fiches"] = []
    assert epreuve.verdicts([r], BORNES)[exigence]


@pytest.mark.parametrize("avant", [None, ""])
def test_jeton_absent_ou_vide_remplace_puis_restaure(
    monkeypatch: pytest.MonkeyPatch, avant: str | None
) -> None:
    if avant is None:
        monkeypatch.delenv("PARTENAIRE_JETON", raising=False)
    else:
        monkeypatch.setenv("PARTENAIRE_JETON", avant)
    with epreuve.partenaire_simule() as url:
        assert os.environ["PARTENAIRE_JETON"] == epreuve.JETON_RECETTE
        rejeu = epreuve.rejouer(url, copy.deepcopy(SCENARIOS["AF-01"]))
        assert all(f["avis_fraude"] is not None for f in rejeu["fiches"])
    assert os.environ.get("PARTENAIRE_JETON") == avant
