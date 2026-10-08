# SP2 · Persistance — pièces par référence, PostgreSQL, filet de sécurité niveau 2

> Source : `dossier-conception.pdf` (2.4 bis, 2.5 niveau 2, 2.6, 2.6 bis).
> Branche : `feature/chantier1-orchestration` · point de départ : `b1be9ff` (SP1 livré : 304 verts,
> 14 rouges A2A hors périmètre). Deuxième des trois sous-projets : SP1 moteur → **SP2 persistance** →
> SP3 ingestion.

## 1. Objectif

| Écart | Dossier | Exigence |
|---|---|---|
| E · pièces = références derrière un port | 2.4 bis | EX-D28, EX-D29 |
| F · PostgreSQL unique, schéma, migrations, adaptateurs | 2.6, 2.6 bis | EX-D41 |
| C2 · snapshot après chaque transition + reaper | 2.5 niveau 2 | EX-D24, EX-01 |

Critère de sortie : `make test` reste sans base et vert (hors les 14 rouges A2A) ; les 28 scénarios
donnent les mêmes issues ; `make test-integration` est vert sur `postgres:16`.

### Décisions prises

| Sujet | Décision |
|---|---|
| Accès base | psycopg 3 **synchrone** + `psycopg_pool.ConnectionPool`, SQL brut, migrations SQL versionnées. SQLAlchemy (`CLAUDE.md`) et l'asynchrone écartés : moteur synchrone depuis SP1, garanties SQL du dossier écrites telles quelles. |
| Base optionnelle | Sans `KALDERA_DATABASE_URL`, aucune persistance : `traiter_demande` et la suite d'acceptance tournent sans service externe (`interface.md`). |
| Montants | `Decimal` uniquement à la frontière : l'adaptateur Postgres convertit `numeric` → float arrondi au centime ; le domaine reste en float. |
| Pièces | L'orchestrateur charge les descripteurs par `DepotPieces` et les met dans la vue de `pieces` ; aucun agent ne reçoit de dépendance. |
| Fiche | Nouvelle colonne `demandes.fiche jsonb`, écrite à la fin normale et par le reaper. |
| Registre A2A | Table `appels_partenaire` + port `RegistreA2A` créés et testés ; branchés au chantier 2. |

### Hors périmètre

`RegistrePieces` (écriture, appelant = ingestion) et `DepotContrats` : SP3. Table `file_ingestion`,
`blobs`, `contrats`, `analyses` : créées par la migration (schéma complet), sans code applicatif avant
SP3. Contrôle d'admission (statut `admission`) : SP3. Branchement du registre A2A : chantier 2.
Domaine en `Decimal` : non prévu.

### Écarts au dossier (consignés au journal)

1. `demandes.fiche jsonb NULL` ajoutée (le dossier ne persiste pas la fiche).
2. `demandes.numero_contrat` nullable : une demande malformée sans contrat est quand même snapshotée.
3. `DepotPieces` prend la `demande` (dict) et non la seule `reference` : l'adaptateur niveau 0 lit le
   JSON ; l'adaptateur Postgres n'en lit que `reference`.
4. Tests d'intégration isolés par `TRUNCATE` et non par rollback (`CLAUDE.md`) : la concurrence exige
   des transactions commitées.

## 2. Fichiers

| Fichier | Rôle |
|---|---|
| `src/kaldera/ports.py` | `PieceRef`, protocoles `DepotPieces`, `Snapshots`, `RegistreA2A`, exception `ErreurPersistance` |
| `src/kaldera/memoire.py` | `DepotDepuisDemande` (niveau 0), `SnapshotsEnMemoire`, `RegistreA2AEnMemoire` |
| `src/kaldera/postgres.py` | `ConfigBase`, `pool(url)`, `appliquer_migrations(conn)`, `DepotPostgres`, `SnapshotsPostgres`, `RegistreA2APostgres` |
| `src/kaldera/reaper.py` | `faucher(snapshots, age_s) -> list[dict]`, boucle `python -m kaldera.reaper` |
| `migrations/001_schema.sql` | les 7 tables de 2.6 bis + `demandes.fiche` + `schema_migrations` |
| `src/kaldera/espace_assure.py` | `depot_pour(depots, type_piece, tentative)` : fonction pure sur une liste |
| `src/kaldera/agents.py`, `agents_llm.py` | `AgentPieces` et l'outil `lire_depot` lisent `vue["initiales"]` / `vue["depots"]` |
| `src/kaldera/orchestrateur.py` | injection `depot`, `snapshots` ; vue de `pieces` ; `_persister` ; snapshot par transition |

## 3. E · Pièces par référence

```python
class PieceRef(BaseModel):
    type: Literal["facture", "photo", "depot_plainte"]
    lisible: bool
    montant: float | None = None          # numeric → float au centime dans l'adaptateur
    piece_id: UUID | None = None          # niveau 1 : référence, jamais d'octets
    sha256: str | None = None
    statut_analyse: Literal["ok", "echec"] = "ok"
    # validateur : statut_analyse == "echec" ⇒ lisible = False

class DepotPieces(Protocol):
    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]: ...
    def depots(self, demande: dict[str, Any]) -> list[PieceRef]: ...   # dans l'ordre de dépôt
```

- `DepotDepuisDemande` : `demande["pieces"]` et `demande["espace_assure"]["depots"]` (absents ⇒ `[]`).
- `DepotPostgres` : `SELECT type, lisible, montant, piece_id, sha256, statut_analyse FROM pieces WHERE
  reference = %s AND relance IS NULL` (initiales) ; `relance IS NOT NULL ORDER BY relance, piece_id`
  (dépôts). `statut_analyse` `en_attente` ou `echec` ⇒ `lisible = False`, `statut_analyse = "echec"`.
- Vue de `pieces` : `{"demande", "relances", "initiales": [dict], "depots": [dict]}` (`PieceRef`
  sérialisés par `model_dump(mode="json")`). Aucune autre vue ne contient de pièces.
- `espace_assure.depot_pour(depots, type_piece, tentative)` reprend la règle actuelle (dernier dépôt
  du type re-soumis) sur une liste ; `demander_piece` disparaît.
- `AgentPieces` : `recues = initiales`, dépôts lus via `depot_pour(vue["depots"], …)`. Outil LLM
  `lister_pieces` → `vue["initiales"]` ; `lire_depot(k)` → `depot_pour(vue["depots"], t, k - 1)`.
- Une pièce malformée (type hors enum) ⇒ `ValidationError` dans l'orchestrateur ⇒ étape `pieces` en
  `echec` (comportement SP1), jamais un plantage.

## 4. C2 · Snapshots et reaper

```python
class Snapshots(Protocol):
    def debuter(self, etat: EtatDemande) -> None: ...                   # upsert, statut 'en_cours'
    def enregistrer(self, etat: EtatDemande) -> None: ...               # etat, etat_courant, maj = now()
    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool: ...  # CAS en_cours → terminee
    def faucher(self, age_s: float) -> list[tuple[str, dict[str, Any]]]: ...   # CAS en_cours → secours
    def classer(self, reference: str, fiche: dict[str, Any]) -> None: ...      # fiche de secours
```

### Écritures de l'orchestrateur

- `debuter` au début de `_executer`, après validation de la demande et du contrat.
- `enregistrer` après chaque transition : fin de `_etape` et de `_sauter`.
- `terminer` dans `traiter`, après `construire_fiche`, sur le chemin normal comme après le filet
  niveau 1. `False` (le reaper a gagné) ⇒ avertissement journalisé ; l'appelant reçoit sa fiche, la
  base garde l'escalade de secours.
- Snapshot = `etat.model_dump(mode="json")` : références de pièces seulement (claim check).
- Toute écriture passe par `_persister(fn, etat)` : `ErreurPersistance` ⇒ journalisée, étape courante
  marquée `persistance: "echec"`, traitement poursuivi (EX-01 : la base ne bloque jamais une
  décision). Plafond assumé : base en panne puis processus mort ⇒ demande hors du reaper.
- `snapshots=None` (pas de base) ⇒ aucune écriture.

### Reaper

`faucher(snapshots, age_s)` :
1. `UPDATE demandes SET statut = 'secours' WHERE statut = 'en_cours' AND maj < now() - make_interval(secs => %s) RETURNING reference, etat` (atomique : deux reapers ne prennent jamais la même ligne).
2. Par ligne : `EtatDemande.model_validate(etat)` ; étape tracée `{agent: "orchestrateur", action:
   "reaper", statut: "echec", de: <etat_courant>, vers: "escalade", garde: "reaper"}` ;
   `escalade_forcee = "processus interrompu (reaper)"` ; `construire_fiche` (file prudente de SP1) ;
   `classer(reference, fiche)`.
3. Snapshot illisible (`ValidationError`) ⇒ fiche minimale : escalade `gestionnaire`, motif
   « Escalade de secours : snapshot illisible ». Une ligne ne fait jamais planter le reaper.
4. Jamais de rejeu de la machine (le partenaire refuserait : `-32029`).
5. Retourne les fiches classées.

`python -m kaldera.reaper` : boucle `faucher` toutes les 10 s ; `ErreurPersistance` journalisée,
nouvel essai au tour suivant. `make reaper`.

### `RegistreA2A`

`reserver(reference) -> bool` (`INSERT … ON CONFLICT (reference) DO NOTHING RETURNING reference`) ;
`noter(reference, evaluation_id) -> None`. Aucun appelant dans SP2.

## 5. F · PostgreSQL

- `migrations/001_schema.sql` : les tables `blobs`, `contrats`, `analyses`, `demandes`, `pieces`,
  `appels_partenaire`, `file_ingestion` et index partiels de 2.6 bis, à l'identique, avec les écarts 1
  et 2 (§1). Table `schema_migrations(version text PRIMARY KEY, applique_le timestamptz)`.
- `appliquer_migrations(conn)` : applique dans l'ordre les fichiers `NNN_*.sql` absents de
  `schema_migrations`, un fichier = une transaction ; rejouable sans effet.
- `ConfigBase(BaseSettings)` : `database_url: str | None` (`KALDERA_DATABASE_URL`),
  `reaper_age_s: float = 30` (`KALDERA_REAPER_AGE_S`), `env_file=".env"`.
- `pool(url)` : `functools.cache`, un pool par processus et par URL, migrations appliquées à
  l'ouverture. `# ponytail: pool par processus ; injection explicite si une app FastAPI le gère (SP3)`.
- Les adaptateurs convertissent `psycopg.Error` en `ErreurPersistance` (aucune capture large).
- Dépendance ajoutée : `psycopg[binary,pool]>=3.2`.

## 6. Tests

| Niveau | Commande | Base | Prouve |
|---|---|---|---|
| Unitaires | `make test` | mémoire | vue de `pieces` issue du port, aucune pièce dans les autres vues ; `depot_pour` ; `PieceRef` (echec ⇒ illisible) ; un snapshot par transition ; `terminer` appelé avec la fiche ; `ErreurPersistance` ne change aucune issue ; reaper : fiche reconstruite depuis un snapshot « mort » (horloge injectée), snapshot illisible ⇒ fiche minimale, une demande terminée n'est pas fauchée |
| Contrat des ports | paramétrés | mémoire **et** Postgres | même comportement : CAS de `terminer` / `faucher`, `reserver` une fois, ordre des dépôts, aller-retour d'un snapshot |
| Intégration | `make test-integration` (marqueur `integration`, exclu de `make test`) | `postgres:16` | 2 reapers concurrents : chaque demande prise une fois ; 2 `reserver` concurrents : un seul `True` ; CHECK `mime`, `taille`, `montant > 0`, `statut` ; UNIQUE `(reference, sha256)` ; `numeric` → float au centime ; migrations rejouables ; `traiter_demande` avec base : ligne `terminee` + fiche |
| Invariance | `make test` | mémoire | les 34 demandes donnent les mêmes issues qu'avant SP2 |

Outillage : service `postgres` (`postgres:16`, profil `integration`) dans `docker-compose.yml` ;
`make test-integration` = `docker compose --profile integration up -d --wait postgres` puis
`KALDERA_DATABASE_URL=… uv run pytest -m integration` ; `addopts = "-m 'not integration'"` ;
`make reaper`. Le démon Docker doit tourner sur la machine.

Journal des ajustements : une ligne par écart (§1) et une ligne pour l'invariance avant / après.
