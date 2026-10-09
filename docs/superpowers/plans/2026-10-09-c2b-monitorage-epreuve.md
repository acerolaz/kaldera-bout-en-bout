# C2b · Monitorage et épreuve — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre l'équipe observable (nature de chaque appel partenaire, métriques par agent et d'équipe) et livrer `make epreuve`, qui rejoue les 28 scénarios contre le simulateur en processus et rend un verdict par exigence, puis consigner l'épreuve au journal.

**Architecture:** `partenaire.nature(cause)` classe les causes là où elles naissent ; l'orchestrateur écrit `nature` et `erreur` dans la trace ; `kaldera.metriques_par_agent` / `kaldera.metriques_equipe` agrègent les fiches ; `tools/epreuve.py` (modèle : `tools/eval_ingestion.py`) démarre `external_agent.app` sur un port libre, rejoue avec un registre et des snapshots en mémoire, calcule verdicts, couverture et seuils (fonctions pures), écrit `eval/rapports/epreuve-<date>.md|.json`.

**Tech Stack:** Python 3.11, httpx, uvicorn, Pydantic v2, pytest, ruff, mypy. Commandes via `uv run`.

**Spec:** `docs/superpowers/specs/2026-10-09-c2b-monitorage-epreuve-design.md`

## Global Constraints

- Ne jamais modifier `tests/acceptance/`, `external_agent/` ni `eval/scenarios.jsonl` (fournis).
- Ne jamais rien lancer contre le port 5433 ; ne pas lancer `make test-integration`. Intégration, si besoin : `TEST_DATABASE_URL=postgresql://kaldera:kaldera@localhost:5434/kaldera_test` (base jetable, à démarrer par le contrôleur).
- Clés existantes de `traiter_lot()["metriques"]` inchangées ; `equipe` est une clé de premier niveau de `traiter_lot()`, jamais une entrée de `metriques`.
- Natures : exactement `ok`, `timeout`, `invalide`, `erreur`, `non_envoye`, `non_requis` ; `appels_externes` ne compte que `ok`, `timeout`, `invalide`, `erreur`.
- Une cause ne contient jamais une valeur ni une clé venue du partenaire.
- `tools/` n'importe rien de `tests/`.
- Lignes ≤ 100 caractères (compter les caractères, pas les octets) ; `uv run ruff check src tests tools`, `uv run mypy src` propres ; aucun import `*`.
- Commits en français, terminés par un trailer `Co-Authored-By:` au nom du modèle réel.

## Review Focus

1. `make epreuve` lancé deux fois de suite, ou avec `KALDERA_DATABASE_URL` dans `.env` (que `make` exporte) → même résultat : l'épreuve n'utilise jamais Postgres (sinon le registre bloquerait le 2ᵉ passage en « déjà soumis »). Test : Task 5.
2. Une exception pendant le rejeu → le simulateur est quand même arrêté (pas de fil ni de port laissés ouverts). Test : Task 5.
3. `metriques_equipe([])` (lot vide) → pas de `ZeroDivisionError`, valeurs à 0. Test : Task 3.
4. Une référence de l'`attendu` sans fiche correspondante → écart nommé dans le verdict, jamais un `KeyError`. Test : Task 4.
5. URL d'appel relative ou sans hôte (`pas une url`, accepté par `httpx.URL`) → « URL partenaire invalide » sans réservation. Test : Task 1.

---

## File Structure

| Fichier | Responsabilité | Tâches |
|---|---|---|
| `src/kaldera/partenaire.py` | URL/jeton avant réservation ; `NATURES`, `ENVOYES`, `nature(cause)` | 1, 2 |
| `src/kaldera/orchestrateur.py` | trace : `nature` (étape antifraude), `erreur` (étape en échec) ; `appels_externes` selon la nature | 2 |
| `src/kaldera/__init__.py` | `metriques_par_agent` (+ `natures`), `metriques_equipe`, `traiter_lot` renvoie `equipe` | 3 |
| `src/kaldera/cli.py` | affiche `equipe` | 3 |
| `docs/interface.md` | `natures`, `equipe`, champs `nature` / `erreur` de la trace | 3 |
| `tools/epreuve.py` | verdicts, couverture, seuils, bornes, rapport (Task 4) ; simulateur, rejeu, `evaluer`, `main` (Task 5) | 4, 5 |
| `Makefile` | cible `epreuve` | 5 |
| `tests/unit/test_orchestrateur.py`, `test_base_par_defaut.py`, `test_partenaire.py` | dette C2a ; nature ; trace | 1, 2 |
| `tests/unit/test_metriques.py` | métriques sur fiches fabriquées | 3 |
| `tests/unit/test_epreuve.py` | verdicts, seuils, rapport, simulateur, fumée | 4, 5 |
| `docs/journal_ajustements.md`, `README.md`, `eval/rapports/` | épreuve consignée, rapport final | 6 |

---

### Task 1: Dette C2a — test déterministe, `.env`, URL et jeton avant la réservation

**Files:**
- Modify: `src/kaldera/partenaire.py` (`evaluer_risque`, juste après le contrôle `jeton absent`)
- Modify: `tests/unit/test_orchestrateur.py` (`test_partenaire_muet_abandonne_au_delai`)
- Modify: `tests/unit/test_base_par_defaut.py` (`test_sans_url_aucun_registre_persistant`)
- Modify: `tests/unit/test_partenaire.py` (`test_sans_base_registre_en_memoire` ; nouveaux tests)

**Interfaces:**
- Consumes: `partenaire.evaluer_risque(demande, url, *, registre, timeout=None)`, fixtures `envoi`, `ordre`, classe `Registre`, helper `_demande` de `tests/unit/test_partenaire.py`.
- Produces: nouvelles causes `"URL partenaire invalide"` et `"jeton invalide"` (aucune réservation).

- [ ] **Step 1: Write the failing tests**

Dans `tests/unit/test_partenaire.py`, ajouter après `test_jeton_absent_aucune_reservation` (ou à la fin de la section « appel complet ») :

```python
@pytest.mark.parametrize(
    "url", ["http://localhost:81OO/a2a", "http://[::1/a2a", "pas une url", "ftp://h/a2a"]
)
def test_url_invalide_aucune_reservation(envoi: Envoi, ordre: list[str], url: str) -> None:
    """Review Focus 5 : une erreur de configuration ne consomme pas l'appel unique."""
    registre = Registre(ordre)
    avis = partenaire.evaluer_risque(_demande(), url, registre=registre, timeout=3)
    assert avis == Indisponible("URL partenaire invalide")
    assert ordre == [] and registre.evaluations == {}


def test_jeton_non_ascii_aucune_reservation(
    envoi: Envoi, ordre: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PARTENAIRE_JETON", "jéton")
    registre = Registre(ordre)
    avis = partenaire.evaluer_risque(_demande(), URL, registre=registre, timeout=3)
    assert avis == Indisponible("jeton invalide")
    assert ordre == [] and registre.evaluations == {}
```

Remplacer l'assertion de `test_partenaire_muet_abandonne_au_delai` (`tests/unit/test_orchestrateur.py`) par :

```python
        # course légitime : l'échéance du fil ou le ReadTimeout de httpx (même délai) gagne
        assert avis in (Indisponible("délai > 0.3 s"), Indisponible("couche ① : ReadTimeout"))
        assert time.monotonic() - debut < 2
```

Isoler du `.env` local (`ConfigBase` lit `.env` relativement au répertoire courant) :

```python
def test_sans_url_aucun_registre_persistant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # aucun .env local lu
    assert registre_par_defaut() is None
```

(ajouter `from pathlib import Path` aux imports de `test_base_par_defaut.py` si absent) et, dans `test_sans_base_registre_en_memoire` (`tests/unit/test_partenaire.py`), ajouter le paramètre `tmp_path: Path` et `monkeypatch.chdir(tmp_path)` en première ligne (ajouter `from pathlib import Path` s'il manque).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_partenaire.py -q -k "url_invalide or non_ascii"`
Expected: FAIL — les URL invalides et le jeton non ASCII renvoient une cause `couche ① : …` après réservation (`ordre == ["reserver", …]`).

- [ ] **Step 3: Write minimal implementation**

Dans `evaluer_risque`, juste après le bloc `if not jeton: return Indisponible("jeton absent")` :

```python
    if not jeton.isascii():  # en-tête HTTP impossible : ne pas consommer l'appel unique
        return Indisponible("jeton invalide")
    try:
        cible: httpx.URL | None = httpx.URL(url)
    except httpx.InvalidURL:
        cible = None
    if cible is None or cible.scheme not in ("http", "https") or not cible.host:
        return Indisponible("URL partenaire invalide")
```

Mettre à jour la docstring : « Projection, jeton, URL, puis réservation, puis envoi … ».

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit -q && uv run ruff check src tests && uv run mypy src`
Expected: tout PASS ; `test_partenaire_muet_abandonne_au_delai` stable : `for i in $(seq 1 20); do uv run pytest -q -p no:cacheprovider "tests/unit/test_orchestrateur.py::test_partenaire_muet_abandonne_au_delai" | tail -1; done | sort | uniq -c` → 20 passed.

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/partenaire.py tests/unit/test_orchestrateur.py tests/unit/test_base_par_defaut.py tests/unit/test_partenaire.py
git commit -m "fix(a2a): URL et jeton vérifiés avant la réservation ; tests sans .env, abandon au délai déterministe"
```

---

### Task 2: Nature de chaque appel, champs `nature` et `erreur` de la trace

**Files:**
- Modify: `src/kaldera/partenaire.py` (constantes et `nature`, après `class Indisponible`)
- Modify: `src/kaldera/orchestrateur.py` (`_etape` : bloc `except`, bloc `externes, motif`, `etat.trace.append`)
- Test: `tests/unit/test_partenaire.py`, `tests/unit/test_orchestrateur.py`

**Interfaces:**
- Consumes: causes produites par `partenaire` (Tasks C2a + Task 1).
- Produces:
  - `partenaire.NATURES: tuple[str, ...] = ("ok", "timeout", "invalide", "erreur", "non_envoye", "non_requis")`
  - `partenaire.ENVOYES: frozenset[str] = frozenset({"ok", "timeout", "invalide", "erreur"})`
  - `partenaire.nature(cause: str | None) -> str` (`None` ⇒ `"ok"`)
  - trace : étape `antifraude` réussie ⇒ clé `"nature"` ; toute étape en échec par exception ⇒ clé `"erreur": <nom de l'exception>` ; `appels_externes = int(nature in ENVOYES)`.

- [ ] **Step 1: Write the failing tests**

Dans `tests/unit/test_partenaire.py` :

```python
# ------------------------------------------------------------------ nature


@pytest.mark.parametrize(
    ("cause", "attendue"),
    [
        (None, "ok"),
        ("délai > 3 s", "timeout"),
        ("couche ① : ReadTimeout", "timeout"),
        ("couche ① : ConnectTimeout", "timeout"),
        ("couche ① : corps illisible (HTTP 200)", "invalide"),
        ("couche ② : enveloppe JSON-RPC invalide", "invalide"),
        ("couche ② : id JSON-RPC différent de la requête", "invalide"),
        ("couche ② : tâche non terminée ou artefact invalide", "invalide"),
        ("couche ③ : champ hors contrat", "invalide"),
        ("couche ④ : score hors bornes", "invalide"),
        ("couche ④ : niveau incohérent avec le score", "invalide"),
        ("couche ④ : référence différente de la requête", "invalide"),
        ("HTTP 401 (jeton)", "erreur"),
        ("HTTP 503", "erreur"),
        ("couche ① : HTTP 500", "erreur"),
        ("JSON-RPC -32602 : projection refusée", "erreur"),
        ("JSON-RPC -32029 : doublon refusé : manquement au contrat", "erreur"),
        ("JSON-RPC ? : erreur inconnue", "erreur"),
        ("couche ① : ConnectError", "erreur"),
        ("cause non précisée", "erreur"),
        ("une cause que personne ne produit", "erreur"),
        ("projection : donnée invalide", "non_envoye"),
        ("projection : donnée absente (sinistre)", "non_envoye"),
        ("jeton absent", "non_envoye"),
        ("jeton invalide", "non_envoye"),
        ("URL partenaire invalide", "non_envoye"),
        ("registre : dossier déjà soumis", "non_envoye"),
        ("registre indisponible", "non_envoye"),
    ],
)
def test_nature_de_chaque_cause(cause: str | None, attendue: str) -> None:
    assert partenaire.nature(cause) == attendue
    assert attendue in partenaire.NATURES


def test_envoyes() -> None:
    assert partenaire.ENVOYES == {"ok", "timeout", "invalide", "erreur"}
```

Dans `tests/unit/test_orchestrateur.py` (section « partenaire », `_indisponible` existe déjà et renvoie `Indisponible("couche ③ : champ hors contrat")`) :

```python
def _non_envoye(demande: dict[str, Any], timeout: float) -> Indisponible:
    return Indisponible("registre : dossier déjà soumis")


@pytest.mark.parametrize(
    ("evaluer", "nature", "externes"),
    [(_indisponible, "invalide", 1), (_non_envoye, "non_envoye", 0)],
)
def test_nature_et_appels_externes_dans_la_trace(
    evaluer: Any, nature: str, externes: int
) -> None:
    fiche = Orchestrateur(evaluer=evaluer).traiter(_demande("PAN-01", 3))
    (etape,) = [e for e in fiche["trace"] if e["agent"] == "antifraude"]
    assert etape["nature"] == nature and etape["appels_externes"] == externes


def test_nature_non_requis_sans_indicateur() -> None:
    fiche = Orchestrateur(evaluer=_sans_partenaire).traiter(_demande("NOM-01"))
    (etape,) = [e for e in fiche["trace"] if e["agent"] == "antifraude"]
    assert etape["nature"] == "non_requis" and etape["appels_externes"] == 0


def test_erreur_nommee_dans_l_etape_en_echec() -> None:
    def ecrit_ailleurs(vue: dict[str, Any]) -> dict[str, Any]:
        return {"issue": {"issue": "decision"}}  # section d'un autre agent

    fiche = _orchestrateur(estimation=ecrit_ailleurs).traiter(_demande("NOM-01"))
    (etape,) = [e for e in fiche["trace"] if e["action"] == "estimation"]
    assert etape["statut"] == "echec" and etape["erreur"] == "ErreurEcriture"
```

(`_orchestrateur(**remplacements)` existe déjà dans ce fichier et remplace l'action de l'état nommé. Si `fusionner` lève autre chose qu'`ErreurEcriture` pour ce patch, lire `fusionner` dans `orchestrateur.py` et choisir un patch qui déclenche bien `ErreurEcriture` — section d'un autre agent ou section déjà écrite — sans changer l'assertion.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_partenaire.py tests/unit/test_orchestrateur.py -q -k "nature or envoyes or erreur_nommee"`
Expected: FAIL — `AttributeError: module 'kaldera.partenaire' has no attribute 'nature'`, puis `KeyError: 'nature'` / `'erreur'`.

- [ ] **Step 3: Write minimal implementation**

`src/kaldera/partenaire.py`, après `class Indisponible` :

```python
NATURES = ("ok", "timeout", "invalide", "erreur", "non_envoye", "non_requis")
ENVOYES = frozenset({"ok", "timeout", "invalide", "erreur"})  # seuls comptés en appels externes
_NON_ENVOYE = ("projection", "jeton absent", "jeton invalide", "URL partenaire invalide", "registre")
_INVALIDE = ("couche ① : corps illisible", "couche ②", "couche ③", "couche ④")


def nature(cause: str | None) -> str:
    """Nature d'un appel au partenaire d'après sa cause (``None`` : avis obtenu) ; métriques C2b."""
    if cause is None:
        return "ok"
    if cause.startswith(_NON_ENVOYE):
        return "non_envoye"
    if cause.startswith("délai") or (cause.startswith("couche ① : ") and cause.endswith("Timeout")):
        return "timeout"
    if cause.startswith(_INVALIDE):
        return "invalide"
    return "erreur"  # HTTP, JSON-RPC, réseau, cause non précisée ou inconnue
```

`src/kaldera/orchestrateur.py`, dans `_etape` :
- initialiser `erreur: str | None = None` avec `debut, statut, ecrit` ;
- dans le bloc `except (...) as exc:` ajouter `erreur = type(exc).__name__` ;
- remplacer le bloc `externes, motif = 0, None` … par :

```python
        externes, motif, nature = 0, None, None
        if statut == "ok" and courant is Etat.ANTIFRAUDE and etat.avis_fraude is not None:
            avis = etat.avis_fraude
            nature = partenaire.nature(avis.cause) if avis.requis else "non_requis"
            externes = int(nature in partenaire.ENVOYES)  # un appel non parti n'est pas compté
            if avis.statut == "indisponible":
                statut = "echec"  # avis non obtenu : compté en échec, mode dégradé en aval
                motif = avis.cause  # code et couche, jamais le corps (C2-Q8)
```

- dans `etat.trace.append({...})`, après la ligne `**({"motif": motif} if motif else {}),` ajouter :

```python
                **({"nature": nature} if nature else {}),
                **({"erreur": erreur} if erreur else {}),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit -q && uv run pytest tests/acceptance -q && uv run ruff check src tests && uv run mypy src`
Expected: tout PASS ; acceptance 56 passed.

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/partenaire.py src/kaldera/orchestrateur.py tests/unit/test_partenaire.py tests/unit/test_orchestrateur.py
git commit -m "feat(metriques): nature de chaque appel partenaire ; nature et erreur dans la trace"
```

---

### Task 3: Métriques par agent (`natures`) et d'équipe (`equipe`)

**Files:**
- Modify: `src/kaldera/__init__.py`
- Modify: `src/kaldera/cli.py` (ligne qui affiche `{"metriques": ...}`)
- Modify: `docs/interface.md` (section « Métriques » ; table de `traiter_lot`)
- Create: `tests/unit/test_metriques.py`

**Interfaces:**
- Consumes: champs de trace `nature`, `erreur`, `duree_ms`, `agent`, `statut`, `appels_externes` (Task 2) ; `partenaire.NATURES`.
- Produces:
  - `kaldera.metriques_par_agent(fiches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]` (renommage public de `_metriques_par_agent` ; l'agent qui porte des étapes avec `nature` reçoit `"natures": {nature: n}` avec les 6 clés de `NATURES`)
  - `kaldera.metriques_equipe(fiches: list[dict[str, Any]]) -> dict[str, Any]`
  - `kaldera.traiter_lot(...)` renvoie `{"fiches": [...], "metriques": {...}, "equipe": {...}}`

- [ ] **Step 1: Write the failing tests**

Créer `tests/unit/test_metriques.py` :

```python
"""Unitaires — métriques par agent et d'équipe (C2b, C2-Q15) sur des fiches fabriquées."""

from __future__ import annotations

from typing import Any

import kaldera
from kaldera.partenaire import NATURES


def _etape(agent: str, duree: float = 10.0, **champs: Any) -> dict[str, Any]:
    return {"agent": agent, "statut": "ok", "duree_ms": duree, "appels_externes": 0, **champs}


def _fiche(
    trace: list[dict[str, Any]],
    issue: str = "decision",
    file: str | None = None,
    mode_degrade: bool = False,
    arret: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "reference": "KAL-26-0001",
        "issue": issue,
        "file": file,
        "mode_degrade": mode_degrade,
        "arret": arret,
        "trace": trace,
    }


def test_natures_de_l_agent_antifraude() -> None:
    fiches = [
        _fiche([_etape("antifraude", nature="ok", appels_externes=1)]),
        _fiche([_etape("antifraude", nature="timeout", appels_externes=1, statut="echec")]),
        _fiche([_etape("antifraude", nature="non_envoye", statut="echec")]),
        _fiche([_etape("antifraude", nature="non_requis")]),
    ]
    m = kaldera.metriques_par_agent(fiches)["antifraude"]
    assert m["natures"] == {
        "ok": 1, "timeout": 1, "invalide": 0, "erreur": 0, "non_envoye": 1, "non_requis": 1
    }
    assert set(m["natures"]) == set(NATURES)
    assert m["appels_externes"] == 2 and m["echecs"] == 2


def test_agent_sans_nature_sans_cle_natures() -> None:
    m = kaldera.metriques_par_agent([_fiche([_etape("pieces")])])["pieces"]
    assert "natures" not in m


def test_equipe() -> None:
    fiches = [
        _fiche([_etape("pieces", duree=float(i)) for _ in range(3)]) for i in range(1, 21)
    ]
    fiches.append(
        _fiche(
            [_etape("decision", duree=500.0, statut="echec", erreur="ErreurEcriture")],
            issue="escalade",
            file="cellule_fraude",
            mode_degrade=True,
            arret={"borne": "relances_pieces_max", "valeur": 1, "etape": 4},
        )
    )
    e = kaldera.metriques_equipe(fiches)
    assert e["demandes"] == 21
    assert e["etapes"] == {"max": 3, "moyenne": round(61 / 21, 2)}
    assert e["arrets"] == {"relances_pieces_max": 1}
    assert e["issues"] == {"decision": 20, "escalade": 1}
    assert e["escalades_par_file"] == {"cellule_fraude": 1}
    assert e["mode_degrade"] == {"n": 1, "taux": round(1 / 21, 4)}
    # durées par fiche : 3, 6, …, 60 (20 fiches) puis 500 ; rang 95 % (plus proche) : ceil(0,95×21) = 20
    assert e["duree_ms"] == {"p95": 60.0, "max": 500.0}
    assert e["ecritures_rejetees"] == 1


def test_equipe_lot_vide() -> None:
    """Review Focus 3."""
    e = kaldera.metriques_equipe([])
    assert e["demandes"] == 0
    assert e["etapes"] == {"max": 0, "moyenne": 0.0}
    assert e["mode_degrade"] == {"n": 0, "taux": 0.0}
    assert e["duree_ms"] == {"p95": 0.0, "max": 0.0}
    assert e["issues"] == {"decision": 0, "escalade": 0}


def test_traiter_lot_renvoie_equipe() -> None:
    import copy
    import json
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    nom = json.loads((racine / "eval/scenarios.jsonl").read_text("utf-8").splitlines()[0])
    resultat = kaldera.traiter_lot(copy.deepcopy(nom["demandes"]))
    assert set(resultat) == {"fiches", "metriques", "equipe"}
    assert resultat["equipe"]["demandes"] == len(nom["demandes"])
    assert "equipe" not in resultat["metriques"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_metriques.py -q`
Expected: FAIL — `AttributeError: module 'kaldera' has no attribute 'metriques_par_agent'`.

- [ ] **Step 3: Write minimal implementation**

`src/kaldera/__init__.py` : ajouter `import math` et `from collections import Counter` aux imports, `from .partenaire import NATURES` après `from .orchestrateur import Orchestrateur`, mettre `__all__ = ["bornes", "metriques_equipe", "metriques_par_agent", "traiter_demande", "traiter_lot"]`, faire renvoyer à `traiter_lot` :

```python
    return {
        "fiches": fiches,
        "metriques": metriques_par_agent(fiches),
        "equipe": metriques_equipe(fiches),
    }
```

renommer `_metriques_par_agent` en `metriques_par_agent` (docstring : « Métriques par agent (EX-D14, C2-Q15) : clés de `docs/interface.md`. ») et, dans sa boucle, après `m["appels_externes"] += etape["appels_externes"]` :

```python
        if "nature" in etape:  # agent antifraude (C2b)
            natures = m.setdefault("natures", dict.fromkeys(NATURES, 0))
            natures[etape["nature"]] += 1
```

puis ajouter à la fin du module :

```python
def metriques_equipe(fiches: list[dict[str, Any]]) -> dict[str, Any]:
    """Métriques de l'équipe sur un lot (C2-Q15) ; un lot vide donne des zéros."""
    n = len(fiches)
    etapes = [len(f["trace"]) for f in fiches]
    durees = sorted(sum(e["duree_ms"] for e in f["trace"]) for f in fiches)
    degrades = sum(bool(f.get("mode_degrade")) for f in fiches)
    issues = Counter(f["issue"] for f in fiches)
    return {
        "demandes": n,
        "etapes": {"max": max(etapes, default=0), "moyenne": round(sum(etapes) / n, 2) if n else 0.0},
        "arrets": dict(Counter(f["arret"]["borne"] for f in fiches if f.get("arret"))),
        "issues": {"decision": issues["decision"], "escalade": issues["escalade"]},
        "escalades_par_file": dict(Counter(f["file"] for f in fiches if f["issue"] == "escalade")),
        "mode_degrade": {"n": degrades, "taux": round(degrades / n, 4) if n else 0.0},
        "duree_ms": {
            # centile au rang le plus proche : une durée réellement observée
            "p95": round(durees[math.ceil(0.95 * n) - 1], 2) if n else 0.0,
            "max": round(durees[-1], 2) if n else 0.0,
        },
        "ecritures_rejetees": sum(
            e.get("erreur") == "ErreurEcriture" for f in fiches for e in f["trace"]
        ),
    }
```

(si une ligne dépasse 100 caractères, la couper ; `ruff format` est permis sur ce fichier.)

`src/kaldera/cli.py` : remplacer la ligne finale d'affichage par
`print(json.dumps({"metriques": resultat["metriques"], "equipe": resultat["equipe"]}, ensure_ascii=False))`
(couper la ligne si besoin).

`docs/interface.md` :
- table des fonctions : `traiter_lot` retourne `{"fiches": [...], "metriques": {...}, "equipe": {...}}` ;
- section « Métriques », après la table existante :

```markdown
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit -q && uv run pytest tests/acceptance -q && uv run ruff check src tests && uv run mypy src`
Expected: tout PASS (`test_points_entree.py` inchangé : `set(metriques)` = agents des traces).

- [ ] **Step 5: Commit**

```bash
git add src/kaldera/__init__.py src/kaldera/cli.py docs/interface.md tests/unit/test_metriques.py
git commit -m "feat(metriques): natures de l'antifraude et métriques d'équipe dans traiter_lot"
```

---

### Task 4: Épreuve — verdicts, couverture, seuils, bornes, rapport (fonctions pures)

**Files:**
- Create: `tools/epreuve.py` (partie pure ; le rejeu vient en Task 5)
- Create: `tests/unit/test_epreuve.py`

**Interfaces:**
- Consumes: `kaldera.metriques_equipe`, `kaldera.etat.PROPRIETAIRES`, `kaldera.etat.Bornes`, `kaldera.machine.TRANSITIONS`.
- Produces (dans `tools/epreuve.py`) — un **rejeu** est un `dict` `{"scenario": <ligne de scenarios.jsonl>, "fiches": [fiche…], "journal": [entrée du simulateur…]}` :
  - `CHAMPS_CONTRAT: frozenset[str]` (les 7 champs)
  - `valeurs_personnelles(demande: dict[str, Any]) -> list[str]`
  - `verdicts(rejeux: list[dict[str, Any]], bornes: Bornes) -> dict[str, list[str]]` — clés `"EX-01"` … `"EX-06"`, `"attendu"` ; liste vide = ✅
  - `couverture(rejeux: list[dict[str, Any]]) -> dict[str, Any]` — `{"empruntees": [...], "manquantes": [...], "hors_scenarios": {"T0": "ING-01 / ING-02 (make eval-ingestion)"}}`
  - `seuils(rejeux: list[dict[str, Any]], equipe: dict[str, Any], bornes: Bornes) -> list[dict[str, Any]]` — chaque élément `{"nom": str, "mesure": float | int, "seuil": str, "ok": bool}`
  - `bornes_observees(rejeux: list[dict[str, Any]], equipe: dict[str, Any], bornes: Bornes) -> list[dict[str, Any]]` — `{"borne", "valeur", "observe"}`
  - `ecrire_rapport(rapport: dict[str, Any], dossier: Path = RAPPORTS) -> Path`
  - `RAPPORTS = Path(__file__).resolve().parents[1] / "eval/rapports"`

- [ ] **Step 1: Write the failing tests**

Créer `tests/unit/test_epreuve.py` :

```python
"""Unitaires — l'outil d'épreuve (C2b) : verdicts, couverture, seuils, rapport."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import Bornes
from tools import epreuve

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}
BORNES = Bornes()


def _etape(agent: str, ecrit: list[str], garde: str = "T1", **champs: Any) -> dict[str, Any]:
    return {
        "agent": agent, "ecrit": ecrit, "statut": "ok", "garde": garde,
        "duree_ms": 5.0, "appels_externes": 0, **champs,
    }


def _fiche_conforme(attendu: dict[str, Any]) -> dict[str, Any]:
    """Fiche qui respecte son attendu et les règles de rôles."""
    avis = attendu.get("avis_fraude")
    return {
        "reference": attendu["reference"],
        "issue": attendu["issue"],
        "decision": attendu.get("decision"),
        "montant_rembourse": attendu.get("montant_rembourse"),
        "file": attendu.get("file"),
        "mode_degrade": attendu.get("mode_degrade", False),
        "motif": "Motif suffisant",
        "avis_fraude": {"niveau": avis} if avis else None,
        "arret": {"borne": "relances_pieces_max", "valeur": 1, "etape": 4}
        if attendu.get("arret") else None,
        "trace": [
            _etape("orchestrateur", ["eligibilite"]),
            _etape("decision", ["issue"], garde="T11"),
        ],
    }


def _rejeu(scenario_id: str) -> dict[str, Any]:
    scenario = copy.deepcopy(SCENARIOS[scenario_id])
    return {
        "scenario": scenario,
        "fiches": [_fiche_conforme(a) for a in scenario["attendu"]],
        "journal": [],
    }


def test_verdicts_tout_conforme() -> None:
    rejeux = [_rejeu(i) for i in ("NOM-01", "INV-01", "PAN-01", "BCL-01")]
    assert all(not e for e in epreuve.verdicts(rejeux, BORNES).values())


def test_ex01_issue_sans_motif() -> None:
    r = _rejeu("NOM-01")
    r["fiches"][0]["motif"] = ""
    assert epreuve.verdicts([r], BORNES)["EX-01"]


def test_ex02_section_ecrite_par_un_autre_agent() -> None:
    r = _rejeu("NOM-01")
    r["fiches"][0]["trace"].append(_etape("pieces", ["issue"]))
    assert epreuve.verdicts([r], BORNES)["EX-02"]


def test_ex02_ecriture_rejetee() -> None:
    r = _rejeu("NOM-01")
    r["fiches"][0]["trace"].append(_etape("estimation", [], statut="echec", erreur="ErreurEcriture"))
    assert epreuve.verdicts([r], BORNES)["EX-02"]


def test_ex03_champ_hors_contrat_et_donnee_personnelle() -> None:
    r = _rejeu("AF-01")
    demande = r["scenario"]["demandes"][0]
    r["journal"] = [
        {"reference": demande["reference"], "champs": sorted(epreuve.CHAMPS_CONTRAT | {"iban"}),
         "corps_brut": "{}"},
        {"reference": demande["reference"], "champs": sorted(epreuve.CHAMPS_CONTRAT),
         "corps_brut": json.dumps({"nom": demande["assure"]["nom"]})},
    ]
    ecarts = epreuve.verdicts([r], BORNES)["EX-03"]
    assert len(ecarts) == 2 and all(demande["assure"]["nom"] not in e for e in ecarts)


def test_ex03_requete_conforme() -> None:
    r = _rejeu("AF-01")
    r["journal"] = [{"reference": r["scenario"]["demandes"][0]["reference"],
                     "champs": sorted(epreuve.CHAMPS_CONTRAT), "corps_brut": "{}"}]
    assert not epreuve.verdicts([r], BORNES)["EX-03"]


def test_ex03_requete_non_lue_en_panne_pas_un_ecart() -> None:
    r = _rejeu("PAN-01")
    r["journal"] = [{"reference": r["scenario"]["demandes"][0]["reference"], "champs": [],
                     "statut_http": 503, "corps_brut": "{}"}]
    assert not epreuve.verdicts([r], BORNES)["EX-03"]


def test_ex04_avis_propage_sur_invalide() -> None:
    r = _rejeu("INV-01")
    r["fiches"][0]["avis_fraude"] = {"niveau": "faible"}
    assert epreuve.verdicts([r], BORNES)["EX-04"]


def test_ex05_panne_mode_degrade_faux() -> None:
    r = _rejeu("PAN-01")
    fiche = next(f for f in r["fiches"] if f["mode_degrade"])
    fiche["mode_degrade"] = False
    assert epreuve.verdicts([r], BORNES)["EX-05"]


def test_ex06_boucle_sans_arret_ou_trop_longue() -> None:
    r = _rejeu("BCL-01")
    r["fiches"][0]["arret"] = None
    assert epreuve.verdicts([r], BORNES)["EX-06"]
    r = _rejeu("BCL-01")
    r["fiches"][0]["trace"] = [_etape("pieces", [])] * (BORNES.etapes_max + 1)
    assert epreuve.verdicts([r], BORNES)["EX-06"]


def test_attendu_ecart_et_fiche_absente() -> None:
    """Review Focus 4 : une référence sans fiche est un écart, pas un KeyError."""
    r = _rejeu("NOM-01")
    r["fiches"][0]["montant_rembourse"] = (r["fiches"][0]["montant_rembourse"] or 0) + 1
    assert epreuve.verdicts([r], BORNES)["attendu"]
    r = _rejeu("NOM-01")
    r["fiches"] = []
    ecarts = epreuve.verdicts([r], BORNES)["attendu"]
    assert ecarts and "aucune fiche" in ecarts[0]


def test_couverture() -> None:
    r = _rejeu("NOM-01")
    r["fiches"][0]["trace"] = [_etape("x", [], garde=f"T{i}") for i in range(1, 11)]
    c = epreuve.couverture([r])
    assert c["manquantes"] == ["T11"] and "T0" in c["hors_scenarios"]
    assert "T0" not in c["manquantes"]


def test_seuils() -> None:
    r = _rejeu("NOM-01")
    reference = r["scenario"]["demandes"][0]["reference"]
    r["journal"] = [{"reference": reference}, {"reference": reference}]
    equipe = {
        "duree_ms": {"p95": 9000.0, "max": 100.0},
        "ecritures_rejetees": 0,
        "etapes": {"max": 5, "moyenne": 5.0},
        "arrets": {"duree_max_s": 1},
    }
    resultat = {s["nom"]: s["ok"] for s in epreuve.seuils([r], equipe, BORNES)}
    assert resultat == {
        "durée p95 (ms)": False,
        "durée max (ms)": True,
        "écritures rejetées": True,
        "étapes max": True,
        "arrêts hors relances_pieces_max": False,
        "appels partenaire par référence": False,
    }


def test_ecrire_rapport(tmp_path: Path) -> None:
    """Review Focus : dossier créé, JSON sérialisable, Markdown lisible."""
    rapport = {
        "date": "2026-10-09",
        "reussi": False,
        "modeles": ["aucun"],
        "duree_s": 9.5,
        "seuils": [{"nom": "étapes max", "mesure": 6, "seuil": "≤ 12", "ok": True}],
        "verdicts": {"EX-01": [], "EX-02": ["KAL-26-0001 : section issue écrite par pieces"]},
        "couverture": {"empruntees": ["T1"], "manquantes": ["T2"],
                       "hors_scenarios": {"T0": "ING-01 / ING-02 (make eval-ingestion)"}},
        "scenarios": [{"id": "NOM-01", "ok": True, "ecarts": []}],
        "metriques": {"decision": {"appels": 1}},
        "equipe": {"demandes": 1},
        "bornes": [{"borne": "etapes_max", "valeur": 12, "observe": 6}],
    }
    chemin = epreuve.ecrire_rapport(rapport, tmp_path / "rapports")
    texte = chemin.read_text("utf-8")
    assert chemin.name == "epreuve-2026-10-09.md"
    assert "en échec" in texte and "T2" in texte and "ING-01" in texte and "EX-02" in texte
    assert json.loads(chemin.with_suffix(".json").read_text("utf-8"))["reussi"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_epreuve.py -q`
Expected: FAIL — `ImportError` / `ModuleNotFoundError: No module named 'tools.epreuve'`.

- [ ] **Step 3: Write minimal implementation**

Créer `tools/epreuve.py` :

```python
"""Épreuve de l'équipe (dossier 4.1, 4.2 ; C2b) : rejoue les 28 scénarios contre le partenaire
simulé, rend un verdict par exigence, la couverture des transitions et les seuils.

Usage : uv run python -m tools.epreuve (ou make epreuve)
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from kaldera.etat import PROPRIETAIRES, Bornes
from kaldera.machine import TRANSITIONS

RAPPORTS = Path(__file__).resolve().parents[1] / "eval/rapports"
CHAMPS_CONTRAT = frozenset(
    {
        "reference_dossier",
        "type_sinistre",
        "montant_declare",
        "date_survenance",
        "anciennete_contrat_jours",
        "sinistres_12_mois",
        "departement",
    }
)
HORS_SCENARIOS = {"T0": "ING-01 / ING-02 (make eval-ingestion)"}  # garde d'entrée : niveau 1


def valeurs_personnelles(demande: dict[str, Any]) -> list[str]:
    """Données qui ne doivent jamais partir chez le partenaire (contrat §2)."""
    assure = demande.get("assure", {})
    champs = ("id_client", "nom", "prenom", "email", "telephone", "iban", "adresse", "code_postal")
    valeurs = [assure.get(c) for c in champs]
    valeurs += [demande.get("contrat", {}).get("numero"), demande.get("sinistre", {}).get("description")]
    return [v for v in valeurs if isinstance(v, str) and v]


def _par_reference(rejeu: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f.get("reference"): f for f in rejeu["fiches"]}


def _ecarts_attendu(fiche: dict[str, Any], attendu: dict[str, Any]) -> list[str]:
    ref, ecarts = attendu["reference"], []
    for champ in ("issue", "decision", "file"):
        if champ in attendu and fiche.get(champ) != attendu[champ]:
            ecarts.append(f"{ref} : {champ} = {fiche.get(champ)!r}, attendu {attendu[champ]!r}")
    if "montant_rembourse" in attendu:
        obtenu, prevu = fiche.get("montant_rembourse"), attendu["montant_rembourse"]
        if (prevu is None) != (obtenu is None) or (
            prevu is not None and obtenu is not None and abs(obtenu - prevu) >= 0.01
        ):
            ecarts.append(f"{ref} : montant {obtenu!r}, attendu {prevu!r}")
    if "mode_degrade" in attendu and bool(fiche.get("mode_degrade")) is not attendu["mode_degrade"]:
        ecarts.append(f"{ref} : mode_degrade = {fiche.get('mode_degrade')!r}")
    if "avis_fraude" in attendu:
        avis = fiche.get("avis_fraude")
        niveau = avis.get("niveau") if isinstance(avis, dict) else None
        if niveau != attendu["avis_fraude"]:
            ecarts.append(f"{ref} : avis {niveau!r}, attendu {attendu['avis_fraude']!r}")
    if attendu.get("arret") and not fiche.get("arret"):
        ecarts.append(f"{ref} : arrêt non signalé")
    return ecarts


def verdicts(rejeux: list[dict[str, Any]], bornes: Bornes) -> dict[str, list[str]]:
    """Écarts par exigence (dossier 4.1, C2-Q14) ; une liste vide vaut ✅."""
    v: dict[str, list[str]] = {k: [] for k in ("EX-01", "EX-02", "EX-03", "EX-04", "EX-05", "EX-06")}
    v["attendu"] = []
    for rejeu in rejeux:
        scenario, fiches = rejeu["scenario"], _par_reference(rejeu)
        categorie, demandes = scenario["categorie"], {d["reference"]: d for d in scenario["demandes"]}
        for ref, fiche in fiches.items():
            motif = fiche.get("motif")
            if fiche.get("issue") not in ("decision", "escalade") or not (
                isinstance(motif, str) and motif.strip()
            ):
                v["EX-01"].append(f"{ref} : issue non motivée")
            for etape in fiche.get("trace", []):
                for section in etape.get("ecrit", []):
                    if PROPRIETAIRES.get(section) != etape["agent"]:
                        v["EX-02"].append(f"{ref} : section {section} écrite par {etape['agent']}")
                if etape.get("erreur") == "ErreurEcriture":
                    v["EX-02"].append(f"{ref} : écriture rejetée ({etape['agent']})")
            if categorie == "invalide" and fiche.get("avis_fraude") is not None:
                v["EX-04"].append(f"{ref} : réponse non conforme propagée dans la fiche")
            if categorie == "boucle":
                arret = fiche.get("arret") or {}
                if arret.get("borne") != "relances_pieces_max":
                    v["EX-06"].append(f"{ref} : arrêt {arret.get('borne')!r}")
                if len(fiche.get("trace", [])) > bornes.etapes_max:
                    v["EX-06"].append(f"{ref} : {len(fiche['trace'])} étapes > {bornes.etapes_max}")
        for entree in rejeu["journal"]:
            ref = entree.get("reference")
            # 401 / 503 : le simulateur répond avant de lire le corps (champs vides) — seul le
            # corps brut est alors contrôlé
            lu = entree.get("statut_http") not in (401, 503)
            if lu and set(entree.get("champs", [])) != CHAMPS_CONTRAT:
                v["EX-03"].append(f"{ref} : champs envoyés ≠ les 7 du contrat")
            demande = demandes.get(ref, {})
            if any(val in entree.get("corps_brut", "") for val in valeurs_personnelles(demande)):
                v["EX-03"].append(f"{ref} : donnée personnelle dans la requête")  # jamais la valeur
        for attendu in scenario["attendu"]:
            fiche = fiches.get(attendu["reference"])
            if fiche is None:
                v["attendu"].append(f"{attendu['reference']} : aucune fiche produite")
                continue
            ecarts = _ecarts_attendu(fiche, attendu)
            v["attendu"] += ecarts
            if categorie == "panne":
                v["EX-05"] += [e for e in ecarts if "mode_degrade" in e or "file" in e]
    return v


def couverture(rejeux: list[dict[str, Any]]) -> dict[str, Any]:
    """Transitions T1 … T11 empruntées par les scénarios (dossier 4.2) ; T0 : épreuve d'ingestion."""
    gardes = {e.get("garde") for r in rejeux for f in r["fiches"] for e in f.get("trace", [])}
    toutes = [f"T{i}" for i in range(1, len(TRANSITIONS) + 1)]
    return {
        "empruntees": [t for t in toutes if t in gardes],
        "manquantes": [t for t in toutes if t not in gardes],
        "hors_scenarios": dict(HORS_SCENARIOS),
    }


def seuils(
    rejeux: list[dict[str, Any]], equipe: dict[str, Any], bornes: Bornes
) -> list[dict[str, Any]]:
    """Seuils de l'équipe (spec C2b §4.3) : mesure, seuil lisible, verdict."""
    hors_relance = sum(n for b, n in equipe["arrets"].items() if b != "relances_pieces_max")
    appels = max(
        (n for r in rejeux for n in Counter(e.get("reference") for e in r["journal"]).values()),
        default=0,
    )
    duree_max_ms = bornes.duree_max_s * 1000
    return [
        {"nom": "durée p95 (ms)", "mesure": equipe["duree_ms"]["p95"],
         "seuil": f"< {duree_max_ms:g}", "ok": equipe["duree_ms"]["p95"] < duree_max_ms},
        {"nom": "durée max (ms)", "mesure": equipe["duree_ms"]["max"],
         "seuil": "< 10000", "ok": equipe["duree_ms"]["max"] < 10_000},
        {"nom": "écritures rejetées", "mesure": equipe["ecritures_rejetees"],
         "seuil": "= 0", "ok": equipe["ecritures_rejetees"] == 0},
        {"nom": "étapes max", "mesure": equipe["etapes"]["max"],
         "seuil": f"≤ {bornes.etapes_max}", "ok": equipe["etapes"]["max"] <= bornes.etapes_max},
        {"nom": "arrêts hors relances_pieces_max", "mesure": hors_relance,
         "seuil": "= 0", "ok": hors_relance == 0},
        {"nom": "appels partenaire par référence", "mesure": appels,
         "seuil": "≤ 1", "ok": appels <= 1},
    ]


def bornes_observees(
    rejeux: list[dict[str, Any]], equipe: dict[str, Any], bornes: Bornes
) -> list[dict[str, Any]]:
    """Bornes provisoires en vigueur ↔ valeurs observées pendant l'épreuve."""
    antifraude_ms = max(
        (e["duree_ms"] for r in rejeux for f in r["fiches"] for e in f.get("trace", [])
         if e.get("agent") == "antifraude"),
        default=0.0,
    )
    return [
        {"borne": "etapes_max", "valeur": bornes.etapes_max, "observe": equipe["etapes"]["max"]},
        {"borne": "duree_max_s", "valeur": bornes.duree_max_s,
         "observe": round(equipe["duree_ms"]["max"] / 1000, 2)},
        {"borne": "relances_pieces_max", "valeur": bornes.relances_pieces_max,
         "observe": equipe["arrets"].get("relances_pieces_max", 0)},
        {"borne": "delai_partenaire_s", "valeur": bornes.delai_partenaire_s,
         "observe": round(antifraude_ms / 1000, 2)},
    ]


def _ok(valeur: bool) -> str:
    return "✅" if valeur else "❌"


def ecrire_rapport(rapport: dict[str, Any], dossier: Path = RAPPORTS) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"epreuve-{rapport['date']}.md"
    chemin.with_suffix(".json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2, default=str), "utf-8"
    )
    couv = rapport["couverture"]
    lignes = [
        f"# Épreuve de l'équipe — {rapport['date']}",
        "",
        f"**Résultat : {'réussie' if rapport['reussi'] else 'en échec'}** · modèles : "
        + (", ".join(rapport["modeles"]) or "aucun")
        + f" · durée : {rapport['duree_s']} s",
        "",
        "## Seuils",
        "",
        "| Mesure | Résultat | Seuil | |",
        "|---|---|---|---|",
        *(f"| {s['nom']} | {s['mesure']} | {s['seuil']} | {_ok(s['ok'])} |" for s in rapport["seuils"]),
        "",
        "## Exigences",
        "",
        "| Exigence | Verdict | Écarts |",
        "|---|---|---|",
        *(
            f"| {k} | {_ok(not e)} | {'<br>'.join(e) or '—'} |"
            for k, e in rapport["verdicts"].items()
        ),
        "",
        "## Couverture des transitions",
        "",
        f"Empruntées : {', '.join(couv['empruntees']) or '—'}  ",
        f"Non empruntées : {', '.join(couv['manquantes']) or 'aucune'}  ",
        *(f"{t} : couverte par {ou}  " for t, ou in couv["hors_scenarios"].items()),
        "",
        "## Scénarios",
        "",
        "| Scénario | Verdict | Écarts |",
        "|---|---|---|",
        *(
            f"| {s['id']} | {_ok(s['ok'])} | {'<br>'.join(s['ecarts']) or '—'} |"
            for s in rapport["scenarios"]
        ),
        "",
        "## Bornes",
        "",
        "| Borne | En vigueur | Observé |",
        "|---|---|---|",
        *(f"| {b['borne']} | {b['valeur']} | {b['observe']} |" for b in rapport["bornes"]),
        "",
        "## Métriques",
        "",
        "```json",
        json.dumps({"agents": rapport["metriques"], "equipe": rapport["equipe"]},
                   ensure_ascii=False, indent=2),
        "```",
    ]
    chemin.write_text("\n".join(lignes) + "\n", "utf-8")
    return chemin
```

Couper toute ligne > 100 caractères (`uv run ruff format tools/epreuve.py tests/unit/test_epreuve.py` est permis sur ces deux nouveaux fichiers).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_epreuve.py -q && uv run ruff check src tests tools && uv run mypy src`
Expected: PASS. Si un verdict de `test_verdicts_tout_conforme` échoue parce qu'un `attendu` des scénarios porte une clé non gérée par `_fiche_conforme`, adapter `_fiche_conforme` (le test), jamais la règle.

- [ ] **Step 5: Commit**

```bash
git add tools/epreuve.py tests/unit/test_epreuve.py
git commit -m "feat(epreuve): verdicts EX-01 → EX-06, couverture, seuils et rapport"
```

---

### Task 5: Épreuve — simulateur en processus, rejeu, `make epreuve`, fumée

**Files:**
- Modify: `tools/epreuve.py` (ajouts : `partenaire_simule`, `rejouer`, `evaluer`, `main`)
- Modify: `Makefile` (`.PHONY` et cible `epreuve`, à côté de `eval-ingestion`)
- Test: `tests/unit/test_epreuve.py`

**Interfaces:**
- Consumes: Task 4 (`verdicts`, `couverture`, `seuils`, `bornes_observees`, `ecrire_rapport`, `RAPPORTS`) ; `kaldera.metriques_par_agent`, `kaldera.metriques_equipe` (Task 3) ; `kaldera.etat.BORNES` ; `Orchestrateur(partenaire_url, snapshots=…, registre=…)` ; `memoire.SnapshotsEnMemoire`, `memoire.RegistreA2AEnMemoire` ; `external_agent.app.app` (routes `/_sim/reset`, `/_sim/mode`, `/_sim/journal`).
- Produces:
  - `partenaire_simule() -> contextlib.AbstractContextManager[str]` (rend l'URL de base)
  - `orchestrateur(url: str) -> Orchestrateur` — registre et snapshots **en mémoire**
  - `rejouer(url: str, scenario: dict[str, Any]) -> dict[str, Any]` (un rejeu)
  - `evaluer(scenarios: list[dict[str, Any]] | None = None) -> dict[str, Any]` (le rapport ; `None` ⇒ `eval/scenarios.jsonl`)
  - `main() -> None`

- [ ] **Step 1: Write the failing tests**

Ajouter à `tests/unit/test_epreuve.py` (imports à ajouter : `import httpx`, `from kaldera.memoire import SnapshotsEnMemoire`) :

```python
def test_epreuve_rejouable_deux_fois_meme_avec_une_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review Focus 1 : `make` exporte le .env ; sans registre en mémoire, le 2ᵉ passage (ou une
    base injoignable) donnerait « registre … » au lieu de l'avis du partenaire."""
    monkeypatch.setenv("KALDERA_DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    monkeypatch.setattr(postgres, "registre_par_defaut", REGISTRE_PAR_DEFAUT)  # le vrai
    monkeypatch.setattr(postgres, "snapshots_par_defaut", SNAPSHOTS_PAR_DEFAUT)
    scenario = copy.deepcopy(SCENARIOS["AF-01"])
    with epreuve.partenaire_simule() as url:
        for _ in range(2):
            rejeu = epreuve.rejouer(url, scenario)
            assert all(f["avis_fraude"] is not None for f in rejeu["fiches"]), rejeu["fiches"]
    assert isinstance(epreuve.orchestrateur(url).snapshots, SnapshotsEnMemoire)


def test_simulateur_arrete_meme_si_le_rejeu_leve() -> None:
    """Review Focus 2."""
    with pytest.raises(RuntimeError), epreuve.partenaire_simule() as url:
        assert httpx.get(f"{url}/_sim/etat", timeout=2).status_code == 200
        raise RuntimeError("rejeu interrompu")
    with pytest.raises(httpx.HTTPError):
        httpx.get(f"{url}/_sim/etat", timeout=1)


def test_epreuve_complete_reussie(tmp_path: Path) -> None:
    """Fumée : les 28 scénarios rejoués contre le simulateur en processus (≈ 10 s)."""
    rapport = epreuve.evaluer()
    echecs = {k: e for k, e in rapport["verdicts"].items() if e}
    assert rapport["reussi"], (echecs, [s for s in rapport["seuils"] if not s["ok"]])
    assert len(rapport["scenarios"]) == 28
    assert rapport["couverture"]["manquantes"] == []
    assert epreuve.ecrire_rapport(rapport, tmp_path).exists()
```

Imports à ajouter **en tête** de `tests/unit/test_epreuve.py`, avant tout patch autouse du conftest (même motif que `tests/unit/test_base_par_defaut.py`) : `from kaldera import postgres` et `from kaldera.postgres import registre_par_defaut as REGISTRE_PAR_DEFAUT, snapshots_par_defaut as SNAPSHOTS_PAR_DEFAUT` (couper la ligne). Le premier test rejoue AF-01 deux fois avec le vrai `registre_par_defaut` et une base configurée mais injoignable : l'avis du partenaire doit arriver les deux fois, ce qui n'est vrai que si `orchestrateur()` passe un registre et des snapshots en mémoire.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_epreuve.py -q -k "postgres or simulateur or complete"`
Expected: FAIL — `AttributeError: module 'tools.epreuve' has no attribute 'orchestrateur'`.

- [ ] **Step 3: Write minimal implementation**

Ajouter aux imports de `tools/epreuve.py` :

```python
import os
import socket
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date

import httpx
import uvicorn

import kaldera
from kaldera import partenaire
from kaldera.etat import BORNES
from kaldera.memoire import RegistreA2AEnMemoire, SnapshotsEnMemoire
from kaldera.orchestrateur import Orchestrateur
```

puis, après `HORS_SCENARIOS` :

```python
SCENARIOS = Path(__file__).resolve().parents[1] / "eval/scenarios.jsonl"
JETON_RECETTE = "jeton-recette"
```

et, après `ecrire_rapport` :

```python
@contextmanager
def partenaire_simule() -> Iterator[str]:
    """Partenaire simulé (``external_agent``) dans le processus, sur un port libre."""
    os.environ.setdefault("PARTENAIRE_JETON", JETON_RECETTE)  # même jeton côté client et simulateur
    from external_agent.app import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", ws="none")
    serveur = uvicorn.Server(config)
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    limite = time.monotonic() + 10
    while not serveur.started:
        if time.monotonic() > limite or not fil.is_alive():
            serveur.should_exit = True
            raise RuntimeError("le partenaire simulé n'a pas démarré")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        serveur.should_exit = True
        fil.join(5)


def orchestrateur(url: str) -> Orchestrateur:
    """Snapshots et registre en mémoire : une épreuve ne dépend d'aucune base et se rejoue."""
    return Orchestrateur(url, snapshots=SnapshotsEnMemoire(), registre=RegistreA2AEnMemoire())


def rejouer(url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(base_url=url, timeout=5) as sim:
        sim.post("/_sim/reset").raise_for_status()
        sim.post("/_sim/mode", json=scenario["partenaire"]).raise_for_status()
        orch = orchestrateur(url)
        # en parallèle, comme traiter_lot (§12)
        with ThreadPoolExecutor() as pool:
            fiches = list(pool.map(orch.traiter, scenario["demandes"]))
        journal = sim.get("/_sim/journal").json()
    return {"scenario": scenario, "fiches": fiches, "journal": journal}


def evaluer(scenarios: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if scenarios is None:
        lignes = SCENARIOS.read_text("utf-8").splitlines()
        scenarios = [json.loads(ligne) for ligne in lignes if ligne.strip()]
    debut = time.monotonic()
    with partenaire_simule() as url:
        rejeux = [rejouer(url, s) for s in scenarios]
    fiches = [f for r in rejeux for f in r["fiches"]]
    equipe = kaldera.metriques_equipe(fiches)
    v = verdicts(rejeux, BORNES)
    couv = couverture(rejeux)
    s = seuils(rejeux, equipe, BORNES)
    par_scenario = []
    for r in rejeux:
        ecarts = verdicts([r], BORNES)
        tous = [e for liste in ecarts.values() for e in liste]
        par_scenario.append({"id": r["scenario"]["id"], "ok": not tous, "ecarts": tous})
    modeles = sorted({e.get("modele") or "aucun" for f in fiches for e in f["trace"] if "mode" in e})
    return {
        "date": date.today().isoformat(),
        "reussi": all(not e for e in v.values()) and not couv["manquantes"] and all(x["ok"] for x in s),
        "modeles": modeles,
        "duree_s": round(time.monotonic() - debut, 1),
        "seuils": s,
        "verdicts": v,
        "couverture": couv,
        "scenarios": par_scenario,
        "metriques": kaldera.metriques_par_agent(fiches),
        "equipe": equipe,
        "bornes": bornes_observees(rejeux, equipe, BORNES),
    }


def main() -> None:
    rapport = evaluer()
    chemin = ecrire_rapport(rapport)
    print(chemin.read_text("utf-8"))
    if not rapport["reussi"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

Couper les lignes > 100 caractères (`ruff format` permis sur `tools/epreuve.py`).

`Makefile` : ajouter `epreuve` à `.PHONY` et, après la cible `eval-ingestion` :

```makefile
epreuve:
	uv run python -m tools.epreuve
```

(une tabulation avant `uv`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_epreuve.py -q && uv run pytest -q && uv run ruff check src tests tools && uv run mypy src`
Expected: PASS. Si `test_epreuve_complete_reussie` échoue, **ne pas modifier les règles de `verdicts` / `seuils` pour le faire passer** : écrire dans le rapport de tâche le scénario, le verdict ou le seuil en échec et la mesure, puis rendre le statut `DONE_WITH_CONCERNS` (c'est la boucle d'épreuve de la Task 6 qui décide de l'ajustement).

Puis vérifier la commande réelle : `make epreuve` (ou `uv run python -m tools.epreuve`) affiche le rapport et sort en 0 ; supprimer le rapport généré dans `eval/rapports/` avant de commiter (le rapport final est commité en Task 6).

- [ ] **Step 5: Commit**

```bash
git add tools/epreuve.py tests/unit/test_epreuve.py Makefile
git commit -m "feat(epreuve): make epreuve — simulateur en processus, rejeu des 28 scénarios"
```

---

### Task 6: Boucle d'épreuve, journal, README, rapport final

**Files:**
- Modify: `docs/journal_ajustements.md` (tableau principal ; « Bornes provisoires en vigueur » ; « Restant (chantier 2) »)
- Modify: `README.md` (commande `make epreuve`)
- Create: `eval/rapports/epreuve-<AAAA-MM-JJ>.md` et `.json` (générés, commités)

**Interfaces:**
- Consumes: `make epreuve` (Task 5).
- Produces: rien pour le code.

- [ ] **Step 1: Run the épreuve**

Run: `uv run python -m tools.epreuve; echo "sortie: $?"`
Relever : résultat, seuils (mesures), bornes observées, natures `antifraude`, `equipe`.

- [ ] **Step 2: Adjustment loop**

Si un seuil ou un verdict est ❌ : **STOP**, statut `BLOCKED` avec le rapport (chemin, lignes en échec, mesures). Le contrôleur décide de l'ajustement (borne, garde, frontière ou routage) ; il ne doit jamais être choisi ici « au doigt mouillé ».
Si tout est ✅ : continuer.

- [ ] **Step 3: Update the journal**

Dans `docs/journal_ajustements.md` :
1. ajouter au tableau principal (après la dernière ligne, format existant, 6 colonnes) :

```markdown
| 2026-10-09 | C2b · épreuve (`make epreuve`, 28 scénarios) | appels comptés même non partis ; aucune vue d'équipe ni de couverture | C2-Q15, dossier 4.2 | nature de chaque appel, `appels_externes` = appels partis, métriques `equipe`, rapport d'épreuve | <D> ; couverture T1 → T11 <C> (T0 : ING-01 / ING-02) ; EX-01 → EX-06 ✅ |
```

où `<D>` = « durée p95 <p95> ms, max <max> ms, étapes max <n> » et `<C>` = « 11/11 », lus dans le rapport.
2. dans « Bornes provisoires en vigueur », colonne Statut : `etapes_max` → « éprouvée (max observé : <n> étapes) » ; `duree_max_s` → « éprouvée (max observé : <x> s, p95 <y> s) » ; `delai_partenaire_s` → « éprouvée (antifraude max observé : <z> s, PAN-02) » ; `relances_pieces_max` inchangée (« à valider avec le métier »). Chaque valeur vient du rapport.
3. remplacer le contenu de « Restant (chantier 2) » par :

```markdown
C2a (liaison A2A) et C2b (monitorage et épreuve, `make epreuve`) livrés. Reste :

| Lot | Contenu |
|---|---|
| C2c · LLM réel | `make eval` (matrice agent × modèle), disjoncteur LLM, seuils propres au LLM (replis, latence LLM, tours) |
```

- [ ] **Step 4: Update the README**

Dans `README.md`, à l'endroit où `make eval-ingestion` est documenté (le chercher), ajouter une ligne équivalente :
`make epreuve` — rejoue les 28 scénarios contre le partenaire simulé (en processus) et écrit `eval/rapports/epreuve-<date>.md` : verdict par exigence EX-01 → EX-06, couverture des transitions, seuils, métriques par agent et d'équipe ; code de sortie 1 en cas d'échec.
Mettre à jour « Known issues » si elle mentionne encore les métriques détaillées de l'agent `antifraude` ou la remesure des bornes comme C2b à faire.

- [ ] **Step 5: Final verification and commit**

Run: `uv run pytest -q && uv run pytest tests/acceptance -q && uv run ruff check src tests tools && uv run mypy src && git status --short`
Expected: tout vert ; seuls le journal, le README et le rapport du jour (`eval/rapports/epreuve-*.md|.json`) sont nouveaux ou modifiés.

```bash
git add docs/journal_ajustements.md README.md eval/rapports/
git commit -m "docs(epreuve): C2b consigné — bornes éprouvées, rapport d'épreuve"
```
