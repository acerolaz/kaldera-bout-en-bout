# C3-0 · Retrait de l'espace assuré — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retirer entièrement l'espace assuré (UI1) — front, API `/assure`, agent de relance, tables — et remettre la recette, la doc et le dossier de conception à l'état livré.

**Architecture:** Retrait mécanique en couches : renommage de l'utilitaire métier gardé, débranchement du back-end, migration `005` qui supprime les tables, front réduit à une page d'attente, puis documents (cahier de recette, README, journal, dossier de conception PDF). Aucune fonctionnalité du back-office n'est ajoutée.

**Tech Stack:** Python 3 / FastAPI / psycopg 3 / pytest / ruff / mypy (uv) ; React 19 / Vite / Vitest / vitest-axe / Playwright (npm) ; reportlab (cahier de recette) ; Chromium via `docs/conception/rendre.cjs` (dossier).

**Spec:** `docs/superpowers/specs/2026-10-11-c3-0-retrait-espace-assure-design.md`

Toutes les commandes se lancent depuis `src/kaldera-bout-en-bout/` (racine du dépôt), sauf mention `cd front`.

## Global Constraints

- Branche : `feature/chantier3-c3-0-retrait` (déjà créée, spec commitée).
- Migration : `005_retrait_assure.sql` ; `004_assure.sql` **intacte** ; `DROP TABLE IF EXISTS evenements_assure, demandes_assure, utilisateurs;`
- Colonnes `demandes.cree_le` et `pieces.depose_le` **conservées**.
- **Deux « relances »** : seul l'agent de relance (`relance.py`, rôle LLM `relance`, `KALDERA_RELANCE__*`) part. La relance métier (`pieces.relance`, `depot_pour`, borne `relances_pieces_max`) reste intacte.
- La **clé de données** `espace_assure` des demandes (présente dans `eval/scenarios.jsonl`, 28 lignes, ressource fournie) **ne change pas** : seul le *module* Python `espace_assure.py` est renommé `depots_assure.py`.
- Les routes de dépôt de `api.py` (`POST /demandes`, `POST /demandes/{ref}/pieces`, `POST /demandes/{ref}/soumettre`, `GET /demandes/{ref}`) restent.
- Dossier de démo : `tools/demo.py`, KAL-26-0101, **sans compte** ; message « Demande KAL-26-0101 prête ».
- Page d'attente : titre exact « Kaldera · back-office gestionnaire », texte « En construction (chantier 3). »
- Commentaires et textes en français, style du code environnant (docstrings courtes, pas de commentaires superflus).
- Commits terminés par `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

1. **Base locale déjà migrée en `004`** (cas de l'utilisateur) : `make api` sur une base existante doit appliquer `005` sans erreur et sans `recette-reset` → test d'intégration Task 3 (tables absentes après migrations, migrations rejouables).
2. **Un client qui appelle encore `/assure/...`** (ancien onglet, favori) : l'API répond 404, pas 500 ni 503 → test Task 2 (`aucune route /assure`).
3. **`.env` existant contenant encore `KALDERA_RELANCE__*` / `KALDERA_SESSION_SECRET`** : le démarrage ne doit pas échouer (`extra="ignore"`) → test Task 2 (`ConfigAgents` chargé avec `KALDERA_RELANCE__MODELE` présent).
4. **Relance métier cassée par erreur** (confusion des deux « relances ») : un dossier avec dépôt de complément doit toujours être traité → couvert par les tests existants de l'agent pièces et `test_ports.py`, qui lisent la clé `espace_assure` (relancés à chaque tâche) ; Task 1 vérifie que cette clé de données reste intacte dans les scénarios.
5. **`make recette` relancé deux fois sans reset** : `tools.demo` refuse proprement (« base déjà préparée »), sans trace Python → test Task 2 (`preparer` renvoie `False` la seconde fois).

---

### Task 1: Renommer `espace_assure.py` en `depots_assure.py`

**Files:**
- Rename: `src/kaldera/espace_assure.py` → `src/kaldera/depots_assure.py`
- Modify: `src/kaldera/agents.py:13,63,69`, `src/kaldera/agents_llm.py:23,105`
- Modify: `tests/unit/test_ports.py:8`, `tests/unit/test_agents_llm.py:13,253,261`

**Interfaces:**
- Produces: `kaldera.depots_assure.depot_pour(depots: list[dict[str, Any]], type_piece: str, tentative: int) -> dict[str, Any] | None` (signature inchangée).

- [ ] **Step 1: Renommer le module**

```bash
git mv src/kaldera/espace_assure.py src/kaldera/depots_assure.py
```

Remplacer la docstring de tête de `src/kaldera/depots_assure.py` par :

```python
"""Dépôts de complément de l'assuré (relance métier, simulation).

Les dépôts qu'un assuré effectue en réponse aux demandes de complément sont lus par le port
``DepotPieces``, dans l'ordre où il les effectue. Un assuré qui n'a rien de nouveau à transmettre
re-soumet son dernier dépôt pour le type de pièce demandé. La clé de données reste
``espace_assure`` (format des scénarios fournis).
"""
```

- [ ] **Step 2: Adapter les imports (module seulement, jamais la clé de données)**

Dans `src/kaldera/agents.py` et `src/kaldera/agents_llm.py` :
- `from . import espace_assure, regles` → `from . import depots_assure, regles`
- `espace_assure.depot_pour(` → `depots_assure.depot_pour(`

Dans `tests/unit/test_ports.py` : `from kaldera.espace_assure import depot_pour` → `from kaldera.depots_assure import depot_pour`. **Ne pas toucher** `DEMANDE["espace_assure"]` ni la clé `"espace_assure": {` (données).

Dans `tests/unit/test_agents_llm.py` :
- `from kaldera import espace_assure` → `from kaldera import depots_assure`
- ligne 253 : `reel, appels = espace_assure.depot_pour, []` → `reel, appels = depots_assure.depot_pour, []`
- ligne 261 : `monkeypatch.setattr(espace_assure, "depot_pour", casse)` → `monkeypatch.setattr(depots_assure, "depot_pour", casse)`

- [ ] **Step 3: Vérifier qu'aucun import de l'ancien module ne reste**

Run: `grep -rn -E 'import espace_assure|espace_assure\.depot_pour|from kaldera\.espace_assure|from \. import .*espace_assure' src tests tools`
Expected: aucune sortie.

Run: `grep -c '"espace_assure"' eval/scenarios.jsonl`
Expected: `28` (clé de données intacte).

- [ ] **Step 4: Lancer les tests unitaires, lint, types**

Run: `make test && make lint && make typecheck`
Expected: tout vert (même nombre de tests qu'avant le renommage).

- [ ] **Step 5: Commit**

```bash
git add -A src/kaldera tests/unit
git commit -m "refactor: espace_assure.py devient depots_assure.py (relance métier, pas d'UI)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Débrancher et supprimer le back-end de l'espace assuré

**Files:**
- Delete: `src/kaldera/api_assure.py`, `src/kaldera/auth.py`, `src/kaldera/relance.py`, `src/kaldera/vue_assure.py`, `src/kaldera/assure_postgres.py`, `src/kaldera/evenements.py`
- Delete: `tests/unit/test_auth.py`, `tests/unit/test_relance.py`, `tests/unit/test_vue_assure.py`, `tests/unit/test_confidentialite_assure.py`, `tests/integration/test_api_assure.py`, `tests/integration/test_assure_postgres.py`, `tests/integration/test_evenements.py`
- Rename: `tools/demo_assure.py` → `tools/demo.py` ; `tests/integration/test_demo_assure.py` → `tests/integration/test_demo.py`
- Modify: `src/kaldera/api.py:1-38`, `src/kaldera/worker.py:15-16,88-105,149-166`, `src/kaldera/reaper.py:13-17,72-76,98`, `src/kaldera/llm.py:159`
- Modify: `tests/e2e/serveur.py`, `Makefile`, `.env.example:29-39`, `pyproject.toml` (+ `uv.lock`)
- Create: `tests/unit/test_retrait_assure.py`

**Interfaces:**
- Consumes: `kaldera.depots_assure` (Task 1).
- Produces: `tools.demo.preparer(connexions: ConnectionPool, reference: str = "KAL-26-0101", manifeste: list[dict[str, Any]] | None = None) -> bool` ; cible `make demo`.

- [ ] **Step 1: Écrire les tests de garde du retrait (rouges)**

Créer `tests/unit/test_retrait_assure.py` :

```python
"""Unitaires — l'espace assuré (UI1) est retiré : plus de route /assure, plus d'agent de relance."""

from __future__ import annotations

import pytest

from kaldera.api import app
from kaldera.llm import ConfigAgents


def test_aucune_route_assure_les_routes_de_depot_restent() -> None:
    chemins = {getattr(route, "path", "") for route in app.routes}
    assert not any(chemin.startswith("/assure") for chemin in chemins)
    assert {"/demandes", "/demandes/{reference}/pieces", "/demandes/{reference}"} <= chemins


def test_aucun_role_llm_relance() -> None:
    assert "relance" not in ConfigAgents.model_fields


def test_un_ancien_env_avec_relance_et_session_ne_bloque_pas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KALDERA_RELANCE__MODELE", "Kimi-K2.6")
    monkeypatch.setenv("KALDERA_SESSION_SECRET", "ancien")
    config = ConfigAgents(_env_file=None)
    assert not hasattr(config, "relance")
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/unit/test_retrait_assure.py -v`
Expected: FAIL sur `test_aucune_route_assure_les_routes_de_depot_restent` (routes `/assure/...` présentes), `test_aucun_role_llm_relance` et `test_un_ancien_env_avec_relance_et_session_ne_bloque_pas` (`relance` est un champ).

- [ ] **Step 3: `api.py` — plus de routeur assuré**

Dans `src/kaldera/api.py`, supprimer :
- `import logging`, `from collections.abc import AsyncIterator`, `from contextlib import asynccontextmanager` ;
- `from .api_assure import router as routeur_assure` et `from .auth import ConfigAssure` ;
- `LOGGER = logging.getLogger(__name__)` ;
- la fonction `_cycle` entière et la ligne `app.include_router(routeur_assure)`.

Remplacer la création de l'application par :

```python
app = FastAPI(title="Kaldera — dépôt des demandes et des pièces")
```

- [ ] **Step 4: `worker.py` — plus de publication vers l'assuré**

Dans `src/kaldera/worker.py` :
- supprimer `from . import evenements, relance` et `from .assure_postgres import DepotAssure` ;
- supprimer les deux dernières lignes du traitement d'une tâche :
  ```python
      if tache.tache == "analyser_piece":
          _publier_analyse(ingestion, tache, config)
  ```
- supprimer la fonction `_publier_analyse` entière ;
- remplacer `_admettre` par :

```python
def _admettre(
    ingestion: IngestionPostgres, reference: str, disjoncteur: Disjoncteur
) -> None:
    demande = ingestion.admettre(reference)
    if demande is None:
        return
    demande = demande_niveau_1(demande, ingestion.contrat(demande["contrat"]["numero"]))
    Orchestrateur(
        depot=DepotPostgres(ingestion.connexions),
        snapshots=SnapshotsPostgres(ingestion.connexions),
        disjoncteur=disjoncteur,
    ).traiter(demande)
```

Si ruff signale ensuite un paramètre ou import devenu inutile (ex. `config` dans la fonction qui appelait `_publier_analyse`), le retirer **seulement** s'il n'est plus utilisé ailleurs dans la fonction (`config.delai_analyse_s` y reste utilisé : ne pas le retirer).

- [ ] **Step 5: `reaper.py` — plus de publication du verdict**

Dans `src/kaldera/reaper.py` :
- supprimer `from psycopg_pool import ConnectionPool`, `from . import evenements`, `from .assure_postgres import DepotAssure` ;
- supprimer la fonction `publier` entière ;
- dans `main()`, supprimer la ligne `publier(snapshots.connexions, fiches)`.

- [ ] **Step 6: `llm.py` — plus de rôle `relance`**

Dans `src/kaldera/llm.py`, supprimer la ligne :

```python
    relance: ConfigLLM | None = None  # agent de relance de l'espace assuré (UI1), hors moteur
```

- [ ] **Step 7: Supprimer les modules et leurs tests**

```bash
git rm src/kaldera/api_assure.py src/kaldera/auth.py src/kaldera/relance.py \
  src/kaldera/vue_assure.py src/kaldera/assure_postgres.py src/kaldera/evenements.py \
  tests/unit/test_auth.py tests/unit/test_relance.py tests/unit/test_vue_assure.py \
  tests/unit/test_confidentialite_assure.py tests/integration/test_api_assure.py \
  tests/integration/test_assure_postgres.py tests/integration/test_evenements.py
```

- [ ] **Step 8: Dossier de démo sans compte**

```bash
git mv tools/demo_assure.py tools/demo.py
git mv tests/integration/test_demo_assure.py tests/integration/test_demo.py
```

Remplacer le contenu de `tools/demo.py` par :

```python
"""Dossier de démonstration : une demande et son contrat, déposés comme par l'API.

Usage : make demo (KALDERA_DATABASE_URL requis ; lancer ensuite make api, make worker).
Demande KAL-26-0101 (NOM-01) tirée du manifeste.
"""

from __future__ import annotations

from typing import Any

from psycopg_pool import ConnectionPool

from kaldera.ingestion import controler_fichier
from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.postgres import ConfigBase, pool
from tools.seed import MANIFESTE, lire_manifeste


def preparer(
    connexions: ConnectionPool,
    reference: str = "KAL-26-0101",
    manifeste: list[dict[str, Any]] | None = None,
) -> bool:
    """Crée la demande et dépose son contrat ; faux si la demande existe déjà."""
    lignes = [x for x in (manifeste or lire_manifeste()) if x["reference"] == reference]
    demande = next(x["json"] for x in lignes if x["role"] == "demande")
    contrat = next(x for x in lignes if x["role"] == "contrat")
    # le contrat est lu et contrôlé avant toute écriture (pool en autocommit : pas de rollback)
    octets = (MANIFESTE.parent / contrat["fichier"]).read_bytes()
    mime, sha256 = controler_fichier(octets, 10, contrat=True)
    ingestion = IngestionPostgres(connexions)
    if not ingestion.creer_demande(demande):
        return False
    ingestion.deposer_contrat(reference, octets, mime, sha256)
    return True


def main() -> None:
    url = ConfigBase().database_url
    if not url:
        raise SystemExit("KALDERA_DATABASE_URL absente")
    if not preparer(pool(url)):
        raise SystemExit("KAL-26-0101 existe déjà : base déjà préparée")
    print("Demande KAL-26-0101 prête")


if __name__ == "__main__":
    main()
```

Remplacer le contenu de `tests/integration/test_demo.py` par :

```python
"""Intégration — démonstration : une demande et son contrat en analyse, sans compte."""

from __future__ import annotations

from typing import Any

import pytest

from tools.demo import preparer
from tools.seed import lire_manifeste

pytestmark = pytest.mark.integration


def test_preparer_puis_refuser_une_seconde_fois(base: Any) -> None:
    assert preparer(base) is True
    with base.connection() as conn:
        (taches,) = conn.execute(
            "SELECT count(*) FROM file_ingestion WHERE tache = 'extraire_contrat'"
        ).fetchone()
    assert taches == 1 and preparer(base) is False


def test_contrat_illisible_n_ecrit_rien(base: Any) -> None:
    abime = [
        {**x, "fichier": "KAL-26-0101/absent.pdf"} if x["role"] == "contrat" else x
        for x in lire_manifeste()
    ]
    with pytest.raises(FileNotFoundError):
        preparer(base, manifeste=abime)
    with base.connection() as conn:
        (demandes,) = conn.execute("SELECT count(*) FROM demandes").fetchone()
    assert demandes == 0 and preparer(base) is True
```

- [ ] **Step 9: Serveur e2e, Makefile, `.env.example`, dépendances**

`tests/e2e/serveur.py` :
- docstring, ligne 3 : `préparée (tools.demo_assure)` → `préparée (tools.demo)` ;
- regex : `KALDERA_(PIECES|ESTIMATION|ANTIFRAUDE|DECISION|RELANCE|INGESTION)__` → `KALDERA_(PIECES|ESTIMATION|ANTIFRAUDE|DECISION|INGESTION)__` ;
- dans `os.environ.update(...)`, supprimer les lignes `KALDERA_SESSION_SECRET=...`, `KALDERA_COOKIE_SECURE="false",`, `KALDERA_FRONT_ORIGIN="http://localhost:5173",` ;
- `from tools.demo_assure import preparer` → `from tools.demo import preparer`.
(Le `TRUNCATE` est modifié en Task 3, avec la migration.)

`Makefile` :
- dans `.PHONY`, `demo-assure` → `demo` ;
- la cible devient :
  ```makefile
  demo:
  	uv run python -m tools.demo
  ```
- dans `recette:`, `uv run python -m tools.demo_assure` → `uv run python -m tools.demo`.

`.env.example` : supprimer le bloc des lignes 29 à 39 (commentaire « Agent de relance… », 4 variables `KALDERA_RELANCE__*`, ligne vide, commentaire « Espace assuré (UI1)… », `KALDERA_SESSION_SECRET=`, `KALDERA_FRONT_ORIGIN=…`, `KALDERA_COOKIE_SECURE=false`). Garder une seule ligne vide entre le bloc précédent et le suivant.

Dépendances (utilisées seulement par `auth.py`) :

```bash
uv remove argon2-cffi itsdangerous
```

- [ ] **Step 10: Les tests de garde passent, plus aucune référence**

Run: `uv run pytest tests/unit/test_retrait_assure.py -v`
Expected: 3 PASS.

Run: `grep -rn -E 'api_assure|kaldera\.auth|from \. import .*\bauth\b|from \.auth|vue_assure|assure_postgres|kaldera\.evenements|from \. import .*evenements|from \.evenements|demo_assure|relance\.py|import relance|ConfigAssure|SESSION_SECRET|COOKIE_SECURE|FRONT_ORIGIN|KALDERA_RELANCE|argon2|itsdangerous' src tests tools Makefile .env.example pyproject.toml`
Expected: aucune sortie.

- [ ] **Step 11: Suite complète**

Run: `make test && make lint && make typecheck`
Expected: vert.

Run: `make test-integration`
Expected: vert (l'ancien `TRUNCATE` vise encore des tables qui existent : la migration 005 n'existe pas encore).

- [ ] **Step 12: Commit**

```bash
git add -A src tests tools Makefile .env.example pyproject.toml uv.lock
git commit -m "feat(c3-0): retire le back-end de l'espace assuré (routes /assure, sessions, agent de relance)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Migration `005` — supprimer les tables de l'espace assuré

**Files:**
- Create: `src/kaldera/migrations/005_retrait_assure.sql`
- Modify: `tests/conftest.py:36-39`, `tests/e2e/serveur.py` (`TRUNCATE`)
- Test: `tests/integration/test_schema.py`

**Interfaces:**
- Consumes: `kaldera.postgres.appliquer_migrations(conn) -> list[str]` et `pool(url)` (applique les migrations à l'ouverture).

- [ ] **Step 1: Écrire le test (rouge)**

Ajouter à la fin de `tests/integration/test_schema.py` :

```python
def test_tables_de_l_espace_assure_retirees_colonnes_gardees(base: Any) -> None:
    with base.connection() as conn:
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename IN ('utilisateurs', 'demandes_assure', 'evenements_assure')"
        ).fetchall()
        colonnes = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE (table_name, column_name) IN (('demandes', 'cree_le'), ('pieces', 'depose_le'))"
        ).fetchall()
        assert appliquer_migrations(conn) == []  # rejouable : rien de plus à appliquer
    assert tables == []
    assert sorted(colonnes) == [("demandes", "cree_le"), ("pieces", "depose_le")]
```

- [ ] **Step 2: Vérifier qu'il échoue**

Run: `make test-integration` (ou `TEST_DATABASE_URL=… uv run pytest tests/integration/test_schema.py -k retirees -v` avec PostgreSQL de test démarré)
Expected: FAIL — `tables` contient les 3 tables.

- [ ] **Step 3: Écrire la migration**

Créer `src/kaldera/migrations/005_retrait_assure.sql` :

```sql
-- v5 : l'espace assuré (UI1) est retiré, remplacé par le back-office gestionnaire (chantier 3).
-- cree_le et depose_le (004) restent : tri des pièces et tri de la liste des demandes.
DROP TABLE IF EXISTS evenements_assure, demandes_assure, utilisateurs;
```

- [ ] **Step 4: Retirer les tables supprimées des `TRUNCATE`**

Dans `tests/conftest.py` et dans `tests/e2e/serveur.py`, remplacer :

```python
            "TRUNCATE evenements_assure, demandes_assure, utilisateurs, appels_partenaire, "
            "pieces, file_ingestion, analyses, demandes, contrats, blobs"
```

par :

```python
            "TRUNCATE appels_partenaire, pieces, file_ingestion, analyses, demandes, contrats, "
            "blobs"
```

- [ ] **Step 5: Vérifier**

Run: `make test-integration`
Expected: vert, dont `test_tables_de_l_espace_assure_retirees_colonnes_gardees`.

Run: `make test`
Expected: vert (`test_serveur_e2e.py` inchangé).

- [ ] **Step 6: Commit**

```bash
git add src/kaldera/migrations/005_retrait_assure.sql tests/conftest.py tests/e2e/serveur.py tests/integration/test_schema.py
git commit -m "feat(c3-0): migration 005 supprime les tables de l'espace assuré

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Front réduit à une page d'attente

**Files:**
- Delete: `front/src/pages/` (Connexion.tsx, MesSinistres.tsx, Sinistre.tsx, pages.test.tsx) ; `front/src/components/{Chat,Depot,Soumettre,ListePieces,Stepper,VerdictCarte,BandeauStatut}.tsx`, `front/src/components/{composants,Chat}.test.tsx` ; `front/src/useFluxDemande.ts`, `front/src/useFluxDemande.test.tsx`, `front/src/api.ts`, `front/src/textes.ts`, `front/src/test/donnees.ts` ; `front/e2e/parcours.spec.ts`
- Modify: `front/src/App.tsx`, `front/vite.config.ts:13`, `front/index.html:6`
- Create: `front/src/App.test.tsx`, `front/e2e/fumee.spec.ts`

**Interfaces:**
- Produces: `App` (export par défaut) — page d'attente ; C3-1 le remplacera par le socle.

- [ ] **Step 1: Écrire le test de la page d'attente (rouge)**

Créer `front/src/App.test.tsx` :

```tsx
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { axe } from "vitest-axe";
import App from "./App";

it("affiche la page d'attente du back-office, sans violation axe", async () => {
  const { container } = render(<App />);
  expect(
    screen.getByRole("heading", { level: 1, name: "Kaldera · back-office gestionnaire" }),
  ).toBeInTheDocument();
  expect(screen.getByText("En construction (chantier 3).")).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});
```

- [ ] **Step 2: Vérifier qu'il échoue**

Run: `cd front && npx vitest run src/App.test.tsx`
Expected: FAIL — titre introuvable (l'ancienne `App` rend le routeur de l'espace assuré).

- [ ] **Step 3: Supprimer l'espace assuré du front**

```bash
git rm -r front/src/pages front/src/components/Chat.tsx front/src/components/Depot.tsx \
  front/src/components/Soumettre.tsx front/src/components/ListePieces.tsx \
  front/src/components/Stepper.tsx front/src/components/VerdictCarte.tsx \
  front/src/components/BandeauStatut.tsx front/src/components/composants.test.tsx \
  front/src/components/Chat.test.tsx front/src/useFluxDemande.ts front/src/useFluxDemande.test.tsx \
  front/src/api.ts front/src/textes.ts front/src/test/donnees.ts front/e2e/parcours.spec.ts
```

Garder : `front/src/components/ui/*`, `front/src/index.css`, `front/src/format.ts` (+ test), `front/src/lib/utils.ts`, `front/src/test/{contraste.test.ts,setup.ts,axe.d.ts}`.

- [ ] **Step 4: Nouvelle `App.tsx`**

Remplacer le contenu de `front/src/App.tsx` par :

```tsx
export default function App() {
  return (
    <main className="mx-auto flex min-h-svh max-w-3xl flex-col justify-center gap-3 px-4">
      <h1 className="text-2xl font-semibold text-primary">Kaldera · back-office gestionnaire</h1>
      <p className="text-muted-foreground">En construction (chantier 3).</p>
    </main>
  );
}
```

`front/index.html` ligne 6 : `<title>Kaldera · Mon sinistre</title>` → `<title>Kaldera · Back-office</title>`.

`front/vite.config.ts` : supprimer la ligne
`    proxy: { "/assure": { target: "http://127.0.0.1:8000", changeOrigin: false } },`
(C3-2 ajoutera le proxy de l'API gestionnaire).

- [ ] **Step 5: Test de fumée Playwright**

Créer `front/e2e/fumee.spec.ts` :

```ts
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("page d'attente du back-office", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Kaldera · back-office gestionnaire" }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});
```

- [ ] **Step 6: Vérifier le front**

Run: `cd front && npm test && npm run lint && npm run build`
Expected: vert (`App.test.tsx`, `format.test.ts`, `contraste.test.ts`) ; build sans erreur TypeScript.

Run: `make front-e2e`
Expected: `fumee.spec.ts` vert en `mobile` et `desktop`.

Run: `grep -rn -i -E 'assure|connexion|sinistre|relance|chat' front/src front/e2e front/vite.config.ts front/index.html`
Expected: aucune sortie.

- [ ] **Step 7: Commit**

```bash
git add -A front
git commit -m "feat(c3-0): le front devient une page d'attente du back-office gestionnaire

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Cahier de recette

**Files:**
- Modify: `docs/recette/generer_cahier_recette.py`
- Regenerate: `docs/recette/cahier-recette.pdf`

**Interfaces:**
- Produces: `STATUTS: dict[str, str]` (ID de cas → `"OK"` / `"KO"` / `"NT"`), lu par `groupes()` ; vide ici, rempli en Task 8.

- [ ] **Step 1: Colonne de statut alimentée**

Sous `F = "fixtures/pieces/"`, ajouter :

```python
# Statut relevé au dernier déroulé (vide : à dérouler) ; mis à jour à chaque recette.
STATUTS: dict[str, str] = {}
```

Dans `groupes()`, remplacer `[[i, a, r, "", ""] for i, a, r in lignes]` par
`[[i, a, r, STATUTS.get(i, ""), ""] for i, a, r in lignes]`.

- [ ] **Step 2: Setup (S-01 → S-05)**

Remplacer les résultats attendus :
- S-01 : `"Base remise à zéro, partenaire anti-fraude (port 8100) et PostgreSQL (port 5433) démarrés et sains, puis : « Demande KAL-26-0101 prête »."`
- S-02 : `"Uvicorn écoute sur http://127.0.0.1:8000 ; http://localhost:8000/docs liste les routes <i>/demandes</i> et aucune route <i>/assure</i>."`
- S-04 : `"Vite sert la page d'attente du back-office gestionnaire sur http://localhost:5173."`

- [ ] **Step 3: Section 2 — interface gestionnaire**

Remplacer toute la liste `UI = [...]` (U-01 → U-17) par :

```python
UI = [
    ("Page d'attente", [
        ("U-01", "Ouvrir <b>http://localhost:5173</b>.",
         "Titre « Kaldera · back-office gestionnaire », texte « En construction (chantier 3). » ; "
         "aucune page de connexion, aucun espace assuré."),
    ]),
]
```

Dans `construire()`, remplacer le titre et l'introduction de la section 2 :

```python
        Paragraph("2. Interface gestionnaire", H1),
        Paragraph("Navigateur sur http://localhost:5173. L'espace assuré est retiré (v5) ; les "
                  "cas du back-office gestionnaire (EX-D44 → EX-D51) s'ajoutent avec chaque "
                  "sous-projet du chantier 3.", TXT),
```

- [ ] **Step 4: Page de garde, variables, données, contrôles**

Dans `construire()` :
- Objet : `"Recette de démonstration : setup par commandes make (administrateur), interface gestionnaire en construction, contrôles d'exploitation."`
- Date : `"11 octobre 2026"` ; Durée estimée : `"15 minutes environ"`.
- Légende : `"<b>S-01 à S-05</b>, puis <b>U-01 à U-17</b>, puis <b>A-01 à A-04</b>."` → `"<b>S-01 à S-05</b>, puis <b>U-01</b>, puis <b>A-01 à A-04</b>."`
- Tableau des variables : supprimer les lignes `KALDERA_SESSION_SECRET` et `KALDERA_COOKIE_SECURE` ; `"KALDERA_&lt;AGENT&gt;__MODELE, KALDERA_RELANCE__MODELE"` → `"KALDERA_&lt;AGENT&gt;__MODELE"`.
- « Données de démo créées par make recette » : garder seulement les lignes `Dossier` et `Verdict attendu` (supprimer `Compte assuré`, `Pièces valides`, `Pièce illisible`, `Fichier refusé`).
- Introduction de la section 3 : `"Pas encore de console d'administration web (prévue aux specs 2 et 3) : les contrôles se font par make."` → `"Le back-office gestionnaire (chantier 3) n'est pas encore livré : les contrôles se font par make."`
- `ADMIN` / A-01, résultat attendu → `"Journal vide : aucun dossier n'a encore été traité, le partenaire n'a reçu aucun appel."`

- [ ] **Step 5: Régénérer et contrôler le PDF**

Run: `uv run python docs/recette/generer_cahier_recette.py`
Expected: affiche le chemin de `docs/recette/cahier-recette.pdf`.

Run:
```bash
uv run python -I -c "
from pypdf import PdfReader
t = ' '.join(p.extract_text() for p in PdfReader('docs/recette/cahier-recette.pdf').pages)
interdits = ['claire', 'kaldera-demo', 'SESSION_SECRET', 'COOKIE_SECURE', 'RELANCE', 'Se connecter', 'U-17', '/assure/']
print([m for m in interdits if m in t] or 'OK')"
```
Expected: `OK` (seul `/assure` peut apparaître dans S-02 sous la forme « aucune route /assure » ; `'/assure/'` ne doit pas apparaître). Si `pypdf` n'est pas dans l'environnement, utiliser `uv run --with pypdf python -I -c …`.

- [ ] **Step 6: Commit**

```bash
git add docs/recette/generer_cahier_recette.py docs/recette/cahier-recette.pdf
git commit -m "docs(recette): cahier de recette sans espace assuré, page d'attente du back-office

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: README, journal des ajustements, `interface_web.md`

**Files:**
- Modify: `README.md`, `docs/journal_ajustements.md`, `docs/interface_web.md`

- [ ] **Step 1: README**

Repérer : `grep -n -i -E 'assur|relance|5173|front|demo|session|argon2|itsdangerous|claire' README.md`. Pour chaque ligne :
- l.45-48 (« Espace sinistre de l'assuré », assistant pièces / agent de relance) : remplacer le bloc par
  `- **IHM gestionnaire** (\`front/\`) : back-office en cours (chantier 3) ; aujourd'hui une page d'attente.`
- l.61-62 : `- React, Vite, TypeScript, Tailwind, shadcn/ui (back-office gestionnaire, \`front/\`)` ; supprimer la ligne argon2-cffi / itsdangerous.
- l.72 : commentaire `# dépendances du front (espace assuré)` → `# dépendances du front`.
- l.96-101 : supprimer les paragraphes `KALDERA_SESSION_SECRET` (avec `KALDERA_FRONT_ORIGIN`, `KALDERA_DUREE_SESSION_H`, `KALDERA_COOKIE_SECURE`) et `KALDERA_RELANCE__MODELE`.
- l.174-190 (section de lancement de l'espace sinistre, `make demo-assure`, compte « claire », `KALDERA_DEMO_MOT_DE_PASSE`) : remplacer par
  ~~~markdown
  IHM (back-office gestionnaire, chantier 3 en cours) :

  ```bash
  make demo    # demande KAL-26-0101 et son contrat
  make api     # http://127.0.0.1:8000/docs
  make worker
  make front   # http://localhost:5173 : page d'attente
  ```
  ~~~
- l.207 : supprimer la mention « ni de commande pour créer un compte assuré ».
- l.235 : `\`espace_assure.py\`` → `\`depots_assure.py\`` et « espace assuré » → « dépôts de complément ».
- l.238-241 : supprimer la puce des modules assuré ; `front/` : `back-office gestionnaire (page d'attente, React, Vite, Playwright dans \`front/e2e/\`)`.
- l.244-245 : `\`demo_assure.py\` (\`make demo-assure\`, \`make recette\`)` → `\`demo.py\` (\`make demo\`, \`make recette\`)`.
- l.253 : supprimer la ligne `docs/interface_web.md` ou la remplacer par `- \`docs/interface_web.md\` : espace assuré (retiré en v5, archive)`.
- l.267 : `# Playwright : parcours complet de l'assuré` → `# Playwright : test de fumée du back-office`.

Run: `grep -n -i -E 'claire|kaldera-demo|demo-assure|SESSION_SECRET|COOKIE_SECURE|RELANCE__|api_assure|vue_assure|argon2' README.md`
Expected: aucune sortie.

- [ ] **Step 2: Journal des ajustements**

Dans `docs/journal_ajustements.md`, ajouter à la fin du premier tableau (après la dernière ligne datée du 2026-10-08 de ce tableau) :

```markdown
| 2026-10-11 | brief v5 (chantier 3) | l'IHM livrée est l'espace assuré (UI1) ; le brief demande un back-office gestionnaire | EX-D44 | espace assuré retiré : front, routes `/assure/*`, sessions, agent de relance (rôle LLM `relance`), tables `utilisateurs`, `demandes_assure`, `evenements_assure` (migration `005`) ; `espace_assure.py` → `depots_assure.py` (relance métier conservée) | UI1 → page d'attente du back-office |
```

- [ ] **Step 3: `interface_web.md`**

Insérer sous le titre `# Interface web : espace sinistre de l'assuré` :

```markdown
> ⚠️ **Retiré en v5 (11/10/2026)** : l'espace assuré est remplacé par l'IHM gestionnaire
> (chantier 3, `prompt_ui.md`). Ce document est conservé comme archive de l'UI1.
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/journal_ajustements.md docs/interface_web.md
git commit -m "docs: README, journal et interface_web à jour du retrait de l'espace assuré

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Dossier de conception (pages HTML + PDF)

**Files:**
- Delete: `docs/conception/pages/295-espace-assure.html`, `docs/conception/pages/296-parcours-relance.html`
- Modify: `docs/conception/pages/{020-sommaire,040-carte-agents,060-fiches-agents,090-fabrique,180-bornes,200-bornes-llm,230-ingestion,260-persistance,270-schema,280-generateur,310-contrat-champs,380-synthese,410-glossaire-2,440-glossaire-5}.html`
- Regenerate: `docs/conception/dossier-conception.pdf` (ignoré par git) → copie vers `../../dossier-conception.pdf` (racine du brief `kaldera-agents/`, hors dépôt)

Les pages sont rendues dans l'ordre des noms (`rendre.cjs`) : supprimer un fichier suffit à retirer la page. Modifier le HTML en gardant la mise en forme existante (balises, classes) ; seul le texte change.

- [ ] **Step 1: Supprimer les pages de l'espace assuré**

```bash
git rm docs/conception/pages/295-espace-assure.html docs/conception/pages/296-parcours-relance.html
```

- [ ] **Step 2: Corriger les mentions, page par page**

| Fichier:ligne | Texte actuel (extrait) | Nouveau texte |
|---|---|---|
| `020-sommaire.html:21` | « …générateur de pièces (2.7), espace assuré et agent de relance (2.8) » | « …générateur de pièces (2.7) » ; ajouter si une liste de numéros de page existe : la décaler de −2 à partir des pages qui suivaient 2.8 |
| `020-sommaire.html:27` | « Le vocabulaire technique utilisé, du LLM à l'espace assuré » | « Le vocabulaire technique utilisé, du LLM à la liaison A2A » |
| `040-carte-agents.html:24` | « …par un outil VLM ; côté espace assuré, un agent de relance répond hors de la machine (2.8). » | « …par un outil VLM. » |
| `040-carte-agents.html:81` | élément « 💬 relance espace assuré · hors machine (2.8) » | supprimer l'élément entier (et son conteneur s'il ne contient que lui) |
| `060-fiches-agents.html:26` | « …, dépôts de l'espace assuré » | « …, dépôts de complément (API) » |
| `090-fabrique.html:58` | phrase commençant par « L'agent de relance » | supprimer cette phrase |
| `180-bornes.html:35` | « T4 relit les dépôts de l'espace assuré (port… » | « T4 relit les dépôts de complément (port… » |
| `200-bornes-llm.html:28` | « L'agent de relance (2.8) a ses propres bornes (2,0 s, 600 jetons, 2 tours), hors des 8 s. » | supprimer la phrase |
| `230-ingestion.html:12` | « …quelle que soit son entrée (API, espace assuré, `make seed`). » | « …quelle que soit son entrée (API, `make seed`, `make demo`). » |
| `230-ingestion.html:16` | « Dépôt POST …/pieces · API ou espace assuré » | « Dépôt POST …/pieces · API » |
| `260-persistance.html:8` | « …le registre A2A et l'espace assuré — dès que… » | « …et le registre A2A — dès que… » |
| `260-persistance.html:22` | « Ingestion et espace assuré : IngestionPostgres , DepotAssure . » | « Ingestion : IngestionPostgres . » |
| `270-schema.html:45-50` | cartes de table 👤 `utilisateurs`, 🔗 `demandes_assure`, 📣 `evenements_assure` | supprimer les trois cartes |
| `270-schema.html:56` | « Moteur, ingestion, A2A (001 → 003) Espace assuré (004, 2.8) » | « Moteur, ingestion, A2A (001 → 003) · colonnes `cree_le`, `depose_le` (004) · retrait de l'espace assuré (005) » |
| `270-schema.html:64` | ligne d'index « Flux de l'assuré evenements_assure (reference, id) … (2.8). » | supprimer la ligne |
| `280-generateur.html:48` | « # depot1_01_photo.png ⇒ relance 1 ⇒ premier dépôt de l'espace assuré » | « # depot1_01_photo.png ⇒ relance 1 ⇒ premier dépôt de complément » |
| `310-contrat-champs.html:39` | « …— c'est d'ailleurs ce que fait l'espace assuré pour suivre son dossier (2.8). » | « …— c'est ce que fera le back-office gestionnaire pour suivre l'avancement (chantier 3). » |
| `380-synthese.html:45` | ligne n°25 « 🧑 Espace assuré : vue projetée… » du tableau des choix | supprimer la ligne ; renuméroter 26 → 25 ; corriger toute mention du nombre de choix (« 26 » → « 25 ») et « Lignes 23 à 26 » → « Lignes 23 à 25 » (l.53) |
| `380-synthese.html:52` | « Chantier 2 : liaison A2A, monitorage, LLM réel, espace assuré. » | « Chantier 2 : liaison A2A, monitorage, LLM réel. Chantier 3 (v5) : back-office gestionnaire, l'espace assuré est retiré. » |
| `380-synthese.html:60` | point « 6 Espace assuré (UI1) : front React, API /assure/*, flux SSE, vue projetée ; un 5ᵉ agent LLM, la relance . » | « 6 IHM gestionnaire (v5, chantier 3) : back-office local non sécurisé ; l'espace assuré (UI1) et l'agent de relance sont retirés. » |
| `410-glossaire-2.html:23` | « …utilisé par le flux de l'espace assuré (5/5), pas avec le partenaire. » | « …prévu pour le suivi en direct du back-office (chantier 3), pas avec le partenaire. » |
| `440-glossaire-5.html:8` | « Les termes liés à l'espace assuré, à la liaison A2A et à la mesure (chantier 2). » | « Les termes liés à la liaison A2A et à la mesure (chantier 2). » |
| `440-glossaire-5.html:12-16` | entrées « Espace assuré », « Vue projetée », « Flux SSE », « Agent de relance », « argon2 / session » | supprimer les cinq entrées |

Contrôle des sources :
Run: `grep -n -i -E 'espace assur|agent de relance|relance\.py|api_assure|/assure|vue_assure|evenements_assure|demandes_assure|utilisateurs|SESSION_SECRET|UI1|cookie|argon2|DepotAssure' docs/conception/pages/*.html`
Expected: seule la mention volontaire de `380-synthese.html` (« l'espace assuré (UI1)… sont retirés ») et celles de `270-schema.html:56` / `380-synthese.html:52` (« retrait de l'espace assuré », « l'espace assuré est retiré »).

- [ ] **Step 3: Rendre le PDF et vérifier la mise en page**

Run: `make dossier`
Expected: « 46 fragments → …/docs/conception/dossier-conception.pdf » et **aucun** avertissement de débordement de pied de page. Si une page déborde, raccourcir son texte (jamais réduire la police).

Run (aperçu des pages modifiées si besoin) : `node docs/conception/rendre.cjs --png /tmp/apercu --seulement 2,4,27,39`

- [ ] **Step 4: Copier à la racine du brief et contrôler le texte**

```bash
cp docs/conception/dossier-conception.pdf ../../dossier-conception.pdf
```

Run:
```bash
uv run --with pypdf python -I -c "
import re
from pypdf import PdfReader
r = PdfReader('../../dossier-conception.pdf')
pat = re.compile(r'agent de relance|relance\.py|/assure/|vue_assure|evenements_assure|demandes_assure|utilisateurs|SESSION_SECRET|argon2|DepotAssure', re.I)
hits = [(i, m.group(0)) for i, p in enumerate(r.pages, 1) for m in pat.finditer(p.extract_text() or '')]
print(len(r.pages), 'pages', hits or 'OK')"
```
Expected: `46 pages OK`. (« espace assuré » n'apparaît plus que dans les phrases de retrait de la synthèse et du schéma.)

- [ ] **Step 5: Commit (sources seulement ; le PDF est ignoré par git)**

```bash
git add -A docs/conception/pages
git commit -m "docs(conception): dossier sans espace assuré ni agent de relance (v5)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Vérification finale et déroulé de la recette

**Files:**
- Modify: `docs/recette/generer_cahier_recette.py` (`STATUTS`), `docs/recette/cahier-recette.pdf`

- [ ] **Step 1: Toutes les suites**

Run: `make test && make test-integration && make lint && make typecheck`
Expected: vert.

Run: `cd front && npm test && npm run lint && npm run build && cd .. && make front-e2e`
Expected: vert.

- [ ] **Step 2: Critère `grep` de la spec**

Run: `grep -rn -E 'api_assure|\bauth\.|vue_assure|assure_postgres|kaldera\.evenements|from \. import evenements|demo_assure|relance\.py|import relance|KALDERA_RELANCE' src tests tools front/src Makefile docs/recette`
Expected: aucune sortie.

- [ ] **Step 3: Dérouler la recette S-01 → A-04**

Suivre `docs/recette/cahier-recette.pdf` dans l'ordre (`.env` de l'utilisateur requis pour `make worker` : profil VLM). Noter pour chaque cas OK / KO / NT. Tout KO est corrigé dans cette branche (retour à la tâche concernée) avant de continuer.

- [ ] **Step 4: Renseigner les statuts et régénérer**

Dans `docs/recette/generer_cahier_recette.py`, remplir `STATUTS` avec les résultats relevés, par exemple :

```python
STATUTS: dict[str, str] = {
    "S-01": "OK", "S-02": "OK", "S-03": "OK", "S-04": "OK", "S-05": "OK",
    "U-01": "OK",
    "A-01": "OK", "A-02": "OK", "A-03": "OK", "A-04": "OK",
}
```

(Valeurs réelles du déroulé ; `NT` pour un cas non déroulable, avec la raison dans le compte rendu de PR.)

Run: `uv run python docs/recette/generer_cahier_recette.py`

- [ ] **Step 5: Commit**

```bash
git add docs/recette/generer_cahier_recette.py docs/recette/cahier-recette.pdf
git commit -m "docs(recette): statuts du déroulé C3-0

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
