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
