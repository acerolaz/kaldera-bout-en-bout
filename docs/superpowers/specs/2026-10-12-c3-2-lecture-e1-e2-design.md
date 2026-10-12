# C3-2 · Lecture : E1 « Liste des demandes » et E2 « Dossier »

> Source : `prompt_ui.md` v5, chantier 3 (EX-D44, EX-D47 ; étapes 16 et 18 de l'ordre
> d'implémentation, partie lecture). Branche : `feature/chantier3-c3-2-lecture` · point de départ :
> `188894d` (C3-1 fusionné, #14).
> Chantier 3 : C3-0 retrait ✅ → C3-1 design system et socle ✅ → **C3-2 lecture (E1, E2)** → C3-3
> temps réel et lots (E3) → C3-4 reprise d'étape et notes → C3-5 documents et recette.

## 1. Objectif

Donner au gestionnaire la **lecture** des dossiers traités par l'équipe d'agents : E1 liste et filtre
les demandes, E2 restitue ce que chaque agent a fait (timeline, garanties, carte anti-fraude,
issue). L'IHM **n'interprète rien** (EX-D44) : une **projection serveur** transforme l'état en base
en vues typées ; le front les affiche.

| Exigence | Où |
|---|---|
| EX-D44 aucune règle métier dans l'IHM | §2 (projection serveur), §3 |
| EX-D47 détail par étape : statut, durée, modèle et mode, résumé du patch, transition ; carte anti-fraude ; garanties du contrat | §2.3, §3.3 |
| EX-D51 statuts = icône + libellé + couleur (`<Statut>` de C3-1) | §3 |
| Checklist UX : états chargement / vide / erreur, clavier, axe | §3, §5 |

**Critère de sortie** : `make test`, `make lint`, `make typecheck`, `make test-integration` verts ;
`npm test`, `npm run lint`, `npm run build`, `make front-e2e` verts ; cahier de recette régénéré
et déroulé (U-01 → U-10) ; dossier de conception régénéré avec la page 2.9, sans débordement,
copié à la racine du brief.

### Décisions prises

| Sujet | Décision |
|---|---|
| Périmètre de E1 | **Lecture seule** : ni cases à cocher, ni « Traiter la sélection », ni règle de non-sélectionnabilité (C3-3, avec `POST /traitements` et E3). |
| Où interpréter l'état | **Projection serveur** `kaldera/vue_gestionnaire.py`, fonctions pures `EtatDemande` → schémas Pydantic ; l'API renvoie ces vues ; le flux SSE de C3-3 réutilisera la même projection. |
| Branchement front ↔ API | Proxy Vite `/api` → `http://127.0.0.1:8000` (même origine, pas de CORS). |
| Lecture côté front | **TanStack Query** (`@tanstack/react-query`), stack nommée par le brief ; seule dépendance ajoutée. |
| Filtres et pagination | Filtres **côté serveur** (paramètres de requête), filtrage en Python sur les lignes lues ; **pas de pagination** (données factices, quelques dizaines de dossiers). |
| Données personnelles | **Liste blanche** : seuls nom, prénom, n° de police, formule et les champs listés au §2 sortent de l'API ; email, téléphone, IBAN, adresse, `id_client` jamais. |
| Compatibilité de `GET /demandes/{ref}` | La réponse devient `DossierVue`, **sur-ensemble** de l'actuel `StatutDemande` (`reference`, `statut`, `fiche` conservés) : `tools/seed.py` et les tests du worker continuent de lire `statut`. |
| Bouton « Reprendre » | **Non affiché** en C3-2 (pas de bouton mort) ; arrive en C3-4. |
| Avancement du dossier | **Écart assumé au brief** (« (termine + sautee) / 5 ») : une étape finie en `repli` ou `degrade` compte aussi comme faite, sinon la barre stagne alors que l'étape est terminée. Un état terminal vaut 100 % dans les deux lectures. |
| Titre de E2 | Le `<h1>` reste « Dossier {reference} » (tests C3-1, recette U-04) ; nom et prénom de l'assuré juste en dessous. |

### Hors périmètre

Sélection et `POST /traitements`, E3, SSE et statut `en_cours` en direct (C3-3) ; reprise d'étape,
notes, table `notes_etape` (C3-4) ; `make ui` ; toute modification de l'orchestrateur, des agents
ou du schéma SQL.

## 2. Back-end

### 2.1 Projection (`src/kaldera/vue_gestionnaire.py`)

Fonctions **pures** (aucune entrée / sortie), testables sur des états construits à la main :

- `ligne(reference: str, statut: str, etat: EtatDemande) -> LigneDemande`
- `dossier(reference: str, statut: str, fiche: dict | None, etat: EtatDemande) -> DossierVue`

Tolérance : un champ absent de l'état (dossier en `admission`, état ancien) donne une valeur vide
ou `en_attente`, jamais une exception.

### 2.2 `LigneDemande` (E1)

| Champ | Source |
|---|---|
| `reference` | colonne `demandes.reference` |
| `nom`, `prenom` | `etat.demande.assure` |
| `police` | `etat.demande.contrat.numero` |
| `type_sinistre`, `montant_declare` | `etat.demande.sinistre` |
| `statut` | colonne `demandes.statut` (`admission` / `en_cours` / `terminee` / `secours`) |
| `issue` | `acceptee` / `refusee` / `escalade` (de `etat.issue`), ou `null` |
| `file` | `etat.issue.file` ou `null` |
| `mode_degrade` | `etat.issue.mode_degrade` (faux si pas d'issue) |

### 2.3 `DossierVue` (E2)

- **Compatibilité** : `reference`, `statut`, `fiche` (fiche de secours, inchangée).
- **En-tête** : `nom`, `prenom`, `police`, `formule`, `avancement` (0–100), `duree_ms`,
  `budget_ms` (= `Bornes.duree_max_s` × 1000), `issue`, `file`, `motif`, `mode_degrade`,
  `montant_rembourse`.
- **`garanties`** : `formule`, `franchise` et `plafond` (barème `regles.FORMULES` de la formule),
  `date_souscription`, `statut_contrat`, `cotisations_a_jour`, `statut_extraction`, `source`,
  `modele`, `sha256` (de `etat.contrat`).
- **`etapes`** : exactement 5 cartes, dans l'ordre `eligibilite`, `pieces`, `estimation`,
  `antifraude`, `decision` :

| Champ de carte | Source |
|---|---|
| `etat` | nom de l'étape |
| `statut` | règle du §2.4 |
| `avancement` | 100 si l'étape est faite (présente dans la trace ou court-circuitée), 0 sinon (sous-étapes en C3-3) |
| `duree_ms`, `latence_llm_ms` | entrée de trace (`mesure`) |
| `modele`, `mode`, `cause`, `tours_llm`, `jetons`, `sortie_rejetee` | entrée de trace (`mesure`) |
| `de`, `vers`, `garde` | entrée de trace |
| `resume` | gabarit du §2.5 |

  Si une étape apparaît plusieurs fois dans la trace (relance de pièces), la carte reflète la
  **dernière** entrée et `passages` en donne le nombre.
- **`antifraude`** (carte détaillée, `null` si l'étape n'a pas été atteinte) : `requis`,
  `indicateurs` (F1–F4), `statut` (`ok` si avis obtenu, sinon `indisponible` / `non_requis`),
  `niveau`, `score`, `evaluation_id`, `version_modele`, `note`, `cause`.
- **`arret`** : `borne`, `valeur`, `etat` si une borne a interrompu le flux, sinon `null`.

**Avancement du dossier** : (étapes `termine` + `sautee` + `repli` + `degrade`) / 5 × 100 ;
statut `terminee` ou `secours` ⇒ 100.

### 2.4 Statut d'affichage d'une étape (codes du catalogue `STATUTS` de C3-1)

Dans l'ordre, la première règle vraie gagne :

| Condition | Statut |
|---|---|
| étape absente de la trace, mais une étape aval y figure (court-circuit : la machine saute de `eligibilite` à `decision` sans tracer les étapes intermédiaires) | `sautee` |
| étape absente de la trace, aucune étape aval n'y figure | `en_attente` |
| garde d'entrée (action non exécutée : `ecrit` vide, `duree_ms` 0, pas de `mode`) | `sautee` |
| `statut` de trace `echec` et étape `antifraude` avec avis indisponible | `degrade` |
| `statut` de trace `echec` | `echec` |
| `mode` = `repli` | `repli` |
| sinon | `termine` |

`en_cours` n'est jamais produit en C3-2 (réservé au temps réel, C3-3).

Les cartes sont rattachées aux entrées de trace par leur `action`. Une entrée `filet_securite`
(filet niveau 1, agent `orchestrateur`) n'a pas de carte propre : elle marque la carte de son état
`de` en `echec`, avec le résumé « Filet de sécurité : <erreur> ».

### 2.5 Résumé du patch (gabarits déterministes, sans LLM)

| Étape | Gabarit (exemples) |
|---|---|
| `eligibilite` | « Éligible » · « Non éligible : E2, E4 » |
| `pieces` | « Pièces complètes (3 retenues) » · « Incomplet : manque facture » |
| `estimation` | « Estimé 1 230 € = min(déclaré 1 850 €, justifié 1 380 €) − franchise 150 €, plafond 8 000 € non atteint » |
| `antifraude` | « Avis non requis » · « Avis obtenu : niveau faible, score 12 » · « Avis indisponible : <cause> » |
| toute étape `sautee` | « Sautée (garde <garde>) » (garde d'entrée) · « Sautée (court-circuit) » (étape non tracée) |
| `decision` | « Acceptée : 1 230 € » · « Refusée : <motif> » · « Escaladée vers <file> : <motif> » |

Montants formatés en français (espace insécable des milliers, « € »). Section absente ⇒ résumé vide.

### 2.6 Routes (`src/kaldera/api.py`, routes minces)

| Méthode | Route | Réponse |
|---|---|---|
| GET | `/demandes?statut=&issue=&file=&mode_degrade=&q=` | `list[LigneDemande]`, triée par référence décroissante ; `q` (insensible à la casse) cherche dans référence, nom, police ; filtres combinés en ET |
| GET | `/demandes/{reference}` | `DossierVue` ; 404 « demande inconnue » |

Lecture : méthodes `lister()` et `lire_dossier(reference)` sur le dépôt PostgreSQL existant
(`ingestion_postgres.py`) qui lisent `reference`, `statut`, `fiche`, `etat` ; filtrage et
projection en Python.

### 2.7 Tests back-end

| Fichier | Vérifie |
|---|---|
| `tests/unit/test_vue_gestionnaire.py` | chaque ligne du §2.4 ; chaque gabarit du §2.5 ; avancement ; état minimal (`admission`) sans exception ; relance de pièces (`passages`) ; **liste blanche** : aucune valeur d'email, téléphone, IBAN, adresse dans `model_dump_json()` |
| `tests/integration/test_api.py` | `GET /demandes` (filtres, `q`, tri, liste vide) ; `GET /demandes/{ref}` (clés de `DossierVue`, 404) ; compatibilité `statut` |

## 3. Front (`front/src/`)

### 3.1 Branchement

- `vite.config.ts` : `server.proxy = { "/api": { target: "http://127.0.0.1:8000", rewrite: retire "/api" } }`.
- `main.tsx` / `App.tsx` : `QueryClientProvider` (un `QueryClient` créé dans `App`, pas de global
  mutable de module).
- `api.ts` : `lire<T>(chemin)` sur `fetch("/api" + chemin)`, lève `ErreurApi(statut, message)` ;
  types `LigneDemande`, `DossierVue`, `Etape`, `Garanties`, `CarteAntifraude` écrits à la main
  (miroir des schémas Pydantic, vérifiés par le test d'intégration et les fixtures).

### 3.2 E1 · Liste des demandes (`/`)

- Barre de filtres (`<form role="search">`) : recherche texte (référence, nom, police), `<select>`
  natifs statut / issue / file, case « Mode dégradé » ; **filtres dans l'URL**
  (`useSearchParams`), conservés au rechargement et au retour arrière.
- Tableau dense (`<table>`, `<caption>` masquée visuellement) : référence (lien vers E2, Plex
  Mono) · nom, prénom · police (Plex Mono) · type de sinistre · montant déclaré (`tabular-nums`,
  `format.ts`) · statut (`<Statut>`) · issue (`<Statut>`) · file · badge `mode_degrade`
  (`<Statut>`). Lignes de 40 px, en-têtes collants.
- États : chargement (squelettes de 40 px, `aria-busy="true"`) ; vide avec filtres (« Aucune
  demande ne correspond aux filtres » + bouton « Effacer les filtres ») ; base vide (« Aucune
  demande en base : lancer `make demo` ») ; erreur (`role="alert"`, message + « Réessayer »).

### 3.3 E2 · Dossier (`/demandes/:reference`)

- En-tête : `<h1>` « Dossier {reference} » (inchangé depuis C3-1), puis nom et prénom, police,
  formule, statut et issue (`<Statut>`), file et motif ; avancement (`role="progressbar"`,
  `aria-valuenow`) ; durée / budget (« 2,4 s / 8 s », `tabular-nums`) ; montant remboursé.
- Bouton **« Garanties »** ⇒ `Sheet` shadcn (lecture seule, focus piégé, Échap ferme, focus rendu
  au bouton) : formule, franchise, plafond, date de souscription, statut du contrat, cotisations,
  extraction (statut, source, modèle, sha256 abrégé).
- Timeline : `<ol>` de 5 cartes (`<li>`) ; par carte : nom de l'étape, `<Statut>`, durée,
  modèle et mode (+ cause), tours, jetons, transition « de → vers (garde) », résumé ; carte
  `antifraude` enrichie de la carte détaillée ; passages > 1 signalés.
- Encadré « Borne atteinte » (`<Statut code="borne">`) si `arret`.
- 404 ⇒ « Dossier introuvable » + lien « Retour à la liste des demandes » ; erreur ⇒ `role="alert"`
  + « Réessayer » ; chargement ⇒ squelettes.

### 3.4 Tests front

| Fichier | Vérifie |
|---|---|
| `src/pages/ListeDemandes.test.tsx` | colonnes et `<Statut>` ; filtres ⇒ URL et requête ; « Effacer les filtres » ; états chargement / vide / base vide / erreur + Réessayer ; axe |
| `src/pages/Dossier.test.tsx` | en-tête, progressbar, 5 cartes et leurs statuts ; carte anti-fraude ; Garanties au clavier (ouverture, Échap, focus rendu) ; 404 ; axe |
| `src/api.test.ts` | `lire` : succès, `ErreurApi` sur 404 / 500 |
| `e2e/lecture.spec.ts` | contre la base de test amorcée : E1 liste et filtre, clic sur une référence ⇒ E2, timeline et Garanties ; axe dans les deux thèmes |

Fixtures front : JSON copiés d'une réponse réelle de l'API (scénario nominal et scénario dégradé).

## 4. Documents

| Document | Mise à jour |
|---|---|
| Cahier de recette (générateur + PDF, déroulé) | **U-05** E1 (liste après `make demo` / `make scenarios`, colonnes, statuts icône + libellé) ; **U-06** filtres et recherche, URL conservée, « Effacer les filtres » ; **U-07** E2 (en-tête, %, durée / 8 s, 5 cartes, résumés) ; **U-08** Garanties au clavier ; **U-09** carte anti-fraude sur un scénario dégradé (`indisponible`, motif, carte `degrade`) ; **U-10** états (API arrêtée ⇒ erreur + Réessayer, base vide, référence inconnue). Légende U-01 → U-10. |
| Dossier de conception (`make dossier` + copie à la racine) | page `299-ihm-lecture.html`, section « 2.9 IHM gestionnaire · E1 et E2 » (écrans, projection serveur, statut d'affichage d'une étape, avancement, liste blanche, routes) ; sommaire ; glossaire (projection, vue gestionnaire). |
| `README.md` | section IHM : E1 et E2, deux captures (`docs/captures/e1-liste.png`, `e2-dossier.png`). |
| `docs/interface_web.md` | routes `GET /demandes` et `GET /demandes/{ref}`, paramètres, exemple de réponse. |
| `docs/journal_ajustements.md` | une ligne si un ajustement est nécessaire. |

## 5. Risques

| Risque | Parade |
|---|---|
| Fuite de données personnelles | liste blanche dans la projection ; test qui cherche email, téléphone, IBAN, adresse dans le JSON |
| États en base de formes différentes (anciens, `admission`) | projection tolérante, testée sur un état minimal et sur un état réel de chaque scénario |
| Divergence types TS / schémas Pydantic | test d'intégration sur les clés ; fixtures front copiées d'une réponse réelle |
| Statut d'affichage trompeur (garde vs repli) | règle ordonnée du §2.4, une ligne de test par condition |
| `make front-e2e` dépend de données amorcées | le serveur e2e (`tests/e2e/serveur.py`) amorce la base de test avec au moins un dossier nominal et un dossier dégradé (seule modification Python hors `src/kaldera/`, côté tests) |
