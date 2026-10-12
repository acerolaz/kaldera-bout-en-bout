# Interface gestionnaire : back-office

> Documentation de ce qui est **livré** (chantier 3). Spec C3-1 : `docs/superpowers/specs/2026-10-12-c3-1-design-system-design.md` ;
> spec C3-2 : `docs/superpowers/specs/2026-10-12-c3-2-lecture-e1-e2-design.md` ;
> spec C3-3 : `docs/superpowers/specs/2026-10-12-c3-3-traitement-temps-reel-design.md`. L'ancien espace assuré (UI1) est archivé dans
> `docs/interface_web.md`.

IHM **non sécurisée** (EX-D44) : usage local, données factices, ni authentification ni rôles. Elle n'interprète rien :
le serveur projette l'état en base (`src/kaldera/vue_gestionnaire.py`) et le front affiche.

## 1. Écrans

| Route | Écran | Livré |
|---|---|---|
| `/` | E1 · Liste des demandes : filtres (statut, issue, file, mode dégradé, recherche) mémorisés dans l'URL ; sélection des dossiers prêts et « Traiter la sélection » (1 ⇒ E2, N ⇒ E3) | C3-2 / C3-3 |
| `/demandes/:reference` | E2 · Dossier : en-tête, panneau Garanties, timeline des 5 étapes, carte anti-fraude ; en direct (étape en cours, % agent) | C3-2 / C3-3 |
| `/lots/:id` | E3 · Suivi de lot : avancement, compteurs, une barre par dossier, en direct | C3-3 |

### Cycle de vie

`admission → prete → en_cours → terminee | secours`. Le worker s'arrête à `prete` ; seul le gestionnaire
lance le traitement. Seul `prete` est sélectionnable dans E1 :

| Statut | Motif de non-sélection |
|---|---|
| `admission` | Pièces en cours d'analyse |
| `en_cours` | Traitement en cours |
| `terminee`, `secours` | Déjà traité |

## 2. API

Le front appelle `/api/…` ; le proxy Vite retire `/api` et transmet à FastAPI (`make api`, port 8000).

### `GET /demandes`

Paramètres facultatifs, combinés en ET (un paramètre vide est ignoré) : `statut` (`admission`, `prete`, `en_cours`, `terminee`,
`secours`), `issue` (`acceptee`, `refusee`, `escalade`), `file`, `mode_degrade` (`true` / `false`), `q` (recherche sans
casse dans référence, nom, police). Réponse : liste triée par référence décroissante, avec `selectionnable` et
`motif_non_selectionnable` (voir Cycle de vie).

```json
[{"reference": "KAL-26-0203", "nom": "Durand", "prenom": "Paul", "police": "CTR-778803",
  "type_sinistre": "degat_des_eaux", "montant_declare": 9200.0, "statut": "terminee",
  "issue": "escalade", "file": "cellule_fraude", "mode_degrade": true,
  "selectionnable": false, "motif_non_selectionnable": "Déjà traité"}]
```

### `GET /demandes/{reference}`

`DossierVue` ; 404 `{"detail": "demande inconnue"}`. Garde `reference`, `statut`, `fiche` (compatibilité).

| Bloc | Champs |
|---|---|
| En-tête | `nom`, `prenom`, `police`, `formule`, `avancement` (0–100), `duree_ms`, `budget_ms`, `issue`, `file`, `motif`, `mode_degrade`, `montant_rembourse` |
| `garanties` | `formule`, `franchise`, `plafond`, `date_souscription`, `statut_contrat`, `cotisations_a_jour`, `statut_extraction`, `source`, `modele`, `sha256` |
| `etapes` (5) | `etat`, `statut`, `avancement`, `passages`, `duree_ms`, `latence_llm_ms`, `modele`, `mode`, `cause`, `tours_llm`, `jetons`, `sortie_rejetee`, `de`, `vers`, `garde`, `resume` |
| `antifraude` | `requis`, `indicateurs`, `statut` (`ok` / `indisponible` / `non_requis`), `niveau`, `score`, `evaluation_id`, `version_modele`, `note`, `cause` |
| `arret` | `borne`, `valeur`, `etat` |

**Statut d'affichage d'une étape** (première règle vraie) : absente de la trace alors qu'une étape aval y figure
(court-circuit) ⇒ `sautee` ; absente sans étape aval ⇒ `en_attente` ; filet de sécurité ⇒
`echec` ; échec de l'anti-fraude sur avis indisponible ⇒ `degrade` ; autre échec ⇒ `echec` ; action non exécutée (garde
d'entrée) ⇒ `sautee` ; mode `repli` ⇒ `repli` ; sinon `termine`.

**Avancement du dossier** : (étapes `termine` + `sautee` + `repli` + `degrade`) / 5 ; dossier `terminee` ou `secours` ⇒ 100 %.

**% agent** : prévues = `tours_max + 3` ; `vue` = 1, `tour` / `outil` k = 1 + k, `garde_fou` = `tours_max + 2`,
fin d'étape = 100 % ; arrondi entier. **% lot** : dossiers clos / dossiers.

**Liste blanche** : email, téléphone, IBAN, adresse, code postal et identifiant client de l'assuré ne sortent jamais de l'API.

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

404 `demande inconnue` / `lot inconnu` (les deux routes) ; sinon `text/event-stream` ; `: ouvert` à la connexion, `: ping` toutes les 15 s, puis un message par
événement du dossier (ou des dossiers du lot) :

```
event: avancement
data: {"type": "sous_etape", "reference": "KAL-26-0105", "etat": "estimation", "statut": "en_cours", "avancement_agent": 50}
```

`type` : `etape_debut` (% 0), `sous_etape` (% agent), `etape_fin` (100), `dossier_fin`. Source :
`pg_notify('kaldera_avancement', …)` émis par l'orchestrateur, l'agent et le reaper (best effort). À
l'ouverture et à chaque `etape_fin` / `dossier_fin`, l'IHM relit l'état complet (`GET`).

## 3. Lancer en local

```bash
make up && docker compose --profile integration up -d --wait postgres
make demo && make scenarios ARGS=--charger   # KAL-26-0101 en admission + 33 dossiers prêts
make api                      # http://127.0.0.1:8000/docs
make worker                   # analyse des pièces, admission en « prete »
make front                    # http://localhost:5173
```

Puis lancer le traitement depuis E1 (cocher des dossiers « Prête », « Traiter la sélection »).
