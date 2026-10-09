# Contrat d'intégration

Ce document fixe ce que la plateforme expose au reste du système d'information et
à la suite d'acceptance (`tests/acceptance/`). Le comportement métier attendu est
décrit dans `docs/specs_metier.md` ; le contrat du partenaire anti-fraude dans
`external_agent/contrat.md`.

## Points d'entrée (paquet `kaldera`)

| Fonction | Rôle |
|---|---|
| `traiter_demande(demande, *, partenaire_url=None) -> dict` | traite une demande, retourne sa fiche de décision |
| `traiter_lot(demandes, *, partenaire_url=None) -> dict` | traite un lot ; retourne `{"fiches": [...], "metriques": {...}, "equipe": {...}}`, fiches dans l'ordre des demandes |
| `bornes() -> dict` | bornes d'exécution en vigueur (voir plus bas) |

`partenaire_url` est l'URL de base du partenaire anti-fraude ; à défaut, la
variable d'environnement `PARTENAIRE_URL`. Le jeton d'accès au partenaire est lu
dans `PARTENAIRE_JETON`.

## Fiche de décision

Les champs métier sont définis en section 11 des spécifications fonctionnelles
(`reference`, `issue`, `decision`, `montant_rembourse`, `motif`, `file`,
`avis_fraude`, `mode_degrade`). La fiche porte en plus :

| Champ | Description |
|---|---|
| `trace` | liste ordonnée des étapes du traitement de la demande |
| `arret` | `null`, ou un objet décrivant l'interruption du traitement par une borne d'exécution ; il contient au moins `borne` (nom de la borne atteinte) |

### Trace

Chaque étape de `trace` est un objet contenant au moins :

- `agent` : nom de l'agent qui a réalisé l'étape ;
- `ecrit` : liste des sections de la demande écrites pendant l'étape (liste vide
  si aucune).

D'autres champs sont libres (action, durée, statut…).

Les **sections métier** d'une demande sont : `eligibilite`, `pieces`,
`estimation`, `avis_fraude`, `issue` (cette dernière portant la conclusion de la
demande). Une section métier n'est écrite que par un seul agent, et un agent
n'écrit qu'une seule section métier.

## Bornes d'exécution

`bornes()` retourne au minimum :

| Clé | Description |
|---|---|
| `etapes_max` | nombre maximal d'étapes pour une demande ; la longueur de `trace` ne le dépasse jamais |
| `duree_max_s` | durée maximale de traitement d'une demande, en secondes (au plus 10, voir l'engagement de service) |

Toute autre borne est libre. Une demande interrompue par une borne reçoit
quand même une issue, et sa fiche le signale dans `arret`.

## Métriques

`traiter_lot(...)["metriques"]` est un dictionnaire indexé par nom d'agent (tel
qu'il apparaît dans les traces). Chaque entrée contient au moins :

| Clé | Description |
|---|---|
| `appels` | nombre d'étapes réalisées par l'agent |
| `echecs` | nombre d'étapes en échec (erreur, délai dépassé, réponse écartée…) |
| `latence_ms` | durée moyenne d'une étape, en millisecondes |
| `appels_externes` | nombre d'appels à un service externe |

L'agent `antifraude` porte aussi `natures` : nombre d'étapes par nature d'appel au partenaire —
`ok` (avis validé), `timeout`, `invalide` (réponse écartée), `erreur` (erreur du service ou du
réseau), `non_envoye` (projection, jeton, URL ou registre : rien n'est parti), `non_requis` (aucun
indicateur F1–F4). `appels_externes` ne compte que `ok`, `timeout`, `invalide` et `erreur`.

`traiter_lot(...)["equipe"]` résume le lot :

| Clé | Description |
|---|---|
| `demandes` | nombre de fiches |
| `etapes` | `{"max", "moyenne"}` : longueur des traces |
| `arrets` | nombre d'arrêts par borne |
| `issues` | `{"decision", "escalade"}` |
| `escalades_par_file` | nombre d'escalades par file |
| `mode_degrade` | `{"n", "taux"}` |
| `duree_ms` | `{"p95", "max"}` : somme des durées des étapes d'une fiche |
| `ecritures_rejetees` | étapes en échec sur `ErreurEcriture` (attendu : 0) |

Dans la trace, l'étape `antifraude` porte `nature`, et toute étape en échec sur une exception
porte `erreur` (nom de l'exception).

Les étapes des agents LLM portent `mode` (`llm` ou `repli`) et, en repli, `cause` :
`llm_non_configure`, `disjoncteur`, `budget`, `erreur_llm`, `sortie_invalide`, `outil_refuse`,
`tours_max` ou `garde_fou`. La cause
`disjoncteur` signale un repli forcé sans appel au LLM : plus de 50 % des tentatives LLM de la
dernière minute (10 au moins) ont fini en repli. Le disjoncteur se referme seul.

## Scénarios de recette

`eval/scenarios.jsonl` contient un scénario par ligne :

| Champ | Description |
|---|---|
| `id` | identifiant du scénario |
| `categorie` | `nominal`, `antifraude`, `invalide`, `panne` ou `boucle` |
| `titre` | libellé |
| `partenaire` | comportement du partenaire simulé pendant le scénario : `mode` (`normal`, `lent`, `invalide`, `panne`), `variante` et `delai_s` éventuels |
| `demandes` | demandes soumises (format de la section 3 des spécifications) |
| `attendu` | issue attendue pour chaque demande, dans le même ordre ; seuls les champs présents sont vérifiés (`avis_fraude` y désigne le niveau attendu, `arret: true` un arrêt signalé) |

Le partenaire simulé se pilote avec `scripts/partner_ctl.py`.

## Suite d'acceptance

`make test` démarre le partenaire simulé dans le processus de test (port
libre, jeton de recette) : aucun service externe n'est requis.
