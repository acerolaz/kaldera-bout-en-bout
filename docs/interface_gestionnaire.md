# Interface gestionnaire : back-office

> Documentation de ce qui est **livré** (chantier 3). Spec C3-1 : `docs/superpowers/specs/2026-10-12-c3-1-design-system-design.md` ;
> spec C3-2 : `docs/superpowers/specs/2026-10-12-c3-2-lecture-e1-e2-design.md`. L'ancien espace assuré (UI1) est archivé dans
> `docs/interface_web.md`.

IHM **non sécurisée** (EX-D44) : usage local, données factices, ni authentification ni rôles. Elle n'interprète rien :
le serveur projette l'état en base (`src/kaldera/vue_gestionnaire.py`) et le front affiche.

## 1. Écrans

| Route | Écran | Livré |
|---|---|---|
| `/` | E1 · Liste des demandes : filtres (statut, issue, file, mode dégradé, recherche) mémorisés dans l'URL | C3-2 |
| `/demandes/:reference` | E2 · Dossier : en-tête, panneau Garanties, timeline des 5 étapes, carte anti-fraude | C3-2 |
| `/lots/:id` | E3 · Suivi de lot (cadre) | C3-3 |

## 2. API de lecture

Le front appelle `/api/…` ; le proxy Vite retire `/api` et transmet à FastAPI (`make api`, port 8000).

### `GET /demandes`

Paramètres facultatifs, combinés en ET (un paramètre vide est ignoré) : `statut` (`admission`, `en_cours`, `terminee`,
`secours`), `issue` (`acceptee`, `refusee`, `escalade`), `file`, `mode_degrade` (`true` / `false`), `q` (recherche sans
casse dans référence, nom, police). Réponse : liste triée par référence décroissante.

```json
[{"reference": "KAL-26-0203", "nom": "Durand", "prenom": "Paul", "police": "CTR-778803",
  "type_sinistre": "degat_des_eaux", "montant_declare": 9200.0, "statut": "terminee",
  "issue": "escalade", "file": "cellule_fraude", "mode_degrade": true}]
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

**Liste blanche** : email, téléphone, IBAN, adresse et identifiant client de l'assuré ne sortent jamais de l'API.

## 3. Lancer en local

```bash
make up && docker compose --profile integration up -d --wait postgres
make demo && make scenarios   # KAL-26-0101 en admission + les dossiers des scénarios
make api                      # http://127.0.0.1:8000/docs
make front                    # http://localhost:5173
```
