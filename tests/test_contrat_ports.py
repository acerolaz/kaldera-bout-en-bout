"""Contrat des ports (LSP) : mêmes tests pour l'adaptateur mémoire et l'adaptateur PostgreSQL."""

from __future__ import annotations

from typing import Any

import pytest

from kaldera.etat import EtatDemande
from kaldera.memoire import RegistreA2AEnMemoire, SnapshotsEnMemoire
from kaldera.ports import ErreurPersistance, RegistreA2A, Snapshots

REF = "KAL-26-9001"
FICHE = {"reference": REF, "issue": "escalade", "file": "gestionnaire"}


@pytest.fixture(params=["memoire", pytest.param("postgres", marks=pytest.mark.integration)])
def ports(request: pytest.FixtureRequest) -> tuple[Snapshots, RegistreA2A]:
    if request.param == "memoire":
        return SnapshotsEnMemoire(), RegistreA2AEnMemoire()
    from kaldera.postgres import RegistreA2APostgres, SnapshotsPostgres

    base = request.getfixturevalue("base")
    return SnapshotsPostgres(base), RegistreA2APostgres(base)


def _etat(reference: Any = REF) -> EtatDemande:
    return EtatDemande(demande={"reference": reference, "contrat": {"numero": "CTR-1"}})


def test_terminer_une_seule_fois(ports: tuple[Snapshots, RegistreA2A]) -> None:
    snapshots, _ = ports
    etat = _etat()
    snapshots.debuter(etat)
    assert snapshots.terminer(etat, FICHE) is True
    assert snapshots.terminer(etat, FICHE) is False


def test_demande_terminee_jamais_fauchee(ports: tuple[Snapshots, RegistreA2A]) -> None:
    snapshots, _ = ports
    etat = _etat()
    snapshots.debuter(etat)
    snapshots.terminer(etat, FICHE)
    assert snapshots.faucher(0) == []


def test_demande_inactive_fauchee_une_seule_fois(ports: tuple[Snapshots, RegistreA2A]) -> None:
    snapshots, _ = ports
    etat = _etat()
    snapshots.debuter(etat)
    etat.etat_courant = "pieces"
    snapshots.enregistrer(etat)
    ((reference, brut),) = snapshots.faucher(0)
    assert reference == REF and brut["etat_courant"] == "pieces"
    assert EtatDemande.model_validate(brut).demande["reference"] == REF
    snapshots.classer(REF, FICHE)
    assert snapshots.faucher(0) == []  # classée : jamais escaladée deux fois
    assert snapshots.terminer(etat, FICHE) is False  # le reaper a gagné


def test_demande_recente_non_fauchee(ports: tuple[Snapshots, RegistreA2A]) -> None:
    snapshots, _ = ports
    snapshots.debuter(_etat())
    assert snapshots.faucher(3600) == []


def test_demande_sans_reference_refusee(ports: tuple[Snapshots, RegistreA2A]) -> None:
    snapshots, _ = ports
    with pytest.raises(ErreurPersistance):
        snapshots.debuter(_etat(reference=None))


def test_un_seul_appel_partenaire_reserve(ports: tuple[Snapshots, RegistreA2A]) -> None:
    snapshots, registre = ports
    snapshots.debuter(_etat())  # en base, le registre référence la demande
    assert registre.reserver(REF) is True
    assert registre.reserver(REF) is False
    registre.noter(REF, "EVA-1")


def test_demande_fauchee_sans_fiche_reprise_au_passage_suivant(
    ports: tuple[Snapshots, RegistreA2A],
) -> None:
    snapshots, _ = ports
    snapshots.debuter(_etat())
    assert [r for r, _ in snapshots.faucher(0)] == [REF]  # le reaper meurt avant classer
    assert [r for r, _ in snapshots.faucher(0)] == [REF]  # repris, jamais oublié
