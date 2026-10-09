# Journal des ajustements

Chaque changement de borne, de garde, de frontière ou de routage laisse une ligne
(dossier de conception, 4.2). Mesures relevées avec `uv run pytest` sur la suite d'acceptance.

| Date | Scénario | Signal observé | Seuil | Ajustement | Avant → après |
|---|---|---|---|---|---|
| 2026-10-08 | suite complète | fiches `en_attente` (AF, INV, PAN) ; rôles mélangés ; pas de `bornes()` | EX-01, EX-02, EX-06 | agent généraliste remplacé par la machine à états T1–T11 + 4 agents + tool `is_eligible()` | acceptance 11/56 → 42/56 |
| 2026-10-08 | NOM-05 | refus « montant supérieur au plafond » | attendu : acceptée 3 000 € | plafond retiré de l'éligibilité, appliqué par l'estimation après la franchise | refusée → acceptée 3 000 € |
| 2026-10-08 | BCL-01 | relance sans fin possible (facture toujours illisible) | `relances_pieces_max` = 1 | garde T4 ; T5 sur borne pose `arret` | sans arrêt → escalade, `arret.borne = relances_pieces_max`, 4 étapes |
| 2026-10-08 | PAN-02 (partenaire à 5 s) | appel A2A sans délai (`timeout=None`) | `delai_partenaire_s` = 3, `duree_max_s` = 8 | délai = min(3 s, temps restant de la demande) | non borné → ≤ 3 s *(non encore éprouvé en acceptance : la requête non projetée est rejetée avant le délai, voir chantier 2)* |
| 2026-10-08 | test unitaire « compte-gouttes » (1 octet / 100 ms) | httpx borne chaque lecture, pas la durée totale : 103 s pour un délai de 0,5 s | échéance totale = délai | échéance globale autour de l'appel (fil abandonné au-delà) | 103 s → < 1 s |
| 2026-10-08 | lot unitaire (8 demandes de 0,2 s, `test_lot_traite_les_demandes_en_parallele`) | lot traité en séquentiel : durée = somme des demandes | §12 : une demande n'en retarde pas une autre (EX-D15) | `traiter_lot` en `ThreadPoolExecutor` | 1,63 s → 0,21 s *(lots `panne` en acceptance non discriminants : 0,01 s, la requête non projetée est rejetée avant le délai — à remesurer au chantier 2)* |
| 2026-10-08 | contrat non exploitable (`test_is_eligible_non_appele_si_contrat_non_valide`) | `is_eligible()` appelé sur un contrat non validé | EX-D40 | garde d'entrée T0 + règle 0 (escalade gestionnaire) | 1 appel → 0 appel |
| 2026-10-08 | exception imprévue (`test_exception_imprevue_rattrapee_par_le_filet`) | `RuntimeError` dans un agent remonte à l'appelant | EX-01 | filet niveau 1 dans `traiter`, file prudente | exception → escalade motivée |
| 2026-10-08 | invariance (`tests/unit/test_invariance.py`) | pièces lues directement dans la demande | EX-D28 (claim check) | pièces chargées par le port `DepotPieces`, vue de `pieces` seule à les recevoir | 34/34 issues identiques avant → après |
| 2026-10-08 | processus tué (`test_demande_morte_escaladee_depuis_le_snapshot`) | demande perdue si le processus meurt | EX-D24, EX-01 | snapshot après chaque transition + reaper (`en_cours` → `secours`, CAS) | aucune fiche → escalade de secours classée |
| 2026-10-08 | schéma 2.6 bis | la fiche n'est persistée nulle part ; une demande sans contrat ne peut être snapshotée | file humaine consultable ; EX-01 | écarts : `demandes.fiche jsonb`, `numero_contrat` nullable | — |
| 2026-10-08 | port `DepotPieces` | le niveau 0 a besoin du JSON, pas seulement de la référence | EX-D28 | `DepotPieces.initiales(demande)` au lieu de `(reference)` | — |
| 2026-10-08 | tests d'intégration | le rollback par test (`CLAUDE.md`) empêche d'éprouver la concurrence | 2 reapers, 1 seule réservation A2A | isolation par `TRUNCATE` | — |
| 2026-10-08 | NOM-01, base tombée après l'ouverture du pool (revue finale SP2) | 2 s d'attente par écriture × 6 écritures : 12,03 s, `duree_max_s` atteinte, escalade au lieu de 1 700 € | EX-01, §12 (10 s) | persistance coupée pour la demande au 1er échec ; attente d'écriture 0,5 s ; échec de connexion mémorisé 30 s | 12,03 s escalade → 0,51 s acceptée 1 700 € |
| 2026-10-08 | NOM-01 niveau 1 (`test_nom01_niveau_1_meme_issue_que_niveau_0`) | pièces et contrat lus dans le JSON | EX-D37, EX-D39 : fichier lu une fois, au dépôt ; le PDF fait foi | API de dépôt + worker + FakeVLM ; termes du contrat extraits sous 3 verrous | même issue niveau 0 → niveau 1 (acceptée 1 700 €) |
| 2026-10-08 | admission (schéma 2.6 bis) | l'admission ne savait pas quand le dossier est complet ; la tâche ne connaissait pas sa demande | EX-D40 | migration `002` : `demandes.soumise_le`, `file_ingestion.reference`, `file_ingestion.pris_le` | — |
| 2026-10-08 | invariants des pièces | une photo déposée comme facture passait l'analyse | descripteur fidèle au dépôt | invariant ajouté : type lu = type déclaré | — |
| 2026-10-08 | ports d'ingestion (spec SP2) | `RegistrePieces` et `DepotContrats` : une implémentation, aucun équivalent mémoire | YAGNI | un seul dépôt `IngestionPostgres` (API + worker) | — |
| 2026-10-08 | PDF abîmé (revue finale SP3a, 185/3000 PDF mutés) | `AttributeError` de pypdf : le worker meurt, chaque reprise replante, demande bloquée en `admission` | EX-01 : jamais de blocage silencieux | erreurs de pypdf rattrapées ; migration `003` : `essais`, échec après 3 prises (`ESSAIS_MAX`) | boucle infinie → escalade motivée |
| 2026-10-08 | sortie VLM hors des bornes de la base (`montant=1e12`, `plafond ≤ 0`) | CHECK refusé avant la fin de la tâche : reprise sans fin | EX-01 | bornes `numeric(10,2)` dans les schémas `AnalysePiece` / `ExtractionContrat` | boucle → pièce en échec / contrat non exploitable |
| 2026-10-08 | deux demandes sur un même contrat | un second PDF (erroné ou forgé) écrasait la ligne `contrats` partagée | « extrait une fois par contrat » (2.4 quater) | un contrat `valide` n'est jamais remplacé | termes écrasés → premier contrat valide fait foi |
| 2026-10-09 | générateur (`generer_pieces.py` du dossier) | lisait une demande par ligne (34 demandes perdues), barème limité à `essentiel` (`KeyError`), police Linux seule | EX-D42 | `tools/generer_pieces.py` : `scenario["demandes"]`, barème `regles.FORMULES`, police Pillow ; un numéro de contrat par scénario ING ; identifiant du document imprimé (le redépôt BCL-01 n'est plus un doublon) | 0 → 39 demandes générées, déterministes |
| 2026-10-09 | VLM réel (dossier 1.4 ter) | API vision Azure : images seules | verrou ③ indépendant du VLM | `pypdfium2` : page 1 rendue en PNG, aucun texte du fichier envoyé ; `ConfigLLM.vision` ; consigne `{"illisible": true}` | — |
| 2026-10-09 | épreuve FakeVLM (`test_chaine_complete_fakevlm`) | outillage d'épreuve à prouver indépendamment du modèle | contrats 100 %, ING-01 → 05, invariance 28/28 | seed par l'API + worker + épreuve | contrats 100 %, ING-01 → 05 ✅, invariance 28/28, protocole ✅ |
| 2026-10-09 | épreuve réelle (`make eval-ingestion`) | précision du VLM (aucun modèle configuré) | contrats nets 100 %, invariance 28/28 | — | non mesurée (aucun VLM configuré) |
| 2026-10-09 | UI1 · routeur `/assure` | le plan prévoyait de ne pas monter le routeur sans secret de session | spec §6 : sans secret, rien d'exposé | routeur toujours monté ; sans `KALDERA_SESSION_SECRET`, chaque route `/assure/*` répond 503 et l'API l'indique au démarrage (testable sans recharger le module) | routeur absent → 503 « espace assuré non configuré » |
| 2026-10-09 | UI1 · messages du chat | table `messages_assure` prévue par la spec | YAGNI : l'historique existe déjà | messages = événements `message` de `evenements_assure` ; la relecture du flux depuis 0 donne l'historique | 4 tables → 3 tables |
| 2026-10-09 | UI1 · outils de l'agent de relance | `etat_fichier` n'apporte rien au LLM : les raisons de rejet sont dans `liste_pieces` et il lui faut la référence pour la recopier | spec §5 : le LLM formule, le code calcule | outil `reference_relance` (intention, pièces concernées) au lieu d'`etat_fichier` | `etat_fichier` → `reference_relance` |
| 2026-10-09 | UI1 · liste déroulante | `Select` de shadcn : accessibilité et `selectOption` de Playwright | WCAG AA, test de bout en bout | `<select>` natif stylé | `Select` shadcn → `<select>` natif |
| 2026-10-09 | UI1 · contenu des événements | spec : contenu = DTO projeté, sans préciser lequel | confidentialité : rien de non projeté dans `evenements_assure` | `etape`, `piece` et `verdict` portent la `VueDemande` complète (le front remplace sa vue) ; seul `message` porte un `MessageChat` | — |
| 2026-10-09 | UI1 · ordre des pièces (`_manquantes()`) | pièces lues par `piece_id` (UUID aléatoire) : la « dernière » facture redéposée était choisie au hasard | la dernière pièce d'un type fait foi | migration `004` : `pieces.depose_le` ; lecture `ORDER BY depose_le, piece_id` | ordre aléatoire → ordre de dépôt |
| 2026-10-09 | UI1 · temps écoulé | aucune date de création de la demande | spec C3 : temps écoulé | migration `004` : `demandes.cree_le` ; horodatage de l'étape 1 = `cree_le` | — |
| 2026-10-09 | UI1 · secret de session vide (`KALDERA_SESSION_SECRET=` de `.env.example`) | un secret vide était accepté comme `SecretStr("")` : jetons forgeables | spec : secret requis | secret vide ou fait d'espaces ⇒ absent (503) | clé HMAC vide → 503 |
| 2026-10-09 | UI1 · connexion d'un compte bloqué | réponse sans hachage argon2 : le blocage se devinait au temps (énumération) | spec : même réponse quelle que soit la cause | hachage factice avant le retour, comme pour un compte inconnu | réponse immédiate → même coût qu'un essai |
| 2026-10-09 | UI1 · jetons de session | jetons sans état : la déconnexion et un changement de mot de passe n'invalident pas un jeton ouvert | durée de session 8 h | limite connue, non corrigée (OIDC ou jetons révocables plus tard) | jeton valable jusqu'à son expiration (8 h) |
| 2026-10-09 | UI1 · garde-fou de l'agent de relance | `TERMES_INTERDITS` laissait passer l'argent, la décision et l'état interne (EUR, virement, payé, approuvé, couvert, prise en charge, estimation, escalade, cellule, dégradé, chiffres + devise) | spec §5 : borné aux pièces | liste élargie ; `<` et `>` neutralisés dans la question de l'assuré (elle ne ferme plus `<donnees_non_fiables>`) | sondes de relecture acceptées → repli sur gabarit |
| 2026-10-09 | UI1 · événements du worker et du reaper | une insertion en échec avant `traiter()` envoyait le dossier au reaper ; une erreur de projection arrêtait worker et reaper | EX-01 : la base ne bloque jamais une décision | événements au mieux : `ErreurPersistance`, `KeyError`, `TypeError`, `ValueError`, `ValidationError` captées et journalisées dans `evenements.py` | issue modifiée par un événement → un événement manqué, rattrapé au rechargement |
| 2026-10-09 | UI1 · étapes 3 et 4 | événements émis après `traiter()` : contenu = vue finale | — | limite connue : les horodatages des étapes 3, 4 et 5 sont séparés de quelques millisecondes | — |
| 2026-10-09 | UI1 · flux SSE (`useFluxDemande`) | `EventSource` fermé par une erreur HTTP (401, 404, 502, 503) : « hors ligne » permanent, session expirée invisible | spec §6 : reconnexion sans perte ; Review Focus : session expirée | sonde `api.demande` : 401/404 ⇒ erreur affichée ; sinon réouverture après délai (rejeu depuis 0, idempotent) | flux mort → réouverture, 401/404 signalés |
| 2026-10-09 | UI1 · serveur e2e (`tests/e2e/serveur.py`) | sans `TEST_DATABASE_URL`, `pool("")` suit les variables `PG*` et le `TRUNCATE` vidait une base non voulue | base de test seule | le serveur refuse de démarrer sans l'URL (`SystemExit`) | vidage possible de toute base → refus |
| 2026-10-09 | UI1 · parcours de bout en bout (Playwright) | `cd front && TEST_DATABASE_URL=postgresql://kaldera:kaldera@localhost:5433/kaldera_test npx playwright test` : 3 passés, 1 ignoré (parcours complet en mobile ; desktop ignoré, une seule base de test) ; vert 3 fois de suite à l'implémentation, puis relancé à la rédaction du journal : même résultat ; `make front-e2e` lui-même non lancé (port 5433 occupé par un autre projet compose) | — | — | — |
| 2026-10-09 | UI1 · chat après le verdict (revue finale) | le flux se ferme au verdict : une question posée ensuite, et sa réponse, n'apparaissaient jamais | spec §5 : le chat sert aux pièces, avant la décision | chat masqué dès que la vue porte un verdict ; `POST /messages` répond 409 `dossier_clos` (`terminee`, `secours`) avant tout appel au LLM | messages perdus → chat fermé au verdict |
| 2026-10-09 | UI1 · panne au chargement (revue finale) | un 503 ou une coupure réseau au premier `GET` affichait « Ce dossier est introuvable » à vie | spec §6 : bandeau « service momentanément indisponible », le front réessaie | seuls 401/404 sont définitifs ; sinon bandeau et relecture de la vue toutes les 3 s ; « Mes sinistres » : bandeau et « Réessayer » ; connexion : 401 seul parle du mot de passe | « introuvable » → bandeau puis vue |
| 2026-10-09 | UI1 · horodatages (revue finale) | « Demande reçue » datée du premier dépôt (événement `piece`, colonne `etape` = 1) ; l'étape 5 sans heure en direct (vue construite avant l'insertion) | décision 7 : étape 1 = `cree_le` | `cree_le` l'emporte sur la colonne ; la vue publiée reçoit l'heure de sa propre étape | heure du dépôt → heure de création ; étape 5 sans heure → avec |
| 2026-10-09 | UI1 · repli de l'agent de relance (revue finale) | `MesureAgent` jeté : un repli ne laissait aucune trace | repli tracé (`AgentLLM`) | journal INFO `mode` et `cause` seulement (jamais le texte, la question ni l'identité) | repli muet → repli journalisé |
| 2026-10-09 | UI1 · flux SSE abandonné (revue finale) | un flux déconnecté interrogeait la base chaque seconde jusqu'à 900 s | §12 : rien ne tourne pour rien | sortie dès que `request.is_disconnected()` | jusqu'à 900 requêtes → 0 |

## Bornes provisoires en vigueur

| Borne | Valeur | Justification | Statut |
|---|---|---|---|
| `etapes_max` | 12 | chemin nominal le plus long : 6 étapes (avec relance) → marge ×2 | à éprouver au chantier 2 |
| `duree_max_s` | 8 | 10 s (§12) moins 2 s de marge | à éprouver au chantier 2 |
| `relances_pieces_max` | 1 | déduite des scénarios NOM-07 / BCL-01 | à valider avec le métier |
| `delai_partenaire_s` | 3 | abandon client du contrat partenaire | à éprouver avec la projection 7 champs |

## Restant (chantier 2)

14 tests rouges, tous dans `tests/acceptance/test_collaboration_a2a.py` :

| Tests | Ce qu'ils éprouvent | Cause bloquante actuelle |
|---|---|---|
| `test_echange_antifraude_…[AF-01…AF-07]` | requête conforme au contrat, données minimisées | requête non projetée sur les 7 champs : le partenaire la refuse |
| `test_reponse_invalide_…[INV-01…INV-07]` | rejet d'une réponse non conforme (validation 4 couches) | même refus en amont ; la validation des réponses reste à écrire derrière |

Le plan estimait ~49 verts sur 56 en acceptance, en supposant que des INV passeraient via le
mode dégradé ; ils vérifient aussi la forme de la requête, d'où 42/56.

## 2026-10-08 — Agents LLM (dossier v3, EX-D30 → EX-D36)

**Constat.** Les 4 agents étaient des fonctions : un workflow, pas une équipe d'agents.
**Ajustement.** Chaque agent a son LLM (Azure, modèle lu dans le `.env` par agent), son prompt
versionné, ses outils exclusifs et un garde-fou de sortie ; le code déterministe d'avant devient
la référence et le repli. Machine à états, orchestrateur, propriété des sections et A2A inchangés.
**Mesure** (chiffres réellement observés). Critère d'invariance (`tests/unit/test_invariance.py`) : 34 demandes, issue / file /
montant / mode dégradé identiques en mode fake et en mode repli. Les 7 saboteurs du FakeLLM
finissent tous en repli tracé, patch identique (`test_chaque_saboteur_finit_en_repli`,
`tests/unit/test_agents_llm.py`). Partenaire appelé une seule fois par demande dans tous les cas
(`test_partenaire_appele_une_seule_fois`, même fichier). Suite complète : 14 rouges (A2A), 268 verts.
**Reste au chantier 2.** `make eval` (matrice agent × modèle), disjoncteur LLM, 14 tests A2A.
