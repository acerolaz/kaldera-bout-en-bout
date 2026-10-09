# Addendum au dossier de conception — écarts avec le code

*Dossier de conception du 8 octobre 2026 · code au commit `a5dc629` (fin du chantier 2) · audit du
9 octobre 2026.*

Le dossier a été écrit avant le chantier 2 (liaison A2A, monitorage, LLM réel, interface web).
Cet addendum liste ce qui, dans le dossier, ne correspond plus au code, pour qu'un lecteur qui
part du dossier ne soit pas induit en erreur. Quand un écart est déjà consigné dans
`docs/journal_ajustements.md`, la colonne « Journal » le signale. Les numéros de page renvoient
au PDF.

## 1. Écarts majeurs

| # | Dossier | Code | Journal |
|---|---|---|---|
| 1 | p. 7, 10, 38, 42 — `ClientLLM` avec adaptateurs Anthropic / OpenAI / local / fake ; `fournisseur` au choix | Un seul fournisseur réel : Azure AI Foundry, via `azure-ai-inference` (`ChatCompletionsClient`). `fournisseur: Literal["azure"]` (`src/kaldera/llm.py`), plus `FakeLLM` pour les tests | non |
| 2 | p. 10, 38 — un modèle par rôle, exemples Claude Haiku / Sonnet / Opus 5.5, choix final « par la mesure » (4.3) | La configuration permet toujours un modèle par rôle, mais `.env.example` met `Kimi-K2.6` sur les 4 agents et `gpt-4.1` sur le VLM. La mesure qui devait trancher (`make eval`) n'a pas encore été lancée avec des clés : l'épreuve de référence a tourné sans LLM (« llm 0 / repli 116 », `docs/epreuves/epreuve-2026-10-09.md`) | mesure manquante : oui |
| 3 | p. 6, 8, 19 — le LLM choisit ses outils, décide quand consulter le partenaire ; la frise montre le LLM antifraude puis l'appel A2A « dans l'outil » | Chaque agent calcule d'abord sa **référence déterministe**, qui sert aussi de repli. Pour l'antifraude, c'est elle qui appelle le partenaire, dès qu'un indicateur F1–F4 est levé, **avant** le LLM (`agents.py`, `AgentAntifraude`) ; l'outil `consulter_partenaire` du LLM ne renvoie que l'avis mémorisé (`agents_llm.py`). Le garde-fou impose que les champs décisifs du LLM égalent la référence (`gardes_fous.py`). Le LLM rédige donc la note explicative ; il ne change ni l'appel au partenaire ni la décision. C'est un choix de sûreté (invariance, EX-D19 : un seul appel par dossier) | en partie |
| 4 | p. 1, 4, 38 — « quatre agents LLM » | Un 5ᵉ agent LLM existe hors de la machine à états : l'agent de **relance** de l'espace assuré (`relance.py`, `KALDERA_RELANCE__*`), borné aux pièces | oui (UI1) |
| 5 | p. 6, 22, 26 — appels LLM, ports et base asynchrones (`async def`, psycopg asynchrone) | Tout est **synchrone** : LLM, VLM et A2A sous délai par thread (`ThreadPoolExecutor`, `join`), `traiter_lot` en threads, psycopg et `ConnectionPool` synchrones, ports synchrones. Seuls le cycle de vie de l'API et le flux SSE sont `async` | lot en threads : oui ; le reste : non |
| 6 | p. 2, 13, 21, 25, 26, 38 — « tout est persisté dans PostgreSQL » | La persistance est **facultative** : sans `KALDERA_DATABASE_URL`, ni snapshot ni reaper, et le registre A2A reste en mémoire. `traiter_demande` et `make scenarios` tournent sans base | non |
| 7 | p. 10 — `.env` : `AZURE_AI_ENDPOINT`, `AZURE_AI_API_KEY`, `KALDERA_INGESTION__VLM__FOURNISSEUR=azure` | Les variables sont `AZURE_AI_CHAT_ENDPOINT` et `AZURE_AI_CHAT_KEY` (partagées par les agents et le VLM) ; le fournisseur VLM n'est pas configurable. Avec les noms du dossier, aucun LLM n'est branché : chaque agent passe en repli, cause `llm_non_configure`. Référence : `README.md` et `.env.example` | non |

## 2. Écarts mineurs

**État partagé et données**
- p. 6 — section `pieces` : pas de champ `relances`, le compteur est dans `compteurs`.
- p. 6, 8 — section `avis_fraude` : `{requis, indicateurs, statut, avis, note, cause}`, l'avis du
  partenaire (6 champs) étant imbriqué dans `avis`.
- p. 15 — gardes T9 et T10 : `issue.decision` (et non `issue.resultat`).
- p. 21 — `ContratDemande` ne porte que la provenance ; les termes du contrat restent dans
  `demande["contrat"]`.
- p. 22-23 — montants en `float` dans le moteur ; `Decimal` seulement à l'ingestion.

**Ports, fabrique, configuration**
- p. 22 — `DepotPieces` est synchrone et prend la demande (journal : oui pour la demande).
- p. 22, 26 — `RegistrePieces` et `DepotContrats` sont remplacés par `IngestionPostgres`
  (journal : oui).
- p. 9 — `SpecAgent(section, modele_section, champ, gabarit, outils, controle, fabrique_repli,
  prives)`, prompt lu dans `prompts/<agent>.md` ;
  `creer_agent(nom, llm, config, bornes, evaluer, disjoncteur)`.
- p. 10 — les `ConfigLLM` des agents sont facultatives : un agent non configuré passe en repli.
- p. 20 — `jetons_max` borne la sortie d'un appel (`max_tokens`), pas l'entrée + sortie ni un
  cumul par agent.

**Orchestration et bornes**
- p. 16, 18 — garde globale TG : `etapes + 1 >= etapes_max` (une étape reste réservée à
  `decision`).
- p. 13 — si l'agent `decision` lui-même échoue, le moteur passe directement à `ESCALADE`.
- p. 18 — erreurs : `ErreurEcriture`, `TransitionInconnue`, `Indisponible`, `ErreurLLM`,
  `OutilRefuse`, `ToursEpuises` (pas `ErreurAgent`, `BorneAtteinte`, `DelaiPartenaire`…).
- p. 19 — frise : les délais configurés sont 1,5 s (antifraude) et 1,2 s (decision), comme en
  p. 20 ; et l'appel A2A précède le LLM (écart majeur n° 3).
- p. 20, 42 — disjoncteur : fenêtre glissante de 60 s, ouvert si plus de 50 % de replis sur
  10 tentatives au moins, refermé seul (journal : oui). Il y en a un par orchestrateur :
  `traiter_demande` en crée un à chaque appel, il ne s'ouvre donc que dans `traiter_lot` et le
  worker.

**Épreuve et métriques**
- p. 37 — `make eval` mesure replis, sorties rejetées, latence p95, tours, jetons par demande et
  invariance ; il n'y a ni coût, ni alerte à 16 000 jetons par demande.
- p. 37 — l'invariance est éprouvée par injection (`tests/unit/test_invariance.py`) ;
  `traiter_demande(…, llm=mode)` n'existe pas.
- p. 35 — `make epreuve` couvre T1–T11 ; TG n'est pas comptée, T0 relève de l'ingestion
  (journal : oui pour T0).
- p. 36 — pas de ligne `is_eligible()` séparée (comptée sous `orchestrateur`), pas de matrice
  des transitions.

**Ingestion et schéma**
- p. 23-24 — le VLM ne reçoit que l'image de la page 1 du PDF (journal : oui).
- p. 24 — verrou ③ : numéro, franchise, plafond et date sont vérifiés dans la couche texte, pas
  la formule.
- p. 13, 27 — l'admission exige aussi une soumission explicite (`POST …/soumettre`) (journal :
  oui).
- p. 28-29 — générateur : `generer_pieces.py --seed 42 [--sortie]` ; le « À compléter » du barème
  est fait (journal : oui).
- p. 27 — dix tables, et non sept : `utilisateurs`, `demandes_assure`, `evenements_assure` en
  plus, et de nouvelles colonnes (journal : oui).

## 3. Réalisé mais absent du dossier

- **Espace sinistre de l'assuré** (UI1) : front React 19 / Vite / Tailwind / shadcn, suivi en
  5 étapes, dépôt de pièces, verdict expliqué ; API `/assure/*` avec flux SSE ; comptes argon2,
  cookie signé, blocage après 5 échecs ; vue projetée qui ne montre ni avis anti-fraude, ni
  score, ni mode dégradé. Détails : `docs/interface_web.md`.
- **Agent de relance** (5ᵉ agent LLM), borné aux pièces par une liste de termes interdits.
- **Événements** de l'assuré (`evenements_assure`), publiés par le worker et le reaper.
- **Liaison A2A conforme au contrat v2.0** : Agent Card lue au démarrage, URL d'appel limitée à
  la même origine que la base (le jeton ne part jamais ailleurs), `/a2a` en secours.
- **Disjoncteur LLM** (`disjoncteur.py`), cause de repli `disjoncteur`.
- **Mesure** : `make epreuve` (verdict EX-01 à EX-06, seuils d'équipe, partenaire simulé dans le
  processus) et `make eval` (matrice agent × modèle, 5 répétitions, invariance, recommandation
  par rôle, remesure des bornes) ; métriques d'équipe et nature des appels A2A.
- **Robustesse** : 3 essais par tâche d'ingestion, reprise des tâches bloquées, persistance
  coupée au premier échec de base.
- **Recette** : `make recette`, cahier de recette (`docs/recette/`).

## 4. Conforme au dossier

Machine à états (états, T0–T11, terminaux) ; bornes (`etapes_max` 12, `duree_max_s` 8,
`delai_partenaire_s` 3, une relance, réserve de `decision`, 4 appels d'outil) et budgets par
agent ; budget dégressif ; règles métier (barème, seuils, F1–F4, E1–E5, règle 0, mode dégradé) ;
écriture de l'état par section ; protocole A2A (projection sur 7 champs, 4 couches de validation,
un appel par dossier réservé avant l'envoi, abandon à 3 s) ; filet, reaper et `SKIP LOCKED` ;
contrôles d'ingestion (MIME, taille, verrous du contrat, cache) ; saboteurs du `FakeLLM`.
