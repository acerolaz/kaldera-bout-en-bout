# C2c · LLM réel : disjoncteur, `make eval`, seuils du LLM

> Source : `dossier-conception.pdf` (2.3 bis bornes LLM, 4.3 niveaux d'épreuve), `prompt.md` C1-Q22b,
> C2-Q14c, C2-Q16, EX-D33, EX-D14 ; `docs/journal_ajustements.md` (bornes provisoires, « Restant »).
> Branche : `feature/chantier2-c2c-llm-reel` · point de départ : `906243a` (C2b livré, PR #8 :
> `make epreuve` réussie, suite 642 verts, acceptance 56/56).
> Troisième sous-projet du chantier 2 : C2a liaison A2A → C2b monitorage et épreuve → **C2c LLM réel**.

## 1. Objectif

Rendre l'équipe d'agents **sûre face à un LLM en panne** (disjoncteur) et **mesurable avec un LLM
réel** : une commande, `make eval`, rejoue les 28 scénarios avec chaque modèle candidat, remplit la
matrice agent × modèle, compare aux seuils d'alerte du LLM, vérifie l'invariance et remesure les
bornes de temps.

| Exigence | Où |
|---|---|
| EX-D33 disjoncteur LLM : taux de repli > 50 % / 1 min ⇒ repli pour tous | §2 |
| C2-Q14c niveau ③ : matrice agent × modèle, 28 × 5 (taux de repli, latence p95, coût, qualité) | §3 |
| C2-Q14c seuils d'alerte : replis > 20 %, sorties rejetées > 5 %, latence LLM p95 > `delai_agent_s`, tours moyens > 2,5 | §3.3 |
| C2-Q14c critère d'invariance : issue, file, montant, mode dégradé identiques en `llm` et `repli` | §3.3 |
| Journal (bornes) : `duree_max_s` et `delai_partenaire_s` à remesurer avec LLM | §3.3, §5 |
| C2-Q16 : un changement de modèle est un ajustement consigné, jamais automatique | §3.4 |

**Critère de sortie** : tests du §4 verts ; `make test`, `make lint`, `make typecheck` verts (dont
`tools/eval_llm.py`) ; `make epreuve` toujours réussie ; `make eval` sans clés sort en 2 avec un
rapport « non mesuré ». La mesure réelle (matrice remplie, bornes remesurées) est consignée au
journal comme restant, à lancer dès que les clés Azure sont dans le `.env`.

### Décisions prises

| Sujet | Décision |
|---|---|
| LLM réel | Aucune clé Azure disponible : tout passe par le port `ClientLLM` et `fabrique_llm` ; `AzureLLM` n'est pas modifié (une autre branche, `worktree-azure-chat-completions-client`, le réécrit). |
| Portée du disjoncteur | Un seul disjoncteur pour les 4 agents (« repli pour tous », EX-D33). |
| Vie du disjoncteur | Injecté (pas d'état global) : un par `Orchestrateur` par défaut, partagé par `traiter_lot` ; le worker en crée un dans `main()` et le passe à chaque demande. |
| Volume minimal | 10 tentatives dans la fenêtre avant toute ouverture (choix C2c, absent du dossier). |
| Modèles évalués | `KALDERA_EVAL__MODELES` (liste séparée par des virgules) ; à défaut, les modèles distincts des 4 agents. |
| Matrice | Une passe = un modèle pour les 4 agents (chacun garde délai, jetons, tours) ; 5 répétitions par modèle. |
| Recommandation | Un avis dans le rapport ; le `.env` n'est jamais modifié par l'outil. |

### Hors périmètre

Adaptateur Azure (autre branche) ; disjoncteur par modèle ou par agent (à ajouter si les agents
finissent sur des fournisseurs différents) ; prix en euros (le coût est mesuré en jetons) ; matrice
croisée (agent A sur M1 et agent B sur M2 dans la même passe) ; mesure réelle sans clés.

## 2. Disjoncteur LLM

### 2.1 Module

Nouveau module `src/kaldera/disjoncteur.py` :

```python
class Disjoncteur:
    def __init__(self, taux: float, fenetre_s: float, minimum: int = 10,
                 horloge: Callable[[], float] = monotonic) -> None: ...
    def ouvert(self) -> bool: ...          # purge la fenêtre puis évalue
    def noter(self, repli: bool) -> None:  # enregistre une tentative LLM
```

- État : une `deque` de `(instant, repli)` protégée par un `threading.Lock`.
- `ouvert()` : retire les tentatives plus vieilles que `fenetre_s`, puis renvoie
  `n >= minimum and replis / n > taux` (strictement supérieur : 5 sur 10 reste fermé).
- Refermeture : implicite, quand les tentatives sortent de la fenêtre ; au plus `fenetre_s` après
  la dernière tentative notée.

### 2.2 Bornes

`Bornes` reçoit deux champs : `taux_repli_disjoncteur: float = Field(default=0.5, gt=0, lt=1)` et
`fenetre_disjoncteur_s: float = Field(default=60, gt=0)`. Le minimum (10) est un paramètre du
constructeur, pas une borne.

### 2.3 Branchement

- `AgentLLM.__init__` reçoit `disjoncteur: Disjoncteur | None` (via `creer_agent`).
- `AgentLLM.executer`, dans l'ordre : `llm is None` ⇒ `llm_non_configure` ; **disjoncteur ouvert ⇒
  repli, `cause = "disjoncteur"`, aucun appel LLM, rien n'est noté** ; budget insuffisant ⇒
  `budget` (non noté) ; sinon tentative, puis `noter(repli=mesure.mode == "repli")`.
- Comptent comme replis notés : `erreur_llm`, `sortie_invalide`, `outil_refuse`, `tours_max`,
  `garde_fou`.
- `Orchestrateur.__init__` reçoit `disjoncteur: Disjoncteur | None = None` ; à défaut, il en crée un
  depuis ses bornes et le passe aux 4 agents.
- `worker.main()` crée un disjoncteur et le transmet (`travailler` → `_admettre`) à chaque
  `Orchestrateur` créé.
- `docs/interface.md` : nouvelle valeur de `cause`, `disjoncteur`.

## 3. `make eval`

### 3.1 Outil

`tools/eval_llm.py`, cible `eval: uv run python -m tools.eval_llm` dans le `Makefile` (et `.PHONY`).
Il réutilise `tools/epreuve.py` : `partenaire_simule()`, `rejouer()`, `SCENARIOS`, `RAPPORTS`.
`epreuve.orchestrateur(url)` et `epreuve.rejouer(url, scenario)` reçoivent des paramètres optionnels
`llms`, `config` et `disjoncteur` transmis à l'`Orchestrateur` (comportement inchangé sans eux).

### 3.2 Flux

1. **Configuration** : `charger_config()` (ou `ConfigAgents.model_construct()` si le `.env` est
   malformé). Modèles = `KALDERA_EVAL__MODELES` nettoyé (espaces, entrées vides, doublons) ; liste
   vide ⇒ modèles distincts des agents configurés. Sans endpoint, sans clé ou sans modèle ⇒ rapport
   « non mesuré : aucun modèle configuré », code 2, aucun appel réseau.
2. **Référence** : un rejeu des 28 scénarios en repli (`llms` = `{}` ⇒ aucun agent configuré).
   Pour chaque référence de demande : `DECISIFS = ("issue", "decision", "montant_rembourse", "file",
   "mode_degrade")`.
3. **Passes** : pour chaque modèle M, pour r = 1 … `REPETITIONS` (5) : config clonée avec
   `modele = M` pour les 4 agents (`cfg.model_copy(update=…)`), `llms` construits par une fabrique
   (par défaut `fabrique_llm`, injectable pour les tests), **disjoncteur neuf**, rejeu des 28
   scénarios.
4. **Agrégation** (§3.3), **recommandation** (§3.4), **rapport** (§3.5).

### 3.3 Mesures et seuils

Par case agent × modèle, sur les étapes de l'agent (étapes de trace portant `mode`) de toutes les
répétitions :

| Mesure | Calcul | Alerte |
|---|---|---|
| `replis` | étapes `mode = repli` ÷ étapes | > 0,20 |
| `sorties_rejetees` | étapes `sortie_rejetee` ÷ étapes | > 0,05 |
| `latence_llm_p95_ms` | p95 (rang le plus proche) de `latence_llm_ms` par étape | > `delai_agent_s` × 1000 de l'agent |
| `tours_moyen` | somme des `tours_llm` ÷ étapes | > 2,5 |
| `jetons_par_demande` | somme des `jetons` ÷ demandes rejouées | — |
| `causes` | compte des replis par cause | — |

Agent sans étape ⇒ toutes les mesures à `None`, case « — », sans alerte. Seuils égaux à la limite
⇒ verts (les alertes sont strictement supérieures).

Par modèle (équipe) :
- **invariance** : part des demandes dont les `DECISIFS` sont identiques à la référence ; écarts
  listés `référence · champ · référence → observé` ; attendu 100 %.
- **bornes remesurées** : `metriques_equipe` sur toutes les fiches du modèle : durée p95 et max
  contre `duree_max_s` × 1000, étapes max contre `etapes_max`, arrêts par borne ; nombre d'étapes
  en cause `disjoncteur`.

### 3.4 Recommandation par rôle

Pour chaque agent : parmi les modèles dont la case est sans alerte **et** dont l'invariance vaut
100 %, celui au taux de replis le plus bas, puis à la latence p95 la plus basse. Aucun candidat ⇒
« aucun modèle ne passe les seuils ». Un avis : le `.env` n'est jamais modifié ; tout changement de
modèle est consigné au journal (C2-Q16).

### 3.5 Rapport et code de sortie

`eval/rapports/eval-<date>.md` et `.json` (dossier ignoré par git ; la copie retenue est archivée
dans `docs/epreuves/`). Sections du `.md` : en-tête (date, modèles, répétitions, nombre de
scénarios) ; matrice agent × modèle (replis, rejetées, latence p95, tours, jetons/demande, verdict
avec les seuils franchis) ; modèle recommandé par rôle ; invariance par modèle ; bornes remesurées.
Rapport « non mesuré » : en-tête et cause seulement.

Codes de sortie : 0 tout vert ; 1 au moins une alerte ou une invariance < 100 % ; 2 non mesuré.

## 4. Erreurs et tests

| Cas | Comportement |
|---|---|
| Modèle inconnu du fournisseur | `ErreurLLM` à chaque appel ⇒ 100 % de replis ⇒ alertes ; l'outil ne plante pas |
| Partenaire simulé | Démarrage, arrêt, jeton : déjà gérés par `partenaire_simule()` |
| Disjoncteur sous `traiter_lot` | Verrou ; une étape refusée par le disjoncteur n'est jamais notée |

Tests, sans réseau, `FakeLLM` injecté :

- `tests/unit/test_disjoncteur.py` (horloge injectée) : ouvert à 6/10, fermé à 5/10, fermé sous le
  minimum, refermé après `fenetre_s`, notes concurrentes (100 en threads) sans perte.
- `tests/unit/test_agents_llm.py` : disjoncteur ouvert ⇒ `cause = "disjoncteur"`, 0 appel au
  `FakeLLM`, même section que le repli ; une tentative est notée, un repli `budget` ne l'est pas.
- `tests/unit/test_orchestrateur.py` : saboteur `casse` sur un lot séquentiel de 12 demandes ⇒ le
  disjoncteur s'ouvre et les demandes suivantes sont en `disjoncteur` sans appel au LLM.
- `tests/unit/test_eval_llm.py` : matrice à 2 modèles factices (`fidele` vert, `casse` en alerte
  `replis`) sur 2 scénarios × 1 répétition, recommandation = le modèle sain ; limites des seuils
  (20 % vert, au-dessus alerte) ; agent sans étape ⇒ « — » ; invariance 100 % avec un `menteur` ;
  rapport `.md`/`.json` avec ses sections ; sans clés ⇒ code 2 et « non mesuré » ; nettoyage de
  `KALDERA_EVAL__MODELES` et retour aux modèles des agents.
- Fumée : `make eval` sans clés sort en 2 ; `make epreuve` réussie.

## 5. Documentation

- `docs/interface.md` : cause `disjoncteur`.
- `README.md` : `make eval` (prérequis : clés Azure et `KALDERA_EVAL__MODELES`).
- `.env.example` : `KALDERA_EVAL__MODELES=` commenté.
- `docs/journal_ajustements.md` : ligne C2c (disjoncteur, outil d'eval) ; bornes `duree_max_s` et
  `delai_partenaire_s` : « à remesurer au premier `make eval` avec clés » ; nouvelles bornes
  `taux_repli_disjoncteur` et `fenetre_disjoncteur_s` (provisoires) ; « Restant » : premier
  `make eval` réel, choix du modèle par rôle.
