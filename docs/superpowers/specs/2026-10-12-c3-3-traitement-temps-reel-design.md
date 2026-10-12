# C3-3 · Traitement, temps réel et E3 « Suivi de lot »

> Source : `prompt_ui.md` v5, chantier 3 (EX-D44, EX-D45, EX-D46 ; étapes 17 et 19 de l'ordre
> d'implémentation). Branche : `feature/chantier3-c3-3-traitement` · point de départ : `f24e15d`
> (C3-2 fusionné, #15).
> Chantier 3 : C3-0 retrait ✅ → C3-1 design system et socle ✅ → C3-2 lecture (E1, E2) ✅ →
> **C3-3 traitement, temps réel et lots (E3)** → C3-4 reprise d'étape et notes → C3-5 documents et recette.

## 1. Objectif

Le gestionnaire **lance** le traitement d'un ou plusieurs dossiers depuis E1 et en **suit
l'avancement en direct** : E2 pour un dossier, E3 pour un lot. L'IHM n'interprète toujours rien
(EX-D44) : sélectionnabilité, pourcentages et compteurs sont calculés par la projection serveur.

| Exigence | Où |
|---|---|
| EX-D44 aucune règle métier dans l'IHM | §2.4 (projection), §4 |
| EX-D45 sélection 1 / N, `POST /traitements` ⇒ `traiter_lot`, `admission` et `en_cours` non sélectionnables | §2.1, §2.2, §4.1 |
| EX-D46 événements de `tracer()` et des agents (tour LLM, outil), `LISTEN/NOTIFY` puis SSE ; % agent, dossier, lot | §3 |
| EX-D15 un dossier lent n'en bloque aucun autre | §2.2 (`traiter_lot` parallèle), §4.3 |
| EX-D51 statuts = icône + libellé + couleur | §4 (`<Statut>`) |

**Critère de sortie** : `make test`, `make lint`, `make typecheck`, `make test-integration` verts ;
`npm test`, `npm run lint`, `npm run build`, `make front-e2e` verts ; cahier de recette régénéré
et déroulé (U-01 → U-15) ; dossier de conception régénéré avec la page 2.10, sans débordement,
copié à la racine du brief.

### Décisions prises

| Sujet | Décision |
|---|---|
| Quels dossiers lancer | Nouveau statut **`prete`** : le worker s'arrête après l'admission, seul le gestionnaire lance le traitement. Seul `prete` est sélectionnable ; `terminee` / `secours` ne le sont pas (leur reprise : C3-4). Un re-traitement complet est écarté : le partenaire refuse un second appel (contrat §6) et l'état serait écrasé sans historique (EX-D48). |
| Finesse du temps réel | **Sous-étapes d'agent** (conforme à EX-D46) : vue reçue → tours LLM / appels d'outil → garde-fou → patch fusionné. |
| Qui exécute | **L'API**, dans une `BackgroundTask` FastAPI qui appelle `traiter_lot`. API tuée en plein lot ⇒ le reaper escalade (inchangé). Un orchestrateur, donc un disjoncteur, par lot. |
| Acheminement des événements | **Port `Signaux`** injecté, `pg_notify` émis par le code (orchestrateur, agent, reaper) ; une seule source, quel que soit le processus qui traite. Trigger SQL et file en mémoire écartés. |
| Données des scénarios | `make scenarios ARGS=--charger` insère les 28 scénarios en `prete` (niveau 0) au lieu de les traiter. |
| Seed et épreuve | `tools/seed.py` attend `prete`, appelle `POST /traitements`, puis attend `terminee` : l'épreuve C2b passe par la nouvelle route (API lancée par `make api-epreuve`, partenaire indisponible). |
| Infobulle « non sélectionnable » | Pas de nouvelle dépendance : motif en `title` (souris) et `aria-describedby` (clavier, lecteur d'écran). |

### Hors périmètre

Reprise d'étape, exécutions, notes, table `notes_etape` (C3-4) ; `make ui` (C3-5) ; toute
modification des règles métier, des gardes ou de la table de transitions.

## 2. Back-end : cycle de vie et lots

### 2.1 Statut `prete` et migration `006_traitements.sql`

Cycle de vie : `admission → prete → en_cours → terminee | secours`.

```sql
ALTER TABLE demandes DROP CONSTRAINT demandes_statut_check;
ALTER TABLE demandes ADD CONSTRAINT demandes_statut_check
  CHECK (statut IN ('admission','prete','en_cours','terminee','secours'));
CREATE TABLE lots (id bigserial PRIMARY KEY, cree_le timestamptz NOT NULL DEFAULT now());
CREATE TABLE lot_demandes (
  lot_id    bigint NOT NULL REFERENCES lots,
  reference text   NOT NULL REFERENCES demandes,
  PRIMARY KEY (lot_id, reference)
);
```

(Le nom de la contrainte est vérifié dans `test_schema.py` ; migration commentée.)

| Composant | Changement |
|---|---|
| `IngestionPostgres.admettre` | Passe la demande en **`prete`** (et non plus `en_cours`) et écrit dans `etat.demande` la **demande niveau 1** (`demande_niveau_1`, termes du contrat), dans **une seule transaction**. Compare-and-set inchangé. |
| `worker._admettre` | Ne construit plus d'`Orchestrateur` : l'admission s'arrête à `prete` ; `travailler()` perd son paramètre `disjoncteur`. |
| Reaper | Inchangé : il ne fauche que `en_cours`. Il émet `dossier_fin` après `classer` (§3.2). |
| `cli.py --charger` | Insère chaque demande des scénarios en `prete` (`etat = {"demande": …}`, niveau 0 : contrat et pièces dans la demande). Référence déjà en base ⇒ ignorée et signalée. Sans `--charger` : comportement actuel. |
| Dépôt de pièces | `DepotPostgres` lu d'abord ; table vide pour la référence ⇒ pièces de la demande (niveau 0). Sans risque : une demande créée par l'API n'a jamais de champ `pieces` (`DemandeCreation`, `extra=forbid`). |

### 2.2 `POST /traitements`

Corps `{references: [str]}` : liste non vide, sans doublon, références au format `KAL-\d{2}-\d{4}`
(sinon **422**). Route mince ; la logique est dans un service `traitements.py`.

1. Une transaction : référence inconnue ⇒ **404** ; `INSERT INTO lots` ;
   `UPDATE demandes SET statut = 'en_cours', maj = now() WHERE reference = ANY(%s) AND statut = 'prete' RETURNING reference, etat` ;
   si le nombre de lignes diffère ⇒ annulation et **409** `{"detail": "dossiers non lançables", "references": [...]}` (tout ou rien) ;
   sinon `INSERT INTO lot_demandes`.
2. Réponse **202** `{lot_id, references}`.
3. `BackgroundTasks` : `traiter_lot(demandes, orchestrateur=…)` avec un orchestrateur câblé sur
   Postgres (snapshots, dépôt du §2.1, `SignauxPostgres` ; un disjoncteur par lot).

`traiter_lot` gagne un paramètre facultatif `orchestrateur` ; le `cli` et les tests existants
l'appellent sans changement. `Orchestrateur.traiter` reste le point d'entrée : `debuter` réécrit le
snapshot (statut déjà `en_cours`), le filet couvre chaque dossier.

### 2.3 `GET /lots/{id}`

`LotVue` (404 `{"detail": "lot inconnu"}`) :

| Champ | Source |
|---|---|
| `id`, `debut` | `lots.cree_le` |
| `fin` | `max(maj)` des dossiers quand tous sont terminaux, sinon `null` |
| `avancement` | dossiers terminaux (`terminee`, `secours`) / dossiers du lot × 100 |
| `compteurs` | `acceptee`, `refusee`, `escalade` par file, `mode_degrade` |
| `dossiers` | `LigneLot` par dossier (ordre des références) |

`LigneLot` : `reference`, `nom`, `prenom`, `police`, `statut`, `avancement` (celui de `DossierVue`),
`etape_en_cours` (`etat_courant` si `en_cours`, sinon `null`), `duree_ms`, `issue`, `file`,
`mode_degrade`, `borne` (nom de la borne si `arret`, sinon `null`).

### 2.4 Projection (`vue_gestionnaire.py`)

Fonctions pures ajoutées ou modifiées, tolérantes comme en C3-2 :

- `LigneDemande` gagne `selectionnable: bool` et `motif_non_selectionnable: str | None` :

  | Statut | Sélectionnable | Motif |
  |---|---|---|
  | `prete` | oui | — |
  | `admission` | non | « Pièces en cours d'analyse » |
  | `en_cours` | non | « Traitement en cours » |
  | `terminee`, `secours` | non | « Déjà traité » |

- `StatutDemande` accepte `prete` (filtre E1).
- Dossier `en_cours` : l'étape `etat_courant` est projetée **`en_cours`** (avancement 0 dans le
  `GET`) ; les étapes aval restent `en_attente`.
- `avancement_agent(sous_etape, tour, tours_max) -> int` (§3.3).
- `lot(id, debut, lignes) -> LotVue`.
- Liste blanche inchangée : aucune donnée personnelle hors nom, prénom, police, formule.

## 3. Événements et SSE

### 3.1 Port `Signaux`

```python
class Signaux(Protocol):
    def emettre(self, evenement: dict[str, Any]) -> None: ...
```

- `SignauxPostgres` : `SELECT pg_notify('kaldera_avancement', %s)` (JSON) sur le pool ; une
  `ErreurPersistance` est journalisée et l'événement perdu. **Jamais bloquant** (EX-01).
- `signaux_par_defaut()` : même logique que `snapshots_par_defaut()` ; sans base, aucun signal.
  L'API, le `cli` et le worker émettent donc tous.
- `Orchestrateur(signaux=…)` : injecté comme `snapshots` ; aucun état partagé entre threads.

### 3.2 Événements émis

Charge utile minimale (limite NOTIFY : 8 000 octets) ; jamais de donnée personnelle ni de contenu
de patch.

| `type` | Émetteur | Champs |
|---|---|---|
| `etape_debut` | `Orchestrateur._etape`, avant l'action | `reference`, `etat` |
| `sous_etape` | `AgentLLM.executer(vue, budget, signaler=None)` ; `signaler(sous_etape, tour)` est une fermeture créée par l'orchestrateur pour l'appel (l'agent est partagé entre threads) | `reference`, `etat`, `sous_etape` (`vue` · `tour` · `outil` · `garde_fou`), `tour`, `tours_max` |
| `etape_fin` | `Orchestrateur._etape` et `_sauter`, **après** l'écriture du snapshot | `reference`, `etat` |
| `dossier_fin` | `Orchestrateur.traiter` après `terminer` (que le compare-and-set réussisse ou non : la base fait foi, le front relit) ; reaper après `classer` | `reference` |

Points d'émission dans l'agent : `vue` au début de `executer` ; `tour` après chaque `completer` ;
`outil` après chaque appel d'outil ; `garde_fou` avant `verifier_sortie`, ou directement en cas de
repli (LLM absent, disjoncteur, budget, erreur). L'éligibilité (outil, sans LLM) n'émet que
`etape_debut` et `etape_fin`.

### 3.3 Pourcentages

| Niveau | Calcul (serveur) |
|---|---|
| Agent | sous-étapes faites / prévues, prévues = `tours_max + 3` : `vue` = 1 ; `tour k` = 1 + k ; `garde_fou` = `tours_max + 2` (tours non utilisés comptés comme faits, repli compris) ; `etape_fin` = 100 % |
| Dossier | celui de C3-2 : (`termine` + `sautee` + `repli` + `degrade`) / 5 ; état terminal ⇒ 100 % |
| Lot | dossiers terminaux / dossiers du lot |

### 3.4 Routes SSE

| Route | Filtre | 404 |
|---|---|---|
| `GET /flux/demandes/{ref}` | `reference == ref` | dossier inconnu |
| `GET /flux/lots/{id}` | `reference ∈` références du lot (lues à la connexion) | lot inconnu |

- `async def` et `StreamingResponse(media_type="text/event-stream")` ; chaque client ouvre **sa**
  `psycopg.AsyncConnection` (autocommit) et fait `LISTEN kaldera_avancement` ; rien de bloquant
  dans la boucle d'événements.
- Chaque notification filtrée devient
  `event: avancement` / `data: {type, reference, etat, statut, avancement_agent}`, où
  `avancement_agent` vient de `avancement_agent()` (§3.3) et `statut` vaut `en_cours` pour
  `etape_debut` et `sous_etape`.
- Battement `: ping` toutes les 15 s ; fin de la boucle quand le client se déconnecte.

Exemple :

```
event: avancement
data: {"type": "sous_etape", "reference": "KAL-26-0203", "etat": "estimation", "statut": "en_cours", "avancement_agent": 50}
```

## 4. Front

### 4.1 E1 · Liste des demandes (`ListeDemandes.tsx`)

- Première colonne : case à cocher par ligne ; case « Tout sélectionner » dans l'en-tête (lignes
  sélectionnables visibles).
- Ligne non sélectionnable : case `disabled`, motif du serveur en `title` et en `aria-describedby`
  (texte `sr-only`).
- Barre d'action : bouton « Traiter la sélection (n) », inactif à 0 ; `useMutation`
  `POST /traitements`. 202 : 1 dossier ⇒ `/demandes/:ref`, plusieurs ⇒ `/lots/:id` ; 409 ⇒
  `role="alert"` avec les références refusées, puis relecture de la liste.
- Sélection vidée au changement de filtres ; option `prete` dans le filtre statut ; codes `prete` et
  `en_cours` ajoutés à `statuts.ts` (icône + libellé + couleur, AA dans les deux thèmes).

### 4.2 E2 · Dossier (`Dossier.tsx`)

- `useFlux("/flux/demandes/" + ref, cle)` actif tant que le dossier n'est pas terminal.
- Carte de l'étape `en_cours` : `<Statut code="en_cours">` et barre `role="progressbar"` du % agent ;
  l'avancement de l'en-tête suit à chaque `etape_fin`.
- Région `aria-live="polite"` : « Étape en cours : {x} », puis « Traitement terminé » (pas les sous-étapes) ; mention « Reconnexion… » si le flux est coupé.

### 4.3 E3 · Suivi de lot (`pages/Lot.tsx`, remplace le cadre de `socle.tsx`)

- `<h1>` « Lot {id} » (inchangé, tests C3-1).
- En-tête : avancement du lot (progressbar), compteurs acceptée / refusée / escalade par file, modes
  dégradés, durée écoulée = (`fin` ?? maintenant) − `debut`, rafraîchie chaque seconde tant que
  `fin` est nul (affichage, pas une règle).
- Tableau dense : référence (lien vers E2, Plex Mono) · nom, prénom · police · barre % (progressbar
  étiquetée) · étape en cours · durée (`tabular-nums`) · issue (`<Statut>`) · badges dégradé et
  borne (`<Statut>`).
- `useFlux("/flux/lots/" + id, cle)` : une `sous_etape` ne met à jour **que sa ligne** ; les barres
  avancent indépendamment.
- États : chargement (squelettes) ; 404 « Lot introuvable » + retour à la liste ; erreur
  `role="alert"` + « Réessayer » ; flux coupé ⇒ badge « Reconnexion… ».

### 4.4 `useFlux` (hook partagé)

- `EventSource` sur `/api` + chemin.
- `open` (y compris à la reconnexion) ⇒ invalidation de la requête : l'état complet est relu.
- `etape_fin`, `dossier_fin` ⇒ invalidation (la projection serveur reste la seule source).
- `etape_debut`, `sous_etape` ⇒ `setQueryData` avec les valeurs du serveur (statut, % agent) sur
  l'étape ou la ligne concernée.
- Fermeture quand le dossier ou le lot est terminal, et au démontage.

## 5. Erreurs

| Cas | Réponse |
|---|---|
| Corps invalide (liste vide, doublon, format) | 422 (format Pydantic) |
| Référence inconnue | 404 `demande inconnue` |
| Dossier non `prete` | 409, rien n'est lancé, références refusées listées |
| Lot inconnu (`GET /lots`, flux) | 404 `lot inconnu` |
| Base indisponible | 503 (gestionnaire existant) |
| Exception pendant le traitement | filet de l'orchestrateur, par dossier ; API tuée ⇒ reaper |

## 6. Tests

### 6.1 Back

| Fichier | Vérifie |
|---|---|
| `unit/test_vue_traitement.py` (+ `test_vue_gestionnaire.py`) | sélectionnabilité et motif par statut ; `avancement_agent` (vue, tour k, garde-fou, repli) ; étape `en_cours` ; `LotVue` (avancement, compteurs, `fin`, liste blanche) |
| `unit/test_orchestrateur.py` | ordre des signaux avec un faux `Signaux` (`etape_debut` → `sous_etape`… → `etape_fin` après le snapshot → `dossier_fin`) ; éligibilité sans sous-étape ; décisions identiques avec et sans signaux |
| `unit/test_agents_llm.py` | `signaler` : tours, outils, garde-fou ; repli ⇒ `garde_fou` directement ; `signaler=None` ⇒ comportement actuel |
| `integration/test_cli.py` | `--charger` : 28 scénarios en `prete` ; référence existante ignorée |
| `test_contrat_ports.py` | faux `Signaux` en mémoire conforme au port |
| `integration/test_api.py` | `POST /traitements` 202 (puis `terminee`), 409 tout ou rien, 422, 404 ; `GET /lots` ; SSE : un `pg_notify` reçu sur `/flux/demandes`, filtrage par lot |
| `integration/test_worker.py` | admission ⇒ `prete` avec demande niveau 1, aucun traitement |
| `integration/test_seed.py`, `test_epreuve.py` | seed ⇒ `prete` ⇒ `POST /traitements` ⇒ `terminee` |
| `integration/test_schema.py` | migration 006 (CHECK `prete`, `lots`, `lot_demandes`) |

### 6.2 Front

| Fichier | Vérifie |
|---|---|
| `src/pages/ListeDemandes.test.tsx` | cases, motif accessible, tout sélectionner, bouton (n), navigation 1 ⇒ E2 / N ⇒ E3, 409 en alerte, axe |
| `src/pages/Lot.test.tsx` | en-tête, lignes, une `sous_etape` ne touche qu'une ligne, 404, erreur, axe |
| `src/pages/Dossier.test.tsx` | étape `en_cours` et son % agent, région `aria-live` |
| `src/useFlux.test.ts` | faux `EventSource` : `open` ⇒ relecture, `etape_fin` ⇒ invalidation, fermeture une fois terminal |
| `e2e/traitement.spec.ts` | `tests/e2e/serveur.py` amorce des dossiers `prete` ; traiter 1 dossier (E2 en direct jusqu'à l'état terminal), puis 3 (E3 jusqu'à 100 %) ; axe dans les deux thèmes |

## 7. Documents

| Document | Mise à jour |
|---|---|
| Cahier de recette (générateur + PDF, déroulé) | **S-06** `make scenarios ARGS=--charger` ; groupe « Traitement » placé avant la lecture (qui porte sur les dossiers ainsi traités) : **U-05** sélection (non sélectionnables et motifs) ; **U-06** traiter 1 dossier : E2 en direct, état terminal ≤ 8 s ; **U-07** lot des scénarios chargés (E3, barres indépendantes, partenaire lent via `make ctl` : les dossiers sans anti-fraude ne sont pas retardés) ; **U-08** reconnexion (API relancée ⇒ relecture) ; **U-09** 409 (dossier déjà lancé dans un autre onglet). Cas de lecture C3-2 renumérotés **U-10 → U-15**. Légende S-01 → S-06, U-01 → U-15. |
| Dossier de conception (`make dossier` + copie à la racine) | page `299b-ihm-traitement.html`, section « 2.10 IHM gestionnaire · traitement, temps réel et E3 » : cycle de vie avec `prete`, séquence `POST /traitements` → `BackgroundTask` → `pg_notify` → SSE, calcul des %, tables `lots` / `lot_demandes` ; sommaire ; glossaire (lot, SSE, `LISTEN/NOTIFY`). |
| `docs/interface_gestionnaire.md` | routes `POST /traitements`, `GET /lots/{id}`, flux SSE avec exemples d'événements ; E3 marqué livré ; statut `prete`. |
| `README.md` | `make scenarios ARGS=--charger`, lancement d'un lot depuis E1, capture `docs/captures/e3-lot.png`. |
| `docs/journal_ajustements.md` | le worker ne traite plus (statut `prete`) ; le seed lance par l'API. |

## 8. Risques

| Risque | Parade |
|---|---|
| Pool Postgres (10 connexions, attente 0,5 s) sous 28 dossiers parallèles : snapshots + notify | signaux best effort ; un signal perdu ne fausse rien (`etape_fin` et `open` relisent `GET`) ; lot de 28 déroulé en recette (U-13) ; `ponytail:` sur la taille du pool |
| Une connexion PG par client SSE | usage local mono-gestionnaire ; `ponytail:` (écouteur unique partagé si plusieurs gestionnaires) |
| Événement perdu entre `GET` et ouverture du flux | relecture à l'`open` |
| Régressions seed, épreuve, worker | tests d'intégration mis à jour dans la même PR |
| Fenêtre entre `prete` et l'écriture de la demande niveau 1 | une seule transaction dans `admettre` |
| Événement contenant une donnée personnelle | charge utile limitée aux champs du §3.2 ; test qui le vérifie |
