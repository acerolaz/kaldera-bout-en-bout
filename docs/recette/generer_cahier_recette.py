"""Génère le cahier de recette (démo) : uv run python docs/recette/generer_cahier_recette.py"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SORTIE = Path(__file__).with_name("cahier-recette.pdf")
BLEU = colors.HexColor("#1e3a5f")
GRIS = colors.HexColor("#eef2f6")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=BLEU, spaceBefore=6, spaceAfter=8)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=BLEU, spaceBefore=10, spaceAfter=4)
TXT = ParagraphStyle("txt", parent=ss["BodyText"], fontSize=9.5, leading=13)
CEL = ParagraphStyle("cel", parent=TXT, fontSize=8.5, leading=11)
ENT = ParagraphStyle("ent", parent=CEL, textColor=colors.white, fontName="Helvetica-Bold")
CODE = ParagraphStyle("code", parent=CEL, fontName="Courier", fontSize=8.5, leading=11,
                      backColor=GRIS, borderPadding=5, spaceBefore=4, spaceAfter=8)


def p(texte, style=CEL):
    return Paragraph(texte, style)


def m(commande):
    return f"<font face='Courier'><b>{commande}</b></font>"


def tableau(entetes, lignes, largeurs):
    donnees = [[p(e, ENT) for e in entetes]] + [[p(c) for c in ligne] for ligne in lignes]
    t = Table(donnees, colWidths=[largeur * cm for largeur in largeurs], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLEU),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa8b8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def groupes(liste):
    """Une fiche par groupe : ID, action, résultat attendu, OK/KO, remarques."""
    return [KeepTogether([Paragraph(nom, H2), tableau(
        ["ID", "Action", "Résultat attendu", "OK / KO", "Remarques"],
        [[i, a, r, STATUTS.get(i, ""), REMARQUES.get(i, "")] for i, a, r in lignes], [1.3, 6.2, 6.6, 1.4, 2.5])])
        for nom, lignes in liste]


# Statut relevé au dernier déroulé ; mis à jour à chaque recette.
STATUTS: dict[str, str] = {
    "S-01": "OK", "S-02": "OK", "S-03": "NT", "S-04": "OK", "S-05": "OK", "S-06": "OK",
    "U-01": "OK", "U-02": "OK", "U-03": "OK", "U-04": "OK", "U-05": "OK", "U-06": "OK",
    "U-07": "OK", "U-08": "OK", "U-09": "OK", "U-10": "OK", "U-11": "OK", "U-12": "OK",
    "U-13": "OK", "U-14": "OK", "U-15": "OK", "A-01": "OK", "A-02": "OK", "A-03": "OK",
    "A-04": "NT",
}

# Remarque relevée au dernier déroulé ; mise à jour à chaque recette.
REMARQUES: dict[str, str] = {
    "S-01": (
        "Adapté : make recette non lancé (docker) ; tables vidées, make demo, make "
        "partenaire."
    ),
    "S-03": "Pas de profil VLM Azure sur ce poste : le worker refuse de démarrer.",
    "S-05": "Jeton PARTENAIRE_JETON passé à make api en ligne de commande (pas de .env).",
    "U-02": "Sans flash : vérifié par l'e2e fumee.spec.ts, pas à l'œil.",
    "U-05": "Infobulle = attribut title ; motif lu par aria-describedby.",
    "U-06": (
        "Adapté : 0103 refusé d'emblée (non éligible), 100 % en 0,1 s ; cartes non "
        "observables."
    ),
    "U-07": (
        "Rejoué après correctif : 30 dossiers, lot 3,5 s, dossier max 3,35 s ; 12 sans anti-fraude "
        "finis à 0,5 s, 18 à 3,5 s ; tous démarrés en 5 ms (un fil par dossier)."
    ),
    "U-08": (
        "Rejoué après correctif : SIGINT, API arrêtée en 0,2 s ; « Reconnexion… » à +3 s ; "
        "levé 2 s après le redémarrage, état relu."
    ),
    "U-14": "Adapté : partenaire lent (délai > 3 s), pas en panne ; dossier KAL-26-0404.",
    "A-01": "18 appels, 18 dossiers distincts, aucun doublon.",
    "A-04": "make recette-reset non lancé : PostgreSQL du checkout principal conservé.",
}

# Python 3.11 : pas de guillemets imbriqués dans une expression de f-string.
PARTENAIRE_LENT = m('make ctl ARGS="lent --delai 5"')

SETUP = [
    ("Démarrage (un terminal par commande longue)", [
        ("S-01", f"{m('make recette')}",
         "Base remise à zéro, partenaire anti-fraude (port 8100) et PostgreSQL (port 5433) "
         "démarrés et sains, puis : « Demande KAL-26-0101 prête »."),
        ("S-02", f"Terminal 1 : {m('make api')}",
         "Uvicorn écoute sur http://127.0.0.1:8000 ; http://localhost:8000/docs liste les "
         "routes <i>/demandes</i> et aucune route <i>/assure</i>."),
        ("S-03", f"Terminal 2 : {m('make worker')}",
         "Le worker démarre sans erreur et attend des pièces à analyser ; une demande soumise "
         "et analysée passe en « Prête » (elle n'est plus traitée par le worker)."),
        ("S-04", f"Terminal 3 : {m('make front')}",
         "Vite sert le back-office gestionnaire sur http://localhost:5173."),
        ("S-05", f"{m('make ctl ARGS=etat')}",
         "Partenaire en mode <i>normal</i>, aucun appel reçu."),
        ("S-06", f"{m('make scenarios ARGS=--charger')}",
         "« 33 demandes prêtes ; déjà en base, ignorées : KAL-26-0101 » (créée par make demo)."),
    ]),
]

UI = [
    ("Socle du back-office", [
        ("U-01", "Ouvrir <b>http://localhost:5173</b>.",
         "En-tête « Kaldera · back-office gestionnaire », lien « Demandes » souligné (page "
         "courante), bouton de thème ; titre « Liste des demandes » (contenu vérifié en U-10)."),
        ("U-02", "Cliquer le bouton de thème (lune), recharger la page, puis recliquer (soleil).",
         "Passage en sombre ; après rechargement la page reste en sombre, sans flash clair ; "
         "second clic : retour en clair. Navigateur sans choix enregistré (fenêtre privée) : "
         "la page suit le thème du système."),
        ("U-03", "Recharger, puis appuyer sur Tab trois fois.",
         "1er Tab : « Aller au contenu » apparaît en haut à gauche ; 2e : « Demandes » ; 3e : "
         "bouton de thème. Anneau de focus or visible à chaque fois, dans les deux thèmes."),
        ("U-04", "Ouvrir <i>/demandes/KAL-26-0101</i>, <i>/lots/1</i>, puis <i>/inconnu</i>.",
         "Titres « Dossier KAL-26-0101 » et « Lot 1 » ; aucun lot encore lancé : « Lot "
         "introuvable. » et lien de retour ; adresse inconnue : « Page introuvable » et lien "
         "« Retour à la liste des demandes »."),
    ]),
    ("Traitement depuis l'IHM (E1 → E2 / E3)", [
        ("U-05", "Ouvrir <b>http://localhost:5173</b>, filtrer Statut = Prête ; survoler puis "
         "atteindre au clavier la case de KAL-26-0101 (filtre Tous).",
         "33 dossiers « Prête » cochables ; KAL-26-0101 « En analyse » : case grisée, motif "
         "« Pièces en cours d'analyse » en infobulle et lu au clavier ; « Traiter la "
         "sélection (0) » inactif."),
        ("U-06", "Cocher KAL-26-0103, cliquer « Traiter la sélection (1) ».",
         "E2 « Dossier KAL-26-0103 » : l'étape en cours s'affiche « En traitement » avec son %, "
         "les cartes passent une à une ; état terminal en ≤ 8 s, avancement 100 %, « Traitement "
         "terminé » ; de retour sur E1, la case est grisée (« Déjà traité »)."),
        ("U-07", f"{PARTENAIRE_LENT} ; sur E1 (Statut = Prête), « Tout sélectionner », décocher "
         "KAL-26-0110 et KAL-26-0111 (gardés pour U-08 et U-09), puis « Traiter la sélection "
         f"(30) » ; après la fin, {m('make ctl ARGS=normal')}.",
         "E3 « Lot … » : une ligne par dossier, barres indépendantes (les dossiers sans "
         "anti-fraude finissent tout de suite, ceux qui attendent le partenaire lent ensuite) ; "
         "aucun dossier au-delà de 8 s ; compteurs (acceptées, refusées, escaladées par file, "
         "modes dégradés) et durée écoulée ; avancement 100 % à la fin ; clic sur une ligne ⇒ E2."),
        ("U-08", "Ouvrir <i>/demandes/KAL-26-0110</i> (encore « Prête ») ; arrêter <i>make api</i> "
         "5 s puis le relancer.",
         "API arrêtée : mention « Reconnexion… » ; API relancée : la mention disparaît seule et "
         "l'état est relu (pas de rechargement manuel)."),
        ("U-09", "Ouvrir E1 dans deux onglets ; cocher KAL-26-0111 dans les deux ; lancer dans "
         "l'onglet 1, puis dans l'onglet 2.",
         "Onglet 2 : alerte « Impossible de lancer le traitement : dossiers non lançables : "
         "KAL-… » ; la liste est relue ; un seul traitement (A-01 : un seul appel partenaire)."),
    ]),
    ("Lecture des dossiers (E1, E2)", [
        ("U-10", "Après U-07, ouvrir <b>http://localhost:5173</b>.",
         "E1 liste les dossiers traités en U-06 et U-07 et KAL-26-0101 : référence, assuré, "
         "police, sinistre, montant, statut et issue en icône + libellé, file, badge mode "
         "dégradé ; aucun email, téléphone ni IBAN affiché."),
        ("U-11", "Filtrer Issue = Escaladée, cocher « Mode dégradé seulement », chercher un "
         "nom ; recharger ; cliquer « Effacer les filtres ».",
         "La liste se restreint à chaque filtre ; l'adresse porte les filtres et les conserve "
         "au rechargement ; un filtre sans résultat affiche « Aucune demande ne correspond aux "
         "filtres. » ; « Effacer les filtres » rend la liste complète."),
        ("U-12", "Cliquer la référence d'un dossier accepté.",
         "E2 « Dossier KAL-… » : assuré, police, formule, issue, avancement 100 %, durée / 8 s ; "
         "5 cartes (Éligibilité → Décision) avec statut, durée, mode llm / repli, transition et "
         "résumé (ex. « Estimé … = min(déclaré, justifié) − franchise … »)."),
        ("U-13", "Sur E2, Tab jusqu'au bouton « Garanties », Entrée, puis Échap.",
         "Panneau Garanties : formule, franchise, plafond, souscription, statut du contrat, "
         "cotisations, extraction et provenance ; Échap ferme et rend le focus au bouton."),
        ("U-14", "Ouvrir un dossier PAN-01 (partenaire hors service).",
         "Carte anti-fraude : requis, indicateurs F1–F4, statut Indisponible, motif du mode "
         "dégradé ; carte d'étape « Mode dégradé » ; issue Escaladée avec sa file."),
        ("U-15", "Arrêter <i>make api</i> puis recharger E1 ; relancer l'API et cliquer "
         "« Réessayer » ; ouvrir <i>/demandes/KAL-26-9999</i>.",
         "API arrêtée : message d'erreur et « Réessayer » (pas de page blanche) ; après "
         "relance, la liste revient ; référence inconnue : « Dossier introuvable. » et lien de "
         "retour."),
    ]),
]

ADMIN = [
    ("Contrôles par make", [
        ("A-01", f"{m('make ctl ARGS=journal')}",
         "Journal : un appel au plus par dossier soumis à l'anti-fraude pendant les "
         "lancements U-06, U-07 et U-09, aucun doublon (EX-D19)."),
        ("A-02", f"{m('make reaper')}, observer 20 s puis Ctrl+C.",
         "Aucune ligne « escaladée par le reaper » : aucune demande bloquée."),
        ("A-03", "Relire la sortie de <i>make scenarios ARGS=--charger</i> (S-06).",
         "Aucune fiche : les demandes sont chargées en « prete », jamais traitées par la "
         "commande ; le traitement passe par l'IHM (U-06, U-07)."),
        ("A-04", f"Ctrl+C dans les 3 terminaux, puis {m('make recette-reset')}",
         "Services arrêtés et base vidée ; la recette peut être rejouée depuis S-01."),
    ]),
]


def pied(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(1.5 * cm, 1 * cm, "Kaldera — cahier de recette (démo)")
    canvas.drawRightString(A4[0] - 1.5 * cm, 1 * cm, f"Page {doc.page}")
    canvas.restoreState()


def construire():
    histoire = [
        Spacer(1, 3 * cm),
        Paragraph("Cahier de recette", ParagraphStyle("t", parent=H1, fontSize=28, leading=34)),
        Paragraph("Kaldera — traitement des demandes de remboursement (assurance habitation)",
                  ParagraphStyle("st", parent=TXT, fontSize=13, leading=17)),
        Spacer(1, 1 * cm),
        tableau(["Rubrique", "Valeur"], [
            ["Objet", "Recette de démonstration : setup par commandes make (administrateur), "
                      "interface gestionnaire en construction, contrôles d'exploitation."],
            ["Version testée", "<i>kaldera-bout-en-bout</i>, branche "
             "<i>feature/chantier3-c3-3-traitement</i>"],
            ["Date", "12 octobre 2026"],
            ["Durée estimée", "40 minutes environ"],
            ["Testeur", ""],
        ], [4, 14]),
        Spacer(1, 1 * cm),
        Paragraph("Légende", H2),
        Paragraph("<b>OK</b> : résultat conforme · <b>KO</b> : écart (le décrire en remarque) · "
                  "<b>NT</b> : non testé. Les cas s'enchaînent dans l'ordre : "
                  "<b>S-01 à S-06</b>, puis <b>U-01 à U-15</b>, puis <b>A-01 à A-04</b>.", TXT),
        Spacer(1, 1 * cm),
        Paragraph("Validation", H2),
        tableau(["Rôle", "Nom", "Date", "Signature"],
                [["Testeur", "", "", ""], ["Responsable produit", "", "", ""]], [4.5, 5, 3, 5.5]),
        PageBreak(),

        Paragraph("1. Setup de recette (administrateur)", H1),
        Paragraph("<b>Prérequis, une seule fois</b> (Docker, uv et Node.js installés), dans "
                  "<i>kaldera-bout-en-bout</i> :", TXT),
        Paragraph(
            "make install<br/>cp .env.example .env<br/>cd front &amp;&amp; npm install", CODE
        ),
        Paragraph("Variables à renseigner dans <i>.env</i> :", TXT),
        tableau(["Variable", "Valeur pour la démo"], [
            ["KALDERA_DATABASE_URL", "postgresql://kaldera:kaldera@localhost:5433/kaldera_test"],
            ["AZURE_AI_CHAT_ENDPOINT, AZURE_AI_CHAT_KEY",
             "identifiants Azure AI Foundry (agents et VLM)"],
            ["KALDERA_INGESTION__VLM__MODELE, ..._VISION=true",
             "modèle VLM (sans eux, le worker refuse de démarrer)"],
            ["KALDERA_&lt;AGENT&gt;__MODELE",
             "facultatifs : sans eux, repli déterministe, même verdict"],
            ["PARTENAIRE_URL, PARTENAIRE_JETON", "service anti-fraude simulé (port 8100)"],
        ], [7, 11]),
        *groupes(SETUP),
        Spacer(1, 8),
        Paragraph("Données de démo créées par make recette", H2),
        tableau(["Élément", "Valeur"], [
            ["Dossier", "KAL-26-0101 — Claire Martin, dégât des eaux, formule confort, "
                        "1 850 € déclarés (scénario NOM-01)"],
        ], [4, 14]),
        PageBreak(),

        Paragraph("2. Interface gestionnaire", H1),
        Paragraph("Navigateur sur http://localhost:5173. Socle (C3-1), lecture E1 / E2 (C3-2), "
                  "traitement depuis l'IHM, temps réel et E3 (C3-3) livrés ; la reprise d'étape "
                  "et les notes s'ajoutent avec C3-4.", TXT),
        *groupes(UI),
        PageBreak(),

        Paragraph("3. Contrôles d'exploitation (administrateur)", H1),
        Paragraph("La reprise d'étape (C3-4) n'est pas encore livrée : ces contrôles se font "
                  "par make.", TXT),
        *groupes(ADMIN),
        Spacer(1, 12),
        Paragraph("4. Anomalies relevées", H1),
        tableau(["N°", "Cas", "Description de l'écart", "Gravité", "Statut"],
                [["<br/><br/>", "", "", "", ""] for _ in range(6)], [1, 1.8, 9.7, 2.5, 3]),
    ]
    SimpleDocTemplate(str(SORTIE), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                      topMargin=1.5 * cm, bottomMargin=1.8 * cm,
                      title="Cahier de recette Kaldera", author="Kaldera").build(
        histoire, onFirstPage=pied, onLaterPages=pied)
    print(SORTIE)


if __name__ == "__main__":
    construire()
