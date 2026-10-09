# C2b · Monitorage par agent et épreuve de l'équipe

> Source : `dossier-conception.pdf` (4.1 plan d'épreuve, 4.2 journal et critère de sortie, 2.3 bornes),
> `prompt.md` C2-Q11 → C2-Q17, `docs/journal_ajustements.md` (bornes provisoires, « Restant »).
> Branche : `feature/chantier2-c2b-epreuve` · point de départ : `39280ec` (C2a livré, PR #5 :
> acceptance 56/56, suite 573 verts).
> Deuxième sous-projet du chantier 2 : C2a liaison A2A → **C2b monitorage et épreuve** → C2c LLM réel.

## 1. Objectif

Rendre l'équipe **observable** (métriques par agent et d'équipe) et **éprouvée** : une commande,
`make epreuve`, rejoue les 28 scénarios contre le partenaire simulé, mesure, compare aux seuils et
rend un verdict par exigence. Chaque seuil franchi donne lieu à un ajustement mesuré et consigné ;
sinon, les bornes provisoires passent à « éprouvées ».

| Exigence | Où |
|---|---|
| EX-06 / EX-D14 métriques par agent, ajustements consignés | §3, §5 |
| C2-Q15 signaux par agent et d'équipe | §3 |
| C2-Q14 / Q14b une assertion par exigence, une commande, rapport par exigence | §4 |
| PDF 4.2 critère de sortie : chaque transition empruntée par au moins un scénario | §4 |
| C2-Q16 / Q17 boucle d'épreuve, format du journal | §5 |

**Critère de sortie** : `make epreuve` sort en 0 (tous les verdicts ✅) et son rapport final est
commité ; `make test`, `make lint`, `make typecheck` verts ; tests fournis non modifiés ; bornes
provisoires au journal passées à « éprouvée » (ou ajustées et consignées).

### Décisions prises

| Sujet | Décision |
|---|---|
| Livrable | Un rapport d'épreuve (`tools/epreuve.py`, `make epreuve`) sur le modèle de `tools/eval_ingestion.py`. |
| Partenaire | Simulateur `external_agent.app` démarré **dans le processus**, port libre (le port 8100 peut être pris par un autre projet). |
| Métriques d'équipe | Nouvelle clé de premier niveau `traiter_lot()["equipe"]`, à côté de `metriques` (pas un pseudo-agent). |
| Nature d'un appel | Une seule fonction `partenaire.nature(cause)` classe les causes, là où elles sont produites. |
| Seuils | Seuils de l'équipe seulement ; seuils du LLM réel (replis, latence LLM, tours) en C2c. |
| Mode LLM | L'épreuve tourne dans le mode LLM configuré (par défaut : repli sans LLM) ; le rapport l'indique. |
| Dette C2a | Reprise en premier (test instable, `.env` dans deux tests, URL et jeton vérifiés avant la réservation). |

### Hors périmètre

`make eval` (matrice agent × modèle) et disjoncteur LLM (C2c) ; seuils propres au LLM réel ;
OpenTelemetry et logs structurés d'exploitation ; conteneur Kaldera ; épreuve de l'ingestion (déjà
`make eval-ingestion`).

## 2. Dette reprise de C2a

1. **Test instable** `tests/unit/test_orchestrateur.py::test_partenaire_muet_abandonne_au_delai` :
   course entre le `ReadTimeout` de httpx (même délai) et l'échéance du fil. Le test accepte les deux
   causes légitimes (`délai > 0.3 s` ou `couche ① : ReadTimeout`) et garde l'assertion de durée.
2. **`.env` local** : `test_sans_url_aucun_registre_persistant` et `test_sans_base_registre_en_memoire`
   ne doivent plus dépendre du `.env` du développeur (`ConfigBase` lu avec `_env_file=None`, ou
   `registre_par_defaut` éprouvé avec l'URL forcée par `monkeypatch`).
3. **URL et jeton vérifiés avant la réservation** (`partenaire.evaluer_risque`) : une URL d'appel
   que httpx refuse (`httpx.URL(url)` lève `httpx.InvalidURL`) ⇒ `Indisponible("URL partenaire
   invalide")` ; un jeton non ASCII ⇒ `Indisponible("jeton invalide")` ; dans les deux cas, **aucune
   réservation** (l'appel unique du dossier n'est pas consommé par une erreur de configuration).

## 3. Métriques

### 3.1 Nature d'un appel au partenaire

`partenaire.nature(cause: str | None) -> str`, à côté des causes qu'elle classe :

| Nature | Causes (préfixes produits par l'adaptateur) |
|---|---|
| `ok` | avis validé (`cause` absente, statut `avis`) |
| `timeout` | `délai > …` ; `couche ① : <Nom>` dont le nom finit par `Timeout` |
| `invalide` | `couche ① : corps illisible…`, `couche ② …`, `couche ③ …`, `couche ④ …` |
| `erreur` | `HTTP …`, `JSON-RPC …`, `couche ① : HTTP …`, `couche ① : <autre exception réseau>`, `cause non précisée`, toute cause inconnue |
| `non_envoye` | `projection …`, `jeton absent`, `jeton invalide`, `URL partenaire invalide`, `registre …` |
| `non_requis` | aucun indicateur F1–F4 (section `avis_fraude.statut = "non_requis"`) |

`appels_externes` (trace et métriques) ne compte que `ok`, `timeout`, `invalide` et `erreur` : un
appel qui n'est pas parti n'est plus compté. Un test vérifie que chaque cause produite par
l'adaptateur a la nature attendue (table exhaustive).

### 3.2 Métriques par agent — `traiter_lot()["metriques"]`

Clés existantes inchangées (`appels`, `echecs`, `latence_ms`, `appels_externes`, et celles du LLM).
L'agent `antifraude` gagne `"natures": {"ok": n, "timeout": n, "invalide": n, "erreur": n,
"non_envoye": n, "non_requis": n}`, calculé depuis la section `avis_fraude` et le `motif` de
l'étape `antifraude` de la trace.

### 3.3 Métriques d'équipe — `traiter_lot()["equipe"]`

| Clé | Contenu |
|---|---|
| `demandes` | nombre de fiches |
| `etapes` | `{"max": n, "moyenne": x}` — longueur de la trace par fiche |
| `arrets` | `{borne: n}` — d'après `fiche["arret"]["borne"]` |
| `issues` | `{"decision": n, "escalade": n}` |
| `escalades_par_file` | `{file: n}` |
| `mode_degrade` | `{"n": n, "taux": x}` (taux ∈ [0 ; 1]) |
| `duree_ms` | `{"p95": x, "max": x}` — somme des `duree_ms` des étapes de chaque fiche |
| `ecritures_rejetees` | nombre d'étapes en échec dont `erreur == "ErreurEcriture"` |

Pour `ecritures_rejetees`, l'étape de trace en échec reçoit `"erreur": <nom de l'exception>`
(aujourd'hui l'exception n'apparaît que dans le texte de `escalade_forcee`).

Les fonctions de calcul (par agent, d'équipe) sont publiques dans le paquet pour que l'épreuve les
applique à l'ensemble des fiches de tous les scénarios. `docs/interface.md` documente `natures`,
`equipe` et le champ `erreur` de la trace.

## 4. Épreuve — `tools/epreuve.py`, `make epreuve`

### 4.1 Rejeu

- Gestionnaire de contexte qui démarre `external_agent.app` (uvicorn, fil démon, port libre),
  attend son démarrage, fixe `PARTENAIRE_JETON` à un jeton de recette s'il est absent, et l'arrête
  à la sortie. `tools/` n'importe rien de `tests/`.
- Pour chaque scénario de `eval/scenarios.jsonl` : `POST /_sim/reset`, `POST /_sim/mode` avec
  `scenario["partenaire"]`, `traiter_lot(scenario["demandes"], partenaire_url=url)`, puis
  `GET /_sim/journal` (corps reçus). Fiches, métriques et journaux sont conservés par scénario.

### 4.2 Verdicts (fonctions pures)

| Verdict | Règle |
|---|---|
| EX-01 | chaque fiche a une `issue` (`decision` ou `escalade`) et un `motif` non vide |
| EX-02 | chaque section de la trace est écrite par son seul propriétaire (`etat.PROPRIETAIRES`) et `ecritures_rejetees = 0` |
| EX-03 | chaque entrée du journal du simulateur a exactement les 7 champs du contrat et aucune valeur personnelle de la demande (nom, prénom, e-mail, téléphone, adresse, code postal, IBAN, identifiant client, numéro de contrat, description) dans `corps_brut` |
| EX-04 | `avis_fraude` nul sur chaque fiche des scénarios `invalide` |
| EX-05 | sur les scénarios `panne`, `mode_degrade` et `file` égaux à l'attendu |
| EX-06 | BCL-01 : `arret.borne == "relances_pieces_max"` et longueur de trace ≤ `etapes_max` |
| Attendu | chaque fiche égale à son `attendu` sur les clés présentes (`issue`, `decision`, `file`, `montant_rembourse` à 0,01 près, `mode_degrade`, niveau d'`avis_fraude` ou `null`) |
| Couverture | chaque transition `T1` … `T11` de `machine.TRANSITIONS` apparaît au moins une fois dans les `garde` des traces des 28 scénarios |

**T0** (garde d'entrée : contrat non exploitable) n'est atteignable qu'au niveau 1 (contrat PDF illisible ou
incohérent) : aucun des 28 scénarios JSON ne l'emprunte (mesuré le 2026-10-09 : T1 → T11 couvertes, T0
non). Le rapport l'indique « couverte par ING-01 / ING-02 » (épreuve d'ingestion, `make eval-ingestion`,
`tests/integration/test_epreuve.py`) ; aucun scénario n'est fabriqué pour l'atteindre au niveau 0.

### 4.3 Seuils

| Seuil | Origine |
|---|---|
| `equipe.duree_ms.p95` < 8 000 et `max` < 10 000 | `duree_max_s`, §12 |
| `equipe.ecritures_rejetees` = 0 | EX-02 |
| `equipe.etapes.max` ≤ `etapes_max` (marge affichée) | EX-06 |
| `equipe.arrets` : seulement `relances_pieces_max` | EX-06 |
| au plus 1 entrée de journal du simulateur par référence | EX-D19 |
| tous les verdicts de §4.2 à ✅ | critère de sortie |

Rapportés sans seuil : `mode_degrade.taux`, `natures` de `antifraude`, escalades par file.

### 4.4 Rapport

`eval/rapports/epreuve-<AAAA-MM-JJ>.md` et `.json`, affiché à la fin ; code de sortie 1 si un seul
verdict ou seuil est ❌. Sections du `.md` : résultat (réussie / en échec), mode LLM et durée
totale ; seuils (mesure | seuil | verdict) ; exigences EX-01 → EX-06 ; couverture (transitions non
empruntées nommées) ; tableau par scénario (✅ / ❌ et écart) ; métriques par agent ; équipe ;
bornes en vigueur ↔ valeurs observées.

## 5. Boucle d'épreuve et journal

1. `make epreuve` sur la branche une fois l'outil livré.
2. Seuil franchi ⇒ ajustement (borne, garde, frontière ou routage), rejeu, une ligne au journal
   (date · scénario · signal observé · seuil · ajustement · avant → après), sans casser un autre
   scénario. Pas de réglage au doigt mouillé.
3. Aucun seuil franchi ⇒ tableau « Bornes provisoires en vigueur » : statut « éprouvée » et
   valeurs observées (étapes max, durée max et p95, arrêts) ; `relances_pieces_max` reste « à
   valider avec le métier ».
4. Le rapport final (`.md` et `.json`) est commité ; la section « Restant (chantier 2) » ne garde
   que C2c ; `README.md` mentionne `make epreuve`.

## 6. Fichiers

| Fichier | Changement |
|---|---|
| `src/kaldera/partenaire.py` | `nature(cause)` ; URL et jeton vérifiés avant `reserver` |
| `src/kaldera/orchestrateur.py` | `appels_externes` selon la nature ; `"erreur"` dans l'étape en échec |
| `src/kaldera/__init__.py` | calcul des métriques `natures` et `equipe` (fonctions publiques) ; `traiter_lot` renvoie `equipe` |
| `tools/epreuve.py` | simulateur en processus, rejeu, verdicts, seuils, rapport |
| `Makefile` | cible `epreuve` |
| `tests/unit/test_partenaire.py`, `test_orchestrateur.py`, `test_base_par_defaut.py` | dette C2a ; nature ; `erreur` ; `appels_externes` |
| `tests/unit/test_metriques.py` | métriques par agent et d'équipe sur des fiches fabriquées |
| `tests/unit/test_epreuve.py` | verdicts (un ✅ et un ❌ par exigence), seuils, rapport dans `tmp_path`, fumée de bout en bout |
| `docs/interface.md`, `docs/journal_ajustements.md`, `README.md`, `eval/rapports/` | documentation, journal, rapport final |

## 7. Tests

- Table exhaustive cause → nature (chaque `Indisponible(...)` de l'adaptateur).
- `appels_externes` = 0 pour une demande dont l'appel n'est pas parti (projection, jeton, registre).
- Métriques d'équipe sur fiches fabriquées : p95 (au moins 20 fiches), max, arrêts, files, taux,
  `ecritures_rejetees`.
- Verdicts : pour chaque exigence, une entrée qui passe et une qui échoue.
- Fumée : `epreuve.evaluer()` complet (simulateur en processus, 28 scénarios) ⇒ `reussi` ; environ
  10 s ajoutées à `make test`.
- Dette C2a : test d'abandon au délai déterministe ; deux tests sans `.env` ; URL invalide et jeton
  non ASCII ⇒ aucune réservation.
