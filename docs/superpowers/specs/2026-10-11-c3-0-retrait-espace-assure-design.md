# C3-0 · Retrait de l'espace assuré

> Source : `prompt_ui.md` v5, chantier 3 (EX-D44 : l'IHM devient un back-office gestionnaire).
> Branche : `feature/chantier3-c3-0-retrait` · point de départ : `0dafffc` (dossier v2, #12).
> Premier sous-projet du chantier 3 : **C3-0 retrait** → C3-1 design system et socle → C3-2 lecture
> (E1, E2) → C3-3 temps réel et lots (E3) → C3-4 reprise d'étape → C3-5 documents et recette.

## 1. Objectif

Retirer **entièrement** l'espace assuré (UI1, PR #3) — front **et** back-end — pour laisser une
base propre au back-office gestionnaire. Aucune fonctionnalité du back-office n'est livrée ici.

**Critère de sortie** : `make test`, `make test-integration`, `make lint`, `make typecheck` verts ;
`npm run build`, `npm test`, `npm run lint`, `make front-e2e` verts ; plus aucune référence à
`api_assure`, `auth`, `vue_assure`, `assure_postgres`, `evenements`, `demo_assure` ni à l'agent de
relance dans `src/`, `tests/`, `tools/`, `front/src/`, `Makefile`, `docs/recette/` ; cahier de
recette régénéré, déroulé de S-01 à A-04 sur la branche. Dossier de conception régénéré et copié à la racine du
brief, sans aucune mention de l'espace assuré.

### Décisions prises

| Sujet | Décision |
|---|---|
| Périmètre | Front **et** back-end (choix du 11/10/2026). |
| Base | Nouvelle migration `005_retrait_assure.sql` qui supprime les tables ; `004` reste intacte (historique honnête, une base déjà migrée suit sans `recette-reset`). |
| Colonnes de `004` | `demandes.cree_le` et `pieces.depose_le` **conservées** : `postgres.py` trie les pièces par `depose_le` ; `cree_le` servira au tri d'E1. |
| Deux « relances » | L'**agent de relance** (chat, `relance.py`) est retiré. La **relance métier** (demande de complément : colonne `pieces.relance`, `depot_pour`) reste : l'agent pièces en dépend. |
| `espace_assure.py` | Renommé `depots_assure.py` (même fonction `depot_pour`, nom neutre) : c'est un utilitaire métier, pas de l'UI. |
| Points d'accroche | Les appels de publication dans `worker.py` et `reaper.py` sont **supprimés**, pas remplacés : les événements gestionnaire arrivent en C3-3. |
| Harnais e2e | Conservé (`tests/e2e/serveur.py`, Playwright) ; un test de fumée remplace le parcours assuré pour que `make front-e2e` reste vert. |
| Dossier de démo | `tools/demo_assure.py` → `tools/demo.py` : crée toujours KAL-26-0101 et dépose son contrat, **sans compte** ; `make recette` l'appelle encore (le back-office en aura besoin). |
| Cahier de recette | Mis à jour **dans cette PR** (générateur + PDF régénéré) : il doit décrire le système livré. Les cas assuré U-01 → U-17 sont retirés ; chaque sous-projet C3-1 → C3-4 ajoute ses cas IHM, C3-5 les déroule tous. |
| Dossier de conception | Mis à jour **dans cette PR** : les 16 pages HTML qui citent l'espace assuré sont corrigées, le PDF est régénéré (`make dossier`) puis copié à la racine du brief (`kaldera-agents/dossier-conception.pdf`). Le dossier décrit le système **sans** espace assuré ; les sections IHM gestionnaire arrivent avec C3-1 → C3-4. |

### Hors périmètre

Tout le back-office (design system, écrans, API gestionnaire, SSE, reprise, notes), y compris ses
sections dans le dossier de conception ; la version texte `dossier-conception-v2.md` citée par le
brief (elle n'existe pas encore : C3-5).

## 2. Back-end

### 2.1 Modules supprimés

| Module | Rôle actuel |
|---|---|
| `src/kaldera/api_assure.py` | routeur `/assure/*` (session, demandes, dépôt, soumission, chat, flux SSE) |
| `src/kaldera/auth.py` | comptes, hachage, sessions, `ConfigAssure` |
| `src/kaldera/relance.py` | agent de relance (chat) |
| `src/kaldera/vue_assure.py` | projection de confidentialité vers l'assuré |
| `src/kaldera/assure_postgres.py` | `DepotAssure` (comptes, événements) |
| `src/kaldera/evenements.py` | publication dans `evenements_assure` |

### 2.2 Modules modifiés

| Fichier | Changement |
|---|---|
| `src/kaldera/api.py` | ne monte plus `routeur_assure` ; retire l'avertissement `KALDERA_SESSION_SECRET`. Les routes de dépôt (`POST /demandes`, `/pieces`, `/soumettre`, `GET /demandes/{ref}`) restent : le seed et l'épreuve les utilisent. |
| `src/kaldera/worker.py` | retire `publier_vue`, `publier_message`, `message_spontane` et `DepotAssure` ; le traitement et l'admission sont inchangés. |
| `src/kaldera/reaper.py` | retire la publication du verdict ; l'escalade reste. |
| `src/kaldera/llm.py` | retire le rôle `relance` de `ConfigAgents` (`KALDERA_RELANCE__*`). |
| `src/kaldera/espace_assure.py` → `depots_assure.py` | renommage ; imports adaptés dans `agents.py`, `agents_llm.py`, `tests/unit/test_ports.py`, `tests/unit/test_agents_llm.py`. |
| `.env.example` | retire `KALDERA_SESSION_SECRET`, `KALDERA_COOKIE_SECURE`, `KALDERA_RELANCE__*`. |
| `tools/demo_assure.py` → `tools/demo.py` | `preparer(connexions, reference="KAL-26-0101")` crée la demande et dépose le contrat ; plus d'identifiant ni de mot de passe (`KALDERA_DEMO_MOT_DE_PASSE` retiré). Message : « Demande KAL-26-0101 prête ». |

### 2.3 Migration `005_retrait_assure.sql`

```sql
-- v5 : l'espace assuré (UI1) est retiré, remplacé par le back-office gestionnaire (chantier 3).
-- cree_le et depose_le (004) restent : tri des pièces et tri de la liste des demandes.
DROP TABLE IF EXISTS evenements_assure, demandes_assure, utilisateurs;
```

## 3. Tests

| Action | Fichiers |
|---|---|
| Supprimés | `tests/unit/test_auth.py`, `test_relance.py`, `test_vue_assure.py`, `test_confidentialite_assure.py` ; `tests/integration/test_api_assure.py`, `test_assure_postgres.py`, `test_evenements.py` |
| Adaptés | `tests/conftest.py` et `tests/e2e/serveur.py` : tables supprimées retirées des `TRUNCATE` ; `serveur.py` prépare le dossier de démo via `tools.demo`, sans compte. `test_demo_assure.py` → `test_demo.py` : mêmes deux cas (préparer puis refuser ; contrat illisible n'écrit rien), sans l'assertion de compte. |
| Ajouté | aucun test Python : le retrait est couvert par la suite existante et par le contrôle `grep` du critère de sortie. |

## 4. Front

| Action | Fichiers |
|---|---|
| Supprimés | `pages/` (`Connexion`, `MesSinistres`, `Sinistre`, `pages.test.tsx`) ; `components/` métier (`Chat`, `Depot`, `Soumettre`, `ListePieces`, `Stepper`, `VerdictCarte`, `BandeauStatut`, `composants.test.tsx`, `Chat.test.tsx`) ; `useFluxDemande.ts` (+ test), `api.ts`, `textes.ts`, `test/donnees.ts` ; `e2e/parcours.spec.ts` |
| Conservés | `components/ui/*` (shadcn), `index.css`, `format.ts` (+ test), `lib/utils.ts`, `test/contraste.test.ts`, `test/setup.ts`, configuration Vite / Vitest / Playwright / oxlint |
| `App.tsx` | une page d'attente : titre « Kaldera · back-office gestionnaire », texte « en construction (chantier 3) » ; plus de routeur ni de `Toaster` |
| Ajouté | `e2e/fumee.spec.ts` : la page d'attente s'affiche et `axe` ne relève aucune violation |
| Dépendances | `react-router-dom` et `sonner` restent (E1 → E2 → E3 et notifications en C3-1/C3-2) |

## 5. Makefile et documents

- `Makefile` : `demo-assure` → `demo` (cible et `.PHONY`) ; `recette` lance `tools.demo`.
- **Cahier de recette** (`docs/recette/generer_cahier_recette.py`, puis `cahier-recette.pdf` régénéré) :

  | Partie | Changement |
  |---|---|
  | Page de garde | objet : « setup par commandes make (administrateur), interface gestionnaire en construction, contrôles d'exploitation » |
  | Variables `.env` | retire `KALDERA_SESSION_SECRET`, `KALDERA_COOKIE_SECURE`, `KALDERA_RELANCE__MODELE` |
  | S-01 | résultat attendu : « Demande KAL-26-0101 prête » (plus de connexion) |
  | S-02 | `/docs` liste les routes `/demandes` ; **aucune** route `/assure/*` |
  | S-04 | Vite sert la page d'attente du back-office sur http://localhost:5173 |
  | Données de démo | retire le compte assuré et les pièces à déposer à la main ; garde le dossier KAL-26-0101 et son verdict attendu |
  | Section 2 | « Parcours dans l'interface (utilisateur assuré) » U-01 → U-17 **remplacée** par « Interface gestionnaire » : U-01 « ouvrir http://localhost:5173 » ⇒ page d'attente « back-office gestionnaire, en construction » ; note : cas EX-D44 → EX-D51 ajoutés par C3-1 → C3-4 |
  | A-01 → A-04 | inchangés (A-03 `make scenarios` traite toujours KAL-26-0101) ; A-01 vérifié contre le nouveau déroulé |
  | Statut | chaque cas déroulé une fois sur la branche ; statut renseigné dans le PDF |
- `README.md` : retire la section espace assuré, les identifiants de démo et `KALDERA_SESSION_SECRET` ;
  une ligne « IHM : back-office gestionnaire en cours (chantier 3) ».
- `docs/journal_ajustements.md` : entrée « v5 · espace assuré retiré (front, API `/assure`, agent de
  relance, tables) ; remplacé par le back-office gestionnaire ».
- `docs/interface_web.md` : bandeau en tête « retiré en v5, remplacé par l'IHM gestionnaire (chantier 3) ».
- **Dossier de conception** (`docs/conception/pages/*.html` → `make dossier` → copie vers
  `kaldera-agents/dossier-conception.pdf`, 48 pages aujourd'hui, 19 concernées) :

  | Page HTML (page PDF) | Changement |
  |---|---|
  | `295-espace-assure.html` (p30), `296-parcours-relance.html` (p31) | **supprimées** : l'espace assuré et le parcours de relance n'existent plus |
  | `020-sommaire.html` (p2) | entrées 2.8 et agent de relance retirées ; numérotation recalculée |
  | `040-carte-agents.html` (p4), `060-fiches-agents.html` (p6) | agent de relance retiré de la carte et des fiches ; les 4 agents métier inchangés |
  | `090-fabrique.html` (p9-10), `200-bornes-llm.html` (p20) | rôle LLM `relance` retiré (modèle, bornes, chat) |
  | `180-bornes.html` (p18) | bornes de l'espace assuré retirées |
  | `230-ingestion.html` (p23), `280-generateur.html` (p28), `310-contrat-champs.html` (p33) | « déposé par l'espace assuré » ⇒ « déposé par l'API (`POST /demandes/{ref}/pieces`) » |
  | `260-persistance.html` (p26), `270-schema.html` (p27) | tables `utilisateurs`, `demandes_assure`, `evenements_assure` retirées du schéma ; migration `005` mentionnée |
  | `380-synthese.html` (p41-42) | choix tranchés et points ouverts liés à UI1 retirés ; ligne « v5 : espace assuré retiré, back-office gestionnaire (chantier 3) » |
  | `410-glossaire-2.html` (p45), `440-glossaire-5.html` (p48) | entrées espace assuré, agent de relance, session, `evenements_assure`, `vue_assure` retirées |

  Contrôles : `make dossier` ne signale aucun débordement de pied de page ; une extraction texte du
  PDF (`pypdf`) ne trouve plus « espace assuré », « agent de relance », `/assure`, `vue_assure`,
  `evenements_assure`, `utilisateurs`, `SESSION_SECRET`.

## 6. Risques

| Risque | Parade |
|---|---|
| Un test d'acceptance ou l'épreuve dépend d'un événement assuré | la suite complète (`make test`, `make test-integration`) tourne avant la PR ; tout échec est traité ici, pas contourné. |
| Confusion entre les deux « relances » | seul `relance.py` et le rôle LLM `relance` partent ; `pieces.relance` et `depot_pour` sont vérifiés intacts par les tests de l'agent pièces. |
| Base locale déjà migrée en `004` | `005` utilise `DROP TABLE IF EXISTS` : rejouable, aucune manipulation manuelle. |
