# SP1 · Moteur — garde T0, filet de sécurité niveau 1, lot parallèle

> Source : `dossier-conception.pdf` (2.2, 2.2 bis, 2.4, 2.5, 1.3 « Dépendances & parallélisme », §12).
> Branche : `feature/chantier1-orchestration` · point de départ : `ed75a27` (276 verts, 14 rouges A2A).
> Premier des trois sous-projets du reste du chantier 1 : **SP1 moteur** → SP2 persistance → SP3 ingestion.

## 1. Objectif

Combler trois écarts entre le dossier et le moteur, sans infrastructure nouvelle :

| Écart | Dossier | Exigence |
|---|---|---|
| B · garde d'entrée T0 + règle 0 | 2.2, 2.2 bis, 2.4 quater | EX-D26, EX-D40, EX-01 |
| C1 · filet de sécurité niveau 1 | 2.5 (niveau 1) | EX-D23, EX-01 |
| D · lot en parallèle | 1.3, §12 | EX-D15 |

Critère de sortie : les 276 tests verts le restent (les 28 scénarios passent sans changement, invariance
niveau 0), les nouveaux tests ci-dessous sont verts, les 14 rouges A2A restent rouges (hors périmètre).

### Décisions prises

| Sujet | Décision |
|---|---|
| Parallélisme | `ThreadPoolExecutor` dans `traiter_lot` ; le code reste synchrone. `asyncio` écarté (réécriture de `llm.py`, `partenaire.py`, `AgentLLM` sans gain mesuré). |
| Filet niveau 1 | **Un seul** `except Exception`, à la frontière la plus externe (`Orchestrateur.traiter`), justifié par EX-01 ; partout ailleurs les exceptions restent spécifiques (`CLAUDE.md`). |
| T0 | Table `GARDES_ENTREE` séparée de `TRANSITIONS`, évaluée **avant** l'action. |
| Contrat niveau 0 | `demande.contrat` du JSON est réputé validé : `statut_extraction = "valide"`, `source = "demande_json"`. |

### Hors périmètre

Snapshot, reaper et filet niveau 2 (SP2) ; `PieceRef`, ports et PostgreSQL (SP2) ; extraction VLM du
contrat et contrôle d'admission (SP3) ; A2A strict, disjoncteur LLM, `make eval` (chantier 2).

## 2. B · Garde d'entrée T0 et règle 0

### `machine.py`

```python
# gardes d'ENTRÉE : évaluées AVANT l'action de l'état (is_eligible() n'est pas appelé)
GARDES_ENTREE: tuple[tuple[Etat, Garde, Etat], ...] = (
    (Etat.ELIGIBILITE, lambda e, b: e.contrat.statut_extraction != "valide", Etat.DECISION),  # T0
)

def garde_entree(courant, etat, bornes) -> Etat | None: ...   # première garde vraie, sinon None
```

- `peut_atteindre` parcourt `TRANSITIONS + GARDES_ENTREE` (T0 compris, dossier 2.2 bis ③).
- `TRANSITIONS` et la numérotation T1–T11 ne changent pas (`test_numeros_tn_figes_sur_le_dossier`).

### `etat.py` — `ContratDemande` (provenance seulement)

```python
class ContratDemande(BaseModel):
    model_config = ConfigDict(frozen=True)
    statut_extraction: Literal["valide", "non_exploitable"] = "valide"
    violations: tuple[str, ...] = ()
    source: Literal["extraction_vlm", "demande_json"] = "demande_json"
    modele: str | None = None
    version_prompt: str | None = None
    sha256: str | None = None
```

- Nouveau champ `EtatDemande.contrat: ContratDemande`, construit par l'orchestrateur à l'entrée depuis
  `demande["contrat"]` : les clés de provenance présentes sont lues, les absentes prennent leur défaut
  (niveau 0 ⇒ `valide`). Les termes (`formule`, `franchise`…) restent dans `demande["contrat"]` : SP1 ne
  change ni `is_eligible()` ni l'estimation. SP3 remplira les mêmes champs depuis l'extraction VLM.
- `demande` reste immuable ; `contrat` est écrit par l'orchestrateur seul (pilotage), comme `trace`.
- Un champ de provenance invalide (ex. `statut_extraction: "peut-etre"`) ⇒ `ValidationError` ⇒ filet
  (§3), jamais d'éligibilité calculée.

### `orchestrateur.py` — le tour

Ordre du cycle (dossier 2.2 bis ②) : garde globale → **garde d'entrée** → vue → action → fusion →
transition → trace.

- Garde d'entrée vraie : l'action n'est **pas** exécutée, `eligibilite` reste `None`, étape tracée
  `{agent: "orchestrateur", action: "eligibilite", ecrit: [], statut: "ok", garde: "T0", de: "eligibilite",
  vers: "decision"}` ; `compteurs.etapes += 1`.
- La vue de `decision` gagne `contrat: {statut_extraction, violations}`.

### `agents.py` — règle 0 dans `_issue`

En **tête** de `_issue`, avant la règle 1 :

```python
if (vue.get("contrat") or {}).get("statut_extraction", "valide") != "valide":   # règle 0 (PQ8)
    return _escalade("gestionnaire", "Contrat illisible ou incohérent")
```

Sans règle 0, `decision` verrait `eligibilite = None` et tomberait sur « traitement incomplet » : la
règle 0 donne le motif juste. Le garde-fou `controle_decision` et le gabarit de motif n'ont rien à
ajouter (issue et file viennent de la référence).

## 3. C1 · Filet de sécurité niveau 1

`Orchestrateur.traiter(demande)` devient la frontière :

```python
def traiter(self, demande):
    etat = EtatDemande(demande=copy.deepcopy(demande))
    try:
        self._executer(etat)          # ancien executer, sur un état créé par l'appelant
    except Exception as exc:          # EX-01 : seule capture large du paquet, frontière externe
        self._filet(etat, exc)
    return construire_fiche(etat)
```

- `_filet` : étape tracée `{agent: "orchestrateur", action: "filet_securite", statut: "echec",
  ecrit: [], de: etat_courant, vers: "escalade", garde: "filet"}`, `escalade_forcee =
  "filet de sécurité : <TypeException>"`. Il ne relance rien et ne rappelle aucun agent.
- `construire_fiche`, quand `issue is None`, choisit la **file la plus prudente** (dossier 2.5) :
  1. contrat non exploitable ⇒ `gestionnaire` ;
  2. section `avis_fraude` présente avec avis élevé, ou avec indicateurs levés, sans avis exploitable
     et `estimation.estime` > 1 500 € ⇒ `cellule_fraude` (section absente : indicateurs inconnus ⇒ 3) ;
  3. sinon ⇒ `gestionnaire`.
  Motif : `"Escalade de secours : <raison> (dernier état : <etat_courant>)"`.
- Les `except` spécifiques actuels de `_etape` ne bougent pas : une erreur prévue d'agent reste une
  étape `echec` suivie d'une escalade par `decision` (EX-D07). Le filet ne prend que l'imprévu, y
  compris dans `decision` lui-même ou dans `_etape` hors du `try`.
- `executer(demande) -> EtatDemande` reste exposé (tests existants) : il crée l'état et appelle
  `_executer`, sans filet.
- La construction d'`Orchestrateur` (config, clients) reste hors filet : elle ne dépend d'aucune
  demande, son échec est une erreur de déploiement à laisser remonter.

## 4. D · `traiter_lot` en parallèle

```python
def traiter_lot(demandes, *, partenaire_url=None):
    orchestrateur = Orchestrateur(partenaire_url)
    with ThreadPoolExecutor() as pool:                     # ordre conservé par map
        fiches = list(pool.map(orchestrateur.traiter, demandes))
    return {"fiches": fiches, "metriques": _metriques_par_agent(fiches)}
```

- Isolation : un `EtatDemande` par demande, `debut` propre à chaque demande ; l'`Orchestrateur` et
  les `AgentLLM` partagés ne gardent aucun état par demande (vérifié : `AgentLLM.executer` n'écrit que
  des variables locales et sa `MesureAgent`).
- Grâce au filet (§3), une demande qui plante ne fait pas échouer le lot.
- Taille du pool : défaut de `ThreadPoolExecutor` (`min(32, cpu + 4)`).
  `# ponytail: pool par défaut ; borne explicite si le partenaire ou Azure limitent le débit`.
- Le commentaire `ponytail: séquentiel` de `__init__.py` est retiré ; une ligne au journal des
  ajustements consigne la mesure avant / après sur PAN-02 (lot avec partenaire à 5 s).

## 5. Tests

| Fichier | Test | Prouve |
|---|---|---|
| `test_machine.py` | `test_t0_mene_a_decision` : `(ELIGIBILITE, DECISION)` dans `GARDES_ENTREE` | T0 dans le graphe |
| `test_machine.py` | les preuves de terminaison existantes passent avec `GARDES_ENTREE` dans `peut_atteindre` | EX-D27 |
| `test_orchestrateur.py` | `test_is_eligible_non_appele_si_contrat_non_valide` (espion sur l'action d'éligibilité) : 0 appel, fiche `escalade` / `gestionnaire`, motif « Contrat illisible ou incohérent », étape tracée `garde = "T0"` | EX-D40, règle 0 |
| `test_orchestrateur.py` | provenance invalide ⇒ fiche de secours, jamais d'éligibilité | EX-01 |
| `test_agents.py` | règle 0 passe avant la règle 1 | ordre §10 |
| `test_orchestrateur.py` | action qui lève `RuntimeError` (imprévue) en `estimation`, puis en `decision` : fiche `escalade`, étape `filet_securite`, `dernier état` dans le motif | EX-D23 |
| `test_orchestrateur.py` | file prudente : F1–F4 sans avis + estimé > 1 500 € ⇒ `cellule_fraude` ; contrat non exploitable ⇒ `gestionnaire` | 2.5 |
| `test_points_entree.py` | lot de N demandes dont chaque action dort 0,2 s : durée < N × 0,2 s ; ordre conservé | EX-D15 |
| `test_points_entree.py` | une demande du lot qui plante n'empêche pas les autres fiches | isolation |
| `test_invariance.py` | inchangé : 34 demandes, issues identiques (niveau 0 ⇒ `valide`) | invariance 0 / 1 |

## 6. Fichiers touchés

`machine.py` (GARDES_ENTREE, garde_entree, peut_atteindre) · `etat.py` (ContratDemande, champ
`contrat`) · `orchestrateur.py` (garde d'entrée dans le tour, `traiter` + `_filet`, file prudente dans
`construire_fiche`, contrat dans la vue de `decision`) · `agents.py` (règle 0) · `__init__.py`
(pool) · `docs/journal_ajustements.md` · tests ci-dessus.
