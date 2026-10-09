# C2a · Liaison A2A conforme au contrat v2.0

> Source : `dossier-conception.pdf` (3.1 échange A2A, 3.2 pas de SSE, 3.3 exemples, 3.4 codes
> d'erreur, 3.5 mode dégradé §9, 2.6 registre `appels_partenaire`), `external_agent/contrat.md`
> (v2.0), `prompt.md` C2-Q1 → C2-Q11. Branche : `feature/chantier2-c2a-a2a` · point de départ :
> `49524fd` (UI1 livré ; 14 rouges A2A connus).
> Premier sous-projet du chantier 2 : **C2a liaison A2A** → C2b monitorage et épreuve → C2c LLM
> réel (`make eval`, disjoncteur).

## 1. Objectif

Rendre l'appel au partenaire anti-fraude **conforme au contrat v2.0** : découverte par Agent Card,
projection stricte sur 7 champs, un seul appel par dossier garanti par le registre, validation de
chaque réponse en 4 couches, et mode dégradé §9 pour toute réponse écartée.

| Exigence | Où |
|---|---|
| EX-03 / EX-D20 minimisation : exactement 7 champs, aucune donnée interdite | §3.2 |
| EX-04 / EX-D21 réponse non conforme rejetée, jamais propagée | §3.5, §4 |
| EX-05 / EX-D25 mode dégradé §9 si avis indisponible (délai, erreur, réponse écartée) | §4 |
| EX-D19 un appel par dossier, aucune relance, réservation avant l'envoi | §3.3 |
| EX-D22 rejet journalisé sans le contenu invalide | §4 |

**Critère de sortie** : les 14 tests de `tests/acceptance/test_collaboration_a2a.py` verts **sans
modifier les tests fournis** (acceptance 42/56 → 56/56) ; `make test`, `make lint`,
`make typecheck` verts ; `make test-integration` vert.

### Décisions prises

| Sujet | Décision |
|---|---|
| Emplacement | Tout dans l'adaptateur `src/kaldera/partenaire.py`, seul client A2A, détenu par l'agent `antifraude` (C2-Q3). Pas de paquet `a2a/`. |
| Agent Card | Lue **au démarrage** (`GET /.well-known/agent.json`), une fois par URL de base et par processus ; `/a2a` en secours si la carte est illisible. |
| Registre | `RegistreA2APostgres` si la base est configurée, sinon `RegistreA2AEnMemoire` **par orchestrateur**. |
| Échec du registre | Réservation impossible (doublon ou base en panne) ⇒ **aucun envoi**, avis indisponible. |
| Compatibilité | `None` reste un retour valide de l'évaluateur : les 20 doublures de test existantes ne changent pas. |
| Déploiement | Le client reste un processus hôte (`uv run`) ; le partenaire garde son conteneur. Conteneur Kaldera hors périmètre. |

### Hors périmètre

Métriques `antifraude` détaillées (ok / timeout / invalide / non requis), seuils d'alerte, remesure des
bornes `etapes_max` et `duree_max_s` (C2b) ; `make eval` et disjoncteur LLM (C2c) ; conteneur Docker
pour l'API et le worker Kaldera ; vérification des capacités annoncées par l'Agent Card ; streaming
SSE (écarté par le dossier, 3.2).

## 2. Fichiers

| Fichier | Changement |
|---|---|
| `src/kaldera/partenaire.py` | Agent Card, `RequeteAntifraude`, `projeter`, `ReponseAntifraude`, `valider_reponse`, `Indisponible`, registre dans `evaluer_risque` |
| `src/kaldera/agents.py` | `Evaluateur` accepte `Indisponible` ; `AgentAntifraude` recopie la cause |
| `src/kaldera/etat.py` | `AvisFraude.cause: str \| None = None` |
| `src/kaldera/orchestrateur.py` | registre par défaut passé à l'adaptateur ; `motif` dans l'étape de trace en échec |
| `src/kaldera/postgres.py` | `registre_par_defaut()` sur le modèle de `snapshots_par_defaut()` |
| `tests/unit/test_partenaire.py` | nouveau : projection, validation, registre, Agent Card |
| `tests/unit/test_agents.py` | cause recopiée ; `None` ⇒ « cause non précisée » |
| `tests/unit/test_orchestrateur.py` | `motif` dans l'étape de trace `antifraude` en échec |
| `tests/integration/test_adaptateurs.py` | registre Postgres : second orchestrateur, aucun envoi |
| `docs/journal_ajustements.md`, `README.md` | ajustements consignés ; « Restant » et « Known issues » réécrits |

## 3. L'adaptateur `partenaire.py`

### 3.1 Agent Card

`url_appel(base)` lit `GET {base}/.well-known/agent.json` avec un délai de **1 s** et retourne le
champ `url`. Seul un succès est mis en cache (dictionnaire de module, clé = URL de base). Carte
illisible (connexion refusée, HTTP ≠ 200, JSON invalide, `url` absente ou d'une **autre origine** que la base — le jeton
Bearer ne suit jamais un hôte annoncé par la carte) ⇒
`f"{base}/a2a"`, non mis en cache : le prochain orchestrateur relira la carte.

La lecture se fait à la construction de l'orchestrateur (`Orchestrateur.__init__`), donc une fois par
`traiter_demande` et une fois par `traiter_lot`, et au plus une requête réseau par URL pour toute la
vie du processus en cas de succès. Le simulateur construit `url` depuis l'hôte appelé : un client
dans un autre conteneur (`http://partenaire:8100`) recevrait la bonne adresse.

### 3.2 Projection (requête)

`RequeteAntifraude` (Pydantic, `extra="forbid"`), contraintes du contrat §2 :

| Champ | Source | Contrainte |
|---|---|---|
| `reference_dossier` | `demande["reference"]` | motif `^KAL-\d{2}-\d{4}$` |
| `type_sinistre` | `sinistre.type` | `degat_des_eaux`, `incendie`, `bris_de_glace`, `vol` |
| `montant_declare` | `sinistre.montant_declare` | `> 0` |
| `date_survenance` | `sinistre.date_survenance` | date `AAAA-MM-JJ` |
| `anciennete_contrat_jours` | `regles.jours_entre(contrat.date_souscription, date_survenance)` | `≥ 0` |
| `sinistres_12_mois` | `historique.sinistres_12_mois` (0 si absent) | `≥ 0` |
| `departement` | `assure.code_postal` dérivé | voir ci-dessous |

Département : 2 premiers caractères ; Corse `20000`–`20199` ⇒ `2A`, `20200`–`20999` ⇒ `2B` ;
outre-mer (`97…`) ⇒ 3 premiers chiffres (motif du simulateur : `^(\d{2}|2A|2B|97\d)$`). Code postal absent ou mal formé ⇒ projection en échec.

`projeter(demande) -> RequeteAntifraude` lève une erreur si une donnée manque ou viole une
contrainte. **Projection en échec ⇒ rien n'est envoyé** et le registre n'est pas consommé.

Au niveau 1, la date de souscription est déjà celle du contrat PDF validé (les termes restent dans
`demande["contrat"]`, dossier 2.4) : aucun traitement particulier.

### 3.3 Registre et ordre des opérations

`evaluer_risque(demande, url, *, timeout, registre)` :

1. `projeter(demande)` : échec ⇒ `Indisponible("projection : <champ> invalide")` ;
2. `registre.reserver(reference)` : `False` ⇒ `Indisponible("registre : dossier déjà soumis")` ;
   `ErreurPersistance` (toute `psycopg.Error`, cf. `postgres._connexion`) ⇒
   `Indisponible("registre indisponible")` ;
3. envoi `POST` à l'URL d'appel, en-tête `Authorization: Bearer <PARTENAIRE_JETON>`, échéance globale
   `timeout` (le fil existant est conservé) ; aucune relance, quel que soit le résultat ;
4. `valider_reponse(...)` (§3.4) ;
5. avis valide ⇒ `registre.noter(reference, evaluation_id)` puis retour de l'évaluation.

Le registre est un paramètre : l'orchestrateur le construit (`postgres.registre_par_defaut()` sur le
modèle de `snapshots_par_defaut()`, sinon `RegistreA2AEnMemoire()`) et le passe dans la fermeture
`evaluer_partenaire`. Un `evaluer` injecté (tests) court-circuite l'adaptateur et donc le registre.

Un registre propre à chaque orchestrateur, sans base, est volontaire : la suite d'acceptance rejoue
les mêmes références dans deux fichiers et le simulateur se remet à zéro entre eux ; un registre
global au processus bloquerait le second passage. La durabilité réelle vient de Postgres.

### 3.4 Validation de la réponse (4 couches)

`valider_reponse(statut_http, corps_brut, id_rpc, reference) -> dict | Indisponible`, fonction pure.

| Couche | Règle | Cause en cas d'échec |
|---|---|---|
| ① transport | HTTP 200 ; corps JSON lisible | `HTTP 401 (jeton)`, `HTTP 503`, `HTTP <code>`, `couche ① : corps illisible` |
| ② enveloppe | `jsonrpc = "2.0"`, même `id` ; `error` présent ⇒ lire `error.code` (même sous HTTP 200) ; `result.kind = "task"`, `status.state = "completed"`, exactement un artefact à une partie `data` | `JSON-RPC <code>` (libellé : `-32029` « doublon refusé : manquement au contrat », `-32602` « projection refusée »), `couche ② : <règle>` |
| ③ schéma | `ReponseAntifraude` (`extra="forbid"`) : 6 champs exacts, `score` nombre, `niveau` ∈ {faible, modere, eleve}, `indicateurs` ⊂ {MONTANT_ELEVE, SINISTRE_PRECOCE, FREQUENCE_ELEVEE, TYPE_SENSIBLE}, `evaluation_id` et `version_modele` chaînes | `couche ③ : <type d'erreur> (<champ>)` |
| ④ cohérence | `0 ≤ score ≤ 1` ; `niveau` conforme aux seuils 0,40 / 0,75 ; même `reference_dossier` | `couche ④ : score hors bornes`, `niveau incohérent`, `référence différente` |

Le délai dépassé est détecté par l'appelant : `Indisponible("délai > <timeout> s")`.

**La cause ne contient jamais de valeur de la réponse.** Les messages par défaut de Pydantic recopient
l'entrée fautive (`EVA-NC`, `rembourser_integralement`) : la cause est construite depuis `loc` et
`type` de chaque erreur, jamais depuis `msg` ni `input`.

`Indisponible` : `@dataclass(frozen=True)` avec un seul champ `cause: str`.

## 4. Agent, fiche, trace

- **Type** : `Evaluateur = Callable[..., dict | Indisponible | None]`. `None` ⇒ cause « cause non
  précisée » ; `_sans_partenaire` et les 20 doublures existantes restent valides.
- **`AgentAntifraude`** : évaluation `dict` ⇒ `statut = "avis"`, `avis = dict` ; sinon
  `statut = "indisponible"`, `avis = None`, `cause = <cause>`. Son rôle ne change pas : F1–F4, et un
  appel seulement si au moins un indicateur est levé.
- **`AvisFraude`** : champ optionnel `cause: str | None = None` ; les snapshots `jsonb` existants
  restent lisibles.
- **Trace** : l'étape `antifraude` indisponible reste `statut = "echec"` (donc comptée dans
  `metriques.echecs`) et reçoit `"motif": cause`. Jamais le corps de la réponse (C2-Q8).
- **Fiche** : `avis_fraude` = évaluation validée (6 champs, dont `evaluation_id` et `version_modele`
  pour l'audit), ou `null`.
- **Décision** : aucun changement. `_issue` applique déjà le mode dégradé §9 (estimé ≤ 1 500 € :
  la demande continue ; au-delà : `cellule_fraude`), avec un motif citant §9 ; `file_prudente`
  applique la même règle aux fiches de secours.
- **Agent LLM** : outils, gabarit et garde-fou inchangés ; la cause apparaît dans le résumé de
  `consulter_partenaire` (aucun contenu externe).

## 5. Tests

Écrits avant le code (TDD). Aucun test fourni n'est modifié.

**`tests/unit/test_partenaire.py`**

- projection : exactement les 7 clés ; département `69003` → `69`, `20100` → `2A`, `20200` → `2B`,
  `97411` → `974` ; aucune donnée interdite (nom, prénom, e-mail, téléphone, adresse, code postal, IBAN, identifiant
  client, numéro de contrat, description) dans le JSON sérialisé ;
  donnée manquante ⇒ `Indisponible` et `httpx.post` jamais appelé ;
- validation : un cas par couche ①–④ ; chaque code d'erreur du contrat §4 (401, 503, `-32700`,
  `-32600`, `-32601`, `-32602`, `-32029`), y compris une erreur JSON-RPC sous HTTP 200 ; la cause ne
  contient aucune valeur de la réponse fautive ;
- registre (`httpx.post` remplacé par un compteur) : réservation avant l'envoi ; réservation refusée
  ⇒ 0 envoi ; `noter` appelé avec l'`evaluation_id` après un avis valide, pas après un rejet ;
  `ErreurPersistance` à la réservation ⇒ 0 envoi ;
- Agent Card (`httpx.get` remplacé) : carte lisible ⇒ son `url` ; carte en 503 ou illisible ⇒
  `/a2a`, non mise en cache ; second appel après succès ⇒ aucune requête.

**`tests/unit/test_agents.py`** : `Indisponible(cause)` ⇒ section `indisponible` avec la cause ;
`None` ⇒ « cause non précisée ».

**`tests/unit/test_orchestrateur.py`** : évaluateur renvoyant `Indisponible(cause)` ⇒ étape
`antifraude` en `echec` avec `"motif": cause`.

**`tests/integration/test_adaptateurs.py`** (Postgres) : deux orchestrateurs traitent la même
référence ; le second n'envoie rien et sa fiche est en mode dégradé.

**Acceptance** : AF-01 → AF-07 et INV-01 → INV-07 verts ; PAN-01 et PAN-02 restent verts.

## 6. Journal des ajustements

Une ligne par ajustement dans `docs/journal_ajustements.md`, au format existant (date · scénario ·
constat · exigence · ajustement · avant / après) :

| Scénario | Constat | Ajustement | Mesure attendue |
|---|---|---|---|
| AF-01 → AF-07 | requête refusée (`-32602`, champs hors contrat) | projection 7 champs | refus → requête conforme |
| INV-01 → INV-07 | réponse non vérifiée | validation 4 couches | réponse propagée → `avis_fraude = null` |
| tests unitaires de validation | Pydantic recopie la valeur fautive | cause depuis `loc` / `type` | fuite → aucune valeur |
| registre (EX-D19) | port défini, non branché | réservation avant l'envoi | 0 garantie → 1 appel par dossier, même après redémarrage |
| Agent Card | URL `/a2a` en dur | carte lue au démarrage, `/a2a` en secours | — |
| PAN-02 | abandon à 3 s jamais éprouvé (requête rejetée avant le délai) | aucun (mesure) | durée réellement mesurée consignée ; analyse en C2b |

Plus une ligne de résultat de la suite (14 rouges → 0). La section « Restant (chantier 2) » est
réécrite (C2b, C2c) et la mention « Known issues » du `README.md` mise à jour.
