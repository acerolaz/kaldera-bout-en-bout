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
