# Back-office gestionnaire — règles de page

> **PROJECT:** Kaldera · **Page :** back-office gestionnaire (E1, E2, E3) · spec `docs/superpowers/specs/2026-10-12-c3-1-design-system-design.md`
> Les règles de ce fichier **priment** sur `design-system/kaldera/MASTER.md`. Pour le reste, suivre le Master.

## Mise en page
- En-tête pleine largeur, hauteur 48 px : marque « Kaldera · back-office gestionnaire », lien « Demandes », bouton de thème à droite.
  Clair : fond `--primary`, texte blanc, accent et **anneau de focus** `--or-sur-primaire`. Sombre : fond `--card`, bordure `--border`, anneau `--ring`.
- Lien d'évitement « Aller au contenu », premier élément focalisable, visible au focus.
- Contenu : `<main id="contenu">`, largeur max 1440 px, marges 16 px ; un seul `<h1>` par page.

## Densité
- Tableaux : lignes de 40 px, en-têtes collants, `tabular-nums` pour montants, durées, pourcentages ; références et n° de police en IBM Plex Mono.
- Pas d'ombre portée sur les cartes de données ; séparation par bordure `--border`.

## États
- Vide : phrase qui dit ce qui manque et ce qui le fera apparaître ; annoncé par `role="status"`.
- Chargement : squelettes de même hauteur que le contenu attendu ; `aria-busy="true"` sur la zone, annoncé par `role="status"`.
- Erreur : message + action de récupération (« Réessayer ») ; `role="alert"`.

## Statuts
- Toujours `<Statut code />` (icône + libellé + couleur) ; jamais une couleur seule, jamais une classe de couleur dans un écran.

## Anti-patterns
- ❌ Statut par la couleur seule · ❌ Emoji comme icône · ❌ Or pour du texte courant · ❌ Anneau de focus or foncé sur l'en-tête vert
