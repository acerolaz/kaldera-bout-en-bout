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
        [[i, a, r, "", ""] for i, a, r in lignes], [1.3, 6.2, 6.6, 1.4, 2.5])])
        for nom, lignes in liste]


F = "fixtures/pieces/"

SETUP = [
    ("Démarrage (un terminal par commande longue)", [
        ("S-01", f"{m('make recette')}",
         "Base remise à zéro, partenaire anti-fraude (port 8100) et PostgreSQL (port 5433) "
         "démarrés et sains, puis : « Demande KAL-26-0101 prête ; connexion : claire / ... »."),
        ("S-02", f"Terminal 1 : {m('make api')}",
         "Uvicorn écoute sur http://127.0.0.1:8000 ; http://localhost:8000/docs liste les "
         "routes <i>/demandes</i> et <i>/assure/*</i>."),
        ("S-03", f"Terminal 2 : {m('make worker')}",
         "Le worker démarre sans erreur et attend des pièces à analyser."),
        ("S-04", f"Terminal 3 : {m('make front')}",
         "Vite sert l'espace assuré sur http://localhost:5173."),
        ("S-05", f"{m('make ctl ARGS=etat')}",
         "Partenaire en mode <i>normal</i>, aucun appel reçu."),
    ]),
]

UI = [
    ("Connexion et accueil", [
        ("U-01", "Ouvrir <b>http://localhost:5173</b> sans être connecté.",
         "Redirection vers <i>/connexion</i> : « Connexion à votre espace sinistre »."),
        ("U-02", "Saisir <b>claire</b> / <b>mauvais-mdp</b>, cliquer « Se connecter ».",
         "Refus : « Identifiant ou mot de passe incorrect, ou compte momentanément bloqué. »"),
        ("U-03", "Saisir <b>claire</b> / <b>kaldera-demo</b>, cliquer « Se connecter ».",
         "Page « Mes sinistres » ; la ligne « Sinistre KAL-26-0101 » est affichée."),
        ("U-04", "Cliquer sur « Sinistre KAL-26-0101 ».",
         "Stepper 5 étapes, étape 1 « Demande reçue », branche « En attente de vos pièces » ; "
         "« Pièces attendues » au statut « À fournir »."),
    ]),
    ("Dépôt des pièces et assistant", [
        ("U-05", "Déposer un fichier texte (.txt) comme Facture.",
         "Refus : « Format non accepté : PDF, PNG ou JPEG uniquement. »"),
        ("U-06", f"Déposer comme <b>Facture</b> le fichier illisible <i>{F}KAL-26-0601/"
         "initiale_01_facture.pdf</i>.",
         "« Pièce reçue, analyse en cours. » ; « En analyse » puis « À refaire ». L'assistant "
         "publie de lui-même un message : la facture est à refaire."),
        ("U-07", "Ouvrir « Aide sur mes pièces », écrire : <i>Pourquoi ma facture est "
         "refusée ?</i>",
         "Réponse courte, limitée aux pièces, qui explique comment redéposer ; bouton "
         "« Déposer maintenant »."),
        ("U-08", "Écrire : <i>Combien vais-je être remboursé ?</i>",
         "Aucun montant ni promesse de décision : l'assistant renvoie vers un conseiller."),
        ("U-09", f"Déposer comme <b>Facture</b> <i>{F}KAL-26-0101/initiale_01_facture.pdf</i>.",
         "« En analyse » puis « Validée »."),
        ("U-10", "Redéposer exactement le même fichier.",
         "« Ce fichier a déjà été déposé. » ; pas de doublon dans la liste."),
        ("U-11", f"Déposer comme <b>Photos des dommages</b> <i>{F}KAL-26-0101/"
         "initiale_02_photo.png</i>.",
         "« Validée » ; plus aucune pièce « À fournir »."),
    ]),
    ("Soumission et verdict", [
        ("U-12", "Cliquer « Soumettre mon dossier ».",
         "« Dossier soumis. » ; le stepper avance seul (étapes 2, 3, 4) sans recharger."),
        ("U-13", "Attendre la fin du traitement.",
         "Étape 5 « Décision » : « Remboursement accordé », montant remboursé <b>1 700 €</b> "
         "(1 850 € déclarés, franchise déduite), pièces prises en compte."),
        ("U-14", "Rouvrir le chat, tenter de déposer une pièce.",
         "« Votre dossier est clos : l'assistant n'est plus disponible. » ; dépôt impossible."),
        ("U-15", "Chercher dans la page (Ctrl+F) : <i>fraude</i>, <i>score</i>, <i>agent</i>, "
         "<i>partenaire</i>.",
         "Aucune occurrence : rien de l'anti-fraude ni du fonctionnement interne n'est visible."),
        ("U-16", "Cliquer « Se déconnecter », puis ouvrir <i>/sinistres/KAL-26-0101</i>.",
         "Retour à la page de connexion ; le dossier n'est plus accessible."),
        ("U-17", "5 connexions ratées pour <b>claire</b>, puis une 6e avec le bon mot de passe.",
         "Toujours refusé, même message qu'U-02 : compte bloqué 5 minutes."),
    ]),
]

ADMIN = [
    ("Après le parcours", [
        ("A-01", f"{m('make ctl ARGS=journal')}",
         "Journal vide : KAL-26-0101 ne lève aucun indicateur F1–F4, le partenaire "
         "n'est pas appelé."),
        ("A-02", f"{m('make reaper')}, observer 20 s puis Ctrl+C.",
         "Aucune ligne « escaladée par le reaper » : aucune demande bloquée."),
        ("A-03", f"{m('make scenarios')}",
         "Une fiche JSON par scénario de recette (« == NOM-01 — ... ») puis une synthèse : "
         "métriques par agent et bilan de l'équipe ; chaque scénario finit par une décision "
         "ou une escalade."),
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
                      "parcours dans l'interface (utilisateur assuré), contrôles d'exploitation."],
            ["Version testée", "<i>kaldera-bout-en-bout</i>, branche principale"],
            ["Date", "9 octobre 2026"],
            ["Durée estimée", "30 minutes environ"],
            ["Testeur", ""],
        ], [4, 14]),
        Spacer(1, 1 * cm),
        Paragraph("Légende", H2),
        Paragraph("<b>OK</b> : résultat conforme · <b>KO</b> : écart (le décrire en remarque) · "
                  "<b>NT</b> : non testé. Les cas s'enchaînent dans l'ordre : "
                  "<b>S-01 à S-05</b>, puis <b>U-01 à U-17</b>, puis <b>A-01 à A-04</b>.", TXT),
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
            ["KALDERA_SESSION_SECRET", "une chaîne aléatoire non vide (sinon l'espace assuré "
                                       "répond 503)"],
            ["KALDERA_COOKIE_SECURE", "false (local en http)"],
            ["AZURE_AI_CHAT_ENDPOINT, AZURE_AI_CHAT_KEY",
             "identifiants Azure AI Foundry (agents et VLM)"],
            ["KALDERA_INGESTION__VLM__MODELE, ..._VISION=true",
             "modèle VLM (sans eux, le worker refuse de démarrer)"],
            ["KALDERA_&lt;AGENT&gt;__MODELE, KALDERA_RELANCE__MODELE",
             "facultatifs : sans eux, repli déterministe, même verdict"],
            ["PARTENAIRE_URL, PARTENAIRE_JETON", "service anti-fraude simulé (port 8100)"],
        ], [7, 11]),
        *groupes(SETUP),
        Spacer(1, 8),
        Paragraph("Données de démo créées par make recette", H2),
        tableau(["Élément", "Valeur"], [
            ["Compte assuré", "<b>claire</b> / <b>kaldera-demo</b>"],
            ["Dossier", "KAL-26-0101 — Claire Martin, dégât des eaux, formule confort, "
                        "1 850 € déclarés (scénario NOM-01)"],
            ["Verdict attendu", "Remboursement accordé, 1 700 €"],
            ["Pièces valides", f"{F}KAL-26-0101/initiale_01_facture.pdf, initiale_02_photo.png"],
            ["Pièce illisible", f"{F}KAL-26-0601/initiale_01_facture.pdf"],
            ["Fichier refusé", "n'importe quel fichier .txt"],
        ], [4, 14]),
        PageBreak(),

        Paragraph("2. Parcours dans l'interface (utilisateur assuré)", H1),
        Paragraph("Navigateur sur http://localhost:5173 (en largeur mobile si possible : "
                  "l'interface est pensée mobile d'abord).", TXT),
        *groupes(UI),
        PageBreak(),

        Paragraph("3. Contrôles d'exploitation (administrateur)", H1),
        Paragraph("Pas encore de console d'administration web (prévue aux specs 2 et 3) : "
                  "les contrôles se font par make.", TXT),
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
