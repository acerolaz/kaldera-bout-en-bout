# C3-3 · Traitement, temps réel et E3 « Suivi de lot » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le gestionnaire lance le traitement d'un ou plusieurs dossiers `prete` depuis E1 (`POST /traitements` ⇒ un lot) et en suit l'avancement en direct : E2 pour un dossier, E3 pour un lot, par `pg_notify` → SSE, jusqu'aux sous-étapes d'agent.

**Architecture:** Nouveau statut `prete` (le worker s'arrête après l'admission) et tables `lots` / `lot_demandes` (migration `006`). Un port `Signaux` injecté dans l'orchestrateur (et passé à l'agent sous forme de rappel) émet des événements best effort par `pg_notify('kaldera_avancement', …)` ; deux routes SSE asynchrones écoutent (`LISTEN`), filtrent et traduisent par la projection serveur (`vue_gestionnaire.py`). L'API exécute le lot dans une `BackgroundTask` (`traiter_lot`). Le front consomme le flux par un hook `useFlux` (`EventSource`) qui relit l'état (`GET`) à l'ouverture et à chaque fin d'étape.

**Tech Stack:** Python 3.11, FastAPI 0.119 (Starlette 0.48), Pydantic 2, psycopg 3.3 (synchrone + `AsyncConnection` pour `LISTEN`), pytest ; React 19, TypeScript, Vite 8, Tailwind 4, shadcn/ui, react-router-dom 7, `@tanstack/react-query` 5, Vitest + Testing Library + vitest-axe, Playwright + @axe-core/playwright ; reportlab (cahier) ; `docs/conception/rendre.cjs` (dossier).

**Spec:** `docs/superpowers/specs/2026-10-12-c3-3-traitement-temps-reel-design.md`

Commandes front depuis `front/` ; les autres depuis la racine du dépôt (`src/kaldera-bout-en-bout/`, ou la racine du worktree).

## Global Constraints

- Branche `feature/chantier3-c3-3-traitement` (spec commitée). **Aucune dépendance ajoutée** (ni Python, ni npm) : `EventSource` natif, `psycopg.AsyncConnection` déjà installé.
- Aucune modification des règles métier, des gardes, de la table de transitions, des prompts ni des `SPECS` d'agents. L'orchestrateur et l'agent ne gagnent que des **émissions de signaux**.
- Cycle de vie : `admission → prete → en_cours → terminee | secours`. Seul `prete` est sélectionnable. Motifs exacts : `admission` « Pièces en cours d'analyse », `en_cours` « Traitement en cours », `terminee` / `secours` « Déjà traité ».
- Canal NOTIFY : `kaldera_avancement`. Charge utile : uniquement `type`, `reference`, `etat`, `sous_etape`, `tour`, `tours_max` (jamais de donnée personnelle ni de contenu de patch).
- Types d'événement : `etape_debut`, `sous_etape` (`vue` · `tour` · `outil` · `garde_fou`), `etape_fin` (émis **après** l'écriture du snapshot), `dossier_fin`.
- % agent : prévues = `tours_max + 3` ; `vue` = 1, `tour`/`outil` k = 1 + k, `garde_fou` = `tours_max + 2`, fin d'étape = 100 % ; arrondi entier.
- `POST /traitements` : tout ou rien ; 202 `{lot_id, references}` ; 404 `{"detail": "demande inconnue", "references": [...]}` ; 409 `{"detail": "dossiers non lançables", "references": [...]}` ; 422 (liste vide, doublon, format `^KAL-\d{2}-\d{4}$`).
- Signaux **jamais bloquants** (EX-01) : un échec d'émission est journalisé et l'événement perdu.
- Libellés exacts du front : « Traiter la sélection (n) » ; case « Tout sélectionner » ; cases « Sélectionner {reference} » ; h1 « Lot {id} » (inchangé) ; « Lot introuvable. » ; « Reconnexion… » ; barres « Avancement du dossier », « Avancement du lot », « Avancement de {reference} », « Avancement de l'étape {Libellé} » ; statut `prete` libellé « Prête ».
- Statuts toujours via `<Statut code />` ; jamais de couleur en dur dans un écran.
- Python : ruff (ligne ≤ 100), mypy ; routes asynchrones sans E/S bloquante (`run_in_threadpool` pour psycopg synchrone). Textes et commentaires en français, style du code existant.
- Toute simplification à plafond connu porte un commentaire `# ponytail:` (Python) ou `// ponytail:` (TS).
- Commits terminés par une ligne `Co-Authored-By:` nommant le modèle qui a réellement écrit le commit.
- Décisions de mise en œuvre (la spec est ajustée dans le même commit que ce plan) : un **disjoncteur par lot** (un orchestrateur par lot) ; dossiers d'un lot dans l'ordre des références ; région `aria-live` d'E2 « Étape en cours : {Libellé} » / « Traitement terminé » ; badge « Reconnexion… » sur E2 et E3 ; `travailler()` perd son paramètre `disjoncteur` (le worker ne traite plus) ; nouvelle cible `make api-epreuve` ; cahier de recette renuméroté (U-05 → U-09 traitement, U-10 → U-15 lecture).

## Review Focus

1. **Lot de 34 dossiers en parallèle sur un pool de 10 connexions** : snapshots et signaux se disputent le pool (attente 0,5 s) ; aucun dossier ne doit rester `en_cours` ni passer en « persistance coupée » → `tests/integration/test_epreuve.py` (Task 6) lance tout le manifeste en un seul `POST /traitements` et exige `terminee` partout.
2. **Double lancement** (deux onglets, double clic) : le second `POST` sur un dossier déjà lancé répond 409 sans créer de lot ni toucher l'autre dossier → test `test_relancer_un_dossier_lance_409` (Task 5) et cas de recette U-09.
3. **Événement malformé ou d'un autre dossier** dans le canal partagé (JSON cassé, référence absente, type inconnu) : ignoré, le flux continue → test `test_diffuser_filtre_et_traduit` (Task 7) et `test_evenement_malforme_ignore` (Task 1).
4. **Identifiant de lot non numérique ou inconnu dans l'URL** (`/lots/abc`, `/lots/999`) : « Lot introuvable. » et lien de retour, jamais une page blanche → test `Lot.test.tsx` « lot inconnu ou identifiant invalide » (Task 10).
5. **Dossier déjà terminal à l'ouverture d'E2 / E3** (traitement plus rapide que la navigation) : aucun flux ouvert, l'état final s'affiche → tests « terminal : aucun flux » (Tasks 9 et 10).

---

### Task 1: Projection — sélection, étape en cours, % agent, lot, événements

**Files:**
- Modify: `src/kaldera/vue_gestionnaire.py`
- Modify: `tests/unit/test_vue_gestionnaire.py:270-275` (`test_avancement_et_duree` : `etat_courant` réaliste)
- Create: `tests/unit/test_vue_traitement.py`

**Interfaces:**
- Consumes: `EtatDemande` (`kaldera.etat`), fonctions existantes `ligne`, `dossier`, `_etapes`.
- Produces (utilisés par Tasks 5, 7 et, en miroir TypeScript, Tasks 8 à 10) :
  - `StatutDemande = Literal["admission", "prete", "en_cours", "terminee", "secours"]`
  - `StatutEtape` gagne `"en_cours"`
  - `LigneDemande.selectionnable: bool = False`, `LigneDemande.motif_non_selectionnable: str | None = None`
  - `MOTIFS_NON_SELECTIONNABLE: dict[str, str]`
  - `avancement_agent(sous_etape: str, tour: int, tours_max: int) -> int`
  - `EvenementVue(type, reference, etat, statut, avancement_agent)` ; `evenement(brut: dict[str, Any]) -> EvenementVue | None`
  - `LigneLot`, `CompteursLot`, `LotVue` ; `ligne_lot(reference, statut, fiche, etat) -> LigneLot` ; `lot(id_lot: int, debut: datetime, derniere_maj: datetime, demandes: Iterable[tuple[str, str, dict | None, EtatDemande]]) -> LotVue`

- [ ] **Step 1: Écrire les tests (rouges)**

Créer `tests/unit/test_vue_traitement.py` :

```python
"""Unitaires — projection C3-3 : sélection, étape en cours, % agent, lot, événements (spec §2.4, §3.3)."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import EtatDemande, Issue
from kaldera.vue_gestionnaire import avancement_agent, dossier, evenement, ligne, lot

RACINE = Path(__file__).resolve().parents[2]
NOM_01 = json.loads((RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()[0])
T0 = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)


def _etat(**champs: Any) -> EtatDemande:
    return EtatDemande(demande=copy.deepcopy(NOM_01["demandes"][0]), **champs)


@pytest.mark.parametrize(
    ("statut", "selectionnable", "motif"),
    [
        ("prete", True, None),
        ("admission", False, "Pièces en cours d'analyse"),
        ("en_cours", False, "Traitement en cours"),
        ("terminee", False, "Déjà traité"),
        ("secours", False, "Déjà traité"),
    ],
)
def test_selection_par_statut(statut: str, selectionnable: bool, motif: str | None) -> None:
    vue = ligne("KAL-26-0101", statut, None, _etat())
    assert (vue.selectionnable, vue.motif_non_selectionnable) == (selectionnable, motif)


def test_dossier_en_cours_etape_courante_en_cours() -> None:
    etat = _etat(etat_courant="pieces")
    etat.trace = [{"action": "eligibilite", "ecrit": ["eligibilite"], "statut": "ok",
                   "duree_ms": 1.0, "de": "eligibilite", "vers": "pieces", "garde": "ok"}]
    vue = dossier("KAL-26-0101", "en_cours", None, etat)
    assert [(e.etat, e.statut, e.avancement) for e in vue.etapes] == [
        ("eligibilite", "termine", 100),
        ("pieces", "en_cours", 0),
        ("estimation", "en_attente", 0),
        ("antifraude", "en_attente", 0),
        ("decision", "en_attente", 0),
    ]
    assert vue.avancement == 20


def test_dossier_prete_aucune_etape_en_cours() -> None:
    vue = dossier("KAL-26-0101", "prete", None, _etat())
    assert {e.statut for e in vue.etapes} == {"en_attente"} and vue.avancement == 0


@pytest.mark.parametrize(
    ("sous_etape", "tour", "attendu"),
    [("vue", 0, 17), ("tour", 1, 33), ("outil", 1, 33), ("tour", 2, 50), ("garde_fou", 2, 83),
     ("garde_fou", 0, 83)],  # repli : directement au garde-fou
)
def test_avancement_agent(sous_etape: str, tour: int, attendu: int) -> None:
    assert avancement_agent(sous_etape, tour, tours_max=3) == attendu


def test_evenements_traduits() -> None:
    base = {"reference": "KAL-26-0101", "etat": "pieces"}
    debut = evenement({"type": "etape_debut", **base})
    assert debut is not None and (debut.statut, debut.avancement_agent) == ("en_cours", 0)
    sous = evenement({"type": "sous_etape", **base, "sous_etape": "tour", "tour": 1, "tours_max": 3})
    assert sous is not None and (sous.statut, sous.avancement_agent) == ("en_cours", 33)
    fin = evenement({"type": "etape_fin", **base})
    assert fin is not None and (fin.statut, fin.avancement_agent) == (None, 100)
    clos = evenement({"type": "dossier_fin", "reference": "KAL-26-0101"})
    assert clos is not None and (clos.etat, clos.avancement_agent) == (None, None)


@pytest.mark.parametrize(
    "brut",
    [
        {"type": "inconnu", "reference": "KAL-26-0101"},
        {"type": "etape_debut"},
        {"type": "sous_etape", "reference": "KAL-26-0101", "etat": "pieces", "tour": "x"},
        {"type": "etape_fin", "reference": 12},
    ],
)
def test_evenement_malforme_ignore(brut: dict[str, Any]) -> None:
    assert evenement(brut) is None


def _termine(decision: str, file: str | None = None, degrade: bool = False) -> EtatDemande:
    """Escalade si ``file``, sinon décision (une décision porte toujours un montant)."""
    etat = _etat(etat_courant="fin")
    if file:
        etat.issue = Issue(issue="escalade", motif="motif", file=file, mode_degrade=degrade)
    else:
        montant = 100.0 if decision == "acceptee" else 0.0
        etat.issue = Issue.model_validate(
            {"issue": "decision", "decision": decision, "montant_rembourse": montant, "motif": "motif"}
        )
    return etat


def test_lot_en_cours_puis_clos() -> None:
    en_cours = _etat(etat_courant="estimation")
    demandes = [
        ("KAL-26-0101", "terminee", None, _termine("acceptee")),
        ("KAL-26-0102", "en_cours", None, en_cours),
        ("KAL-26-0103", "terminee", None, _termine("refusee")),
        ("KAL-26-0104", "secours", None, _termine("", file="cellule_fraude", degrade=True)),
    ]
    vue = lot(7, T0, T0 + timedelta(seconds=3), demandes)
    assert (vue.id, vue.avancement, vue.fin) == (7, 75, None)
    assert vue.compteurs.model_dump() == {
        "acceptee": 1, "refusee": 1, "escalade": {"cellule_fraude": 1}, "mode_degrade": 1,
    }
    ligne_en_cours = vue.dossiers[1]
    assert (ligne_en_cours.etape_en_cours, ligne_en_cours.statut) == ("estimation", "en_cours")
    assert vue.dossiers[0].etape_en_cours is None
    clos = lot(7, T0, T0 + timedelta(seconds=3), [demandes[0], demandes[2]])
    assert (clos.avancement, clos.fin) == (100, T0 + timedelta(seconds=3))


def test_lot_sans_donnee_personnelle() -> None:
    etat = _etat()
    etat.demande["assure"].update(email="claire@example.org", telephone="0600000000",
                                  iban="FR7630006000011234567890189")
    texte = lot(1, T0, T0, [("KAL-26-0101", "prete", None, etat)]).model_dump_json()
    assert not any(x in texte for x in ("claire@example.org", "0600000000", "FR7630006"))
```

Dans `tests/unit/test_vue_gestionnaire.py`, `test_avancement_et_duree` : un dossier `en_cours` après 3 étapes a pour état courant `antifraude` ; ajouter la ligne `etat.etat_courant = "antifraude"` juste après `etat.trace = etat.trace[:3]` :

```python
def test_avancement_et_duree() -> None:
    etat = _complet()
    etat.trace = etat.trace[:3]  # eligibilite, pieces, estimation
    etat.etat_courant = "antifraude"  # snapshot réel après estimation (C3-3 : étape courante en_cours)
    vue = dossier("KAL-26-0101", "en_cours", None, etat)
    assert (vue.avancement, vue.duree_ms, vue.budget_ms) == (60, 37.5, 8000.0)
    assert dossier("KAL-26-0101", "secours", None, etat).avancement == 100
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/unit/test_vue_traitement.py -v`
Expected: FAIL (`ImportError: cannot import name 'avancement_agent'`).

- [ ] **Step 3: Implémenter**

Dans `src/kaldera/vue_gestionnaire.py` :

1. Imports : remplacer `from collections.abc import Iterable` par :

```python
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
```

2. Remplacer les deux alias de statuts par :

```python
StatutDemande = Literal["admission", "prete", "en_cours", "terminee", "secours"]
StatutEtape = Literal["en_attente", "en_cours", "termine", "sautee", "echec", "repli", "degrade"]
```

et ajouter sous `STATUT_AVIS` :

```python
# seul un dossier prêt se lance (EX-D45) ; le motif s'affiche dans l'infobulle d'E1
MOTIFS_NON_SELECTIONNABLE: dict[str, str] = {
    "admission": "Pièces en cours d'analyse",
    "en_cours": "Traitement en cours",
    "terminee": "Déjà traité",
    "secours": "Déjà traité",
}
```

3. `LigneDemande` : ajouter à la fin de la classe

```python
    selectionnable: bool = False
    motif_non_selectionnable: str | None = None
```

4. Dans `ligne()`, ajouter les deux champs au constructeur `LigneDemande(...)` :

```python
        mode_degrade=sortie.mode_degrade,
        selectionnable=statut == "prete",
        motif_non_selectionnable=MOTIFS_NON_SELECTIONNABLE.get(statut),
    )
```

et dans `lignes()`, ligne minimale, après `mode_degrade=False,` :

```python
                    selectionnable=statut == "prete",
                    motif_non_selectionnable=MOTIFS_NON_SELECTIONNABLE.get(statut),
```

5. `_etapes` reçoit le statut du dossier ; remplacer sa signature et son `return` :

```python
def _etapes(etat: EtatDemande, statut_dossier: str) -> list[Etape]:
```

```python
    if statut_dossier == "en_cours":  # l'étape courante s'exécute : le flux SSE en donne le %
        cartes = [
            c.model_copy(update={"statut": "en_cours", "avancement": 0})
            if c.etat == etat.etat_courant
            else c
            for c in cartes
        ]
    return cartes
```

et dans `dossier()` : `etapes = _etapes(etat, statut)`.

6. Ajouter en fin de fichier :

```python
# ------------------------------------------------------------------ temps réel (C3-3)

TypeEvenement = Literal["etape_debut", "sous_etape", "etape_fin", "dossier_fin"]


class EvenementVue(BaseModel):
    """Événement SSE prêt à afficher : le front n'en déduit rien (EX-D44)."""

    type: TypeEvenement
    reference: str
    etat: str | None
    statut: Literal["en_cours"] | None
    avancement_agent: int | None


def avancement_agent(sous_etape: str, tour: int, tours_max: int) -> int:
    """% agent (spec C3-3 §3.3) : sous-étapes faites / prévues, prévues = tours_max + 3.

    vue = 1 ; tour ou outil k = 1 + k ; garde-fou = tours_max + 2 (tours non utilisés comptés
    comme faits : un repli saute au garde-fou) ; la fin d'étape (100 %) vient de etape_fin.
    """
    prevues = tours_max + 3
    faites = {"vue": 1, "tour": 1 + tour, "outil": 1 + tour, "garde_fou": tours_max + 2}
    return round(100 * min(faites.get(sous_etape, 0), prevues) / prevues)


def evenement(brut: dict[str, Any]) -> EvenementVue | None:
    """Traduit un signal brut (spec §3.2) ; un signal malformé ou inconnu est ignoré."""
    type_, reference, etat = brut.get("type"), brut.get("reference"), brut.get("etat")
    if not isinstance(reference, str):
        return None
    etape = etat if isinstance(etat, str) else None
    if type_ == "etape_debut":
        return EvenementVue(
            type=type_, reference=reference, etat=etape, statut="en_cours", avancement_agent=0
        )
    if type_ == "sous_etape":
        tour, tours_max = brut.get("tour"), brut.get("tours_max")
        if not isinstance(tour, int) or not isinstance(tours_max, int):
            return None
        return EvenementVue(
            type=type_,
            reference=reference,
            etat=etape,
            statut="en_cours",
            avancement_agent=avancement_agent(str(brut.get("sous_etape")), tour, tours_max),
        )
    if type_ == "etape_fin":
        return EvenementVue(
            type=type_, reference=reference, etat=etape, statut=None, avancement_agent=100
        )
    if type_ == "dossier_fin":
        return EvenementVue(
            type=type_, reference=reference, etat=None, statut=None, avancement_agent=None
        )
    return None


# ------------------------------------------------------------------ E3


class LigneLot(BaseModel):
    reference: str
    nom: str | None
    prenom: str | None
    police: str | None
    statut: str
    avancement: int
    etape_en_cours: str | None
    duree_ms: float
    issue: CodeIssue | None
    file: str | None
    mode_degrade: bool
    borne: str | None


class CompteursLot(BaseModel):
    acceptee: int
    refusee: int
    escalade: dict[str, int]  # par file
    mode_degrade: int


class LotVue(BaseModel):
    id: int
    debut: datetime
    fin: datetime | None
    avancement: int
    compteurs: CompteursLot
    dossiers: list[LigneLot]


def ligne_lot(
    reference: str, statut: str, fiche: dict[str, Any] | None, etat: EtatDemande
) -> LigneLot:
    d = dossier(reference, statut, fiche, etat)
    return LigneLot(
        reference=reference,
        nom=d.nom,
        prenom=d.prenom,
        police=d.police,
        statut=statut,
        avancement=d.avancement,
        etape_en_cours=etat.etat_courant if statut == "en_cours" else None,
        duree_ms=d.duree_ms,
        issue=d.issue,
        file=d.file,
        mode_degrade=d.mode_degrade,
        borne=d.arret.borne if d.arret else None,
    )


def lot(
    id_lot: int,
    debut: datetime,
    derniere_maj: datetime,
    demandes: Iterable[tuple[str, str, dict[str, Any] | None, EtatDemande]],
) -> LotVue:
    """E3 (spec §2.3) : avancement = dossiers clos / dossiers ; fin = dernière mise à jour si clos."""
    lignes_lot = [ligne_lot(*d) for d in demandes]
    clos = sum(lg.statut in TERMINAUX for lg in lignes_lot)
    total = len(lignes_lot)
    escalades = Counter(lg.file or "inconnue" for lg in lignes_lot if lg.issue == "escalade")
    return LotVue(
        id=id_lot,
        debut=debut,
        fin=derniere_maj if total and clos == total else None,
        avancement=round(100 * clos / total) if total else 0,
        compteurs=CompteursLot(
            acceptee=sum(lg.issue == "acceptee" for lg in lignes_lot),
            refusee=sum(lg.issue == "refusee" for lg in lignes_lot),
            escalade=dict(sorted(escalades.items())),
            mode_degrade=sum(lg.mode_degrade for lg in lignes_lot),
        ),
        dossiers=lignes_lot,
    )
```

- [ ] **Step 4: Vérifier qu'ils passent**

Run: `uv run pytest tests/unit/test_vue_traitement.py tests/unit/test_vue_gestionnaire.py -v`
Expected: PASS.

Run: `uv run ruff check src tests && uv run mypy src`
Expected: aucune erreur.

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/vue_gestionnaire.py tests/unit/test_vue_traitement.py tests/unit/test_vue_gestionnaire.py
git commit -m "feat(vue): sélection prete, étape en cours, % agent, vue de lot et événements (C3-3)"
```

---

### Task 2: Port `Signaux` et ses adaptateurs

**Files:**
- Modify: `src/kaldera/ports.py`, `src/kaldera/memoire.py`, `src/kaldera/postgres.py`
- Modify: `tests/conftest.py` (`signaux_par_defaut` neutralisé)
- Modify: `tests/test_contrat_ports.py`

**Interfaces:**
- Consumes: `_connexion`, `_pool_par_defaut`, `ErreurPersistance` (`kaldera.postgres`).
- Produces (Tasks 3, 5, 7) :
  - `Signaux` (Protocol) : `emettre(self, evenement: dict[str, Any]) -> None`
  - `SignauxEnMemoire` (`kaldera.memoire`) : attribut `evenements: list[dict[str, Any]]`
  - `SignauxPostgres(connexions: ConnectionPool)` ; `CANAL = "kaldera_avancement"` ; `signaux_par_defaut() -> SignauxPostgres | None` (`kaldera.postgres`)

- [ ] **Step 1: Écrire les tests (rouges)**

Dans `tests/test_contrat_ports.py`, ajouter à la fin :

```python
@pytest.fixture(params=["memoire", pytest.param("postgres", marks=pytest.mark.integration)])
def signaux(request: pytest.FixtureRequest) -> tuple[Any, Any]:
    """(signaux, lecteur) : le lecteur rend les événements effectivement émis."""
    if request.param == "memoire":
        from kaldera.memoire import SignauxEnMemoire

        memoire = SignauxEnMemoire()
        return memoire, lambda: memoire.evenements
    import json

    import psycopg

    from kaldera.postgres import CANAL, SignauxPostgres

    base = request.getfixturevalue("base")
    ecoute = psycopg.connect(base.conninfo, autocommit=True)
    request.addfinalizer(ecoute.close)
    ecoute.execute(f"LISTEN {CANAL}")
    return SignauxPostgres(base), lambda: [
        json.loads(n.payload) for n in ecoute.notifies(timeout=1.0, stop_after=1)
    ]


def test_signal_emis_tel_quel(signaux: tuple[Any, Any]) -> None:
    emetteur, lire = signaux
    evenement = {"type": "etape_debut", "reference": REF, "etat": "pieces"}
    emetteur.emettre(evenement)
    assert lire() == [evenement]
```

Créer le test du « jamais bloquant » dans `tests/unit/test_ports.py` (à la fin du fichier existant) :

```python
def test_signaux_postgres_jamais_bloquants() -> None:
    """Base injoignable : l'événement est perdu, aucune exception ne remonte (EX-01)."""
    from psycopg_pool import ConnectionPool

    from kaldera.postgres import SignauxPostgres

    connexions = ConnectionPool(
        "postgresql://x@127.0.0.1:9/x", min_size=0, open=False, kwargs={"connect_timeout": 1}
    )
    SignauxPostgres(connexions).emettre({"type": "dossier_fin", "reference": "KAL-26-9001"})
```

(Le pool fermé lève `PoolClosed`, une `psycopg.Error` que `_connexion` convertit en `ErreurPersistance` : le test échoue si elle remonte.)

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_contrat_ports.py tests/unit/test_ports.py -v`
Expected: FAIL (`ImportError: cannot import name 'SignauxEnMemoire'`).

- [ ] **Step 3: Implémenter**

`src/kaldera/ports.py`, à la fin :

```python
class Signaux(Protocol):
    """Événements d'avancement (spec C3-3 §3) : best effort, jamais bloquant (EX-01)."""

    def emettre(self, evenement: dict[str, Any]) -> None: ...
```

`src/kaldera/memoire.py`, à la fin :

```python
class SignauxEnMemoire:
    """Événements gardés dans l'ordre d'émission ; tests et démonstration."""

    def __init__(self) -> None:
        self.evenements: list[dict[str, Any]] = []
        self._verrou = threading.Lock()

    def emettre(self, evenement: dict[str, Any]) -> None:
        with self._verrou:
            self.evenements.append(copy.deepcopy(evenement))
```

`src/kaldera/postgres.py` : ajouter `import json` aux imports, puis, après `class RegistreA2APostgres` (avant `_pool_par_defaut`) :

```python
CANAL = "kaldera_avancement"  # LISTEN / NOTIFY : avancement des dossiers vers les flux SSE


class SignauxPostgres:
    """``pg_notify`` best effort : un événement perdu ne fausse rien (l'IHM relit l'état)."""

    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def emettre(self, evenement: dict[str, Any]) -> None:
        try:
            with _connexion(self.connexions) as conn:
                conn.execute(
                    "SELECT pg_notify(%s, %s)", (CANAL, json.dumps(evenement, ensure_ascii=False))
                )
        except ErreurPersistance as exc:  # jamais bloquant pour une décision (EX-01)
            LOGGER.debug("signal %s perdu : %s", evenement.get("type"), exc)
```

et après `snapshots_par_defaut()` :

```python
def signaux_par_defaut() -> SignauxPostgres | None:
    """Signaux PostgreSQL si la base est configurée et joignable, sinon aucun."""
    connexions = _pool_par_defaut()
    return SignauxPostgres(connexions) if connexions is not None else None
```

`tests/conftest.py`, dans `_sans_llm_reel`, après la ligne `registre_par_defaut` :

```python
    monkeypatch.setattr(postgres, "signaux_par_defaut", lambda: None)
```

- [ ] **Step 4: Vérifier qu'ils passent**

Run: `uv run pytest tests/test_contrat_ports.py tests/unit/test_ports.py -v`
Expected: PASS (la variante `postgres` est désélectionnée hors `make test-integration`).

Run: `make test-integration ARGS="-k signal"` (ou `TEST_DATABASE_URL=… uv run pytest -m integration tests/test_contrat_ports.py -k signal -v`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/ports.py src/kaldera/memoire.py src/kaldera/postgres.py tests/conftest.py tests/test_contrat_ports.py tests/unit/test_ports.py
git commit -m "feat(signaux): port Signaux, adaptateurs mémoire et pg_notify best effort (C3-3)"
```

---

### Task 3: Signaux émis par l'orchestrateur, l'agent et le reaper

**Files:**
- Modify: `src/kaldera/agents_llm.py` (`AgentLLM.executer`, `_tenter`, `_boucle`)
- Modify: `src/kaldera/orchestrateur.py` (`__init__`, `traiter`, `_etape`, `_sauter`)
- Modify: `src/kaldera/reaper.py` (`faucher`, `main`)
- Test: `tests/unit/test_agents_llm.py`, `tests/unit/test_orchestrateur.py`, `tests/unit/test_reaper.py`

**Interfaces:**
- Consumes: `Signaux`, `SignauxEnMemoire`, `SignauxPostgres`, `signaux_par_defaut` (Task 2).
- Produces :
  - `Signaler = Callable[[str, int], None]` (`kaldera.agents_llm`) ; `AgentLLM.executer(vue, budget_s, signaler: Signaler | None = None)`
  - `Orchestrateur(..., signaux: Signaux | None = None)` (défaut : `postgres.signaux_par_defaut()`)
  - `faucher(snapshots, age_s, signaux: Signaux | None = None)`

- [ ] **Step 1: Écrire les tests (rouges)**

`tests/unit/test_agents_llm.py`, à la fin :

```python
def _espion_signaux() -> tuple[list[tuple[str, int]], Any]:
    recus: list[tuple[str, int]] = []
    return recus, lambda sous_etape, tour: recus.append((sous_etape, tour))


def test_signaux_chemin_nominal() -> None:
    recus, signaler = _espion_signaux()
    _agent("estimation", _honnete("estimation")).executer(
        _vues()["estimation"], budget_s=5, signaler=signaler
    )
    assert recus == [("vue", 0), ("tour", 1), ("outil", 1), ("tour", 2), ("garde_fou", 2)]


def test_signaux_repli_directement_au_garde_fou() -> None:
    recus, signaler = _espion_signaux()
    _agent("estimation", None).executer(_vues()["estimation"], budget_s=5, signaler=signaler)
    assert recus == [("vue", 0), ("garde_fou", 0)]


def test_sans_signaler_comportement_inchange() -> None:
    avec = _agent("decision", _honnete("decision")).executer(
        _vues()["decision"], budget_s=5, signaler=lambda s, t: None
    )
    sans = _agent("decision", _honnete("decision")).executer(_vues()["decision"], budget_s=5)
    assert avec[0] == sans[0] and avec[1].tours_llm == sans[1].tours_llm
```

`tests/unit/test_orchestrateur.py` : ajouter `from kaldera.memoire import SignauxEnMemoire, SnapshotsEnMemoire` (fusionner avec l'import `RegistreA2AEnMemoire` existant), puis à la fin :

```python
# --------------------------------------------------------------------- signaux (C3-3)

CLES_SIGNAL = {"type", "reference", "etat", "sous_etape", "tour", "tours_max"}


def test_signaux_dans_l_ordre() -> None:
    signaux = SignauxEnMemoire()
    Orchestrateur(evaluer=_sans_partenaire, signaux=signaux).traiter(_demande("NOM-02"))
    assert [(e["type"], e.get("etat"), e.get("sous_etape")) for e in signaux.evenements] == [
        ("etape_debut", "eligibilite", None),
        ("etape_fin", "eligibilite", None),
        ("etape_debut", "decision", None),
        ("sous_etape", "decision", "vue"),
        ("sous_etape", "decision", "garde_fou"),
        ("etape_fin", "decision", None),
        ("dossier_fin", None, None),
    ]
    assert {e["reference"] for e in signaux.evenements} == {"KAL-26-0102"}
    assert all(set(e) <= CLES_SIGNAL for e in signaux.evenements)  # ni PII ni patch
    assert {e["tours_max"] for e in signaux.evenements if e["type"] == "sous_etape"} == {3}


def test_etape_fin_apres_le_snapshot() -> None:
    snapshots = SnapshotsEnMemoire()

    class Temoin:
        def __init__(self) -> None:
            self.vus: list[str] = []

        def emettre(self, evenement: dict[str, Any]) -> None:
            if evenement["type"] == "etape_fin":
                ligne = snapshots.lignes[evenement["reference"]]
                self.vus.append(ligne["etat"]["trace"][-1]["action"])

    temoin = Temoin()
    Orchestrateur(evaluer=_sans_partenaire, snapshots=snapshots, signaux=temoin).traiter(
        _demande("NOM-02")
    )
    assert temoin.vus == ["eligibilite", "decision"]


def test_decisions_identiques_avec_ou_sans_signaux() -> None:
    decisifs = ("issue", "decision", "montant_rembourse", "file", "mode_degrade")
    absent = lambda d, timeout: None  # noqa: E731 — partenaire muet : avis indisponible si requis
    avec = Orchestrateur(evaluer=absent, signaux=SignauxEnMemoire()).traiter(_demande("AF-03"))
    sans = Orchestrateur(evaluer=absent).traiter(_demande("AF-03"))
    assert {k: avec[k] for k in decisifs} == {k: sans[k] for k in decisifs}
```

(AF-03 parcourt les 5 étapes, anti-fraude comprise : les signaux ne changent aucune décision.)

`tests/unit/test_reaper.py` : ajouter `SignauxEnMemoire` à l'import depuis `kaldera.memoire`, puis :

```python
def test_reaper_signale_la_fin_du_dossier() -> None:
    snapshots, signaux = SnapshotsEnMemoire(), SignauxEnMemoire()
    snapshots.debuter(EtatDemande(demande={"reference": "KAL-26-9001", "contrat": {}}))
    faucher(snapshots, 0, signaux)
    assert signaux.evenements == [{"type": "dossier_fin", "reference": "KAL-26-9001"}]
```

(Adapter l'import d'`EtatDemande` si le fichier ne l'a pas.)

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/unit/test_agents_llm.py tests/unit/test_orchestrateur.py tests/unit/test_reaper.py -k "signa" -v`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'signaler'` / `'signaux'`).

- [ ] **Step 3: Implémenter l'agent**

`src/kaldera/agents_llm.py` : ajouter `Callable` à l'import `collections.abc` (ou `from collections.abc import Callable` s'il n'existe pas), puis près des autres alias de module :

```python
Signaler = Callable[[str, int], None]  # (sous_etape, tour) : vue · tour · outil · garde_fou


def _muet(sous_etape: str, tour: int) -> None:
    return None
```

Renommer le corps actuel de `executer` en `_executer(self, vue, budget_s, signaler)` et le précéder du nouveau `executer` :

```python
    def executer(
        self, vue: Vue, budget_s: float, signaler: Signaler | None = None
    ) -> tuple[dict[str, Any], MesureAgent]:
        """Exécute l'agent ; ``signaler`` reçoit ses sous-étapes (C3-3) : l'agent étant partagé
        entre les threads d'un lot, le rappel est passé à chaque appel, jamais stocké."""
        signaler = signaler or _muet
        signaler("vue", 0)
        patch, mesure = self._executer(vue, budget_s, signaler)
        signaler("garde_fou", mesure.tours_llm)  # garde-fou passé, ou repli direct
        return patch, mesure

    def _executer(
        self, vue: Vue, budget_s: float, signaler: Signaler
    ) -> tuple[dict[str, Any], MesureAgent]:
```

Dans `_executer`, l'appel devient `patch = self._tenter(self.llm, vue, ref, budget, mesure, signaler)`. `_tenter` gagne le paramètre `signaler: Signaler` (dernier) et appelle `self._boucle(llm, vue, ref, budget, mesure, signaler)`. `_boucle` gagne `signaler: Signaler` (dernier) ; après `mesure.jetons += reponse.jetons` :

```python
            signaler("tour", mesure.tours_llm)
```

et dans la boucle des outils, juste après `messages.append({... "role": "tool" ...})` :

```python
                signaler("outil", mesure.tours_llm)
```

- [ ] **Step 4: Implémenter l'orchestrateur**

`src/kaldera/orchestrateur.py` :

- imports : `from .agents_llm import AgentLLM, MesureAgent, Signaler, creer_agent` ; `from .ports import DepotPieces, ErreurPersistance, RegistreA2A, Signaux, Snapshots`.
- `__init__` : nouveau paramètre `signaux: Signaux | None = None` (après `disjoncteur`), et après l'affectation de `self.snapshots` :

```python
        self.signaux = signaux if signaux is not None else postgres.signaux_par_defaut()
```

- méthodes ajoutées (après `_charger_config`) :

```python
    def _signaler(self, evenement: dict[str, Any]) -> None:
        if self.signaux is not None:
            self.signaux.emettre(evenement)

    def _signaleur(self, etat: EtatDemande, courant: Etat, tours_max: int) -> Signaler | None:
        """Rappel de l'agent pour cette étape (fermeture : rien n'est partagé entre threads)."""
        if self.signaux is None:
            return None
        reference = etat.demande.get("reference")

        def signaler(sous_etape: str, tour: int) -> None:
            self._signaler(
                {
                    "type": "sous_etape",
                    "reference": reference,
                    "etat": courant.value,
                    "sous_etape": sous_etape,
                    "tour": tour,
                    "tours_max": tours_max,
                }
            )

        return signaler
```

- `traiter` : après le bloc `if self._persister(...) is False: ...` et avant `return fiche` :

```python
        self._signaler({"type": "dossier_fin", "reference": etat.demande.get("reference")})
```

- `_etape` : première ligne du corps (avant `section = ...`) :

```python
        self._signaler(
            {"type": "etape_debut", "reference": etat.demande.get("reference"), "etat": courant.value}
        )
```

l'appel de l'agent devient :

```python
            if isinstance(action, AgentLLM):
                signaler = self._signaleur(etat, courant, action.config.tours_max)
                patch, mesure = action.executer(vue, self._budget(etat, courant), signaler)
```

et après `self._persister(etat, lambda s: s.enregistrer(etat))` (fin de `_etape`), avant `return suivant` :

```python
        self._signaler(
            {"type": "etape_fin", "reference": etat.demande.get("reference"), "etat": courant.value}
        )
```

- `_sauter` : même ligne `etape_fin` après son `self._persister(...)`, avant `return suivant`.

- [ ] **Step 5: Implémenter le reaper**

`src/kaldera/reaper.py` : `from .ports import ErreurPersistance, Signaux, Snapshots` ; `from .postgres import ConfigBase, SignauxPostgres, SnapshotsPostgres, pool`.

```python
def faucher(
    snapshots: Snapshots, age_s: float, signaux: Signaux | None = None
) -> list[dict[str, Any]]:
    """Passe en ``secours`` les demandes inactives depuis ``age_s`` s ; retourne leurs fiches."""
    fiches = []
    for reference, brut in snapshots.faucher(age_s):
        fiche = fiche_de_secours(reference, brut)
        try:
            snapshots.classer(reference, fiche)
        except ErreurPersistance as exc:  # sans fiche : reprise au passage suivant
            LOGGER.error("demande %s non classée : %s", reference, exc)
            continue
        if signaux is not None:  # E2 / E3 relisent le dossier clos
            signaux.emettre({"type": "dossier_fin", "reference": reference})
        fiches.append(fiche)
    return fiches
```

Dans `main` : `connexions = pool(config.database_url)`, `snapshots = SnapshotsPostgres(connexions)`, `signaux = SignauxPostgres(connexions)` et `fiches = faucher(snapshots, config.reaper_age_s, signaux)`.

- [ ] **Step 6: Vérifier**

Run: `uv run pytest tests/unit -v`
Expected: PASS (toute la suite unitaire : aucune régression des agents ni du moteur).

Run: `uv run ruff check src tests && uv run mypy src`
Expected: aucune erreur.

- [ ] **Step 7: Commit**

```bash
git add src/kaldera/agents_llm.py src/kaldera/orchestrateur.py src/kaldera/reaper.py tests/unit/test_agents_llm.py tests/unit/test_orchestrateur.py tests/unit/test_reaper.py
git commit -m "feat(signaux): début / sous-étapes / fin d'étape et fin de dossier émis par le moteur et l'agent (C3-3)"
```

---

### Task 4: Migration 006, dépôt des lots, chargement `prete`, dépôt de pièces mixte

**Files:**
- Create: `src/kaldera/migrations/006_traitements.sql`
- Create: `src/kaldera/lots_postgres.py`
- Modify: `src/kaldera/ingestion_postgres.py` (`creer_demande` → `_inserer`, `charger`)
- Modify: `src/kaldera/postgres.py` (`DepotPostgres` : repli niveau 0)
- Modify: `src/kaldera/cli.py` (`--charger`)
- Modify: `tests/conftest.py`, `tests/e2e/serveur.py` (TRUNCATE)
- Test: `tests/integration/test_schema.py`, `tests/integration/test_lots.py` (créé), `tests/integration/test_cli.py` (créé)

**Interfaces:**
- Consumes: `_connexion`, `_ligne`, `_demande_lue`, `DemandeLue` (`kaldera.ingestion_postgres`) ; `DepotDepuisDemande` (`kaldera.memoire`).
- Produces (Tasks 5, 6, 7, 11) :
  - `ReferencesInconnues(references: list[str])`, `DossiersNonLancables(references: list[str])` (exceptions, attribut `references`)
  - `DepotLots(connexions)` : `.connexions` ; `lancer(references: list[str]) -> tuple[int, list[dict[str, Any]]]` ; `lire(lot_id: int) -> LotLu | None` ; `references(lot_id: int) -> list[str] | None`
  - `LotLu(id: int, debut: datetime, derniere_maj: datetime, demandes: list[DemandeLue])`
  - `IngestionPostgres.charger(demande: dict[str, Any]) -> bool`
  - `charger(scenarios: list[dict[str, Any]], ingestion: IngestionPostgres) -> tuple[int, list[str]]` (`kaldera.cli`)

- [ ] **Step 1: Écrire les tests (rouges)**

`tests/conftest.py`, fixture `base` : la requête devient

```python
        conn.execute(
            "TRUNCATE lot_demandes, lots, appels_partenaire, pieces, file_ingestion, analyses, "
            "demandes, contrats, blobs"
        )
```

`tests/integration/test_schema.py`, à la fin :

```python
def test_statut_prete_accepte_et_statut_inconnu_refuse(base: Any) -> None:
    with base.connection() as conn:
        _demande(conn, statut="prete")
        with pytest.raises(psycopg.errors.CheckViolation):
            _demande(conn, reference="KAL-26-9002", statut="en_pause")


def test_lot_reference_une_demande_existante(base: Any) -> None:
    with base.connection() as conn:
        (lot_id,) = conn.execute("INSERT INTO lots DEFAULT VALUES RETURNING id").fetchone()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                "INSERT INTO lot_demandes (lot_id, reference) VALUES (%s, 'KAL-26-9999')", (lot_id,)
            )
```

Créer `tests/integration/test_lots.py` :

```python
"""Intégration — lots (spec C3-3 §2.2, §2.3) : lancement tout ou rien, lecture, pièces mixtes."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.lots_postgres import DepotLots, DossiersNonLancables, ReferencesInconnues
from kaldera.postgres import DepotPostgres
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


def _demande(scenario: str) -> dict[str, Any]:
    return copy.deepcopy(SCENARIOS[scenario]["demandes"][0])


def _statuts(base: Any) -> dict[str, str]:
    with base.connection() as conn:
        return dict(conn.execute("SELECT reference, statut FROM demandes").fetchall())


def test_charger_puis_lancer(base: Any) -> None:
    ingestion = IngestionPostgres(base)
    assert ingestion.charger(_demande("NOM-02")) and ingestion.charger(_demande("NOM-03"))
    assert ingestion.charger(_demande("NOM-02")) is False  # déjà en base
    lot_id, demandes = DepotLots(base).lancer(["KAL-26-0103", "KAL-26-0102"])
    assert [d["reference"] for d in demandes] == ["KAL-26-0103", "KAL-26-0102"]
    assert demandes[0]["pieces"] == _demande("NOM-03")["pieces"]  # niveau 0 : pièces incluses
    assert _statuts(base) == {"KAL-26-0102": "en_cours", "KAL-26-0103": "en_cours"}
    lu = DepotLots(base).lire(lot_id)
    assert lu is not None and [d.reference for d in lu.demandes] == ["KAL-26-0102", "KAL-26-0103"]
    assert DepotLots(base).references(lot_id) == ["KAL-26-0102", "KAL-26-0103"]


def test_tout_ou_rien(base: Any) -> None:
    ingestion = IngestionPostgres(base)
    ingestion.charger(_demande("NOM-02"))
    assert ingestion.creer_demande(json_demande(_demande("NOM-03")))  # admission
    with pytest.raises(DossiersNonLancables) as refus:
        DepotLots(base).lancer(["KAL-26-0102", "KAL-26-0103"])
    assert refus.value.references == ["KAL-26-0103"]
    assert _statuts(base) == {"KAL-26-0102": "prete", "KAL-26-0103": "admission"}
    with base.connection() as conn:
        assert conn.execute("SELECT count(*) FROM lots").fetchone() == (0,)
    with pytest.raises(ReferencesInconnues) as inconnues:
        DepotLots(base).lancer(["KAL-26-0102", "KAL-26-9999"])
    assert inconnues.value.references == ["KAL-26-9999"]


def test_un_seul_lancement_concurrent(base: Any) -> None:
    IngestionPostgres(base).charger(_demande("NOM-02"))

    def essai(_: int) -> bool:
        try:
            DepotLots(base).lancer(["KAL-26-0102"])
        except DossiersNonLancables:
            return False
        return True

    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(essai, range(4))) == 1


def test_lot_inconnu(base: Any) -> None:
    assert DepotLots(base).lire(999) is None and DepotLots(base).references(999) is None


def test_pieces_de_la_demande_si_table_vide(base: Any) -> None:
    demande = _demande("NOM-01")
    pieces = DepotPostgres(base).initiales(demande)
    assert [(p.type, p.lisible, p.montant) for p in pieces] == [
        (p["type"], p["lisible"], p.get("montant")) for p in demande["pieces"]
    ]
    assert DepotPostgres(base).initiales(json_demande(demande)) == []  # niveau 1 : jamais inline
```

Créer `tests/integration/test_cli.py` :

```python
"""Intégration — make scenarios ARGS=--charger : les scénarios en « prete », sans traitement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.cli import charger
from kaldera.ingestion_postgres import IngestionPostgres
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = [
    json.loads(x) for x in (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines() if x
]


def test_charger_les_scenarios(base: Any) -> None:
    ingestion = IngestionPostgres(base)
    assert ingestion.creer_demande(json_demande(SCENARIOS[0]["demandes"][0]))  # make demo
    chargees, ignorees = charger(SCENARIOS, ingestion)
    assert (chargees, ignorees) == (33, ["KAL-26-0101"])
    with base.connection() as conn:
        statuts = dict(
            conn.execute("SELECT statut, count(*) FROM demandes GROUP BY statut").fetchall()
        )
    assert statuts == {"prete": 33, "admission": 1}
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `TEST_DATABASE_URL=postgresql://kaldera:kaldera@localhost:5433/kaldera_test uv run pytest -m integration tests/integration/test_schema.py tests/integration/test_lots.py tests/integration/test_cli.py -v`
(`docker compose --profile integration up -d --wait postgres` au préalable.)
Expected: FAIL (`relation "lot_demandes" does not exist`, `ModuleNotFoundError: kaldera.lots_postgres`).

- [ ] **Step 3: Migration**

Créer `src/kaldera/migrations/006_traitements.sql` :

```sql
-- C3-3 (EX-D45) : le gestionnaire lance le traitement depuis l'IHM.
-- Cycle de vie : admission (pièces en analyse) → prete (admise, en attente du gestionnaire)
-- → en_cours → terminee | secours. Le worker s'arrête désormais à « prete ».
ALTER TABLE demandes DROP CONSTRAINT demandes_statut_check;
ALTER TABLE demandes ADD CONSTRAINT demandes_statut_check
  CHECK (statut IN ('admission','prete','en_cours','terminee','secours'));

-- Un lot = un lancement depuis E1 (1 ou N dossiers), suivi par E3 (GET /lots/{id}).
CREATE TABLE lots (
  id      bigserial PRIMARY KEY,
  cree_le timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lot_demandes (
  lot_id    bigint NOT NULL REFERENCES lots,
  reference text   NOT NULL REFERENCES demandes,
  PRIMARY KEY (lot_id, reference)
);
```

- [ ] **Step 4: Dépôt des lots**

Créer `src/kaldera/lots_postgres.py` :

```python
"""Dépôt des lots (spec C3-3 §2.2, §2.3) : lancement tout ou rien, lecture pour E3.

Toute ``psycopg.Error`` devient ``ErreurPersistance`` (via ``postgres._connexion``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg_pool import ConnectionPool

from .ingestion_postgres import DemandeLue, _demande_lue, _ligne
from .postgres import _connexion


class ReferencesInconnues(Exception):
    def __init__(self, references: list[str]) -> None:
        super().__init__(f"demandes inconnues : {', '.join(references)}")
        self.references = references


class DossiersNonLancables(Exception):
    """Au moins un dossier n'est pas « prete » : rien n'est lancé (tout ou rien)."""

    def __init__(self, references: list[str]) -> None:
        super().__init__(f"dossiers non lançables : {', '.join(references)}")
        self.references = references


@dataclass(frozen=True)
class LotLu:
    id: int
    debut: datetime
    derniere_maj: datetime
    demandes: list[DemandeLue]


class DepotLots:
    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def lancer(self, references: list[str]) -> tuple[int, list[dict[str, Any]]]:
        """Crée le lot et passe ses dossiers de ``prete`` à ``en_cours`` en une transaction ;
        renvoie (id du lot, demandes dans l'ordre reçu). Une exception annule tout."""
        with _connexion(self.connexions) as conn, conn.transaction():
            connues = {
                r
                for (r,) in conn.execute(
                    "SELECT reference FROM demandes WHERE reference = ANY(%s)", (references,)
                )
            }
            if inconnues := [r for r in references if r not in connues]:
                raise ReferencesInconnues(inconnues)
            lancees = dict(
                conn.execute(
                    "UPDATE demandes SET statut = 'en_cours', maj = now() "
                    "WHERE reference = ANY(%s) AND statut = 'prete' RETURNING reference, etat",
                    (references,),
                ).fetchall()
            )
            if refusees := [r for r in references if r not in lancees]:
                raise DossiersNonLancables(refusees)
            (lot_id,) = _ligne(conn.execute("INSERT INTO lots DEFAULT VALUES RETURNING id"))
            conn.cursor().executemany(
                "INSERT INTO lot_demandes (lot_id, reference) VALUES (%s, %s)",
                [(lot_id, r) for r in references],
            )
        return int(lot_id), [dict(lancees[r]["demande"]) for r in references]

    def lire(self, lot_id: int) -> LotLu | None:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(
                "SELECT l.cree_le, d.maj, d.reference, d.statut, d.fiche, d.etat FROM lots l "
                "JOIN lot_demandes ld ON ld.lot_id = l.id "
                "JOIN demandes d ON d.reference = ld.reference "
                "WHERE l.id = %s ORDER BY d.reference",
                (lot_id,),
            ).fetchall()
        if not lignes:  # un lot a toujours au moins un dossier
            return None
        return LotLu(
            id=lot_id,
            debut=lignes[0][0],
            derniere_maj=max(ligne[1] for ligne in lignes),
            demandes=[_demande_lue(tuple(ligne[2:])) for ligne in lignes],
        )

    def references(self, lot_id: int) -> list[str] | None:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(
                "SELECT reference FROM lot_demandes WHERE lot_id = %s ORDER BY reference",
                (lot_id,),
            ).fetchall()
        return [r for (r,) in lignes] or None
```

- [ ] **Step 5: Chargement `prete` et dépôt mixte**

`src/kaldera/ingestion_postgres.py` : remplacer `creer_demande` par :

```python
    def creer_demande(self, demande: dict[str, Any]) -> bool:
        """Ligne ``admission`` ; faux si la référence existe déjà."""
        return self._inserer(demande, "admission")

    def charger(self, demande: dict[str, Any]) -> bool:
        """Ligne ``prete`` (niveau 0 : contrat et pièces dans la demande, sans ingestion) ;
        ``make scenarios ARGS=--charger``. Faux si la référence existe déjà."""
        return self._inserer(demande, "prete")

    def _inserer(self, demande: dict[str, Any], statut: str) -> bool:
        etat = EtatDemande(demande=demande).model_dump(mode="json")
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "INSERT INTO demandes (reference, numero_contrat, etat, etat_courant, statut) "
                "VALUES (%s, %s, %s, 'eligibilite', %s) "
                "ON CONFLICT (reference) DO NOTHING RETURNING reference",
                (demande["reference"], demande["contrat"]["numero"], Jsonb(etat), statut),
            ).fetchone()
        return ligne is not None
```

`src/kaldera/postgres.py` : ajouter `from .memoire import DepotDepuisDemande` aux imports, `_NIVEAU_0 = DepotDepuisDemande()  # sans état : partagé` sous les constantes, et dans `DepotPostgres` :

```python
    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]:
        # table vide pour la référence ⇒ pièces de la demande (scénarios chargés, niveau 0) ;
        # une demande créée par l'API n'a jamais de champ « pieces » (extra=forbid)
        return self._lire("relance IS NULL ORDER BY depose_le, piece_id", demande) or (
            _NIVEAU_0.initiales(demande)
        )

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]:
        return self._lire(
            "relance IS NOT NULL ORDER BY relance, depose_le, piece_id", demande
        ) or _NIVEAU_0.depots(demande)
```

Mettre à jour la docstring de la classe : « Niveau 1 : descripteurs de la table ``pieces`` ; à défaut, les pièces de la demande (niveau 0). »

- [ ] **Step 6: `make scenarios ARGS=--charger`**

Remplacer `src/kaldera/cli.py` par :

```python
"""Rejoue des demandes : ``python -m kaldera.cli eval/scenarios.jsonl [--scenario ID]``.

``--charger`` : insère les demandes en « prete » (base requise) ; le gestionnaire les lance
depuis l'IHM (E1 → E2 / E3), rien n'est traité ici.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import traiter_lot
from .ingestion_postgres import IngestionPostgres
from .postgres import ConfigBase, pool


def charger(
    scenarios: list[dict[str, Any]], ingestion: IngestionPostgres
) -> tuple[int, list[str]]:
    """Insère chaque demande en « prete » ; renvoie (chargées, références déjà en base)."""
    chargees, ignorees = 0, []
    for scenario in scenarios:
        for demande in scenario["demandes"]:
            if ingestion.charger(demande):
                chargees += 1
            else:
                ignorees.append(demande["reference"])
    return chargees, ignorees


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fichier", type=Path, help="fichier JSONL de scénarios")
    parser.add_argument("--scenario", action="append", help="identifiant(s) de scénario à rejouer")
    parser.add_argument("--partenaire", default=None, help="URL du partenaire anti-fraude")
    parser.add_argument("--trace", action="store_true", help="affiche la trace de chaque fiche")
    parser.add_argument(
        "--charger", action="store_true", help="insère les demandes en « prete », sans traiter"
    )
    args = parser.parse_args()

    scenarios = [
        s
        for s in map(json.loads, filter(str.strip, args.fichier.read_text("utf-8").splitlines()))
        if not args.scenario or s["id"] in args.scenario
    ]
    if args.charger:
        url = ConfigBase().database_url
        if not url:
            raise SystemExit("KALDERA_DATABASE_URL absente : rien à charger")
        chargees, ignorees = charger(scenarios, IngestionPostgres(pool(url)))
        deja = ", ".join(ignorees) or "aucune"
        print(f"{chargees} demandes prêtes ; déjà en base, ignorées : {deja}")
        return
    for scenario in scenarios:
        print(f"== {scenario['id']} — {scenario['titre']}")
        resultat = traiter_lot(scenario["demandes"], partenaire_url=args.partenaire)
        for fiche in resultat["fiches"]:
            if not args.trace:
                fiche = {k: v for k, v in fiche.items() if k != "trace"}
            print(json.dumps(fiche, ensure_ascii=False))
        synthese = {"metriques": resultat["metriques"], "equipe": resultat["equipe"]}
        print(json.dumps(synthese, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

`tests/e2e/serveur.py` : même TRUNCATE que `tests/conftest.py` (avec `lot_demandes, lots` en tête).

- [ ] **Step 7: Vérifier**

Run: `TEST_DATABASE_URL=postgresql://kaldera:kaldera@localhost:5433/kaldera_test uv run pytest -m integration -v`
Expected: PASS (toute la suite d'intégration : le worker traite encore, il n'est modifié qu'en Task 6).

Run: `uv run pytest && uv run ruff check src tests && uv run mypy src`
Expected: PASS, aucune erreur.

- [ ] **Step 8: Commit**

```bash
git add src/kaldera/migrations/006_traitements.sql src/kaldera/lots_postgres.py src/kaldera/ingestion_postgres.py src/kaldera/postgres.py src/kaldera/cli.py tests/conftest.py tests/e2e/serveur.py tests/integration/test_schema.py tests/integration/test_lots.py tests/integration/test_cli.py
git commit -m "feat(lots): statut prete, tables lots (migration 006), lancement tout ou rien, make scenarios --charger (C3-3)"
```

---

### Task 5: Service de traitement et routes `POST /traitements`, `GET /lots/{id}`

**Files:**
- Create: `src/kaldera/traitements.py`
- Modify: `src/kaldera/__init__.py` (`traiter_lot(..., orchestrateur=None)`)
- Modify: `src/kaldera/api.py`
- Test: `tests/integration/test_traitements.py` (créé), `tests/unit/test_points_entree.py`

**Interfaces:**
- Consumes: `DepotLots`, `ReferencesInconnues`, `DossiersNonLancables` (Task 4) ; `SignauxPostgres` (Task 2) ; `lot`, `LotVue` (Task 1).
- Produces (Tasks 6, 7, 8, 10) :
  - `traiter_lot(demandes, *, partenaire_url=None, orchestrateur: Orchestrateur | None = None)`
  - `traitements.orchestrateur(connexions) -> Orchestrateur` ; `traitements.traiter(connexions, demandes) -> None`
  - API : `POST /traitements` (corps `{"references": [...]}`) ⇒ 202 `{"lot_id": int, "references": [...]}` ; `GET /lots/{lot_id}` ⇒ `LotVue` ; dépendance `depot_lots` / alias `Lots`

- [ ] **Step 1: Écrire les tests (rouges)**

`tests/unit/test_points_entree.py`, à la fin :

```python
def test_lot_avec_un_orchestrateur_fourni() -> None:
    from kaldera.orchestrateur import Orchestrateur

    appels: list[str] = []

    class Espion(Orchestrateur):
        def traiter(self, demande: dict[str, Any]) -> dict[str, Any]:
            appels.append(demande["reference"])
            return super().traiter(demande)

    demandes = [d for d in NOMINAUX if d["reference"] == "KAL-26-0102"]  # NOM-02 : refusée
    resultat = kaldera.traiter_lot(demandes, orchestrateur=Espion(evaluer=lambda d, t: None))
    assert appels == ["KAL-26-0102"] and resultat["fiches"][0]["decision"] == "refusee"
```

(`Orchestrateur` et `Any` sont déjà importés par le fichier ; retirer l'import local s'il fait doublon.)

Créer `tests/integration/test_traitements.py` :

```python
"""Intégration — POST /traitements et GET /lots (spec C3-3 §2.2, §2.3, §5)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kaldera.ingestion_postgres import IngestionPostgres
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


@pytest.fixture(autouse=True)
def _partenaire_coupe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTENAIRE_URL", "http://127.0.0.1:9")  # jamais le partenaire du poste


def _charger(base: Any, *scenarios: str) -> list[str]:
    ingestion = IngestionPostgres(base)
    demandes = [copy.deepcopy(SCENARIOS[s]["demandes"][0]) for s in scenarios]
    assert all(ingestion.charger(d) for d in demandes)
    return [d["reference"] for d in demandes]


def test_lancer_un_lot_puis_le_lire(client: TestClient, base: Any) -> None:
    references = _charger(base, "NOM-02", "NOM-03")
    reponse = client.post("/traitements", json={"references": references})
    assert reponse.status_code == 202, reponse.text
    assert reponse.json()["references"] == references
    # TestClient exécute la tâche de fond avant de rendre la main
    vue = client.get(f"/lots/{reponse.json()['lot_id']}").json()
    assert vue["avancement"] == 100 and vue["fin"] is not None
    assert {d["reference"]: d["statut"] for d in vue["dossiers"]} == dict.fromkeys(
        references, "terminee"
    )
    assert vue["compteurs"]["refusee"] == 2
    lignes = {lg["reference"]: lg for lg in client.get("/demandes").json()}
    assert lignes["KAL-26-0102"]["selectionnable"] is False
    assert lignes["KAL-26-0102"]["motif_non_selectionnable"] == "Déjà traité"


def test_dossier_seul(client: TestClient, base: Any) -> None:
    (reference,) = _charger(base, "NOM-02")
    reponse = client.post("/traitements", json={"references": [reference]})
    assert reponse.status_code == 202
    vue = client.get(f"/demandes/{reference}").json()
    assert vue["statut"] == "terminee" and vue["avancement"] == 100


def test_tout_ou_rien_409(client: TestClient, base: Any) -> None:
    (prete,) = _charger(base, "NOM-02")
    demande = json_demande(SCENARIOS["NOM-03"]["demandes"][0])
    assert client.post("/demandes", json=demande).status_code == 201  # admission
    reponse = client.post("/traitements", json={"references": [prete, demande["reference"]]})
    assert reponse.status_code == 409
    assert reponse.json() == {"detail": "dossiers non lançables", "references": ["KAL-26-0103"]}
    assert client.get(f"/demandes/{prete}").json()["statut"] == "prete"


def test_relancer_un_dossier_lance_409(client: TestClient, base: Any) -> None:
    (reference,) = _charger(base, "NOM-02")
    assert client.post("/traitements", json={"references": [reference]}).status_code == 202
    second = client.post("/traitements", json={"references": [reference]})
    assert second.status_code == 409 and second.json()["references"] == [reference]
    with base.connection() as conn:
        assert conn.execute("SELECT count(*) FROM lots").fetchone() == (1,)


def test_reference_inconnue_404(client: TestClient) -> None:
    reponse = client.post("/traitements", json={"references": ["KAL-26-9999"]})
    assert reponse.status_code == 404
    assert reponse.json() == {"detail": "demande inconnue", "references": ["KAL-26-9999"]}


@pytest.mark.parametrize(
    "corps",
    [
        {"references": []},
        {"references": ["KAL-26-0102", "KAL-26-0102"]},
        {"references": ["pas-une-reference"]},
        {"references": ["KAL-26-0102"], "auteur": "x"},
    ],
)
def test_corps_invalide_422(client: TestClient, corps: dict[str, Any]) -> None:
    assert client.post("/traitements", json=corps).status_code == 422


def test_lot_inconnu_404(client: TestClient) -> None:
    assert client.get("/lots/999").status_code == 404
    assert client.get("/lots/abc").status_code == 422


def test_filtre_statut_prete(client: TestClient, base: Any) -> None:
    _charger(base, "NOM-02")
    lignes = client.get("/demandes", params={"statut": "prete"}).json()
    assert [(lg["reference"], lg["selectionnable"]) for lg in lignes] == [("KAL-26-0102", True)]
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `TEST_DATABASE_URL=… uv run pytest -m integration tests/integration/test_traitements.py -v` et `uv run pytest tests/unit/test_points_entree.py -v`
Expected: FAIL (404 sur `/traitements` ; `TypeError: unexpected keyword argument 'orchestrateur'`).

- [ ] **Step 3: `traiter_lot` et service**

`src/kaldera/__init__.py` :

```python
def traiter_lot(
    demandes: list[dict[str, Any]],
    *,
    partenaire_url: str | None = None,
    orchestrateur: Orchestrateur | None = None,
) -> dict[str, Any]:
    """Traite un lot de demandes en parallèle (§12) ; fiches dans l'ordre, métriques par agent.

    ``orchestrateur`` : câblé par l'appelant (API : PostgreSQL et signaux, C3-3) ; sinon construit
    ici avec la configuration par défaut."""
    orchestrateur = orchestrateur or Orchestrateur(partenaire_url)  # config lue une fois
```

(le reste du corps est inchangé.)

Créer `src/kaldera/traitements.py` :

```python
"""Traitement lancé par le gestionnaire (spec C3-3 §2.2) : un lot, un orchestrateur câblé sur
PostgreSQL (snapshots, pièces, signaux). Appelé en tâche de fond par ``POST /traitements``."""

from __future__ import annotations

from typing import Any

from psycopg_pool import ConnectionPool

from . import traiter_lot
from .orchestrateur import Orchestrateur
from .postgres import DepotPostgres, SignauxPostgres, SnapshotsPostgres


def orchestrateur(connexions: ConnectionPool) -> Orchestrateur:
    # ponytail: un disjoncteur par lot (un orchestrateur par lot) ; un disjoncteur de processus
    # si les pannes LLM doivent être retenues d'un lot à l'autre
    return Orchestrateur(
        depot=DepotPostgres(connexions),
        snapshots=SnapshotsPostgres(connexions),
        signaux=SignauxPostgres(connexions),
    )


def traiter(connexions: ConnectionPool, demandes: list[dict[str, Any]]) -> None:
    """Traite le lot ; chaque dossier a son filet, le reaper couvre un arrêt brutal de l'API."""
    traiter_lot(demandes, orchestrateur=orchestrateur(connexions))
```

- [ ] **Step 4: Routes**

`src/kaldera/api.py` :

- imports : `from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request, Response, UploadFile` ; `from pydantic import BaseModel, ConfigDict, Field, field_validator` ; `from . import traitements` ; `from .lots_postgres import DepotLots, DossiersNonLancables, ReferencesInconnues` ; `from .vue_gestionnaire import DossierVue, LigneDemande, LotVue`.
- docstring du module : ajouter « traitement et suivi de lot (C3-3) ».
- après `Config = Annotated[...]` :

```python
def depot_lots(ingestion: Ingestion) -> DepotLots:
    return DepotLots(ingestion.connexions)


Lots = Annotated[DepotLots, Depends(depot_lots)]
```

- gestionnaires d'exceptions, après `_base_indisponible` :

```python
@app.exception_handler(ReferencesInconnues)
def _references_inconnues(request: Request, exc: ReferencesInconnues) -> JSONResponse:
    return JSONResponse(
        status_code=404, content={"detail": "demande inconnue", "references": exc.references}
    )


@app.exception_handler(DossiersNonLancables)
def _non_lancables(request: Request, exc: DossiersNonLancables) -> JSONResponse:
    return JSONResponse(
        status_code=409, content={"detail": "dossiers non lançables", "references": exc.references}
    )
```

- schémas, après `class Depot` :

```python
class Traitement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    references: list[Annotated[str, Field(pattern=r"^KAL-\d{2}-\d{4}$")]] = Field(min_length=1)

    @field_validator("references")
    @classmethod
    def _sans_doublon(cls, references: list[str]) -> list[str]:
        if len(set(references)) != len(references):
            raise ValueError("référence en double")
        return references


class LotLance(BaseModel):
    lot_id: int
    references: list[str]
```

- routes, à la fin du fichier :

```python
@app.post("/traitements", status_code=202, response_model=LotLance)
def lancer_traitement(corps: Traitement, lots: Lots, taches: BackgroundTasks) -> LotLance:
    lot_id, demandes = lots.lancer(corps.references)  # 404 / 409 : gestionnaires ci-dessus
    taches.add_task(traitements.traiter, lots.connexions, demandes)
    return LotLance(lot_id=lot_id, references=corps.references)


@app.get("/lots/{lot_id}", response_model=LotVue)
def lire_lot(lot_id: int, lots: Lots) -> LotVue:
    lu = lots.lire(lot_id)
    if lu is None:
        raise HTTPException(404, "lot inconnu")
    demandes = ((d.reference, d.statut, d.fiche, d.etat) for d in lu.demandes)
    return vue.lot(lu.id, lu.debut, lu.derniere_maj, demandes)
```

- [ ] **Step 5: Vérifier**

Run: `TEST_DATABASE_URL=… uv run pytest -m integration tests/integration/test_traitements.py tests/integration/test_api.py -v` puis `uv run pytest tests/unit -v`
Expected: PASS.

Run: `uv run ruff check src tests && uv run mypy src`
Expected: aucune erreur.

- [ ] **Step 6: Commit**

```bash
git add src/kaldera/__init__.py src/kaldera/traitements.py src/kaldera/api.py tests/integration/test_traitements.py tests/unit/test_points_entree.py
git commit -m "feat(api): POST /traitements (tâche de fond, tout ou rien) et GET /lots/{id} (C3-3)"
```

---

### Task 6: Le worker s'arrête à `prete` ; seed et épreuve lancent par l'API

**Files:**
- Modify: `src/kaldera/ingestion_postgres.py` (`admettre`, `contrat` → `_lire_contrat`)
- Modify: `src/kaldera/worker.py` (`travailler` sans `disjoncteur`, `_admettre`)
- Modify: `tools/seed.py` (`lancer`, `main`, docstring)
- Modify: `tests/e2e/serveur.py` (appel `travailler`)
- Modify: `Makefile` (cible `api-epreuve`)
- Modify: `tests/integration/dossiers.py` (`lancer_pretes`), `tests/integration/test_worker.py`, `tests/integration/test_seed.py`, `tests/integration/test_epreuve.py`

**Interfaces:**
- Consumes: `DepotLots.lancer` (Task 4) ; `traitements.traiter` (Task 5) ; `demande_niveau_1` (`kaldera.ingestion`).
- Produces :
  - `IngestionPostgres.admettre(reference: str) -> bool`
  - `travailler(ingestion, vlm, config) -> bool`
  - `tools.seed.lancer(client: httpx.Client, references: list[str], attente_s: float, pause_s: float = 2.0) -> None`
  - `tests.integration.dossiers.lancer_pretes(connexions) -> None`

- [ ] **Step 1: Adapter les tests (rouges)**

`tests/integration/dossiers.py`, à la fin (imports `from typing import Any`, déjà présent) :

```python
def lancer_pretes(connexions: Any) -> None:
    """Lance, comme le gestionnaire, toutes les demandes prêtes (un lot, traité tout de suite)."""
    from kaldera import traitements
    from kaldera.lots_postgres import DepotLots

    with connexions.connection() as conn:
        pretes = [
            r
            for (r,) in conn.execute(
                "SELECT reference FROM demandes WHERE statut = 'prete' ORDER BY reference"
            )
        ]
    if pretes:
        _, demandes = DepotLots(connexions).lancer(pretes)
        traitements.traiter(connexions, demandes)
```

`tests/integration/test_worker.py` :
- supprimer les imports `Disjoncteur` et `BORNES` ; importer `from tests.integration.dossiers import json_demande, lancer_pretes` ;
- remplacer chaque `travailler(ingestion, vlm, CONFIG, Disjoncteur.depuis(BORNES))` par `travailler(ingestion, vlm, CONFIG)` ;
- `vider` devient :

```python
def vider(ingestion: IngestionPostgres, vlm: FakeVLM) -> None:
    """Le worker analyse et admet (« prete ») ; le gestionnaire lance ensuite (C3-3)."""
    while travailler(ingestion, vlm, CONFIG):
        pass
    lancer_pretes(ingestion.connexions)
```

- `test_deux_workers_une_seule_admission` : `assert sum(admises) == 1` (au lieu de `sum(a is not None ...)`) ;
- ajouter :

```python
def test_admission_prete_sans_traitement(client: TestClient, ingestion: IngestionPostgres) -> None:
    demande = SCENARIOS["NOM-01"]["demandes"][0]
    vlm = FakeVLM(deposer_dossier(client, demande))
    while travailler(ingestion, vlm, CONFIG):
        pass
    vue = client.get(f"/demandes/{demande['reference']}").json()
    assert (vue["statut"], vue["fiche"], vue["avancement"]) == ("prete", None, 0)
    with ingestion.connexions.connection() as conn:
        (etat,) = conn.execute(
            "SELECT etat FROM demandes WHERE reference = %s", (demande["reference"],)
        ).fetchone()
    assert etat["demande"]["contrat"]["source"] == "extraction_vlm"  # demande niveau 1
    assert etat["trace"] == []  # aucune étape exécutée
```

`tests/integration/test_seed.py` : retirer `Disjoncteur`, `BORNES` ; `from tools.seed import EchecSeed, attendre, deposer, lancer, lire_manifeste, verites_fake` ; dans `test_seed_puis_traitement`, après la boucle `while travailler(ingestion, vlm, CONFIG): pass`, ajouter `lancer(api, references, attente_s=0, pause_s=0)` avant `attendre(...)` ; ajouter :

```python
def test_lancer_attend_la_fin_des_analyses(api: TestClient) -> None:
    references = deposer(api, _extrait(lire_manifeste(), "KAL-26-0101"))
    with pytest.raises(EchecSeed, match="encore en analyse"):
        lancer(api, references, attente_s=0, pause_s=0)
```

`tests/integration/test_epreuve.py` : retirer `Disjoncteur`, `BORNES` ; `travailler(ingestion, vlm, CONFIG)` (deux appels) ; `from tools.seed import attendre, deposer, lancer, lire_manifeste, verites_fake` ; dans `test_chaine_complete_fakevlm`, `lancer(api, references, attente_s=0, pause_s=0)` avant `attendre(...)` (le manifeste entier part en **un seul** lot : Review Focus 1).

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `TEST_DATABASE_URL=… uv run pytest -m integration tests/integration/test_worker.py tests/integration/test_seed.py -v`
Expected: FAIL (`TypeError: travailler() takes 3 positional arguments` inversé / `ImportError: cannot import name 'lancer'`).

- [ ] **Step 3: Admission en `prete`**

`src/kaldera/ingestion_postgres.py` : `from .ingestion import ExtractionContrat, demande_niveau_1`. Remplacer `admettre` et `contrat` par :

```python
    def admettre(self, reference: str) -> bool:
        """Admission atomique (C3-3) : la demande passe en ``prete`` avec sa vue niveau 1 (termes du
        contrat extraits) dans la même transaction ; faux pour les perdants. Le gestionnaire lance."""
        with _connexion(self.connexions) as conn, conn.transaction():
            ligne = conn.execute(
                "SELECT etat FROM demandes WHERE reference = %s AND " + self._ADMISSIBLE
                + " FOR UPDATE SKIP LOCKED",
                (reference,),
            ).fetchone()
            if ligne is None:
                return False
            demande = dict(ligne[0]["demande"])
            contrat = self._lire_contrat(conn, demande["contrat"]["numero"])
            etat = EtatDemande(demande=demande_niveau_1(demande, contrat))
            conn.execute(
                "UPDATE demandes SET statut = 'prete', etat = %s, maj = now() WHERE reference = %s",
                (Jsonb(etat.model_dump(mode="json")), reference),
            )
        return True

    def contrat(self, numero: str) -> dict[str, Any] | None:
        with _connexion(self.connexions) as conn:
            return self._lire_contrat(conn, numero)

    @staticmethod
    def _lire_contrat(conn: Any, numero: str) -> dict[str, Any] | None:
        contrat = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT formule, date_souscription, statut_extraction, violations, modele, "
                "version_prompt, sha256 FROM contrats WHERE numero = %s",
                (numero,),
            )
            .fetchone()
        )
        if contrat is None:
            return None
        if contrat["date_souscription"] is not None:
            contrat["date_souscription"] = contrat["date_souscription"].isoformat()
        contrat["violations"] = list(contrat["violations"])
        return dict(contrat)
```

- [ ] **Step 4: Worker**

`src/kaldera/worker.py` :
- docstring : « Worker d'ingestion (dossier 2.4 ter) : analyse les fichiers, puis admet en ``prete`` ; le gestionnaire lance le traitement depuis l'IHM (C3-3). »
- imports retirés : `Disjoncteur`, `BORNES`, `demande_niveau_1`, `Orchestrateur`, `DepotPostgres`, `SnapshotsPostgres` (garder `ConfigBase`, `pool`).
- `travailler(ingestion, vlm, config) -> bool` (sans `disjoncteur`) ; ses deux appels `_admettre(ingestion, ...)` sans disjoncteur.
- `_admettre` :

```python
def _admettre(ingestion: IngestionPostgres, reference: str) -> None:
    if ingestion.admettre(reference):
        LOGGER.info("demande %s prête : traitement lancé par le gestionnaire (E1)", reference)
```

- `main` : supprimer `disjoncteur = ...` ; `occupe = travailler(ingestion, vlm, config)`.

`tests/e2e/serveur.py` : supprimer `Disjoncteur`, `BORNES` et `disjoncteur = ...` ; `occupe = travailler(ingestion, vlm, config)`.

- [ ] **Step 5: Seed**

`tools/seed.py` :
- docstring, ligne d'usage : `Usage : make api-epreuve & make worker-epreuve, puis uv run python -m tools.seed [--attente-s 3600]`
- remplacer `_traitee` par :

```python
def _lire(client: httpx.Client, reference: str) -> dict[str, Any]:
    reponse = client.get(f"/demandes/{reference}")
    if reponse.status_code == 404:
        raise EchecSeed(f"{reference} inconnue de l'API")
    _verifier(reponse, 200, f"{reference} lecture")
    demande: dict[str, Any] = reponse.json()
    return demande


def _traitee(client: httpx.Client, reference: str) -> bool:
    demande = _lire(client, reference)  # fauchée par le reaper : sa fiche de secours la clôt
    return demande["statut"] == "terminee" or (
        demande["statut"] == "secours" and demande["fiche"] is not None
    )


def lancer(
    client: httpx.Client, references: list[str], attente_s: float, pause_s: float = 2.0
) -> None:
    """Attend la fin des analyses (« prete »), puis lance les demandes prêtes en un lot, comme le
    gestionnaire depuis E1 (POST /traitements, C3-3)."""
    echeance = time.monotonic() + attente_s
    while restantes := [r for r in references if _lire(client, r)["statut"] == "admission"]:
        if time.monotonic() >= echeance:
            raise EchecSeed(f"délai dépassé : {len(restantes)} demande(s) encore en analyse")
        time.sleep(pause_s)
    pretes = [r for r in references if _lire(client, r)["statut"] == "prete"]
    if pretes:
        _verifier(client.post("/traitements", json={"references": pretes}), 202, "lancement du lot")
```

- `main` : après `print(f"{len(references)} demandes déposées et soumises ; attente du traitement…")`, appeler `lancer(client, references, a.attente_s)` puis `attendre(client, references, a.attente_s)`.

`Makefile`, après la cible `api` :

```make
api-epreuve:
	PARTENAIRE_URL=http://127.0.0.1:9 uv run uvicorn kaldera.api:app --port 8000
```

(et ajouter `api-epreuve` à la ligne `.PHONY` si elle existe.)

- [ ] **Step 6: Vérifier**

Run: `TEST_DATABASE_URL=… uv run pytest -m integration -v`
Expected: PASS, dont `test_chaine_complete_fakevlm` (34 dossiers d'un seul lot, tous `terminee` : aucune « persistance coupée »).

Run: `uv run pytest && uv run ruff check src tests tools && uv run mypy src`
Expected: PASS, aucune erreur.

- [ ] **Step 7: Commit**

```bash
git add src/kaldera/ingestion_postgres.py src/kaldera/worker.py tools/seed.py tests/e2e/serveur.py Makefile tests/integration/dossiers.py tests/integration/test_worker.py tests/integration/test_seed.py tests/integration/test_epreuve.py
git commit -m "feat(worker): admission en prete, traitement lancé par le gestionnaire ; seed et épreuve via POST /traitements (C3-3)"
```

---

### Task 7: Flux SSE `/flux/demandes/{ref}` et `/flux/lots/{id}`

**Files:**
- Create: `src/kaldera/flux.py`
- Modify: `src/kaldera/api.py`
- Test: `tests/unit/test_flux.py` (créé), `tests/integration/test_flux.py` (créé)

**Interfaces:**
- Consumes: `CANAL`, `SignauxPostgres` (Task 2) ; `evenement` (Task 1) ; `DepotLots.references` (Task 4).
- Produces :
  - `ecouter(conninfo: str, ping_s: float = PING_S) -> AsyncIterator[str | None]`
  - `diffuser(charges: AsyncIterator[str | None], references: frozenset[str]) -> AsyncIterator[str]`
  - API : `GET /flux/demandes/{reference}`, `GET /flux/lots/{lot_id}` (`text/event-stream`, `event: avancement`)

- [ ] **Step 1: Écrire les tests (rouges)**

Créer `tests/unit/test_flux.py` :

```python
"""Unitaires — diffusion SSE : filtre par dossier, traduction, battement (spec C3-3 §3.4)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from kaldera.flux import diffuser


async def _charges(*charges: str | None) -> AsyncIterator[str | None]:
    for charge in charges:
        yield charge


def _tout(charges: AsyncIterator[str | None], references: frozenset[str]) -> list[str]:
    async def lire() -> list[str]:
        return [morceau async for morceau in diffuser(charges, references)]

    return asyncio.run(lire())


def test_diffuser_filtre_et_traduit() -> None:
    a = {"type": "sous_etape", "reference": "A", "etat": "pieces", "sous_etape": "vue",
         "tour": 0, "tours_max": 3}
    b = {**a, "reference": "B"}
    sorties = _tout(
        _charges(json.dumps(a), json.dumps(b), None, "pas du json", json.dumps({"type": "x"})),
        frozenset({"A"}),
    )
    assert sorties[0] == ": ouvert\n\n"
    assert sorties[1].startswith("event: avancement\ndata: ")
    donnees = json.loads(sorties[1].split("data: ", 1)[1])
    assert donnees == {"type": "sous_etape", "reference": "A", "etat": "pieces",
                       "statut": "en_cours", "avancement_agent": 17}
    assert sorties[2:] == [": ping\n\n"]  # B filtré, JSON cassé et type inconnu ignorés
```

Créer `tests/integration/test_flux.py` :

```python
"""Intégration — LISTEN : un pg_notify émis par SignauxPostgres arrive au flux (spec §3.4)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kaldera.flux import ecouter
from kaldera.postgres import SignauxPostgres

pytestmark = pytest.mark.integration


def test_ecouter_recoit_un_signal(base: Any) -> None:
    async def scenario() -> str | None:
        flux = ecouter(base.conninfo, ping_s=0.2)
        assert await anext(flux) is None  # premier battement : LISTEN est en place
        SignauxPostgres(base).emettre({"type": "dossier_fin", "reference": "KAL-26-9001"})
        charge = await anext(flux)
        while charge is None:  # un battement peut précéder la notification
            charge = await anext(flux)
        await flux.aclose()
        return charge

    charge = asyncio.run(scenario())
    assert charge is not None and json.loads(charge) == {
        "type": "dossier_fin", "reference": "KAL-26-9001"
    }


def test_flux_inconnus_404(client: TestClient) -> None:
    assert client.get("/flux/demandes/KAL-26-9999").status_code == 404
    assert client.get("/flux/lots/999").status_code == 404
```

(Le flux d'un dossier existant ne se termine jamais : il n'est pas testé par `TestClient`, qui attend la fin du corps ; il l'est par `e2e/traitement.spec.ts`, Task 11.)

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/unit/test_flux.py -v`
Expected: FAIL (`ModuleNotFoundError: kaldera.flux`).

- [ ] **Step 3: Implémenter `flux.py`**

Créer `src/kaldera/flux.py` :

```python
"""Flux SSE du back-office (spec C3-3 §3.4) : LISTEN PostgreSQL → événements filtrés, prêts à
afficher. Asynchrone de bout en bout : aucune E/S bloquante dans la boucle d'événements."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import psycopg

from .postgres import CANAL
from .vue_gestionnaire import evenement

PING_S = 15.0  # battement : garde la connexion ouverte à travers proxys et navigateurs


async def ecouter(conninfo: str, ping_s: float = PING_S) -> AsyncIterator[str | None]:
    """Charges utiles du canal d'avancement ; ``None`` à chaque fenêtre de ``ping_s`` secondes."""
    # ponytail: une connexion par client SSE (usage local) ; un écouteur partagé si plusieurs
    # gestionnaires suivent des lots en même temps
    async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
        await conn.execute(f"LISTEN {CANAL}")  # CANAL : constante du module, jamais une donnée
        while True:
            async for notification in conn.notifies(timeout=ping_s):
                yield notification.payload
            yield None


async def diffuser(
    charges: AsyncIterator[str | None], references: frozenset[str]
) -> AsyncIterator[str]:
    """Messages SSE des seuls dossiers suivis ; un signal illisible est ignoré."""
    yield ": ouvert\n\n"  # premier octet tout de suite : EventSource passe à « open »
    async for charge in charges:
        if charge is None:
            yield ": ping\n\n"
            continue
        try:
            brut = json.loads(charge)
        except json.JSONDecodeError:
            continue
        vue = evenement(brut) if isinstance(brut, dict) else None
        if vue is not None and vue.reference in references:
            yield f"event: avancement\ndata: {vue.model_dump_json()}\n\n"
```

- [ ] **Step 4: Routes**

`src/kaldera/api.py` : imports `from fastapi.concurrency import run_in_threadpool` ; `from fastapi.responses import JSONResponse, StreamingResponse` ; `from .flux import diffuser, ecouter`. À la fin :

```python
def _flux(conninfo: str, references: frozenset[str]) -> StreamingResponse:
    return StreamingResponse(
        diffuser(ecouter(conninfo), references),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/flux/demandes/{reference}")
async def flux_demande(reference: str, ingestion: Ingestion) -> StreamingResponse:
    if await run_in_threadpool(ingestion.statut, reference) is None:
        raise HTTPException(404, "demande inconnue")
    return _flux(ingestion.connexions.conninfo, frozenset({reference}))


@app.get("/flux/lots/{lot_id}")
async def flux_lot(lot_id: int, lots: Lots) -> StreamingResponse:
    references = await run_in_threadpool(lots.references, lot_id)
    if references is None:
        raise HTTPException(404, "lot inconnu")
    return _flux(lots.connexions.conninfo, frozenset(references))
```

- [ ] **Step 5: Vérifier**

Run: `uv run pytest tests/unit/test_flux.py -v` et `TEST_DATABASE_URL=… uv run pytest -m integration tests/integration/test_flux.py -v`
Expected: PASS.

Contrôle manuel (base de test lancée, une demande chargée) : `make api`, puis `curl -N http://127.0.0.1:8000/flux/demandes/KAL-26-0102` affiche `: ouvert` puis `: ping` toutes les 15 s ; Ctrl+C ferme proprement (aucune trace d'erreur côté API).

Run: `uv run ruff check src tests && uv run mypy src`
Expected: aucune erreur.

- [ ] **Step 6: Commit**

```bash
git add src/kaldera/flux.py src/kaldera/api.py tests/unit/test_flux.py tests/integration/test_flux.py
git commit -m "feat(api): flux SSE par dossier et par lot (LISTEN asynchrone, filtre, battement) (C3-3)"
```

---

### Task 8: Front — client API, statut « Prête », sélection et lancement dans E1

**Files:**
- Modify: `front/src/api.ts`, `front/src/api.test.ts`
- Modify: `front/src/statuts.ts`
- Modify: `front/src/test/rendre.tsx` (`simulerApi` reçoit `init`), `front/src/test/fixtures.ts`
- Modify: `front/src/pages/ListeDemandes.tsx`, `front/src/pages/ListeDemandes.test.tsx`

**Interfaces:**
- Consumes: `POST /traitements`, `LigneDemande.selectionnable` / `motif_non_selectionnable` (Tasks 1, 5).
- Produces (Tasks 9, 10) :
  - types `LigneLot`, `CompteursLot`, `LotVue`, `LotLance`, `EvenementVue` ; `StatutEtape` avec `"en_cours"`
  - `ErreurApi(statut, message, references = [])` ; `envoyer<T>(chemin: string, corps: unknown): Promise<T>`
  - `ETAPES: Record<string, string>` exporté par `statuts.ts` (libellés d'étapes, partagés E2 / E3)

- [ ] **Step 1: Écrire les tests (rouges)**

`front/src/test/rendre.tsx`, `simulerApi` devient :

```tsx
/** Remplace fetch ; le gestionnaire reçoit l'URL demandée (ex. "/api/demandes?issue=escalade") et l'init (POST). */
export function simulerApi(gestionnaire: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const espion = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => gestionnaire(String(url), init));
  vi.stubGlobal("fetch", espion);
  return espion;
}
```

`front/src/test/fixtures.ts`, `LIGNES` : ajouter aux trois lignes existantes `selectionnable: false` et le motif (`"Déjà traité"` pour KAL-26-0203 et KAL-26-0103, `"Pièces en cours d'analyse"` pour KAL-26-0101), puis deux lignes prêtes :

```ts
  {
    reference: "KAL-26-0105", nom: "Petit", prenom: "Jean", police: "CTR-778805",
    type_sinistre: "degat_des_eaux", montant_declare: 4200, statut: "prete", issue: null,
    file: null, mode_degrade: false, selectionnable: true, motif_non_selectionnable: null,
  },
  {
    reference: "KAL-26-0104", nom: "Roux", prenom: "Anne", police: "CTR-778804",
    type_sinistre: "incendie", montant_declare: 1500, statut: "prete", issue: null,
    file: null, mode_degrade: false, selectionnable: true, motif_non_selectionnable: null,
  },
```

`front/src/api.test.ts`, à la fin :

```ts
describe("envoyer", () => {
  it("POST JSON et renvoie le corps", async () => {
    const espion = simulerApi(() => json({ lot_id: 7, references: ["KAL-26-0104"] }, 202));
    await expect(envoyer("/traitements", { references: ["KAL-26-0104"] })).resolves.toEqual({
      lot_id: 7, references: ["KAL-26-0104"],
    });
    expect(espion).toHaveBeenCalledWith("/api/traitements", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: '{"references":["KAL-26-0104"]}',
    });
  });

  it("409 : ErreurApi porte les références refusées", async () => {
    simulerApi(() => json({ detail: "dossiers non lançables", references: ["KAL-26-0104"] }, 409));
    await expect(envoyer("/traitements", { references: ["KAL-26-0104"] })).rejects.toMatchObject({
      statut: 409, message: "dossiers non lançables", references: ["KAL-26-0104"],
    });
  });
});
```

(et `import { ErreurApi, envoyer, lire } from "./api";`.)

`front/src/pages/ListeDemandes.test.tsx` : ajouter `import { ErreurApi } from "@/api";` n'est pas nécessaire ; ajouter dans le `describe` :

```tsx
  it("seuls les dossiers prêts sont sélectionnables ; le motif est lisible au clavier", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    const bloquee = await screen.findByRole("checkbox", { name: "Sélectionner KAL-26-0101" });
    expect(bloquee).toBeDisabled();
    expect(bloquee).toHaveAccessibleDescription("Pièces en cours d'analyse");
    expect(bloquee).toHaveAttribute("title", "Pièces en cours d'analyse");
    expect(screen.getByRole("checkbox", { name: "Sélectionner KAL-26-0104" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Traiter la sélection (0)" })).toBeDisabled();
  });

  it("tout sélectionner coche les dossiers prêts visibles", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Tout sélectionner" }));
    expect(screen.getByRole("button", { name: "Traiter la sélection (2)" })).toBeEnabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Tout sélectionner" }));
    expect(screen.getByRole("button", { name: "Traiter la sélection (0)" })).toBeDisabled();
  });

  const lancement = (reponse: Response) =>
    simulerApi((url, init) => (init?.method === "POST" ? reponse : json(LIGNES)));

  it("1 dossier ⇒ E2", async () => {
    const espion = lancement(json({ lot_id: 7, references: ["KAL-26-0104"] }, 202));
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Sélectionner KAL-26-0104" }));
    await userEvent.click(screen.getByRole("button", { name: "Traiter la sélection (1)" }));
    await waitFor(() => expect(screen.getByTestId("url")).toHaveTextContent(/^\/demandes\/KAL-26-0104$/));
    expect(espion).toHaveBeenCalledWith("/api/traitements", expect.objectContaining({
      method: "POST", body: '{"references":["KAL-26-0104"]}',
    }));
  });

  it("N dossiers ⇒ E3", async () => {
    lancement(json({ lot_id: 7, references: ["KAL-26-0105", "KAL-26-0104"] }, 202));
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Tout sélectionner" }));
    await userEvent.click(screen.getByRole("button", { name: "Traiter la sélection (2)" }));
    await waitFor(() => expect(screen.getByTestId("url")).toHaveTextContent(/^\/lots\/7$/));
  });

  it("409 : alerte avec les dossiers refusés", async () => {
    lancement(json({ detail: "dossiers non lançables", references: ["KAL-26-0104"] }, 409));
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Sélectionner KAL-26-0104" }));
    await userEvent.click(screen.getByRole("button", { name: "Traiter la sélection (1)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Impossible de lancer le traitement : dossiers non lançables : KAL-26-0104",
    );
  });

  it("changer de filtre vide la sélection", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Sélectionner KAL-26-0104" }));
    await userEvent.selectOptions(screen.getByLabelText("Statut"), "prete");
    expect(await screen.findByRole("button", { name: "Traiter la sélection (0)" })).toBeDisabled();
  });
```

(Ajouter `waitFor` à l'import de `@testing-library/react`.)

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd front && npx vitest run src/api.test.ts src/pages/ListeDemandes.test.tsx`
Expected: FAIL (`envoyer` absent ; aucune case « Sélectionner … »).

- [ ] **Step 3: Client API et statuts**

`front/src/api.ts` :
- `StatutEtape` : `"en_attente" | "en_cours" | "termine" | "sautee" | "echec" | "repli" | "degrade"`.
- `LigneDemande` : ajouter `selectionnable: boolean; motif_non_selectionnable: string | null;`.
- ajouter après `DossierVue` :

```ts
export type LigneLot = {
  reference: string;
  nom: string | null;
  prenom: string | null;
  police: string | null;
  statut: string;
  avancement: number;
  etape_en_cours: string | null;
  duree_ms: number;
  issue: CodeIssue | null;
  file: string | null;
  mode_degrade: boolean;
  borne: string | null;
};

export type CompteursLot = { acceptee: number; refusee: number; escalade: Record<string, number>; mode_degrade: number };

export type LotVue = {
  id: number;
  debut: string;
  fin: string | null;
  avancement: number;
  compteurs: CompteursLot;
  dossiers: LigneLot[];
};

export type LotLance = { lot_id: number; references: string[] };

/** Événement SSE (spec C3-3 §3.4) : valeurs calculées par le serveur, affichées telles quelles. */
export type EvenementVue = {
  type: "etape_debut" | "sous_etape" | "etape_fin" | "dossier_fin";
  reference: string;
  etat: string | null;
  statut: "en_cours" | null;
  avancement_agent: number | null;
};
```

- `ErreurApi`, `lire`, `envoyer` :

```ts
export class ErreurApi extends Error {
  statut: number;
  references: string[];
  constructor(statut: number, message: string, references: string[] = []) {
    super(message);
    this.name = "ErreurApi";
    this.statut = statut;
    this.references = references;
  }
}

async function decoder<T>(reponse: Response): Promise<T> {
  if (!reponse.ok) {
    const corps = (await reponse.json().catch(() => null)) as { detail?: unknown; references?: unknown } | null;
    const detail = typeof corps?.detail === "string" ? corps.detail : `Erreur ${reponse.status}`;
    const references = Array.isArray(corps?.references) ? corps.references.map(String) : [];
    throw new ErreurApi(reponse.status, detail, references);
  }
  return (await reponse.json()) as T;
}

/** GET sur l'API (proxy Vite /api) ; une réponse non 2xx lève ErreurApi(statut, detail). */
export async function lire<T>(chemin: string): Promise<T> {
  return decoder<T>(await fetch(`/api${chemin}`));
}

/** POST JSON sur l'API ; 404 / 409 portent les références refusées (ErreurApi.references). */
export async function envoyer<T>(chemin: string, corps: unknown): Promise<T> {
  return decoder<T>(
    await fetch(`/api${chemin}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corps),
    }),
  );
}
```

`front/src/statuts.ts` : importer `CirclePlay` de `lucide-react` ; dans `STATUTS`, sous `admission` :

```ts
  prete: { libelle: "Prête", icone: CirclePlay, ton: "info" },
```

et à la fin du fichier :

```ts
/** Libellés des étapes de la machine (E2, E3). */
export const ETAPES: Record<string, string> = {
  eligibilite: "Éligibilité", pieces: "Pièces", estimation: "Estimation", antifraude: "Anti-fraude", decision: "Décision",
};
```

Dans `front/src/pages/Dossier.tsx`, supprimer la constante locale `ETAPES` et l'importer : `import { ETAPES } from "@/statuts";`.

- [ ] **Step 4: E1**

`front/src/pages/ListeDemandes.tsx` :

- imports :

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { envoyer, ErreurApi, lire, type LigneDemande, type LotLance } from "@/api";
```

- `const STATUTS_DEMANDE = ["admission", "prete", "en_cours", "terminee", "secours"];`
- au début du composant, après `const requete = filtres.toString();` :

```tsx
  // sélection rattachée aux filtres : en changer la vide, sans effet ni état dupliqué
  const [choix, setChoix] = useState<{ requete: string; refs: Set<string> }>({ requete, refs: new Set() });
  const selection = choix.requete === requete ? choix.refs : new Set<string>();
  const selectionner = (refs: Set<string>) => setChoix({ requete, refs });
  const navigate = useNavigate();
  const client = useQueryClient();
  const lancer = useMutation({
    mutationFn: (references: string[]) => envoyer<LotLance>("/traitements", { references }),
    onSuccess: (lot) =>
      navigate(lot.references.length === 1 ? `/demandes/${encodeURIComponent(lot.references[0])}` : `/lots/${lot.lot_id}`),
    onError: () => void client.invalidateQueries({ queryKey: ["demandes"] }),
  });
```

- le rendu du tableau devient :

```tsx
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <Button disabled={selection.size === 0 || lancer.isPending} onClick={() => lancer.mutate([...selection])}>
                <Play aria-hidden="true" />
                Traiter la sélection ({selection.size})
              </Button>
              {lancer.isError ? (
                <p role="alert" className="text-sm text-ton-danger">
                  Impossible de lancer le traitement : {messageLancement(lancer.error)}
                </p>
              ) : null}
            </div>
            <Tableau lignes={liste.data} selection={selection} selectionner={selectionner} />
          </div>
        )}
```

- fonction de module :

```tsx
const messageLancement = (erreur: Error) =>
  erreur instanceof ErreurApi && erreur.references.length > 0 ? `${erreur.message} : ${erreur.references.join(", ")}` : erreur.message;
```

- `Tableau` :

```tsx
function Tableau({ lignes, selection, selectionner }: {
  lignes: LigneDemande[];
  selection: Set<string>;
  selectionner: (refs: Set<string>) => void;
}) {
  const possibles = lignes.filter((l) => l.selectionnable).map((l) => l.reference);
  const tout = possibles.length > 0 && possibles.every((r) => selection.has(r));
  const basculer = (reference: string) => {
    const refs = new Set(selection);
    if (refs.has(reference)) refs.delete(reference);
    else refs.add(reference);
    selectionner(refs);
  };
  return (
    <div className="max-h-[70vh] overflow-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Demandes de remboursement</caption>
        <thead className="sticky top-0 bg-card text-left">
          <tr className="border-b">
            <th scope="col" className="w-10 px-3 py-2">
              <input
                type="checkbox"
                aria-label="Tout sélectionner"
                checked={tout}
                disabled={possibles.length === 0}
                onChange={() => selectionner(tout ? new Set() : new Set(possibles))}
                className="size-4"
              />
            </th>
            {["Référence", "Assuré", "Police", "Sinistre", "Montant déclaré", "Statut", "Issue", "File", "Mode"].map((titre) => (
              <th key={titre} scope="col" className="px-3 py-2 font-medium">{titre}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map((l) => (
            <tr key={l.reference} className="h-10 border-b last:border-0">
              <td className="px-3">
                <input
                  type="checkbox"
                  aria-label={`Sélectionner ${l.reference}`}
                  checked={selection.has(l.reference)}
                  disabled={!l.selectionnable}
                  title={l.motif_non_selectionnable ?? undefined}
                  aria-describedby={l.motif_non_selectionnable ? `motif-${l.reference}` : undefined}
                  onChange={() => basculer(l.reference)}
                  className="size-4"
                />
                {l.motif_non_selectionnable ? (
                  <span id={`motif-${l.reference}`} className="sr-only">{l.motif_non_selectionnable}</span>
                ) : null}
              </td>
              {/* … cellules existantes inchangées (référence → mode) … */}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

(Garder à l'identique les neuf `<td>` existants après la nouvelle cellule.)

- [ ] **Step 5: Vérifier**

Run: `cd front && npm test && npm run lint && npm run build`
Expected: PASS (dont l'axe d'E1 et le test de contraste des tons), lint et build sans erreur.

- [ ] **Step 6: Commit**

```bash
git add front/src/api.ts front/src/api.test.ts front/src/statuts.ts front/src/test/rendre.tsx front/src/test/fixtures.ts front/src/pages/ListeDemandes.tsx front/src/pages/ListeDemandes.test.tsx front/src/pages/Dossier.tsx
git commit -m "feat(front): E1 sélection des dossiers prêts et « Traiter la sélection » (C3-3)"
```

---

### Task 9: Front — hook `useFlux`, barre accessible, E2 en direct

**Files:**
- Create: `front/src/useFlux.ts`, `front/src/useFlux.test.tsx`
- Create: `front/src/components/Barre.tsx`
- Create: `front/src/test/flux.ts` (faux `EventSource`)
- Modify: `front/src/pages/Dossier.tsx`, `front/src/pages/Dossier.test.tsx`, `front/src/test/fixtures.ts`

**Interfaces:**
- Consumes: `EvenementVue`, `DossierVue` (Task 8) ; flux `/flux/demandes/{ref}` (Task 7).
- Produces (Task 10) :
  - `useFlux<T>(chemin: string | null, cle: readonly unknown[], maj: (donnees: T, evenement: EvenementVue) => T): boolean` (vrai : flux coupé, reconnexion en cours)
  - `<Barre valeur={number} libelle={string} className? />` (`role="progressbar"`)
  - `FauxEventSource` (`@/test/flux`) : `FauxEventSource.instances`, `.ouvrir()`, `.emettre(evenement)`, `.couper()`, `.ferme`

- [ ] **Step 1: Faux EventSource et tests (rouges)**

Créer `front/src/test/flux.ts` :

```ts
import { act } from "@testing-library/react";
import { vi } from "vitest";
import type { EvenementVue } from "@/api";

/** EventSource de test : on pilote l'ouverture, les événements et les coupures. */
export class FauxEventSource {
  static instances: FauxEventSource[] = [];
  url: string;
  ferme = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private ecouteurs = new Map<string, (e: MessageEvent<string>) => void>();

  constructor(url: string) {
    this.url = url;
    FauxEventSource.instances.push(this);
  }
  addEventListener(type: string, ecouteur: (e: MessageEvent<string>) => void) {
    this.ecouteurs.set(type, ecouteur);
  }
  close() {
    this.ferme = true;
  }
  ouvrir() {
    act(() => this.onopen?.());
  }
  couper() {
    act(() => this.onerror?.());
  }
  emettre(evenement: EvenementVue) {
    act(() => this.ecouteurs.get("avancement")?.(new MessageEvent("avancement", { data: JSON.stringify(evenement) })));
  }
}

export function simulerFlux() {
  FauxEventSource.instances = [];
  vi.stubGlobal("EventSource", FauxEventSource);
}
```

`front/src/test/fixtures.ts`, à la fin :

```ts
export const DOSSIER_EN_COURS: DossierVue = {
  ...DOSSIER_ACCEPTE,
  statut: "en_cours", avancement: 20, issue: null, motif: null, montant_rembourse: null,
  etapes: [
    etape("eligibilite", { vers: "pieces", resume: "Éligible" }),
    etape("pieces", { statut: "en_cours", avancement: 0, duree_ms: null, de: null, garde: null }),
    ...["estimation", "antifraude", "decision"].map((e) =>
      etape(e, { statut: "en_attente", avancement: 0, passages: 0, duree_ms: null, de: null, garde: null })),
  ],
};
```

Créer `front/src/components/Barre.tsx` :

```tsx
import { cn } from "@/lib/utils";

/** Barre de progression accessible (role progressbar, nom, valeur) ; la valeur vient du serveur. */
export function Barre({ valeur, libelle, className }: { valeur: number; libelle: string; className?: string }) {
  return (
    <div
      role="progressbar"
      aria-label={libelle}
      aria-valuenow={valeur}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-2 w-48 overflow-hidden rounded-full bg-muted", className)}
    >
      <div className="h-full bg-primary transition-[width]" style={{ width: `${valeur}%` }} />
    </div>
  );
}
```

Créer `front/src/useFlux.test.tsx` :

```tsx
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EvenementVue } from "./api";
import { FauxEventSource, simulerFlux } from "./test/flux";
import { useFlux } from "./useFlux";

type Donnees = { etat: string | null };
const CLE = ["sonde"] as const; // stable : le flux n'est pas rouvert à chaque rendu
const maj = (d: Donnees, e: EvenementVue): Donnees => ({ etat: e.etat });

function Sonde({ chemin }: { chemin: string | null }) {
  // abonnée au cache : un setQueryData du hook la fait se redessiner
  const { data } = useQuery({ queryKey: CLE, queryFn: async (): Promise<Donnees> => ({ etat: null }), staleTime: Infinity });
  const coupe = useFlux<Donnees>(chemin, CLE, maj);
  return <p>{coupe ? "coupé" : "ok"} · {data?.etat ?? "∅"}</p>;
}

const monter = (chemin: string | null) => {
  const client = new QueryClient();
  client.setQueryData(CLE, { etat: null });
  const invalider = vi.spyOn(client, "invalidateQueries");
  const rendu = render(<QueryClientProvider client={client}><Sonde chemin={chemin} /></QueryClientProvider>);
  return { client, invalider, rendu };
};

beforeEach(simulerFlux);
afterEach(() => vi.unstubAllGlobals());

const base = { reference: "KAL-26-0104", statut: "en_cours" as const, avancement_agent: 33 };

describe("useFlux", () => {
  it("ouvre /api + chemin ; relit à l'ouverture et à chaque fin d'étape", () => {
    const { invalider } = monter("/flux/demandes/KAL-26-0104");
    const source = FauxEventSource.instances[0];
    expect(source.url).toBe("/api/flux/demandes/KAL-26-0104");
    source.ouvrir();
    expect(invalider).toHaveBeenCalledTimes(1);
    source.emettre({ ...base, type: "etape_fin", etat: "pieces", statut: null, avancement_agent: 100 });
    expect(invalider).toHaveBeenCalledTimes(2);
  });

  it("sous-étape : applique les valeurs du serveur au cache", () => {
    monter("/flux/demandes/KAL-26-0104");
    FauxEventSource.instances[0].emettre({ ...base, type: "sous_etape", etat: "pieces" });
    expect(screen.getByText("ok · pieces")).toBeInTheDocument();
  });

  it("coupure : signalée jusqu'à la reconnexion", () => {
    monter("/flux/demandes/KAL-26-0104");
    const source = FauxEventSource.instances[0];
    source.couper();
    expect(screen.getByText(/^coupé/)).toBeInTheDocument();
    source.ouvrir();
    expect(screen.getByText(/^ok/)).toBeInTheDocument();
  });

  it("sans chemin : aucun flux ; démontage : flux fermé", () => {
    monter(null);
    expect(FauxEventSource.instances).toHaveLength(0);
    const { rendu } = monter("/flux/lots/7");
    rendu.unmount();
    expect(FauxEventSource.instances[0].ferme).toBe(true);
  });
});
```

`front/src/pages/Dossier.test.tsx` : importer `DOSSIER_EN_COURS` et `{ FauxEventSource, simulerFlux }` ; ajouter :

```tsx
  it("en cours : étape courante, % agent en direct, région annoncée", async () => {
    simulerFlux();
    simulerApi(() => json(DOSSIER_EN_COURS));
    ouvrir("KAL-26-0101");
    expect(await screen.findByRole("progressbar", { name: "Avancement de l'étape Pièces" })).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("Étape en cours : Pièces")).toBeInTheDocument();
    const source = FauxEventSource.instances[0];
    expect(source.url).toBe("/api/flux/demandes/KAL-26-0101");
    source.emettre({ type: "sous_etape", reference: "KAL-26-0101", etat: "pieces", statut: "en_cours", avancement_agent: 50 });
    expect(screen.getByRole("progressbar", { name: "Avancement de l'étape Pièces" })).toHaveAttribute("aria-valuenow", "50");
    source.couper();
    expect(screen.getByText("Reconnexion…")).toBeInTheDocument();
  });

  it("terminal : aucun flux", async () => {
    simulerFlux();
    simulerApi(() => json(DOSSIER_ACCEPTE));
    ouvrir("KAL-26-0101");
    await screen.findByText("Martin Claire");
    expect(FauxEventSource.instances).toHaveLength(0);
    expect(screen.getByText("Traitement terminé")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd front && npx vitest run src/useFlux.test.tsx src/pages/Dossier.test.tsx`
Expected: FAIL (`useFlux` absent).

- [ ] **Step 3: Implémenter `useFlux`**

Créer `front/src/useFlux.ts` :

```ts
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { EvenementVue } from "./api";

/**
 * Flux SSE (spec C3-3 §4.4). À l'ouverture (et à chaque reconnexion) puis à chaque fin d'étape ou de
 * dossier : relecture de l'état complet (GET, projection serveur). Début et sous-étapes : `maj` pose
 * les valeurs reçues dans le cache. `chemin` nul : aucun flux (dossier ou lot terminé).
 * `cle` et `maj` doivent être stables (useMemo, fonction de module). Renvoie vrai si le flux est coupé.
 */
export function useFlux<T>(chemin: string | null, cle: readonly unknown[], maj: (donnees: T, evenement: EvenementVue) => T): boolean {
  const client = useQueryClient();
  const [coupe, setCoupe] = useState(false);
  useEffect(() => {
    if (!chemin) return;
    const source = new EventSource(`/api${chemin}`);
    const relire = () => void client.invalidateQueries({ queryKey: cle });
    source.onopen = () => {
      setCoupe(false);
      relire();
    };
    source.onerror = () => setCoupe(true); // EventSource se reconnecte seul
    source.addEventListener("avancement", (message) => {
      const evenement = JSON.parse((message as MessageEvent<string>).data) as EvenementVue;
      if (evenement.type === "etape_fin" || evenement.type === "dossier_fin") relire();
      else client.setQueryData<T>(cle, (donnees) => (donnees === undefined ? donnees : maj(donnees, evenement)));
    });
    return () => source.close();
  }, [chemin, cle, maj, client]);
  return chemin !== null && coupe;
}
```

- [ ] **Step 4: E2**

`front/src/pages/Dossier.tsx` :

- imports : `import { type ReactNode, useMemo, useRef } from "react";` ; `import { ErreurApi, lire, type CarteAntifraude, type DossierVue, type Etape, type EvenementVue } from "@/api";` ; `import { Barre } from "@/components/Barre";` ; `import { useFlux } from "@/useFlux";`
- fonction de module :

```tsx
/** Début d'étape et sous-étapes : statut et % agent reçus du serveur, posés sur la carte concernée. */
const majDossier = (d: DossierVue, e: EvenementVue): DossierVue => ({
  ...d,
  etapes: d.etapes.map((x) =>
    x.etat === e.etat ? { ...x, statut: e.statut ?? x.statut, avancement: e.avancement_agent ?? x.avancement } : x,
  ),
});
```

- dans `Dossier()`, la clé devient stable et le flux s'ouvre tant que le dossier n'est pas à 100 % :

```tsx
  const cle = useMemo(() => ["dossier", reference], [reference]);
  const requete = useQuery({
    queryKey: cle,
    queryFn: () => lire<DossierVue>(`/demandes/${encodeURIComponent(reference)}`),
  });
  const enDirect = requete.data !== undefined && requete.data.avancement < 100;
  const coupe = useFlux(enDirect ? `/flux/demandes/${encodeURIComponent(reference)}` : null, cle, majDossier);
```

et `contenu = <Detail dossier={requete.data} coupe={coupe} />;`.

- `Detail({ dossier: d, coupe }: { dossier: DossierVue; coupe: boolean })` : remplacer la barre inline de l'en-tête par `<Barre valeur={d.avancement} libelle="Avancement du dossier" />` ; ajouter, juste après l'ouverture de `<section aria-label="En-tête du dossier" …>`, rien ; et juste avant `<ol aria-label="Étapes du traitement" …>` :

```tsx
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {enCours ? `Étape en cours : ${ETAPES[enCours.etat] ?? enCours.etat}` : d.avancement === 100 ? "Traitement terminé" : null}
        {coupe ? <span className="ml-3 font-medium text-ton-attention">Reconnexion…</span> : null}
      </p>
```

avec, en tête de `Detail` : `const enCours = d.etapes.find((e) => e.statut === "en_cours");`.

- `CarteEtape` : sous la ligne titre / statut, pour l'étape en cours :

```tsx
      {e.statut === "en_cours" ? (
        <div className="flex items-center gap-2 text-sm">
          <Barre valeur={e.avancement} libelle={`Avancement de l'étape ${ETAPES[e.etat] ?? e.etat}`} className="w-32" />
          <span className="tabular-nums">{e.avancement} %</span>
        </div>
      ) : null}
```

- [ ] **Step 5: Vérifier**

Run: `cd front && npm test && npm run lint && npm run build`
Expected: PASS (les tests E2 existants restent verts : dossiers terminaux, aucun flux).

- [ ] **Step 6: Commit**

```bash
git add front/src/useFlux.ts front/src/useFlux.test.tsx front/src/components/Barre.tsx front/src/test/flux.ts front/src/test/fixtures.ts front/src/pages/Dossier.tsx front/src/pages/Dossier.test.tsx
git commit -m "feat(front): hook useFlux (SSE) et E2 en direct : étape en cours, % agent, reconnexion (C3-3)"
```

---

### Task 10: Front — E3 « Suivi de lot »

**Files:**
- Create: `front/src/pages/Lot.tsx`, `front/src/pages/Lot.test.tsx`
- Modify: `front/src/pages/socle.tsx` (retirer `Lot`), `front/src/App.tsx`, `front/src/test/fixtures.ts`

**Interfaces:**
- Consumes: `LotVue`, `LigneLot`, `EvenementVue`, `lire`, `ErreurApi` (Task 8) ; `useFlux`, `Barre`, `FauxEventSource` (Task 9) ; `duree`, `nomComplet`, `ABSENT` (`@/format`) ; `ETAPES` (`@/statuts`).
- Produces : composant `Lot` (route `/lots/:id`).

- [ ] **Step 1: Écrire les tests (rouges)**

`front/src/test/fixtures.ts`, à la fin (importer `LotVue` en tête) :

```ts
export const LOT: LotVue = {
  id: 7, debut: "2026-10-12T09:00:00Z", fin: null, avancement: 50,
  compteurs: { acceptee: 1, refusee: 0, escalade: { cellule_fraude: 1 }, mode_degrade: 1 },
  dossiers: [
    { reference: "KAL-26-0104", nom: "Roux", prenom: "Anne", police: "CTR-778804", statut: "terminee", avancement: 100,
      etape_en_cours: null, duree_ms: 2400, issue: "acceptee", file: null, mode_degrade: false, borne: null },
    { reference: "KAL-26-0105", nom: "Petit", prenom: "Jean", police: "CTR-778805", statut: "en_cours", avancement: 40,
      etape_en_cours: "estimation", duree_ms: 900, issue: null, file: null, mode_degrade: false, borne: null },
    { reference: "KAL-26-0106", nom: "Blanc", prenom: "Lou", police: "CTR-778806", statut: "terminee", avancement: 100,
      etape_en_cours: null, duree_ms: 8100, issue: "escalade", file: "cellule_fraude", mode_degrade: true, borne: "duree_max_s" },
    { reference: "KAL-26-0107", nom: "Noir", prenom: "Max", police: "CTR-778807", statut: "en_cours", avancement: 0,
      etape_en_cours: "eligibilite", duree_ms: 0, issue: null, file: null, mode_degrade: false, borne: null },
  ],
};
```

Créer `front/src/pages/Lot.test.tsx` :

```tsx
import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { LOT } from "@/test/fixtures";
import { FauxEventSource, simulerFlux } from "@/test/flux";
import { json, rendre, simulerApi } from "@/test/rendre";
import { Lot } from "./Lot";

beforeEach(simulerFlux);
afterEach(() => vi.unstubAllGlobals());

const ouvrir = (id: string) =>
  rendre(<Routes><Route path="/lots/:id" element={<Lot />} /></Routes>, `/lots/${id}`);

describe("E3 · Suivi de lot", () => {
  it("en-tête : avancement, compteurs, durée écoulée", async () => {
    simulerApi(() => json(LOT));
    ouvrir("7");
    expect(screen.getByRole("heading", { level: 1, name: "Lot 7" })).toBeInTheDocument();
    expect(await screen.findByRole("progressbar", { name: "Avancement du lot" })).toHaveAttribute("aria-valuenow", "50");
    const entete = screen.getByRole("region", { name: "En-tête du lot" });
    expect(within(entete).getByText("Acceptées").nextElementSibling).toHaveTextContent("1");
    expect(within(entete).getByText("Escaladées").nextElementSibling).toHaveTextContent("cellule_fraude 1");
    expect(within(entete).getByText("Modes dégradés").nextElementSibling).toHaveTextContent("1");
    expect(within(entete).getByText("Durée écoulée")).toBeInTheDocument();
  });

  it("une ligne par dossier : barre, étape en cours, badges, lien vers E2", async () => {
    simulerApi(() => json(LOT));
    ouvrir("7");
    const ligne = (await screen.findByRole("link", { name: "KAL-26-0106" })).closest("tr")!;
    expect(screen.getByRole("link", { name: "KAL-26-0106" })).toHaveAttribute("href", "/demandes/KAL-26-0106");
    expect(within(ligne).getByRole("progressbar", { name: "Avancement de KAL-26-0106" })).toHaveAttribute("aria-valuenow", "100");
    expect(within(ligne).getByText("Mode dégradé")).toBeInTheDocument();
    expect(within(ligne).getByText("Borne atteinte")).toBeInTheDocument();
    const enCours = screen.getByRole("link", { name: "KAL-26-0105" }).closest("tr")!;
    expect(within(enCours).getByText("Estimation")).toBeInTheDocument();
  });

  it("une sous-étape ne met à jour que sa ligne ; fin d'étape ⇒ relecture", async () => {
    const espion = simulerApi(() => json(LOT));
    ouvrir("7");
    await screen.findByRole("link", { name: "KAL-26-0105" });
    const source = FauxEventSource.instances[0];
    expect(source.url).toBe("/api/flux/lots/7");
    source.emettre({ type: "etape_debut", reference: "KAL-26-0107", etat: "pieces", statut: "en_cours", avancement_agent: 0 });
    const ligne107 = screen.getByRole("link", { name: "KAL-26-0107" }).closest("tr")!;
    const ligne105 = screen.getByRole("link", { name: "KAL-26-0105" }).closest("tr")!;
    expect(within(ligne107).getByText("Pièces")).toBeInTheDocument();
    expect(within(ligne105).getByText("Estimation")).toBeInTheDocument();
    const appels = espion.mock.calls.length;
    source.emettre({ type: "etape_fin", reference: "KAL-26-0107", etat: "pieces", statut: null, avancement_agent: 100 });
    await vi.waitFor(() => expect(espion.mock.calls.length).toBeGreaterThan(appels));
  });

  it("lot terminé : aucun flux", async () => {
    simulerApi(() => json({ ...LOT, avancement: 100, fin: "2026-10-12T09:00:09Z" }));
    ouvrir("7");
    await screen.findByRole("link", { name: "KAL-26-0104" });
    expect(FauxEventSource.instances).toHaveLength(0);
    expect(screen.getByText("9 s")).toBeInTheDocument();
  });

  it.each([["999", 404], ["abc", 422]])("lot inconnu ou identifiant invalide (%s)", async (id, statut) => {
    simulerApi(() => json({ detail: "lot inconnu" }, statut));
    ouvrir(id);
    expect(await screen.findByText("Lot introuvable.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retour à la liste des demandes" })).toHaveAttribute("href", "/");
  });

  it("API en panne : alerte et Réessayer", async () => {
    simulerApi(() => json({ detail: "base indisponible" }, 503));
    ouvrir("7");
    expect(await screen.findByRole("alert")).toHaveTextContent("base indisponible");
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("flux coupé : « Reconnexion… »", async () => {
    simulerApi(() => json(LOT));
    ouvrir("7");
    await screen.findByRole("link", { name: "KAL-26-0105" });
    FauxEventSource.instances[0].couper();
    expect(screen.getByText("Reconnexion…")).toBeInTheDocument();
  });

  it("n'a aucune violation axe", async () => {
    simulerApi(() => json(LOT));
    const { container } = ouvrir("7");
    await screen.findByRole("link", { name: "KAL-26-0105" });
    expect(await axe(container)).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd front && npx vitest run src/pages/Lot.test.tsx`
Expected: FAIL (`Cannot find module './Lot'`).

- [ ] **Step 3: Implémenter E3**

Créer `front/src/pages/Lot.tsx` :

```tsx
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErreurApi, lire, type EvenementVue, type LigneLot, type LotVue } from "@/api";
import { Barre } from "@/components/Barre";
import { Statut } from "@/components/Statut";
import { Button } from "@/components/ui/button";
import { ABSENT, duree, nomComplet } from "@/format";
import { ETAPES } from "@/statuts";
import { useFlux } from "@/useFlux";
import { Cadre, Vide } from "./socle";

/** Début d'étape et sous-étapes : seule la ligne du dossier concerné change (barres indépendantes). */
const majLot = (lot: LotVue, e: EvenementVue): LotVue => ({
  ...lot,
  dossiers: lot.dossiers.map((d) =>
    d.reference === e.reference ? { ...d, statut: e.statut ?? d.statut, etape_en_cours: e.etat ?? d.etape_en_cours } : d,
  ),
});

export function Lot() {
  const { id = "" } = useParams();
  const zone = useRef<HTMLDivElement>(null);
  const cle = useMemo(() => ["lot", id], [id]);
  const requete = useQuery({ queryKey: cle, queryFn: () => lire<LotVue>(`/lots/${encodeURIComponent(id)}`) });
  const enDirect = requete.data !== undefined && requete.data.avancement < 100;
  const coupe = useFlux(enDirect ? `/flux/lots/${encodeURIComponent(id)}` : null, cle, majLot);

  let contenu: ReactNode;
  if (requete.isPending) {
    contenu = (
      <div>
        <p role="status" className="sr-only">Chargement du lot…</p>
        <div aria-busy="true" className="h-40 animate-pulse rounded-lg bg-muted" />
      </div>
    );
  } else if (!requete.data && requete.error instanceof ErreurApi && [404, 422].includes(requete.error.statut)) {
    contenu = (
      <Vide>
        Lot introuvable.{" "}
        <Link to="/" className="font-medium text-primary underline underline-offset-4">Retour à la liste des demandes</Link>
      </Vide>
    );
  } else if (!requete.data) {
    contenu = (
      <div role="alert" className="flex items-center gap-3 rounded-lg border border-ton-danger p-4">
        <p>Impossible de charger le lot : {requete.error?.message}</p>
        <Button variant="outline" onClick={() => {
          zone.current?.focus();
          void requete.refetch();
        }}>Réessayer</Button>
      </div>
    );
  } else {
    contenu = <Suivi lot={requete.data} coupe={coupe} />;
  }
  return (
    <Cadre titre={`Lot ${id}`}>
      <div ref={zone} tabIndex={-1} data-testid="lot" className="flex flex-col gap-3 outline-none">{contenu}</div>
    </Cadre>
  );
}

function Suivi({ lot, coupe }: { lot: LotVue; coupe: boolean }) {
  const c = lot.compteurs;
  const escalades = Object.entries(c.escalade).map(([file, n]) => `${file} ${n}`).join(" · ") || "0";
  const lignes: [string, ReactNode][] = [
    ["Acceptées", c.acceptee],
    ["Refusées", c.refusee],
    ["Escaladées", escalades],
    ["Modes dégradés", c.mode_degrade],
    ["Durée écoulée", <Ecoule debut={lot.debut} fin={lot.fin} />],
  ];
  return (
    <>
      <section aria-label="En-tête du lot" className="flex flex-col gap-3 rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Barre valeur={lot.avancement} libelle="Avancement du lot" />
          <span className="tabular-nums">{lot.avancement} %</span>
          <span>{lot.dossiers.length} dossiers</span>
          {coupe ? <span className="font-medium text-ton-attention">Reconnexion…</span> : null}
        </div>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm sm:grid-cols-[repeat(5,max-content_auto)]">
          {lignes.map(([cle, valeur]) => (
            <div key={cle} className="contents">
              <dt className="text-muted-foreground">{cle}</dt>
              <dd className="tabular-nums">{valeur}</dd>
            </div>
          ))}
        </dl>
      </section>
      <div className="overflow-auto rounded-lg border">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">Dossiers du lot</caption>
          <thead className="sticky top-0 bg-card text-left">
            <tr className="border-b">
              {["Référence", "Assuré", "Police", "Avancement", "Étape en cours", "Durée", "Issue", "Badges"].map((titre) => (
                <th key={titre} scope="col" className="px-3 py-2 font-medium">{titre}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lot.dossiers.map((d) => <LigneDossier key={d.reference} dossier={d} />)}
          </tbody>
        </table>
      </div>
    </>
  );
}

function LigneDossier({ dossier: d }: { dossier: LigneLot }) {
  return (
    <tr className="h-10 border-b last:border-0">
      <td className="px-3 font-mono">
        <Link to={`/demandes/${encodeURIComponent(d.reference)}`} className="text-primary underline-offset-4 hover:underline">
          {d.reference}
        </Link>
      </td>
      <td className="px-3">{nomComplet(d.nom, d.prenom)}</td>
      <td className="px-3 font-mono">{d.police ?? ABSENT}</td>
      <td className="px-3">
        <div className="flex items-center gap-2">
          <Barre valeur={d.avancement} libelle={`Avancement de ${d.reference}`} className="w-24" />
          <span className="tabular-nums">{d.avancement} %</span>
        </div>
      </td>
      <td className="px-3">{d.etape_en_cours ? (ETAPES[d.etape_en_cours] ?? d.etape_en_cours) : ABSENT}</td>
      <td className="px-3 tabular-nums">{duree(d.duree_ms / 1000)}</td>
      <td className="px-3">{d.issue ? <Statut code={d.issue} /> : <Statut code={d.statut} />}</td>
      <td className="px-3">
        <div className="flex flex-wrap gap-2">
          {d.mode_degrade ? <Statut code="mode_degrade" /> : null}
          {d.borne ? <Statut code="borne" /> : null}
        </div>
      </td>
    </tr>
  );
}

function Ecoule({ debut, fin }: { debut: string; fin: string | null }) {
  const [maintenant, setMaintenant] = useState(() => Date.now());
  useEffect(() => {
    if (fin) return;
    const minuterie = setInterval(() => setMaintenant(Date.now()), 1000);
    return () => clearInterval(minuterie);
  }, [fin]);
  return <>{duree(((fin ? Date.parse(fin) : maintenant) - Date.parse(debut)) / 1000)}</>;
}
```

`front/src/pages/socle.tsx` : supprimer la fonction `Lot` (et l'import `useParams` s'il n'est plus utilisé).

`front/src/App.tsx` : `import { Introuvable } from "./pages/socle";` et `import { Lot } from "./pages/Lot";`.

`front/src/App.test.tsx` : le test « /lots/1 affiche son titre » reste vert (titre rendu avant les données ; l'API simulée répond 404 ⇒ « Lot introuvable. », aucun `EventSource`).

- [ ] **Step 4: Vérifier**

Run: `cd front && npm test && npm run lint && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add front/src/pages/Lot.tsx front/src/pages/Lot.test.tsx front/src/pages/socle.tsx front/src/App.tsx front/src/test/fixtures.ts
git commit -m "feat(front): E3 suivi de lot — en-tête, une barre par dossier, mise à jour indépendante (C3-3)"
```

---

### Task 11: Bout en bout — amorçage `prete` et `traitement.spec.ts`

**Files:**
- Modify: `tests/e2e/serveur.py`
- Create: `front/e2e/traitement.spec.ts`

**Interfaces:**
- Consumes: `IngestionPostgres.charger` (Task 4) ; toute l'IHM (Tasks 8 à 10) ; flux réels (Task 7).
- Produces : `make front-e2e` couvre le lancement 1 / N et le suivi en direct.

- [ ] **Step 1: Amorcer des dossiers prêts**

`tests/e2e/serveur.py` : docstring, ajouter « NOM-04 → NOM-11 chargés en « prete » (deux jeux disjoints : un par projet Playwright, la base étant partagée) » ; après `ingestion = IngestionPostgres(connexions)` :

```python
    for i in range(4, 12):  # NOM-04 → NOM-11 : à lancer depuis E1 (traitement.spec.ts)
        ingestion.charger(scenarios[f"NOM-{i:02d}"]["demandes"][0])
```

- [ ] **Step 2: Écrire le test e2e**

Créer `front/e2e/traitement.spec.ts` :

```ts
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const sansViolation = async (page: Page) =>
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);

// base partagée par les deux projets : chacun lance ses propres dossiers prêts
const JEUX: Record<string, [string, string[]]> = {
  mobile: ["KAL-26-0104", ["KAL-26-0105", "KAL-26-0106", "KAL-26-0107"]],
  desktop: ["KAL-26-0108", ["KAL-26-0109", "KAL-26-0110", "KAL-26-0111"]],
};

test("traiter 1 dossier (E2 en direct) puis un lot (E3) ; axe dans les deux thèmes", async ({ page }, info) => {
  const [seul, lot] = JEUX[info.project.name];
  await page.emulateMedia({ colorScheme: "light" });

  await page.goto("/?statut=prete");
  await expect(page.getByRole("checkbox", { name: "Sélectionner KAL-26-0101" })).toHaveCount(0); // filtre prete
  await page.getByRole("checkbox", { name: `Sélectionner ${seul}` }).check();
  await page.getByRole("button", { name: "Traiter la sélection (1)" }).click();
  await expect(page).toHaveURL(new RegExp(`/demandes/${seul}$`));
  await expect(page.getByRole("progressbar", { name: "Avancement du dossier" })).toHaveAttribute("aria-valuenow", "100", {
    timeout: 15_000,
  });
  await expect(page.getByText("Traitement terminé")).toBeVisible();
  await sansViolation(page);

  await page.goto("/?statut=prete");
  for (const reference of lot) await page.getByRole("checkbox", { name: `Sélectionner ${reference}` }).check();
  await page.getByRole("button", { name: "Traiter la sélection (3)" }).click();
  await expect(page).toHaveURL(/\/lots\/\d+$/);
  await expect(page.getByRole("progressbar", { name: "Avancement du lot" })).toHaveAttribute("aria-valuenow", "100", {
    timeout: 20_000,
  });
  for (const reference of lot) {
    await expect(page.getByRole("progressbar", { name: `Avancement de ${reference}` })).toHaveAttribute("aria-valuenow", "100");
  }
  await sansViolation(page);
  await page.getByRole("button", { name: "Passer au thème sombre" }).click();
  await sansViolation(page);

  await page.getByRole("link", { name: lot[0] }).click();
  await expect(page.getByRole("heading", { level: 1, name: `Dossier ${lot[0]}` })).toBeVisible();

  await page.goto("/");
  await expect(page.getByRole("checkbox", { name: `Sélectionner ${seul}` })).toBeDisabled(); // déjà traité
});
```

- [ ] **Step 3: Vérifier**

Run: `make front-e2e`
Expected: PASS (fumée, lecture et traitement, projets mobile et desktop).

(Si le port 5433 appartient à la base de test d'un autre checkout : `cd front && TEST_DATABASE_URL=postgresql://kaldera:kaldera@localhost:5433/kaldera_test npx playwright test`, sans arrêter ce conteneur, et le consigner.)

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/serveur.py front/e2e/traitement.spec.ts
git commit -m "test(e2e): lancement 1 / N depuis E1, E2 en direct et E3 jusqu'à 100 % (C3-3)"
```

---

### Task 12: Cahier de recette, README, interface gestionnaire, journal, captures

**Files:**
- Modify: `docs/recette/generer_cahier_recette.py`, `docs/recette/cahier-recette.pdf` (régénéré)
- Modify: `README.md`, `docs/interface_gestionnaire.md`, `docs/journal_ajustements.md`
- Create: `docs/captures/e3-lot.png`

- [ ] **Step 1: Cahier de recette**

Dans `docs/recette/generer_cahier_recette.py` :

- `SETUP`, S-03 : attendu « Le worker démarre sans erreur et attend des pièces à analyser ; une demande soumise et analysée passe en « Prête » (elle n'est plus traitée par le worker). »
- `SETUP`, ajouter **S-06** : `(f"{m('make scenarios ARGS=--charger')}", "« 33 demandes prêtes ; déjà en base, ignorées : KAL-26-0101 » (créée par make demo).")` — formaté comme les autres cas `("S-06", …, …)`.
- `UI`, groupe « Socle du back-office », U-04 : attendu « Titres « Dossier KAL-26-0101 » et « Lot 1 » ; aucun lot encore lancé : « Lot introuvable. » et lien de retour ; adresse inconnue : « Page introuvable » et lien « Retour à la liste des demandes ». »
- Constante de module, sous `REMARQUES` (Python 3.11 : pas de guillemets imbriqués dans une expression de f-string) :

```python
PARTENAIRE_LENT = m('make ctl ARGS="lent --delai 5"')
```

- `UI` : insérer **après** le socle un groupe « Traitement depuis l'IHM (E1 → E2 / E3) » ; les cas de lecture existants sont renumérotés U-10 → U-15 (même texte ; U-05 devient U-10, etc. ; dans l'ancien U-05, remplacer « {m('make scenarios')} (une seule fois), puis ouvrir » par « Après U-07, ouvrir » et « les dossiers des scénarios » par « les dossiers traités en U-06 et U-07 ») :

```python
    ("Traitement depuis l'IHM (E1 → E2 / E3)", [
        ("U-05", "Ouvrir <b>http://localhost:5173</b>, filtrer Statut = Prête ; survoler puis "
         "atteindre au clavier la case de KAL-26-0101 (filtre Tous).",
         "33 dossiers « Prête » cochables ; KAL-26-0101 « En analyse » : case grisée, motif "
         "« Pièces en cours d'analyse » en infobulle et lu au clavier ; « Traiter la "
         "sélection (0) » inactif."),
        ("U-06", "Cocher KAL-26-0103, cliquer « Traiter la sélection (1) ».",
         "E2 « Dossier KAL-26-0103 » : l'étape en cours s'affiche « En traitement » avec son %, "
         "les cartes passent une à une ; état terminal en ≤ 8 s, avancement 100 %, « Traitement "
         "terminé » ; de retour sur E1, la case est grisée (« Déjà traité »)."),
        ("U-07", f"{PARTENAIRE_LENT} ; sur E1 (Statut = Prête), « Tout sélectionner », décocher "
         "KAL-26-0110 et KAL-26-0111 (gardés pour U-08 et U-09), puis « Traiter la sélection "
         f"(30) » ; après la fin, {m('make ctl ARGS=normal')}.",
         "E3 « Lot … » : une ligne par dossier, barres indépendantes (les dossiers sans "
         "anti-fraude finissent tout de suite, ceux qui attendent le partenaire lent ensuite) ; "
         "aucun dossier au-delà de 8 s ; compteurs (acceptées, refusées, escaladées par file, "
         "modes dégradés) et durée écoulée ; avancement 100 % à la fin ; clic sur une ligne ⇒ E2."),
        ("U-08", "Ouvrir <i>/demandes/KAL-26-0110</i> (encore « Prête ») ; arrêter <i>make api</i> "
         "5 s puis le relancer.",
         "API arrêtée : mention « Reconnexion… » ; API relancée : la mention disparaît seule et "
         "l'état est relu (pas de rechargement manuel)."),
        ("U-09", "Ouvrir E1 dans deux onglets ; cocher KAL-26-0111 dans les deux ; lancer dans "
         "l'onglet 1, puis dans l'onglet 2.",
         "Onglet 2 : alerte « Impossible de lancer le traitement : dossiers non lançables : "
         "KAL-… » ; la liste est relue ; un seul traitement (A-01 : un seul appel partenaire)."),
    ]),
```

- `ADMIN`, A-01 : « Journal : un appel au plus par dossier soumis à l'anti-fraude pendant les lancements U-06, U-07 et U-09, aucun doublon (EX-D19). » ; A-03 : `("A-03", "Relire la sortie de <i>make scenarios ARGS=--charger</i> (S-06).", "Aucune fiche : les demandes sont chargées en « prete », jamais traitées par la commande ; le traitement passe par l'IHM (U-06, U-07).")`.
- Légende : `"<b>S-01 à S-06</b>, puis <b>U-01 à U-15</b>, puis <b>A-01 à A-04</b>."`
- Section 2, introduction : `"Navigateur sur http://localhost:5173. Socle (C3-1), lecture E1 / E2 (C3-2), traitement depuis l'IHM, temps réel et E3 (C3-3) livrés ; la reprise d'étape et les notes s'ajoutent avec C3-4."`
- Section 3 : `"La reprise d'étape (C3-4) n'est pas encore livrée : ces contrôles se font par make."`
- « Version testée » : branche `feature/chantier3-c3-3-traitement` ; « Durée estimée » : `"40 minutes environ"`.
- `STATUTS: dict[str, str] = {}` et `REMARQUES: dict[str, str] = {}` (renseignés en Task 14).

Run: `uv run python docs/recette/generer_cahier_recette.py`
Expected: chemin du PDF affiché, sans erreur.

- [ ] **Step 2: `docs/interface_gestionnaire.md`**

- En-tête : ajouter « spec C3-3 : `docs/superpowers/specs/2026-10-12-c3-3-traitement-temps-reel-design.md` ».
- §1 Écrans : E1 « … ; sélection des dossiers prêts et « Traiter la sélection » (1 ⇒ E2, N ⇒ E3) » (livré C3-2 / C3-3) ; E2 « … ; en direct (étape en cours, % agent) » ; `/lots/:id` « E3 · Suivi de lot : avancement, compteurs, une barre par dossier, en direct » livré **C3-3**.
- Nouvelle sous-section « Cycle de vie » : `admission → prete → en_cours → terminee | secours` ; le worker s'arrête à `prete` ; tableau des motifs de non-sélection (Global Constraints).
- §2 API : `GET /demandes` (statut `prete` ajouté ; champs `selectionnable`, `motif_non_selectionnable`) ; nouvelles routes :

````markdown
### `POST /traitements`

Corps `{"references": ["KAL-26-0104", "KAL-26-0105"]}` (non vide, sans doublon). Tout ou rien :

| Code | Corps |
|---|---|
| 202 | `{"lot_id": 7, "references": [...]}` ; le lot est traité en tâche de fond (`traiter_lot`) |
| 404 | `{"detail": "demande inconnue", "references": [...]}` |
| 409 | `{"detail": "dossiers non lançables", "references": [...]}` (dossier non `prete`) |
| 422 | liste vide, doublon, référence mal formée |

### `GET /lots/{id}`

`LotVue` : `id`, `debut`, `fin` (dernière mise à jour quand tous les dossiers sont clos), `avancement`
(clos / total), `compteurs` (`acceptee`, `refusee`, `escalade` par file, `mode_degrade`), `dossiers`
(`reference`, `nom`, `prenom`, `police`, `statut`, `avancement`, `etape_en_cours`, `duree_ms`, `issue`,
`file`, `mode_degrade`, `borne`). 404 `lot inconnu`.

### Flux SSE : `GET /flux/demandes/{ref}` · `GET /flux/lots/{id}`

`text/event-stream` ; `: ouvert` à la connexion, `: ping` toutes les 15 s, puis un message par
événement du dossier (ou des dossiers du lot) :

```
event: avancement
data: {"type": "sous_etape", "reference": "KAL-26-0105", "etat": "estimation", "statut": "en_cours", "avancement_agent": 50}
```

`type` : `etape_debut` (% 0), `sous_etape` (% agent), `etape_fin` (100), `dossier_fin`. Source :
`pg_notify('kaldera_avancement', …)` émis par l'orchestrateur, l'agent et le reaper (best effort). À
l'ouverture et à chaque `etape_fin` / `dossier_fin`, l'IHM relit l'état complet (`GET`).
````

- Règles : ajouter « **% agent** » (formule des Global Constraints) et « **% lot** » (dossiers clos / dossiers).
- §3 Lancer en local : remplacer `make demo && make scenarios` par `make demo && make scenarios ARGS=--charger   # KAL-26-0101 en admission + 33 dossiers prêts` et ajouter `make worker` (analyse, admission en « prete ») ; mention « lancer le traitement depuis E1 ».

- [ ] **Step 3: README**

- Section IHM : titre « (chantier 3 ; socle C3-1, lecture C3-2, traitement, temps réel et E3 C3-3 livrés ; reprise à venir) » ; bloc de lancement : `make scenarios ARGS=--charger  # dossiers prêts, lancés depuis E1` ; paragraphe : « E1 : cocher des dossiers « Prête » puis « Traiter la sélection » (1 ⇒ E2, plusieurs ⇒ E3). E2 et E3 se mettent à jour en direct (SSE, `LISTEN/NOTIFY`) ; E3 montre une barre par dossier. » ; tableau de captures étendu à `| E3 · Lot |` avec `![E3, suivi de lot](docs/captures/e3-lot.png)`.
- Épreuve de l'ingestion : remplacer `make api &` par `make api-epreuve &   # API avec le partenaire indisponible : elle exécute le traitement` et la ligne seed par `make seed             # dépose le manifeste, attend « prete », lance un lot (POST /traitements), attend le traitement`.
- `Useful commands` : `make front-e2e  # Playwright : socle, lecture E1 / E2, traitement 1 / N et E3 (thème, clavier, axe)`.
- `Layout` : `traitements.py` (tâche de fond du lot), `lots_postgres.py` (lots), `flux.py` (SSE).

- [ ] **Step 4: Journal des ajustements**

Ajouter à la fin du tableau de `docs/journal_ajustements.md` :

```markdown
| 2026-10-12 | lancement depuis l'IHM (C3-3) | le worker traitait chaque demande dès l'admission : rien à sélectionner dans E1 | EX-D45 | statut `prete` (migration 006) : le worker s'arrête à l'admission ; `POST /traitements` lance un lot en tâche de fond ; `make scenarios ARGS=--charger`, seed et épreuve lancent par l'API (`make api-epreuve`) | admission ⇒ traitée → admission ⇒ prête ⇒ lancée par le gestionnaire |
| 2026-10-12 | lot de 34 dossiers (`test_chaine_complete_fakevlm`) | snapshots et signaux partagent un pool de 10 connexions | aucune « persistance coupée » | signaux best effort (un événement perdu est rattrapé par la relecture `GET`) ; mesure : remplir avec le résultat observé en Task 14 | — |
```

- [ ] **Step 5: Capture E3**

Base de recette préparée (`make recette`, `make scenarios ARGS=--charger`), `make api`, `make front` ; lancer un lot de 3 dossiers depuis E1 ; capturer E3 terminé en clair, 1280 × 800, avec un script Playwright jetable **hors du dépôt** (dans `$CLAUDE_JOB_DIR/tmp` ou `/tmp`) : `page.goto("http://localhost:5173/lots/<id>")`, attendre `aria-valuenow="100"` sur « Avancement du lot », `page.screenshot({ path: "docs/captures/e3-lot.png" })`. Arrêter les processus lancés.

- [ ] **Step 6: Commit**

```bash
git add docs/recette/generer_cahier_recette.py docs/recette/cahier-recette.pdf docs/interface_gestionnaire.md README.md docs/journal_ajustements.md docs/captures/e3-lot.png
git commit -m "docs: recette (traitement U-05 → U-09), API de traitement et SSE, README, journal, capture E3 (C3-3)"
```

---

### Task 13: Dossier de conception — page 2.10

**Files:**
- Create: `docs/conception/pages/299b-ihm-traitement.html`
- Modify: `docs/conception/pages/020-sommaire.html`, `docs/conception/pages/440-glossaire-5.html`, `docs/conception/pages/299-ihm-lecture.html` (note « en_cours n'est jamais produit ici » → « en_cours : C3-3, page 2.10 »)
- Regenerate: `docs/conception/dossier-conception.pdf` (ignoré par git) → copie à la racine du brief

- [ ] **Step 1: Nouvelle page**

Créer `docs/conception/pages/299b-ihm-traitement.html` sur le modèle de `299-ihm-lecture.html` (`<section class="page" id="ihm-traitement">`, style local des `.tableau`, `surtitre`, `h2.titre` avec `<span class="num">2.10</span>`, `chapo`, `tableau`, `grille-3`, `note petit`) :

- surtitre « Livrable 2 · IHM gestionnaire » ; titre « 2.10 📡 IHM gestionnaire · traitement, temps réel et suivi de lot (E3) » ;
- chapo : le gestionnaire sélectionne des dossiers prêts et lance leur traitement (1 ⇒ E2, N ⇒ E3) ; l'avancement arrive en direct, jusqu'aux sous-étapes d'agent ; l'IHM n'interprète rien (EX-D44, EX-D45, EX-D46) ;
- tableau « Cycle de vie » : `admission` (pièces en analyse, worker) → `prete` (admise, attend le gestionnaire) → `en_cours` (`POST /traitements`, compare-and-set tout ou rien) → `terminee` / `secours` ; colonne « Sélectionnable » (oui seulement pour `prete`) et « Motif » ;
- schéma SVG en ligne (ou tableau si la place manque) de la séquence : E1 → `POST /traitements` → `lots` + `en_cours` (une transaction) → `BackgroundTask` → `traiter_lot` → orchestrateur / agent → `pg_notify('kaldera_avancement')` → `LISTEN` (route SSE) → `EventSource` → `GET` à l'ouverture et à chaque fin d'étape ;
- tableau « Événements » : `etape_debut`, `sous_etape` (vue · tour · outil · garde-fou), `etape_fin` (après le snapshot), `dossier_fin` (orchestrateur, reaper) ; charge utile minimale, sans donnée personnelle ;
- `grille-3` de notes : « % agent / dossier / lot » (formules) ; « Robustesse » (signaux best effort, jamais bloquants ; relecture à l'ouverture et à la reconnexion ; reaper si l'API meurt) ; « Tables » (`lots`, `lot_demandes`, statut `prete` : migration 006).

- [ ] **Step 2: Sommaire, glossaire, page 2.9**

- `020-sommaire.html`, entrée 2 : après « IHM gestionnaire : lecture E1 / E2 (2.9) », ajouter ` · <span class="neuf">IHM gestionnaire : traitement, temps réel et E3 (2.10)</span>` ; retirer la classe `neuf` de l'entrée 2.9 ; chapo : « Version alignée sur le code (chantier 3, sous-projet C3-3). »
- `440-glossaire-5.html` : ajouter trois lignes (définitions courtes ; raccourcir si la page déborde) :
  - « Lot » — Ensemble de dossiers lancés ensemble depuis E1 (`POST /traitements`), suivi par E3 ; un dossier seul forme un lot d'un dossier.
  - « SSE (Server-Sent Events) » — Flux HTTP à sens unique serveur → navigateur (`EventSource`) ; ≈ SignalR en sens unique.
  - « LISTEN / NOTIFY » — Messagerie de PostgreSQL : `pg_notify` publie sur un canal, `LISTEN` y abonne une connexion.
- `299-ihm-lecture.html`, note « Avancement » : remplacer « <code>en_cours</code> n'est jamais produit ici. » par « <code>en_cours</code> : voir 2.10 (temps réel). »

- [ ] **Step 3: Rendre, contrôler, copier**

Run: `make dossier`
Expected : « 49 fragments → …/dossier-conception.pdf », aucun avertissement de débordement (sinon raccourcir le texte, jamais la police).

```bash
cp docs/conception/dossier-conception.pdf /Volumes/CodeSource/myRepos/simplon/briefs/kaldera-agents/dossier-conception.pdf
.venv/bin/python -I -c "import re; from pypdf import PdfReader; r=PdfReader('/Volumes/CodeSource/myRepos/simplon/briefs/kaldera-agents/dossier-conception.pdf'); t=' '.join(p.extract_text() or '' for p in r.pages); print(len(r.pages), 'pages', 'suivi de lot' in t.lower(), 'LISTEN' in t, re.findall(r'espace assur|agent de relance|UI1', t, re.I) or 'OK')"
```

Expected : `49 pages True True OK`. (Depuis le worktree, `.venv` est celui du checkout principal si le worktree n'a pas le sien : `../../../.venv/bin/python`.)

- [ ] **Step 4: Commit**

```bash
git add docs/conception/pages
git commit -m "docs(conception): page 2.10 IHM gestionnaire — traitement, temps réel et E3 ; sommaire et glossaire"
```

---

### Task 14: Vérification finale et déroulé de la recette

**Files:**
- Modify: `docs/recette/generer_cahier_recette.py` (`STATUTS`, `REMARQUES`), `docs/recette/cahier-recette.pdf`
- Modify: `docs/journal_ajustements.md` (mesure du lot, ligne ajoutée en Task 12)

- [ ] **Step 1: Toutes les suites**

Run: `make test && make lint && make typecheck && make test-integration`
Expected : vert.

Run: `cd front && npm test && npm run lint && npm run build && cd .. && make front-e2e`
Expected : vert.

(Si le port 5433 est déjà tenu par la base de test d'un autre checkout, lancer les moitiés non-docker contre cette base — `TEST_DATABASE_URL=postgresql://kaldera:kaldera@localhost:5433/kaldera_test uv run pytest -m integration -v` et `cd front && TEST_DATABASE_URL=… npx playwright test` — sans jamais arrêter ni supprimer ce conteneur, et le consigner.)

- [ ] **Step 2: Aucune fuite, aucune couleur en dur, aucune règle dans le front**

Run: `grep -rn -E 'iban|telephone|email' src/kaldera/vue_gestionnaire.py src/kaldera/flux.py front/src --include=*.ts --include=*.tsx --include=*.py | grep -v test`
Expected : aucune sortie hors docstring de `vue_gestionnaire.py`.

Run: `grep -rn -E 'bg-\[#|text-\[#|\.dark\b' front/src`
Expected : aucune sortie.

Run: `grep -rn -E '"(admission|prete|en_cours|terminee|secours)"' front/src --include=*.tsx | grep -v test`
Expected : seulement la liste `STATUTS_DEMANDE` du filtre d'E1 (aucune décision prise sur un statut dans un écran : sélectionnabilité, % et clôture viennent du serveur).

- [ ] **Step 3: Dérouler la recette**

Suivre `docs/recette/cahier-recette.pdf` : S-01 → S-06, U-01 → U-15, A-01 → A-04 (`KALDERA_DATABASE_URL=postgresql://kaldera:kaldera@localhost:5433/kaldera_test` en ligne de commande si aucun `.env` ; ne jamais créer de `.env`). Sans profil VLM Azure, S-03 est `NT` (« pas de profil VLM Azure sur ce poste »). U-01 → U-15 : navigateur headless (Playwright, script jetable hors du dépôt) contre `make front` + `make api`, en vérifiant chaque résultat attendu ; U-07 mesure la durée de chaque dossier (≤ 8 s) et l'indépendance des barres ; U-08 arrête et relance réellement l'API. Un cas adapté porte une remarque ; un cas non exécutable tel qu'écrit est `NT` avec sa remarque. Arrêter tout processus lancé ; terminer par `make recette-reset` (seulement si la base n'appartient pas à un autre checkout ; sinon A-04 `NT` avec remarque).

- [ ] **Step 4: Renseigner et régénérer**

Renseigner `STATUTS` et `REMARQUES` (S-01 → A-04) selon le déroulé ; compléter la colonne « Avant → après » de la ligne « lot de 34 dossiers » du journal avec la mesure observée (durée du lot, aucune « persistance coupée » ou leur nombre). Puis :

Run: `uv run python docs/recette/generer_cahier_recette.py`

- [ ] **Step 5: Commit**

```bash
git add docs/recette/generer_cahier_recette.py docs/recette/cahier-recette.pdf docs/journal_ajustements.md
git commit -m "docs(recette): statuts du déroulé C3-3"
```
