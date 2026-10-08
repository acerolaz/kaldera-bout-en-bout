# SP2 · Persistance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Les pièces passent par un port (`DepotPieces`), l'état de chaque demande est snapshoté dans PostgreSQL après chaque transition, et un reaper escalade les demandes dont le processus est mort.

**Architecture:** `ports.py` définit `PieceRef` et trois protocoles ; `memoire.py` en donne les adaptateurs sans base, `postgres.py` les adaptateurs psycopg 3 synchrones. L'orchestrateur charge les descripteurs de pièces dans la vue de `pieces`, écrit un snapshot à chaque transition via `_persister` (une `ErreurPersistance` ne bloque jamais une décision) et termine la demande par un compare-and-set. `reaper.py` fauche les demandes inactives et classe une fiche de secours, sans rejouer la machine.

**Tech Stack:** Python 3.11, Pydantic 2, pydantic-settings, psycopg 3 + psycopg_pool (synchrone), PostgreSQL 16 (Docker), pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-sp2-persistance-design.md`

## Global Constraints

- Répertoire de travail : worktree `.claude/worktrees/chantier1`, branche `feature/chantier1-orchestration`. Toutes les commandes partent de là.
- Python `>=3.11,<3.12`. Une seule dépendance ajoutée : `psycopg[binary,pool]>=3.2,<4`.
- `make test` (= `uv run pytest`) reste **sans base** : marqueur `integration` exclu par défaut. Résultat attendu à chaque fin de tâche : 14 échecs, tous dans `tests/acceptance/test_collaboration_a2a.py` (hors périmètre), tout le reste vert.
- `uv run ruff check .`, `uv run ruff format --check src` et `uv run mypy src` restent verts.
- Aucune capture large : un seul `except Exception` dans `src/` (celui de `Orchestrateur.traiter`, SP1). Les adaptateurs convertissent `psycopg.Error` en `ErreurPersistance`.
- Montants : `Decimal` seulement dans l'adaptateur Postgres (`numeric` → `round(float(m), 2)`) ; le domaine reste en float.
- Sans `KALDERA_DATABASE_URL`, aucune persistance. `DepotDepuisDemande` reste le dépôt de pièces par défaut **même avec une base** : la table `pieces` n'est remplie qu'à partir de SP3 (ingestion).
- Les tests d'intégration lisent `TEST_DATABASE_URL` (le `conftest.py` racine efface toutes les variables `KALDERA_*`).
- Noms, docstrings, commentaires et commits en français. Chaque commit finit par `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Décision de plan (écart à la spec §2) : les migrations vivent dans `src/kaldera/migrations/` (lues par `importlib.resources`, comme `prompts/`), pas à la racine.
- Docker : `make test-integration` exige le démon. Si `docker info` échoue, **demander à l'utilisateur** de lancer Docker Desktop ; ne pas le démarrer soi-même.

## Review Focus

- Base configurée mais injoignable (`KALDERA_DATABASE_URL` vers un port fermé) : `Orchestrateur` se construit, traite sans snapshot, aucune exception → test en Task 7.
- Base configurée et demande sans `reference` (`{}`) : `debuter` échoue, la fiche est quand même rendue → test en Task 4.
- Fin normale d'une demande que le reaper a déjà fauchée : l'appelant reçoit sa fiche, la base garde `secours`, avertissement journalisé → test en Task 4.
- Lot parallèle partageant un `SnapshotsEnMemoire` : toutes les demandes finissent `terminee` → test en Task 4.
- Pièce de type inconnu dans le JSON (`"type": "devis"`) : étape `pieces` en échec, escalade `gestionnaire`, pas de plantage → test en Task 2.

---

### Task 1: `PieceRef`, ports et dépôt niveau 0

**Files:**
- Create: `src/kaldera/ports.py`
- Create: `src/kaldera/memoire.py`
- Modify: `src/kaldera/espace_assure.py`
- Test: `tests/unit/test_ports.py`

**Interfaces:**
- Produces: `ports.PieceRef` (champs `type`, `lisible`, `montant: float | None`, `piece_id: UUID | None`, `sha256: str | None`, `statut_analyse: Literal["ok","echec"]`) ; `ports.DepotPieces` (`initiales(demande: dict) -> list[PieceRef]`, `depots(demande: dict) -> list[PieceRef]`) ; `ports.Snapshots` et `ports.RegistreA2A` (protocoles, signatures ci-dessous) ; `ports.ErreurPersistance(Exception)` ; `memoire.DepotDepuisDemande` ; `espace_assure.depot_pour(depots: list[dict], type_piece: str, tentative: int) -> dict | None`. `espace_assure.demander_piece` reste jusqu'à la Task 2.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_ports.py` :

```python
"""Unitaires — pièces par référence (dossier 2.4 bis)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kaldera.espace_assure import depot_pour
from kaldera.memoire import DepotDepuisDemande
from kaldera.ports import PieceRef

DEMANDE = {
    "reference": "KAL-26-0107",
    "pieces": [{"type": "facture", "lisible": True, "montant": 640.0}],
    "espace_assure": {
        "depots": [
            {"type": "photo", "lisible": False},
            {"type": "photo", "lisible": True},
        ]
    },
}


def test_piece_en_echec_d_analyse_est_illisible() -> None:
    piece = PieceRef(type="photo", lisible=True, statut_analyse="echec")
    assert piece.lisible is False


def test_piece_de_type_inconnu_refusee() -> None:
    with pytest.raises(ValidationError):
        PieceRef.model_validate({"type": "devis", "lisible": True})


def test_depot_niveau_0_lit_la_demande() -> None:
    depot = DepotDepuisDemande()
    assert depot.initiales(DEMANDE) == [PieceRef(type="facture", lisible=True, montant=640.0)]
    assert [p.lisible for p in depot.depots(DEMANDE)] == [False, True]
    assert depot.initiales({}) == [] and depot.depots({}) == []


@pytest.mark.parametrize(
    ("tentative", "lisible"),
    [(0, False), (1, True), (5, True)],  # au-delà : l'assuré re-soumet son dernier dépôt
)
def test_depot_pour_la_tentative(tentative: int, lisible: bool) -> None:
    depots = DEMANDE["espace_assure"]["depots"]
    assert depot_pour(depots, "photo", tentative) == {"type": "photo", "lisible": lisible}


def test_depot_pour_un_type_jamais_depose() -> None:
    assert depot_pour(DEMANDE["espace_assure"]["depots"], "facture", 0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ports.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'kaldera.ports'` (ou `kaldera.memoire`).

- [ ] **Step 3: Implement**

`src/kaldera/ports.py` :

```python
"""Ports de persistance (dossier 2.4 bis, 2.5, 2.6) : le domaine ne connaît que ces contrats.

Adaptateurs : ``memoire`` (sans base, niveau 0 et tests), ``postgres`` (production).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, model_validator

from .etat import EtatDemande


class ErreurPersistance(Exception):
    """La base n'a pas pu lire ou écrire : jamais bloquant pour une décision (EX-01)."""


class PieceRef(BaseModel):
    """Descripteur d'une pièce : une référence, jamais d'octets (claim check)."""

    type: Literal["facture", "photo", "depot_plainte"]
    lisible: bool
    montant: float | None = None  # numeric → float au centime dans l'adaptateur Postgres
    piece_id: UUID | None = None
    sha256: str | None = None
    statut_analyse: Literal["ok", "echec"] = "ok"

    @model_validator(mode="after")
    def _illisible_si_echec(self) -> PieceRef:
        if self.statut_analyse == "echec":
            self.lisible = False
        return self


class DepotPieces(Protocol):
    """Lecture des pièces d'une demande ; seule la vue de ``pieces`` les reçoit."""

    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]: ...

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]: ...  # dans l'ordre de dépôt


class Snapshots(Protocol):
    """Exécution durable (dossier 2.5) : un snapshot par transition, CAS en fin de traitement."""

    def debuter(self, etat: EtatDemande) -> None: ...

    def enregistrer(self, etat: EtatDemande) -> None: ...

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool: ...

    def faucher(self, age_s: float) -> list[tuple[str, dict[str, Any]]]: ...

    def classer(self, reference: str, fiche: dict[str, Any]) -> None: ...


class RegistreA2A(Protocol):
    """Un appel partenaire par dossier (contrat §6) ; branché au chantier 2."""

    def reserver(self, reference: str) -> bool: ...

    def noter(self, reference: str, evaluation_id: str) -> None: ...
```

`src/kaldera/memoire.py` :

```python
"""Adaptateurs sans base : niveau 0 (demande JSON) et tests."""

from __future__ import annotations

from typing import Any

from .ports import PieceRef


class DepotDepuisDemande:
    """Niveau 0 : ``pieces`` et ``espace_assure.depots`` de la demande (§3)."""

    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]:
        return [PieceRef.model_validate(p) for p in demande.get("pieces", [])]

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]:
        depots = demande.get("espace_assure", {}).get("depots", [])
        return [PieceRef.model_validate(p) for p in depots]
```

Dans `src/kaldera/espace_assure.py`, ajouter après `demander_piece` :

```python
def depot_pour(
    depots: list[dict[str, Any]], type_piece: str, tentative: int
) -> dict[str, Any] | None:
    """Dépôt n°``tentative`` (0 = première relance) de ce type ; l'assuré re-soumet le dernier."""
    du_type = [piece for piece in depots if piece.get("type") == type_piece]
    if not du_type:
        return None
    return dict(du_type[min(tentative, len(du_type) - 1)])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_ports.py -q && uv run mypy src`
Expected: PASS ; mypy `Success`.

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/ports.py src/kaldera/memoire.py src/kaldera/espace_assure.py tests/unit/test_ports.py
git commit -m "feat(ports): PieceRef, ports de persistance et dépôt de pièces niveau 0

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Les pièces passent par la vue

**Files:**
- Modify: `src/kaldera/orchestrateur.py` (`__init__`, `_etape`, `vue_filtree`)
- Modify: `src/kaldera/agents.py` (`AgentPieces`)
- Modify: `src/kaldera/agents_llm.py` (`_outils_pieces`)
- Modify: `src/kaldera/espace_assure.py` (supprimer `demander_piece`, docstring)
- Test: `tests/unit/test_agents.py`, `tests/unit/test_agents_llm.py`, `tests/unit/test_orchestrateur.py`

**Interfaces:**
- Consumes: `DepotPieces`, `PieceRef` (Task 1), `DepotDepuisDemande`, `depot_pour`.
- Produces: `Orchestrateur(..., depot: DepotPieces | None = None)` (défaut `DepotDepuisDemande()`) ; `vue_filtree(etat, courant, bornes=BORNES, depot=NIVEAU_0)` ; vue de `pieces` = `{"demande": <sans "pieces" ni "espace_assure">, "relances": int, "initiales": list[dict], "depots": list[dict]}` (dicts = `PieceRef.model_dump(mode="json")`).

- [ ] **Step 1: Write the failing tests**

Dans `tests/unit/test_agents.py`, remplacer le helper `_pieces` (importer `EtatDemande` depuis `kaldera.etat`, `Etat` depuis `kaldera.machine`, `vue_filtree` depuis `kaldera.orchestrateur`) :

```python
def _vue_pieces(demande: dict[str, Any], relances: int = 0) -> dict[str, Any]:
    etat = EtatDemande(demande=demande)
    etat.compteurs.relances = relances
    return vue_filtree(etat, Etat.PIECES)


def _pieces(scenario: str, relances: int = 0) -> dict[str, Any]:
    patch = AgentPieces()(_vue_pieces(_demande(scenario), relances))
    assert set(patch) == {"pieces"}
    return patch["pieces"]
```

et ajouter :

```python
def test_l_agent_pieces_ne_lit_que_les_descripteurs() -> None:
    vue = _vue_pieces(_demande("NOM-07"), relances=1)
    assert "pieces" not in vue["demande"] and "espace_assure" not in vue["demande"]
    assert AgentPieces()(vue)["pieces"]["statut"] == "complet"
```

Dans `tests/unit/test_agents_llm.py` : `_vues()["pieces"]` devient `_vue_pieces(demande)` (même helper, mêmes imports, copié en tête du fichier) ; les deux `vue = {"demande": _demande("NOM-07"), "relances": 1}` deviennent `vue = _vue_pieces(_demande("NOM-07"), 1)` ; dans `test_exception_d_outil_finit_en_outil_refuse`, remplacer `espace_assure.demander_piece` par `espace_assure.depot_pour` (deux occurrences : `reel` et `monkeypatch.setattr`).

Dans `tests/unit/test_orchestrateur.py` :

```python
class DepotEspion:
    def __init__(self) -> None:
        self.lu = False

    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]:
        self.lu = True
        return [
            PieceRef(type="facture", lisible=True, montant=600.0),
            PieceRef(type="photo", lisible=True),
        ]

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]:
        return []


def test_les_pieces_viennent_du_port() -> None:
    depot = DepotEspion()
    demande = _demande("NOM-09")  # photo absente du JSON : manquante au niveau 0
    fiche = Orchestrateur(evaluer=_sans_partenaire, depot=depot).traiter(demande)
    assert depot.lu and fiche["decision"] == "acceptee"


def test_piece_de_type_inconnu_escalade_sans_planter() -> None:
    demande = _demande("NOM-01")
    demande["pieces"][0]["type"] = "devis"
    fiche = _orchestrateur().traiter(demande)
    etape = [e for e in fiche["trace"] if e["action"] == "pieces"][0]
    assert etape["statut"] == "echec"
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")
```

(importer `PieceRef` depuis `kaldera.ports`). NOM-09 (bris de glace, confort, 600 € déclarés) est éligible ; avec une facture de 600 € et une photo lisibles, aucun indicateur F1–F4 n'est levé : 600 − 150 = 450 € acceptés.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit -q 2>&1 | tail -15`
Expected: FAIL — échecs attendus : `test_l_agent_pieces_ne_lit_que_les_descripteurs` (`"pieces" in vue["demande"]`), `test_les_pieces_viennent_du_port` (`TypeError: unexpected keyword argument 'depot'`), `test_piece_de_type_inconnu_escalade_sans_planter` (étape `ok`), et `test_exception_d_outil_finit_en_outil_refuse` (`depot_pour` jamais appelé par l'agent).

- [ ] **Step 3: Implement**

`src/kaldera/orchestrateur.py` :

1. Imports : `from .memoire import DepotDepuisDemande` et `from .ports import DepotPieces`. Après les imports : `NIVEAU_0 = DepotDepuisDemande()  # sans état : partagé`.
2. `__init__` : nouveau paramètre `depot: DepotPieces | None = None` (après `config`) ; `self.depot = depot or NIVEAU_0`.
3. Dans `_etape` : `vue_filtree(etat, courant, self.bornes)` devient `vue_filtree(etat, courant, self.bornes, self.depot)`.
4. `vue_filtree` : signature `def vue_filtree(etat: EtatDemande, courant: Etat, bornes: Bornes = BORNES, depot: DepotPieces = NIVEAU_0) -> dict[str, Any]:` et branche `PIECES` :

```python
    if courant is Etat.PIECES:
        # claim check : l'agent ne voit que des descripteurs, chargés par le port
        demande.pop("pieces", None)
        demande.pop("espace_assure", None)
        return {
            "demande": demande,
            "relances": etat.compteurs.relances,
            "initiales": [p.model_dump(mode="json") for p in depot.initiales(etat.demande)],
            "depots": [p.model_dump(mode="json") for p in depot.depots(etat.demande)],
        }
```

`src/kaldera/agents.py`, `AgentPieces.__call__` :

```python
    def __call__(self, vue: dict[str, Any]) -> dict[str, Any]:
        demande, relances, depots = vue["demande"], vue["relances"], vue["depots"]
        recues = list(vue["initiales"])
        for tentative in range(relances):
            for type_piece in _manquantes(demande, recues):
                depot = espace_assure.depot_pour(depots, type_piece, tentative)
                if depot is not None:
                    recues.append(depot)
        manquantes = _manquantes(demande, recues)
        if not manquantes:
            statut = "complet"
        elif any(espace_assure.depot_pour(depots, t, relances) for t in manquantes):
            # l'assuré a déjà déposé ce type : une relance peut aboutir (ou re-soumettre
            # le même dépôt illisible — c'est la borne de relances qui tranche)
            statut = "incomplet"
        else:
            statut = "manquant"  # rien à relancer
        return {
            "pieces": {
                "statut": statut,
                "manquantes": manquantes,
                "retenues": [p for p in recues if p.get("lisible", False)],
            }
        }
```

`src/kaldera/agents_llm.py`, `_outils_pieces` :

```python
def _outils_pieces(vue: Vue, ref: dict[str, Any]) -> list[Outil]:
    demande, relances, depots = vue["demande"], vue["relances"], vue["depots"]
    requises = regles.PIECES_EXIGEES[demande["sinistre"]["type"]]

    def lire_depot(args: dict[str, Any]) -> Any:
        k = args.get("k")
        if not isinstance(k, int) or isinstance(k, bool) or k != relances or relances < 1:
            return {"refus": f"seul le dépôt n°{relances} est lisible"}
        return [d for t in requises if (d := espace_assure.depot_pour(depots, t, k - 1))]

    entier = {"type": "object", "properties": {"k": {"type": "integer"}}, "required": ["k"]}
    return [
        Outil("verifier_completude", "Statut des pièces (fait foi).", lambda a: ref),
        Outil(
            "pieces_requises", "Types de pièces exigés pour ce sinistre.", lambda a: list(requises)
        ),
        Outil("lister_pieces", "Pièces jointes à la demande.", lambda a: vue["initiales"]),
        Outil(
            "lire_depot", "Dépôt n°k de l'espace assuré (k = relance en cours).", lire_depot, entier
        ),
    ]
```

`src/kaldera/espace_assure.py` : supprimer `demander_piece` ; docstring du module : « Les dépôts qu'un assuré effectue … sont lus par le port `DepotPieces` ; comme sur le portail réel, un assuré qui n'a rien de nouveau à transmettre re-soumet son dernier dépôt pour le type de pièce demandé. »

Vérifier : `grep -rn demander_piece src tests` → aucune ligne.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q 2>&1 | tail -3 && uv run ruff check . && uv run mypy src`
Expected: 14 failed (A2A), le reste vert — dont `tests/unit/test_invariance.py` (34 demandes) et les 28 scénarios d'acceptance.

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "feat(pieces): descripteurs chargés par le port DepotPieces, seule la vue de pieces les voit

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Snapshots et registre A2A en mémoire, contrat des ports

**Files:**
- Modify: `src/kaldera/memoire.py`
- Create: `tests/test_contrat_ports.py`

**Interfaces:**
- Consumes: `Snapshots`, `RegistreA2A`, `ErreurPersistance` (Task 1), `EtatDemande`.
- Produces: `memoire.SnapshotsEnMemoire` (attribut `lignes: dict[str, dict]` avec clés `numero_contrat`, `etat` (dict JSON), `etat_courant`, `statut`, `maj`, `fiche`) ; `memoire.RegistreA2AEnMemoire`. Fixture `ports` de `tests/test_contrat_ports.py` → `(Snapshots, RegistreA2A)`, paramétrée (`"memoire"` ; `"postgres"` ajouté en Task 7).

- [ ] **Step 1: Write the failing tests**

`tests/test_contrat_ports.py` :

```python
"""Contrat des ports (LSP) : mêmes tests pour l'adaptateur mémoire et l'adaptateur PostgreSQL."""

from __future__ import annotations

from typing import Any

import pytest

from kaldera.etat import EtatDemande
from kaldera.memoire import RegistreA2AEnMemoire, SnapshotsEnMemoire
from kaldera.ports import ErreurPersistance, RegistreA2A, Snapshots

REF = "KAL-26-9001"
FICHE = {"reference": REF, "issue": "escalade", "file": "gestionnaire"}


@pytest.fixture(params=["memoire"])
def ports(request: pytest.FixtureRequest) -> tuple[Snapshots, RegistreA2A]:
    return SnapshotsEnMemoire(), RegistreA2AEnMemoire()


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
    assert snapshots.faucher(0) == []
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_contrat_ports.py -q`
Expected: FAIL — `ImportError: cannot import name 'RegistreA2AEnMemoire'`.

- [ ] **Step 3: Implement**

Dans `src/kaldera/memoire.py` (imports : `import copy`, `import threading`, `from time import monotonic`, `from .etat import EtatDemande`, `from .ports import ErreurPersistance, PieceRef`) :

```python
def _reference(etat: EtatDemande) -> str:
    reference = etat.demande.get("reference")
    if not isinstance(reference, str):  # même refus que la clé primaire en base
        raise ErreurPersistance("demande sans référence")
    return reference


class SnapshotsEnMemoire:
    """Mêmes règles que ``demandes`` en base (CAS) ; tests et démonstration."""

    def __init__(self) -> None:
        self.lignes: dict[str, dict[str, Any]] = {}
        self._verrou = threading.Lock()

    def debuter(self, etat: EtatDemande) -> None:
        contrat = etat.demande.get("contrat")
        with self._verrou:
            self.lignes[_reference(etat)] = {
                "numero_contrat": contrat.get("numero") if isinstance(contrat, dict) else None,
                "etat": etat.model_dump(mode="json"),
                "etat_courant": etat.etat_courant,
                "statut": "en_cours",
                "maj": monotonic(),
                "fiche": None,
            }

    def enregistrer(self, etat: EtatDemande) -> None:
        with self._verrou:
            ligne = self.lignes.get(_reference(etat))
            if ligne is not None and ligne["statut"] == "en_cours":
                ligne.update(
                    etat=etat.model_dump(mode="json"),
                    etat_courant=etat.etat_courant,
                    maj=monotonic(),
                )

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        with self._verrou:
            ligne = self.lignes.get(_reference(etat))
            if ligne is None or ligne["statut"] != "en_cours":
                return False
            ligne.update(
                statut="terminee",
                etat=etat.model_dump(mode="json"),
                etat_courant=etat.etat_courant,
                fiche=copy.deepcopy(fiche),
                maj=monotonic(),
            )
            return True

    def faucher(self, age_s: float) -> list[tuple[str, dict[str, Any]]]:
        limite = monotonic() - age_s
        with self._verrou:
            mortes = [
                (reference, ligne)
                for reference, ligne in self.lignes.items()
                if ligne["statut"] == "en_cours" and ligne["maj"] < limite
            ]
            for _, ligne in mortes:
                ligne.update(statut="secours", maj=monotonic())
            return [(reference, copy.deepcopy(ligne["etat"])) for reference, ligne in mortes]

    def classer(self, reference: str, fiche: dict[str, Any]) -> None:
        with self._verrou:
            if reference in self.lignes:
                self.lignes[reference]["fiche"] = copy.deepcopy(fiche)


class RegistreA2AEnMemoire:
    """Un appel partenaire par dossier ; même règle que ``appels_partenaire``."""

    def __init__(self) -> None:
        self.evaluations: dict[str, str | None] = {}
        self._verrou = threading.Lock()

    def reserver(self, reference: str) -> bool:
        with self._verrou:
            if reference in self.evaluations:
                return False
            self.evaluations[reference] = None
            return True

    def noter(self, reference: str, evaluation_id: str) -> None:
        with self._verrou:
            if reference in self.evaluations:
                self.evaluations[reference] = evaluation_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_contrat_ports.py -q && uv run mypy src`
Expected: 6 passed ; mypy `Success`.

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/memoire.py tests/test_contrat_ports.py
git commit -m "feat(memoire): snapshots et registre A2A en mémoire, contrat des ports

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Snapshot après chaque transition

**Files:**
- Modify: `src/kaldera/orchestrateur.py` (`__init__`, `traiter`, `_executer`, `_etape`, `_sauter`, nouveau `_persister`)
- Test: `tests/unit/test_persistance.py`

**Interfaces:**
- Consumes: `Snapshots`, `ErreurPersistance` (Task 1), `SnapshotsEnMemoire` (Task 3).
- Produces: `Orchestrateur(..., snapshots: Snapshots | None = None)` (défaut `None` = aucune persistance ; Task 7 branche la base) ; `Orchestrateur._persister(etat, ecrire: Callable[[Snapshots], Any]) -> Any`. Étape tracée enrichie de `"persistance": "echec"` quand une écriture a échoué.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_persistance.py` :

```python
"""Unitaires — exécution durable : snapshot par transition (dossier 2.5, niveau 2)."""

from __future__ import annotations

import copy
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import EtatDemande
from kaldera.machine import Etat
from kaldera.memoire import SnapshotsEnMemoire
from kaldera.orchestrateur import Orchestrateur
from kaldera.ports import ErreurPersistance

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}
NOMINAUX = [d for s in SCENARIOS.values() if s["categorie"] == "nominal" for d in s["demandes"]]
DECISIFS = ("issue", "decision", "montant_rembourse", "file", "mode_degrade")


def _demande(scenario: str = "NOM-01") -> dict[str, Any]:
    return copy.deepcopy(SCENARIOS[scenario]["demandes"][0])


def _sans_partenaire(demande: dict[str, Any], timeout: float) -> None:
    raise AssertionError("aucun appel au partenaire attendu")


class Espion(SnapshotsEnMemoire):
    def __init__(self) -> None:
        super().__init__()
        self.appels: list[Any] = []

    def debuter(self, etat: EtatDemande) -> None:
        self.appels.append("debuter")
        super().debuter(etat)

    def enregistrer(self, etat: EtatDemande) -> None:
        self.appels.append(("enregistrer", etat.etat_courant))
        super().enregistrer(etat)

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        self.appels.append("terminer")
        return super().terminer(etat, fiche)


class EnPanne(SnapshotsEnMemoire):
    def debuter(self, etat: EtatDemande) -> None:
        raise ErreurPersistance("base injoignable")

    def enregistrer(self, etat: EtatDemande) -> None:
        raise ErreurPersistance("base injoignable")

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        raise ErreurPersistance("base injoignable")


def test_un_snapshot_par_transition() -> None:
    snapshots = Espion()
    fiche = Orchestrateur(evaluer=_sans_partenaire, snapshots=snapshots).traiter(_demande())
    assert snapshots.appels == [
        "debuter",
        ("enregistrer", "pieces"),
        ("enregistrer", "estimation"),
        ("enregistrer", "antifraude"),
        ("enregistrer", "decision"),
        ("enregistrer", "acceptee"),
        "terminer",
    ]
    ligne = snapshots.lignes[fiche["reference"]]
    assert ligne["statut"] == "terminee" and ligne["fiche"] == fiche


def test_la_garde_d_entree_est_aussi_snapshotee() -> None:
    snapshots = Espion()
    demande = _demande()
    demande["contrat"]["statut_extraction"] = "non_exploitable"
    Orchestrateur(evaluer=_sans_partenaire, snapshots=snapshots).traiter(demande)
    assert [a for a in snapshots.appels if a[0] == "enregistrer"] == [
        ("enregistrer", "decision"),
        ("enregistrer", "escalade"),
    ]


def test_base_en_panne_ne_change_aucune_issue() -> None:
    temoin = Orchestrateur(evaluer=_sans_partenaire).traiter(_demande())
    fiche = Orchestrateur(evaluer=_sans_partenaire, snapshots=EnPanne()).traiter(_demande())
    assert {k: fiche[k] for k in DECISIFS} == {k: temoin[k] for k in DECISIFS}
    assert all(e.get("persistance") == "echec" for e in fiche["trace"])


def test_demande_sans_reference_rendue_malgre_la_base() -> None:
    fiche = Orchestrateur(snapshots=SnapshotsEnMemoire()).traiter({})
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")


def test_fin_normale_apres_le_reaper(caplog: pytest.LogCaptureFixture) -> None:
    snapshots = SnapshotsEnMemoire()
    orch = Orchestrateur(evaluer=_sans_partenaire, snapshots=snapshots)
    decision = orch.actions[Etat.DECISION]

    def reaper_puis_decision(vue: dict[str, Any]) -> dict[str, Any]:
        snapshots.faucher(0)  # le reaper passe pendant que la demande traîne
        patch, _ = decision.executer(vue, 5.0)  # type: ignore[union-attr]
        return patch

    orch.actions[Etat.DECISION] = reaper_puis_decision
    with caplog.at_level(logging.WARNING):
        fiche = orch.traiter(_demande())
    assert fiche["decision"] == "acceptee"
    assert snapshots.lignes[fiche["reference"]]["statut"] == "secours"
    assert "reaper" in caplog.text


def test_lot_parallele_snapshots_partages() -> None:
    snapshots = SnapshotsEnMemoire()
    # KAL-26-0104 lève F2 : le partenaire est consulté, ici indisponible (mode dégradé)
    orch = Orchestrateur(evaluer=lambda demande, timeout: None, snapshots=snapshots)
    with ThreadPoolExecutor() as pool:
        fiches = list(pool.map(orch.traiter, copy.deepcopy(NOMINAUX)))
    assert {f["reference"] for f in fiches} == set(snapshots.lignes)
    assert {ligne["statut"] for ligne in snapshots.lignes.values()} == {"terminee"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_persistance.py -q`
Expected: FAIL — `TypeError: Orchestrateur.__init__() got an unexpected keyword argument 'snapshots'`.

- [ ] **Step 3: Implement**

`src/kaldera/orchestrateur.py` :

1. Import : `from .ports import DepotPieces, ErreurPersistance, Snapshots`.
2. `__init__` : paramètre `snapshots: Snapshots | None = None` (après `depot`) ; `self.snapshots = snapshots`.
3. `traiter` :

```python
    def traiter(self, demande: dict[str, Any]) -> dict[str, Any]:
        etat = EtatDemande(demande={})
        try:
            etat.demande = copy.deepcopy(demande)  # validée : une entrée malformée passe au filet
            self._executer(etat)
        except Exception as exc:  # noqa: BLE001 — EX-01 : seule capture large du paquet (filet)
            self._filet(etat, exc)
        fiche = construire_fiche(etat)
        if self._persister(etat, lambda s: s.terminer(etat, fiche)) is False:
            LOGGER.warning(
                "demande %s déjà escaladée par le reaper : la base garde l'escalade de secours",
                etat.demande.get("reference"),
            )
        return fiche
```

4. `_executer` : juste après `etat.contrat = ContratDemande.model_validate(...)`, ajouter `self._persister(etat, lambda s: s.debuter(etat))`.
5. Fin de `_etape` et de `_sauter` : juste avant `return suivant`, ajouter `self._persister(etat, lambda s: s.enregistrer(etat))  # exécution durable (2.5)`.
6. Nouvelle méthode, après `_sauter` :

```python
    def _persister(self, etat: EtatDemande, ecrire: Callable[[Snapshots], Any]) -> Any:
        """Écrit un snapshot ; la base ne bloque jamais une décision (EX-01)."""
        if self.snapshots is None:
            return None
        try:
            return ecrire(self.snapshots)
        except ErreurPersistance as exc:
            LOGGER.warning(
                "persistance en échec, demande %s : %s", etat.demande.get("reference"), exc
            )
            if etat.trace:
                etat.trace[-1]["persistance"] = "echec"
            return None
```

`# ponytail: base en panne puis processus mort ⇒ demande hors du reaper ; file d'écritures si mesuré`
en commentaire au-dessus de `_persister`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q 2>&1 | tail -3 && uv run ruff check . && uv run mypy src`
Expected: 14 failed (A2A), le reste vert.

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/orchestrateur.py tests/unit/test_persistance.py
git commit -m "feat(orchestrateur): snapshot après chaque transition, fin de demande par compare-and-set

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Reaper

**Files:**
- Create: `src/kaldera/reaper.py`
- Test: `tests/unit/test_reaper.py`

**Interfaces:**
- Consumes: `Snapshots` (Task 1), `SnapshotsEnMemoire` (Task 3), `Orchestrateur(snapshots=...)` (Task 4), `orchestrateur.construire_fiche`, `orchestrateur._etape_sans_action`.
- Produces: `reaper.faucher(snapshots: Snapshots, age_s: float) -> list[dict[str, Any]]` ; `reaper.fiche_de_secours(reference: str, brut: dict[str, Any]) -> dict[str, Any]`. (`main()` arrive en Task 7.)

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_reaper.py` :

```python
"""Unitaires — le reaper : escalade depuis le dernier snapshot, jamais de rejeu (dossier 2.5)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import AvisFraude, Estimation, EtatDemande
from kaldera.machine import Etat
from kaldera.memoire import SnapshotsEnMemoire
from kaldera.orchestrateur import Orchestrateur
from kaldera.reaper import faucher

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


def _demande(scenario: str = "NOM-01") -> dict[str, Any]:
    return copy.deepcopy(SCENARIOS[scenario]["demandes"][0])


def _processus_tue(vue: dict[str, Any]) -> dict[str, Any]:
    raise KeyboardInterrupt  # BaseException : échappe au filet niveau 1, comme un kill


def test_demande_morte_escaladee_depuis_le_snapshot() -> None:
    snapshots = SnapshotsEnMemoire()
    orch = Orchestrateur(snapshots=snapshots)
    orch.actions[Etat.ESTIMATION] = _processus_tue
    with pytest.raises(KeyboardInterrupt):
        orch.traiter(_demande())

    (fiche,) = faucher(snapshots, 0)
    assert (fiche["reference"], fiche["issue"], fiche["file"]) == (
        "KAL-26-0101",
        "escalade",
        "gestionnaire",
    )
    assert "processus interrompu (reaper)" in fiche["motif"]
    assert "(dernier état : estimation)" in fiche["motif"]
    assert fiche["trace"][-1]["action"] == "reaper"
    ligne = snapshots.lignes["KAL-26-0101"]
    assert ligne["statut"] == "secours" and ligne["fiche"] == fiche
    assert faucher(snapshots, 0) == []  # jamais escaladée deux fois


def test_file_prudente_depuis_le_snapshot() -> None:
    snapshots = SnapshotsEnMemoire()
    etat = EtatDemande(demande=_demande())
    etat.estimation = Estimation(justifie=2000, retenu=2000, franchise=0, plafond=8000, estime=2000)
    etat.avis_fraude = AvisFraude(requis=True, indicateurs=["F1"], statut="indisponible")
    etat.etat_courant = "decision"
    snapshots.debuter(etat)
    (fiche,) = faucher(snapshots, 0)
    assert fiche["file"] == "cellule_fraude"


def test_snapshot_illisible_fiche_minimale() -> None:
    snapshots = SnapshotsEnMemoire()
    snapshots.debuter(EtatDemande(demande=_demande()))
    snapshots.lignes["KAL-26-0101"]["etat"] = {"ancien": "schéma"}
    (fiche,) = faucher(snapshots, 0)
    assert fiche["reference"] == "KAL-26-0101"
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")
    assert fiche["motif"] == "Escalade de secours : snapshot illisible"


def test_rien_a_faucher() -> None:
    assert faucher(SnapshotsEnMemoire(), 0) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_reaper.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'kaldera.reaper'`.

- [ ] **Step 3: Implement**

`src/kaldera/reaper.py` :

```python
"""Reaper (dossier 2.5, niveau 2) : escalade les demandes dont le processus est mort.

Il lit le dernier snapshot, trace son passage et classe une fiche de secours vers la file la plus
prudente. Il ne rejoue jamais la machine : le partenaire refuserait un second appel (-32029).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from .etat import EtatDemande
from .machine import Etat
from .orchestrateur import _etape_sans_action, construire_fiche
from .ports import Snapshots

LOGGER = logging.getLogger(__name__)


def faucher(snapshots: Snapshots, age_s: float) -> list[dict[str, Any]]:
    """Passe en ``secours`` les demandes inactives depuis ``age_s`` s ; retourne leurs fiches."""
    fiches = []
    for reference, brut in snapshots.faucher(age_s):
        fiche = fiche_de_secours(reference, brut)
        snapshots.classer(reference, fiche)
        fiches.append(fiche)
    return fiches


def fiche_de_secours(reference: str, brut: dict[str, Any]) -> dict[str, Any]:
    try:
        etat = EtatDemande.model_validate(brut)
    except ValidationError:
        LOGGER.error("snapshot illisible, demande %s", reference)
        return {
            "reference": reference,
            "issue": "escalade",
            "decision": None,
            "montant_rembourse": None,
            "motif": "Escalade de secours : snapshot illisible",
            "file": "gestionnaire",
            "mode_degrade": False,
            "avis_fraude": None,
            "trace": [],
            "arret": None,
        }
    etat.escalade_forcee = "processus interrompu (reaper)"
    etat.trace.append(
        _etape_sans_action(
            agent="orchestrateur",
            action="reaper",
            statut="echec",
            de=etat.etat_courant,
            vers=Etat.ESCALADE.value,
            garde="reaper",
        )
    )
    return construire_fiche(etat)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_reaper.py -q && uv run ruff check . && uv run mypy src`
Expected: 4 passed ; ruff et mypy verts.

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/reaper.py tests/unit/test_reaper.py
git commit -m "feat(reaper): fiche de secours depuis le dernier snapshot, sans rejeu

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: PostgreSQL — dépendance, schéma, migrations, conteneur de test

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)
- Create: `src/kaldera/migrations/001_schema.sql`
- Create: `src/kaldera/postgres.py`
- Modify: `docker-compose.yml`, `Makefile`, `.env.example`
- Modify: `tests/conftest.py` (fixture `base`)
- Create: `tests/integration/__init__.py` (vide), `tests/integration/test_schema.py`

**Interfaces:**
- Produces: `postgres.ConfigBase` (`database_url: str | None`, `reaper_age_s: float = 30`) ; `postgres.pool(url: str) -> ConnectionPool` (mis en cache, migrations appliquées, connexions `autocommit`) ; `postgres.appliquer_migrations(conn: psycopg.Connection) -> list[str]` ; `postgres._connexion(pool)` (context manager, `psycopg.Error` → `ErreurPersistance`). Fixture `base` (pytest) → `ConnectionPool` sur `TEST_DATABASE_URL`, tables vidées.

- [ ] **Step 0: Docker**

Run: `docker info --format '{{.ServerVersion}}'`
Expected: un numéro de version. Sinon : **s'arrêter et demander à l'utilisateur de lancer Docker Desktop.**

- [ ] **Step 1: Dépendance et outillage**

Run: `uv add "psycopg[binary,pool]>=3.2,<4"`

Dans `pyproject.toml`, section `[tool.pytest.ini_options]`, ajouter :

```toml
addopts = "-m 'not integration'"
markers = ["integration: exige PostgreSQL (make test-integration)"]
```

`docker-compose.yml`, ajouter le service :

```yaml
  postgres:
    image: postgres:16
    profiles: ["integration"]
    environment:
      POSTGRES_USER: kaldera
      POSTGRES_PASSWORD: kaldera
      POSTGRES_DB: kaldera_test
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U kaldera -d kaldera_test"]
      interval: 2s
      timeout: 3s
      retries: 15
```

`Makefile` : ajouter `test-integration` à `.PHONY` et :

```make
TEST_DATABASE_URL ?= postgresql://kaldera:kaldera@localhost:5433/kaldera_test

test-integration:
	docker compose --profile integration up -d --wait postgres
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -m integration -v
```

`.env.example`, à la fin :

```
# Persistance (dossier 2.6) : sans URL, aucune persistance (snapshots désactivés)
KALDERA_DATABASE_URL=
KALDERA_REAPER_AGE_S=30
```

- [ ] **Step 2: Write the failing tests**

Dans `tests/conftest.py`, ajouter (imports `import os`, `from collections.abc import Iterator` déjà ou à ajouter) :

```python
@pytest.fixture
def base() -> Iterator[Any]:
    """Pool PostgreSQL de test, tables vidées (TRUNCATE : la concurrence exige des commits)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL absente : make test-integration")
    from kaldera.postgres import pool

    connexions = pool(url)
    with connexions.connection() as conn:
        conn.execute(
            "TRUNCATE appels_partenaire, pieces, file_ingestion, analyses, demandes, contrats, blobs"
        )
    yield connexions
```

(ajouter `from typing import Any` si absent).

`tests/integration/test_schema.py` :

```python
"""Intégration — les règles de conception tenues par la base (dossier 2.6 bis)."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from kaldera.postgres import appliquer_migrations

pytestmark = pytest.mark.integration
SHA = "a" * 64


def _blob(conn: Any, sha: str = SHA, mime: str = "application/pdf", taille: int = 10) -> None:
    conn.execute(
        "INSERT INTO blobs (sha256, contenu, mime, taille) VALUES (%s, %s, %s, %s)",
        (sha, b"x", mime, taille),
    )


def _demande(conn: Any, reference: str = "KAL-26-9001", statut: str = "en_cours") -> None:
    conn.execute(
        "INSERT INTO demandes (reference, etat, etat_courant, statut) "
        "VALUES (%s, '{}', 'eligibilite', %s)",
        (reference, statut),
    )


def _piece(conn: Any, montant: float | None = None, sha: str = SHA) -> None:
    conn.execute(
        "INSERT INTO pieces (reference, sha256, type, statut_analyse, lisible, montant) "
        "VALUES ('KAL-26-9001', %s, 'facture', 'ok', true, %s)",
        (sha, montant),
    )


def test_migrations_rejouables_sans_effet(base: Any) -> None:
    with base.connection() as conn:
        assert appliquer_migrations(conn) == []


@pytest.mark.parametrize(
    ("mime", "taille"),
    [("application/x-msdownload", 10), ("application/pdf", 10_485_761), ("application/pdf", 0)],
)
def test_fichier_hors_contrat_refuse(base: Any, mime: str, taille: int) -> None:
    with base.connection() as conn, pytest.raises(psycopg.errors.CheckViolation):
        _blob(conn, mime=mime, taille=taille)


def test_empreinte_mal_formee_refusee(base: Any) -> None:
    with base.connection() as conn, pytest.raises(psycopg.errors.CheckViolation):
        _blob(conn, sha="pas-un-sha256")


def test_meme_fichier_depose_deux_fois_compte_une_fois(base: Any) -> None:  # ING-04
    with base.connection() as conn:
        _blob(conn)
        _demande(conn)
        _piece(conn, 640.5)
        with pytest.raises(psycopg.errors.UniqueViolation):
            _piece(conn, 640.5)


def test_montant_nul_refuse(base: Any) -> None:
    with base.connection() as conn:
        _blob(conn)
        _demande(conn)
        with pytest.raises(psycopg.errors.CheckViolation):
            _piece(conn, 0)


def test_statut_de_demande_inconnu_refuse(base: Any) -> None:
    with base.connection() as conn, pytest.raises(psycopg.errors.CheckViolation):
        _demande(conn, statut="perdue")


def test_demande_sans_contrat_acceptee(base: Any) -> None:  # numero_contrat nullable
    with base.connection() as conn:
        _demande(conn)
        (numero,) = conn.execute(
            "SELECT numero_contrat FROM demandes WHERE reference = 'KAL-26-9001'"
        ).fetchone()
    assert numero is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `make test-integration 2>&1 | tail -5`
Expected: FAIL — `ModuleNotFoundError: No module named 'kaldera.postgres'` (le conteneur démarre).

- [ ] **Step 4: Implement**

`src/kaldera/migrations/001_schema.sql` :

```sql
-- Schéma de Kaldera (dossier 2.6 bis). Écarts consignés au journal : demandes.fiche,
-- demandes.numero_contrat nullable.

-- Fichiers : 1 ligne par contenu distinct (déduplication par empreinte)
CREATE TABLE blobs (
  sha256   text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  contenu  bytea NOT NULL,
  mime     text NOT NULL CHECK (mime IN ('application/pdf','image/png','image/jpeg')),
  taille   int  NOT NULL CHECK (taille BETWEEN 1 AND 10485760),
  recu_le  timestamptz NOT NULL DEFAULT now()
);

-- Termes contractuels extraits : 1 ligne par contrat, réutilisée par ses demandes
CREATE TABLE contrats (
  numero            text PRIMARY KEY,
  sha256            text NOT NULL REFERENCES blobs,
  formule           text CHECK (formule IN ('essentiel','confort','premium')),
  date_souscription date,
  franchise numeric(10,2) CHECK (franchise >= 0),
  plafond   numeric(10,2) CHECK (plafond > 0),
  statut_extraction text NOT NULL CHECK (statut_extraction IN ('valide','non_exploitable')),
  violations        text[] NOT NULL DEFAULT '{}',
  modele text NOT NULL,
  version_prompt text NOT NULL
);

-- Cache d'analyse VLM : même fichier + même modèle + même prompt ⇒ même résultat
CREATE TABLE analyses (
  sha256 text REFERENCES blobs,
  modele text,
  version_prompt text,
  resultat jsonb NOT NULL,
  PRIMARY KEY (sha256, modele, version_prompt)
);

-- Snapshot de l'état partagé : claim check, jamais d'octets dans etat
CREATE TABLE demandes (
  reference      text PRIMARY KEY,
  numero_contrat text,
  etat           jsonb NOT NULL,
  etat_courant   text NOT NULL,
  statut         text NOT NULL
                 CHECK (statut IN ('admission','en_cours','terminee','secours')),
  maj            timestamptz NOT NULL DEFAULT now(),
  fiche          jsonb
);
CREATE INDEX demandes_reaper ON demandes (maj) WHERE statut = 'en_cours';

CREATE TABLE pieces (
  piece_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reference      text NOT NULL REFERENCES demandes,
  sha256         text NOT NULL REFERENCES blobs,
  relance        int CHECK (relance >= 1),
  type           text NOT NULL CHECK (type IN ('facture','photo','depot_plainte')),
  statut_analyse text NOT NULL DEFAULT 'en_attente'
                 CHECK (statut_analyse IN ('en_attente','ok','echec')),
  lisible bool,
  montant numeric(10,2) CHECK (montant > 0),
  UNIQUE (reference, sha256)
);

-- Registre A2A : 1 appel par dossier (contrat §6)
CREATE TABLE appels_partenaire (
  reference text PRIMARY KEY REFERENCES demandes,
  reserve_le timestamptz NOT NULL DEFAULT now(),
  evaluation_id text
);

CREATE TABLE file_ingestion (
  id bigserial PRIMARY KEY,
  sha256 text NOT NULL REFERENCES blobs,
  tache  text NOT NULL CHECK (tache IN ('analyser_piece','extraire_contrat')),
  statut text NOT NULL DEFAULT 'en_attente'
         CHECK (statut IN ('en_attente','en_cours','faite','echec'))
);
CREATE INDEX file_a_traiter ON file_ingestion (id) WHERE statut = 'en_attente';
```

`src/kaldera/postgres.py` :

```python
"""Adaptateurs PostgreSQL (dossier 2.6) : psycopg 3 synchrone, SQL brut, migrations versionnées.

Toute ``psycopg.Error`` devient ``ErreurPersistance`` : le domaine ne voit jamais le pilote.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ports import ErreurPersistance

LOGGER = logging.getLogger(__name__)
VERROU_MIGRATIONS = 20261008  # pg_advisory_lock : un seul processus migre à la fois


class ConfigBase(BaseSettings):
    """``KALDERA_DATABASE_URL`` absente ⇒ aucune persistance."""

    model_config = SettingsConfigDict(env_prefix="KALDERA_", env_file=".env", extra="ignore")

    database_url: str | None = None
    reaper_age_s: float = Field(default=30, gt=0)


def appliquer_migrations(conn: psycopg.Connection) -> list[str]:
    """Applique dans l'ordre les ``NNN_*.sql`` absents de ``schema_migrations`` ; rejouable."""
    conn.execute("SELECT pg_advisory_lock(%s)", (VERROU_MIGRATIONS,))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version text PRIMARY KEY, applique_le timestamptz NOT NULL DEFAULT now())"
        )
        faites = {v for (v,) in conn.execute("SELECT version FROM schema_migrations")}
        fichiers = sorted(
            (f for f in resources.files("kaldera").joinpath("migrations").iterdir()
             if f.name.endswith(".sql")),
            key=lambda f: f.name,
        )
        appliquees = []
        for fichier in fichiers:
            if fichier.name in faites:
                continue
            with conn.transaction():
                conn.execute(fichier.read_text("utf-8"))  # sans paramètre : plusieurs requêtes
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (fichier.name,)
                )
            appliquees.append(fichier.name)
        return appliquees
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (VERROU_MIGRATIONS,))


@functools.cache
def pool(url: str) -> ConnectionPool:
    """Un pool par processus et par URL, migrations appliquées à l'ouverture."""
    # ponytail: pool par processus ; injection explicite si une app FastAPI le gère (SP3)
    connexions = ConnectionPool(
        url,
        min_size=1,
        max_size=10,
        timeout=2.0,  # base injoignable : on renonce vite, le traitement continue sans snapshot
        kwargs={"autocommit": True, "connect_timeout": 2},
        open=True,
    )
    try:
        with connexions.connection() as conn:
            appliquer_migrations(conn)
    except psycopg.Error:
        connexions.close()
        raise
    return connexions


@contextmanager
def _connexion(connexions: ConnectionPool) -> Iterator[psycopg.Connection]:
    try:
        with connexions.connection() as conn:
            yield conn
    except psycopg.Error as exc:
        raise ErreurPersistance(f"{type(exc).__name__}: {exc}") from exc
```

Remarque : ruff format reformatera la compréhension de `fichiers` ; lancer `uv run ruff format src/kaldera/postgres.py`. Si mypy se plaint des paramètres génériques de `ConnectionPool` ou `psycopg.Connection`, annoter `ConnectionPool[psycopg.Connection[tuple[Any, ...]]]` / `psycopg.Connection[Any]`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `make test-integration 2>&1 | tail -3 && uv run pytest -q 2>&1 | tail -1 && uv run ruff check . && uv run mypy src`
Expected: intégration : 9 passed ; suite par défaut : 14 failed (A2A), le reste vert, les tests d'intégration désélectionnés.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock docker-compose.yml Makefile .env.example src/kaldera/postgres.py src/kaldera/migrations tests/conftest.py tests/integration
git commit -m "feat(postgres): schéma 2.6 bis, migrations versionnées, pool psycopg, tests d'intégration

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Adaptateurs PostgreSQL, base par défaut, reaper en service, journal

**Files:**
- Modify: `src/kaldera/postgres.py` (adaptateurs, `snapshots_par_defaut`)
- Modify: `src/kaldera/orchestrateur.py` (`__init__` : snapshots par défaut)
- Modify: `src/kaldera/reaper.py` (`main`)
- Modify: `tests/conftest.py` (autouse : `snapshots_par_defaut` → `None`), `tests/test_contrat_ports.py` (param `postgres`), `Makefile` (`reaper`), `docs/journal_ajustements.md`
- Create: `tests/integration/test_adaptateurs.py`, `tests/unit/test_base_par_defaut.py`

**Interfaces:**
- Consumes: `pool`, `_connexion`, `ConfigBase` (Task 6) ; ports (Task 1) ; `faucher` (Task 5).
- Produces: `postgres.DepotPostgres(pool)`, `postgres.SnapshotsPostgres(pool)`, `postgres.RegistreA2APostgres(pool)` ; `postgres.snapshots_par_defaut() -> SnapshotsPostgres | None` ; `reaper.main()` ; `make reaper`.

- [ ] **Step 1: Write the failing tests**

`tests/test_contrat_ports.py` : remplacer la fixture par

```python
@pytest.fixture(params=["memoire", pytest.param("postgres", marks=pytest.mark.integration)])
def ports(request: pytest.FixtureRequest) -> tuple[Snapshots, RegistreA2A]:
    if request.param == "memoire":
        return SnapshotsEnMemoire(), RegistreA2AEnMemoire()
    from kaldera.postgres import RegistreA2APostgres, SnapshotsPostgres

    base = request.getfixturevalue("base")
    return SnapshotsPostgres(base), RegistreA2APostgres(base)
```

`tests/integration/test_adaptateurs.py` :

```python
"""Intégration — adaptateurs PostgreSQL : pièces, garanties sous concurrence, bout en bout."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import EtatDemande
from kaldera.orchestrateur import Orchestrateur
from kaldera.postgres import DepotPostgres, RegistreA2APostgres, SnapshotsPostgres
from kaldera.reaper import faucher

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
NOM_01 = json.loads((RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()[0])


def _pieces(conn: Any) -> None:
    conn.execute(
        "INSERT INTO demandes (reference, etat, etat_courant, statut) "
        "VALUES ('KAL-26-9001', '{}', 'pieces', 'en_cours')"
    )
    lignes = [  # (sha, relance, type, statut_analyse, lisible, montant)
        ("1" * 64, None, "facture", "ok", True, 640.50),
        ("2" * 64, None, "photo", "echec", True, None),
        ("3" * 64, 1, "photo", "ok", True, None),
        ("4" * 64, 2, "facture", "en_attente", None, None),
    ]
    for sha, relance, type_, statut, lisible, montant in lignes:
        conn.execute(
            "INSERT INTO blobs (sha256, contenu, mime, taille) VALUES (%s, 'x', 'application/pdf', 1)",
            (sha,),
        )
        conn.execute(
            "INSERT INTO pieces (reference, sha256, relance, type, statut_analyse, lisible, montant) "
            "VALUES ('KAL-26-9001', %s, %s, %s, %s, %s, %s)",
            (sha, relance, type_, statut, lisible, montant),
        )


def test_depot_postgres(base: Any) -> None:
    with base.connection() as conn:
        _pieces(conn)
    depot = DepotPostgres(base)
    demande = {"reference": "KAL-26-9001"}
    initiales = sorted(depot.initiales(demande), key=lambda p: p.type)
    assert [(p.type, p.lisible, p.montant, p.statut_analyse) for p in initiales] == [
        ("facture", True, 640.5, "ok"),
        ("photo", False, None, "echec"),
    ]
    assert all(p.piece_id is not None and p.sha256 for p in initiales)
    depots = depot.depots(demande)
    assert [(p.type, p.lisible, p.statut_analyse) for p in depots] == [
        ("photo", True, "ok"),
        ("facture", False, "echec"),  # en_attente : jamais lisible
    ]


def test_deux_reapers_ne_prennent_jamais_la_meme_demande(base: Any) -> None:
    snapshots = SnapshotsPostgres(base)
    references = [f"KAL-26-{i:04d}" for i in range(20)]
    for reference in references:
        snapshots.debuter(EtatDemande(demande={"reference": reference}))
    with ThreadPoolExecutor(2) as pool:
        lots = list(pool.map(lambda _: faucher(snapshots, 0), range(2)))
    fauchees = [fiche["reference"] for lot in lots for fiche in lot]
    assert sorted(fauchees) == references  # chacune exactement une fois


def test_un_seul_appel_partenaire_sous_concurrence(base: Any) -> None:
    SnapshotsPostgres(base).debuter(EtatDemande(demande={"reference": "KAL-26-0042"}))
    registre = RegistreA2APostgres(base)
    with ThreadPoolExecutor(8) as pool:
        reserves = list(pool.map(lambda _: registre.reserver("KAL-26-0042"), range(8)))
    assert reserves.count(True) == 1


def test_traiter_demande_avec_base(base: Any) -> None:
    demande = copy.deepcopy(NOM_01["demandes"][0])
    fiche = Orchestrateur(snapshots=SnapshotsPostgres(base)).traiter(demande)
    with base.connection() as conn:
        statut, etat_courant, decision, trace = conn.execute(
            "SELECT statut, etat_courant, fiche->>'decision', jsonb_array_length(etat->'trace') "
            "FROM demandes WHERE reference = %s",
            (demande["reference"],),
        ).fetchone()
    assert (statut, etat_courant, decision) == ("terminee", "acceptee", fiche["decision"])
    assert trace == len(fiche["trace"])


def test_reaper_classe_la_fiche_en_base(base: Any) -> None:
    snapshots = SnapshotsPostgres(base)
    snapshots.debuter(EtatDemande(demande={"reference": "KAL-26-9002"}))
    (fiche,) = faucher(snapshots, 0)
    with base.connection() as conn:
        statut, fichier = conn.execute(
            "SELECT statut, fiche->>'file' FROM demandes WHERE reference = 'KAL-26-9002'"
        ).fetchone()
    assert (statut, fichier) == ("secours", fiche["file"])
```

`tests/unit/test_base_par_defaut.py` :

```python
"""Unitaires — base configurée mais injoignable : jamais bloquant (EX-01)."""

from __future__ import annotations

import pytest

from kaldera.postgres import snapshots_par_defaut  # avant le patch autouse du conftest


def test_sans_url_aucune_persistance() -> None:
    assert snapshots_par_defaut() is None


def test_base_injoignable_traitement_sans_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KALDERA_DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    assert snapshots_par_defaut() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_base_par_defaut.py -q; make test-integration 2>&1 | tail -4`
Expected: FAIL — `ImportError: cannot import name 'snapshots_par_defaut'` / `'DepotPostgres'`.

- [ ] **Step 3: Implement**

Dans `src/kaldera/postgres.py` (imports supplémentaires : `from typing import Any`, `from pydantic import ValidationError`, `from psycopg.types.json import Jsonb`, `from .etat import EtatDemande`, `from .ports import ErreurPersistance, PieceRef`) :

```python
def _piece(
    type_: str, lisible: bool | None, montant: Any, piece_id: Any, sha256: str, statut: str
) -> PieceRef:
    ok = statut == "ok"  # en_attente ou echec : jamais lisible
    return PieceRef(
        type=type_,
        lisible=bool(lisible) and ok,
        montant=None if montant is None else round(float(montant), 2),  # Decimal → float
        piece_id=piece_id,
        sha256=sha256,
        statut_analyse="ok" if ok else "echec",
    )


class DepotPostgres:
    """Niveau 1 : descripteurs de la table ``pieces`` (remplie par l'ingestion, SP3)."""

    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]:
        return self._lire(
            "SELECT type, lisible, montant, piece_id, sha256, statut_analyse FROM pieces "
            "WHERE reference = %s AND relance IS NULL ORDER BY piece_id",
            demande,
        )

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]:
        return self._lire(
            "SELECT type, lisible, montant, piece_id, sha256, statut_analyse FROM pieces "
            "WHERE reference = %s AND relance IS NOT NULL ORDER BY relance, piece_id",
            demande,
        )

    def _lire(self, requete: str, demande: dict[str, Any]) -> list[PieceRef]:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(requete, (demande.get("reference"),)).fetchall()
        return [_piece(*ligne) for ligne in lignes]


def _snapshot(etat: EtatDemande) -> Jsonb:
    return Jsonb(etat.model_dump(mode="json"))


class SnapshotsPostgres:
    """Table ``demandes`` : snapshot par transition, compare-and-set en fin et pour le reaper."""

    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def debuter(self, etat: EtatDemande) -> None:
        contrat = etat.demande.get("contrat")
        numero = contrat.get("numero") if isinstance(contrat, dict) else None
        with _connexion(self.connexions) as conn:
            conn.execute(
                "INSERT INTO demandes (reference, numero_contrat, etat, etat_courant, statut) "
                "VALUES (%s, %s, %s, %s, 'en_cours') "
                "ON CONFLICT (reference) DO UPDATE SET numero_contrat = EXCLUDED.numero_contrat, "
                "etat = EXCLUDED.etat, etat_courant = EXCLUDED.etat_courant, "
                "statut = 'en_cours', maj = now(), fiche = NULL",
                (etat.demande.get("reference"), numero, _snapshot(etat), etat.etat_courant),
            )

    def enregistrer(self, etat: EtatDemande) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE demandes SET etat = %s, etat_courant = %s, maj = now() "
                "WHERE reference = %s AND statut = 'en_cours'",
                (_snapshot(etat), etat.etat_courant, etat.demande.get("reference")),
            )

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "UPDATE demandes SET statut = 'terminee', etat = %s, etat_courant = %s, "
                "fiche = %s, maj = now() WHERE reference = %s AND statut = 'en_cours' "
                "RETURNING reference",
                (_snapshot(etat), etat.etat_courant, Jsonb(fiche), etat.demande.get("reference")),
            ).fetchone()
        return ligne is not None

    def faucher(self, age_s: float) -> list[tuple[str, dict[str, Any]]]:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(
                "UPDATE demandes SET statut = 'secours', maj = now() "
                "WHERE statut = 'en_cours' AND maj < now() - make_interval(secs => %s) "
                "RETURNING reference, etat",
                (age_s,),
            ).fetchall()
        return [(reference, etat) for reference, etat in lignes]

    def classer(self, reference: str, fiche: dict[str, Any]) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE demandes SET fiche = %s WHERE reference = %s", (Jsonb(fiche), reference)
            )


class RegistreA2APostgres:
    """Table ``appels_partenaire`` : la réservation précède l'envoi (contrat §6)."""

    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def reserver(self, reference: str) -> bool:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "INSERT INTO appels_partenaire (reference) VALUES (%s) "
                "ON CONFLICT (reference) DO NOTHING RETURNING reference",
                (reference,),
            ).fetchone()
        return ligne is not None

    def noter(self, reference: str, evaluation_id: str) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE appels_partenaire SET evaluation_id = %s WHERE reference = %s",
                (evaluation_id, reference),
            )


def snapshots_par_defaut() -> SnapshotsPostgres | None:
    """Snapshots PostgreSQL si ``KALDERA_DATABASE_URL`` est configurée et joignable, sinon aucun."""
    try:
        url = ConfigBase().database_url
    except ValidationError as exc:  # .env malformé : jamais bloquant
        LOGGER.warning("configuration de la base invalide, sans snapshot : %s", exc)
        return None
    if not url:
        return None
    try:
        return SnapshotsPostgres(pool(url))
    except psycopg.Error as exc:
        LOGGER.warning("PostgreSQL injoignable, traitement sans snapshot : %s", exc)
        return None
```

`src/kaldera/orchestrateur.py` : import `from . import llm, partenaire, postgres, regles` ; dans `__init__`, remplacer `self.snapshots = snapshots` par :

```python
        # sans base configurée : aucune persistance ; les pièces restent lues dans la demande
        # (niveau 0) tant que l'ingestion (SP3) ne remplit pas la table pieces
        self.snapshots = snapshots if snapshots is not None else postgres.snapshots_par_defaut()
```

`tests/conftest.py`, dans la fixture autouse `_sans_llm_reel`, ajouter :

```python
    from kaldera import postgres

    monkeypatch.setattr(postgres, "snapshots_par_defaut", lambda: None)
```

`src/kaldera/reaper.py`, ajouter (imports `import time`, `from .ports import ErreurPersistance` à côté de `Snapshots`, `from .postgres import ConfigBase, SnapshotsPostgres, pool`) :

```python
PERIODE_S = 10.0


def main() -> None:
    """``python -m kaldera.reaper`` : fauche toutes les 10 s, indépendamment des workers."""
    logging.basicConfig(level=logging.INFO)
    config = ConfigBase()
    if not config.database_url:
        raise SystemExit("KALDERA_DATABASE_URL absente : rien à faucher")
    snapshots = SnapshotsPostgres(pool(config.database_url))
    while True:
        try:
            for fiche in faucher(snapshots, config.reaper_age_s):
                LOGGER.warning(
                    "demande %s escaladée par le reaper (file %s)", fiche["reference"], fiche["file"]
                )
        except ErreurPersistance as exc:
            LOGGER.error("reaper : %s ; nouvel essai dans %s s", exc, PERIODE_S)
        time.sleep(PERIODE_S)


if __name__ == "__main__":
    main()
```

`Makefile` : ajouter `reaper` à `.PHONY` et

```make
reaper:
	uv run python -m kaldera.reaper
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q 2>&1 | tail -1 && make test-integration 2>&1 | tail -3 && uv run ruff check . && uv run ruff format --check src && uv run mypy src && uv run python -c "import kaldera.reaper"`
Expected: suite par défaut : 14 failed (A2A), le reste vert ; intégration : 9 (schéma) + 6 (contrat Postgres) + 5 (adaptateurs) = 20 passed ; ruff, format, mypy verts ; import du reaper sans erreur.

- [ ] **Step 5: Journal**

Dans `docs/journal_ajustements.md`, avant `## Bornes provisoires en vigueur`, ajouter :

```markdown
| 2026-10-08 | invariance (`tests/unit/test_invariance.py`) | pièces lues directement dans la demande | EX-D28 (claim check) | pièces chargées par le port `DepotPieces`, vue de `pieces` seule à les recevoir | 34/34 issues identiques avant → après |
| 2026-10-08 | processus tué (`test_demande_morte_escaladee_depuis_le_snapshot`) | demande perdue si le processus meurt | EX-D24, EX-01 | snapshot après chaque transition + reaper (`en_cours` → `secours`, CAS) | aucune fiche → escalade de secours classée |
| 2026-10-08 | schéma 2.6 bis | la fiche n'est persistée nulle part ; une demande sans contrat ne peut être snapshotée | file humaine consultable ; EX-01 | écarts : `demandes.fiche jsonb`, `numero_contrat` nullable | — |
| 2026-10-08 | port `DepotPieces` | le niveau 0 a besoin du JSON, pas seulement de la référence | EX-D28 | `DepotPieces.initiales(demande)` au lieu de `(reference)` | — |
| 2026-10-08 | tests d'intégration | le rollback par test (`CLAUDE.md`) empêche d'éprouver la concurrence | 2 reapers, 1 seule réservation A2A | isolation par `TRUNCATE` | — |
```

- [ ] **Step 6: Commit**

```bash
git add src tests Makefile docs/journal_ajustements.md
git commit -m "feat(postgres): adaptateurs pièces, snapshots et registre A2A ; reaper en service

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
