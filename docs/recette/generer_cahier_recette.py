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


# Statut relevé au dernier déroulé (vide : à dérouler) ; mis à jour à chaque recette.
STATUTS: dict[str, str] = {}

# Remarque relevée au dernier déroulé (vide : aucune) ; mise à jour à chaque recette.
REMARQUES: dict[str, str] = {}

SETUP = [
    ("Démarrage (un terminal par commande longue)", [
        ("S-01", f"{m('make recette')}",
         "Base remise à zéro, partenaire anti-fraude (port 8100) et PostgreSQL (port 5433) "
         "démarrés et sains, puis : « Demande KAL-26-0101 prête »."),
        ("S-02", f"Terminal 1 : {m('make api')}",
         "Uvicorn écoute sur http://127.0.0.1:8000 ; http://localhost:8000/docs liste les "
         "routes <i>/demandes</i> et aucune route <i>/assure</i>."),
        ("S-03", f"Terminal 2 : {m('make worker')}",
         "Le worker démarre sans erreur et attend des pièces à analyser."),
        ("S-04", f"Terminal 3 : {m('make front')}",
         "Vite sert le back-office gestionnaire sur http://localhost:5173."),
        ("S-05", f"{m('make ctl ARGS=etat')}",
         "Partenaire en mode <i>normal</i>, aucun appel reçu."),
    ]),
]

UI = [
    ("Socle du back-office", [
        ("U-01", "Ouvrir <b>http://localhost:5173</b>.",
         "En-tête « Kaldera · back-office gestionnaire », lien « Demandes » souligné (page "
         "courante), bouton de thème ; titre « Liste des demandes » (contenu vérifié en U-05)."),
        ("U-02", "Cliquer le bouton de thème (lune), recharger la page, puis recliquer (soleil).",
         "Passage en sombre ; après rechargement la page reste en sombre, sans flash clair ; "
         "second clic : retour en clair. Navigateur sans choix enregistré (fenêtre privée) : "
         "la page suit le thème du système."),
        ("U-03", "Recharger, puis appuyer sur Tab trois fois.",
         "1er Tab : « Aller au contenu » apparaît en haut à gauche ; 2e : « Demandes » ; 3e : "
         "bouton de thème. Anneau de focus or visible à chaque fois, dans les deux thèmes."),
        ("U-04", "Ouvrir <i>/demandes/KAL-26-0101</i>, <i>/lots/1</i>, puis <i>/inconnu</i>.",
         "Titres « Dossier KAL-26-0101 » (E2, vérifié en U-07) et « Lot 1 » (cadre C3-3) ; adresse inconnue : "
         "« Page introuvable » et lien « Retour à la liste des demandes »."),
    ]),
    ("Lecture des dossiers (E1, E2)", [
        ("U-05", f"Terminal 4 : {m('make scenarios')} (une seule fois), puis ouvrir "
         "<b>http://localhost:5173</b>.",
         "E1 liste les dossiers des scénarios et KAL-26-0101 : référence, assuré, police, "
         "sinistre, montant, statut et issue en icône + libellé, file, badge mode dégradé ; "
         "aucun email, téléphone ni IBAN affiché."),
        ("U-06", "Filtrer Issue = Escaladée, cocher « Mode dégradé seulement », chercher un "
         "nom ; recharger ; cliquer « Effacer les filtres ».",
         "La liste se restreint à chaque filtre ; l'adresse porte les filtres et les conserve "
         "au rechargement ; un filtre sans résultat affiche « Aucune demande ne correspond aux "
         "filtres. » ; « Effacer les filtres » rend la liste complète."),
        ("U-07", "Cliquer la référence d'un dossier accepté.",
         "E2 « Dossier KAL-… » : assuré, police, formule, issue, avancement 100 %, durée / 8 s ; "
         "5 cartes (Éligibilité → Décision) avec statut, durée, mode llm / repli, transition et "
         "résumé (ex. « Estimé … = min(déclaré, justifié) − franchise … »)."),
        ("U-08", "Sur E2, Tab jusqu'au bouton « Garanties », Entrée, puis Échap.",
         "Panneau Garanties : formule, franchise, plafond, souscription, statut du contrat, "
         "cotisations, extraction et provenance ; Échap ferme et rend le focus au bouton."),
        ("U-09", "Ouvrir un dossier PAN-01 (partenaire hors service).",
         "Carte anti-fraude : requis, indicateurs F1–F4, statut Indisponible, motif du mode "
         "dégradé ; carte d'étape « Mode dégradé » ; issue Escaladée avec sa file."),
        ("U-10", "Arrêter <i>make api</i> puis recharger E1 ; relancer l'API et cliquer "
         "« Réessayer » ; ouvrir <i>/demandes/KAL-26-9999</i>.",
         "API arrêtée : message d'erreur et « Réessayer » (pas de page blanche) ; après "
         "relance, la liste revient ; référence inconnue : « Dossier introuvable. » et lien de "
         "retour."),
    ]),
]

ADMIN = [
    ("Contrôles par make", [
        ("A-01", f"{m('make ctl ARGS=journal')}",
         "Journal : un appel au plus par dossier soumis à l'anti-fraude pendant "
         "<i>make scenarios</i> (U-05), aucun doublon (EX-D19)."),
        ("A-02", f"{m('make reaper')}, observer 20 s puis Ctrl+C.",
         "Aucune ligne « escaladée par le reaper » : aucune demande bloquée."),
        ("A-03", "Relire la sortie de <i>make scenarios</i> lancé en U-05.",
         "Une fiche JSON par scénario (« == NOM-01 — ... ») puis une synthèse : métriques par "
         "agent et bilan de l'équipe ; chaque scénario finit par une décision ou une escalade. "
         "Ne pas relancer : chaque dossier déjà soumis au partenaire passerait en mode dégradé."),
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
            ["Version testée", "<i>kaldera-bout-en-bout</i>, branche <i>feature/chantier3-c3-2-lecture</i>"],
            ["Date", "12 octobre 2026"],
            ["Durée estimée", "30 minutes environ"],
            ["Testeur", ""],
        ], [4, 14]),
        Spacer(1, 1 * cm),
        Paragraph("Légende", H2),
        Paragraph("<b>OK</b> : résultat conforme · <b>KO</b> : écart (le décrire en remarque) · "
                  "<b>NT</b> : non testé. Les cas s'enchaînent dans l'ordre : "
                  "<b>S-01 à S-05</b>, puis <b>U-01 à U-10</b>, puis <b>A-01 à A-04</b>.", TXT),
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
        Paragraph("Navigateur sur http://localhost:5173. Le socle (C3-1) et la lecture des dossiers E1 / E2 "
                  "(C3-2) sont livrés ; le traitement depuis l'IHM, E3, le temps réel et la reprise "
                  "d'étape s'ajoutent avec C3-3 et C3-4.", TXT),
        *groupes(UI),
        PageBreak(),

        Paragraph("3. Contrôles d'exploitation (administrateur)", H1),
        Paragraph("Le traitement depuis l'IHM (C3-3) et la reprise d'étape (C3-4) ne sont pas encore "
                  "livrés : les contrôles se font par make.", TXT),
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
