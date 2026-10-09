"""Intégration — routes de l'espace assuré : session, appartenance, dépôt, soumission, chat, SSE."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from kaldera import api_assure, auth, relance
from kaldera.api import app
from kaldera.assure_postgres import DepotAssure
from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.vlm import ConfigIngestion
from tests.fabrique_pdf import PNG, pdf_pages, pdf_texte
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
ORIGINE = "http://localhost:5173"
CONFIG = auth.ConfigAssure(
    _env_file=None, session_secret="secret-de-test", cookie_secure=False, front_origin=ORIGINE
)
RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}
URL = "/assure/demandes/KAL-26-0101"


@pytest.fixture
def api(base: Any) -> Iterator[TestClient]:
    app.dependency_overrides[api_assure.depot_assure] = lambda: DepotAssure(base)
    app.dependency_overrides[api_assure.config_assure] = lambda: CONFIG
    app.dependency_overrides[api_assure.config_depot] = lambda: ConfigIngestion(
        _env_file=None, taille_max_mo=1
    )
    app.dependency_overrides[api_assure.agent_de_relance] = lambda: relance.agent_relance(
        None, None
    )
    app.dependency_overrides[api_assure.pause_flux] = lambda: 0.0
    yield TestClient(app, headers={"Origin": ORIGINE})
    app.dependency_overrides.clear()


def _dossier(base: Any, scenario: str = "NOM-01", identifiant: str = "claire") -> str:
    demande = json_demande(SCENARIOS[scenario]["demandes"][0])
    IngestionPostgres(base).creer_demande(demande)
    depot = DepotAssure(base)
    uid = depot.creer_compte(identifiant, auth.hacher("mdp-de-test"), "assure")
    depot.rattacher(uid, demande["reference"])
    return str(demande["reference"])


def _connecter(api: TestClient, identifiant: str = "claire", mot: str = "mdp-de-test") -> int:
    return api.post(
        "/assure/session", json={"identifiant": identifiant, "mot_de_passe": mot}
    ).status_code


def _sse(texte: str) -> list[tuple[int, str, dict[str, Any]]]:
    sortie = []
    for bloc in texte.strip().split("\n\n"):
        champs = dict(ligne.split(": ", 1) for ligne in bloc.splitlines() if ": " in ligne)
        sortie.append((int(champs["id"]), champs["event"], json.loads(champs["data"])))
    return sortie


def test_sans_session_401_et_sans_secret_503(api: TestClient, base: Any) -> None:
    _dossier(base)
    assert api.get("/assure/demandes").status_code == 401
    app.dependency_overrides[api_assure.config_assure] = lambda: auth.ConfigAssure(_env_file=None)
    assert api.get("/assure/demandes").status_code == 503


def test_connexion_meme_message_puis_blocage(api: TestClient, base: Any) -> None:
    _dossier(base)
    reponses = [
        api.post("/assure/session", json={"identifiant": i, "mot_de_passe": "faux"})
        for i in ("claire", "inconnu")
    ]
    assert {r.status_code for r in reponses} == {401}
    assert reponses[0].json() == reponses[1].json()
    for _ in range(4):
        _connecter(api, mot="faux")
    assert _connecter(api) == 401  # bloqué, même avec le bon mot de passe
    DepotAssure(base).remettre_a_zero(DepotAssure(base).compte("claire").id)  # type: ignore[union-attr]
    assert _connecter(api) == 204 and api.get("/assure/demandes").status_code == 200


def test_origine_refusee(api: TestClient, base: Any) -> None:
    _dossier(base)
    sans = TestClient(app)
    reponse = sans.post(
        "/assure/session", json={"identifiant": "claire", "mot_de_passe": "mdp-de-test"}
    )
    assert reponse.status_code == 403
    autre = TestClient(app, headers={"Origin": "https://evil.example"})
    assert (
        autre.post(
            "/assure/session", json={"identifiant": "claire", "mot_de_passe": "x"}
        ).status_code
        == 403
    )


def test_cookie_de_session(api: TestClient, base: Any) -> None:
    _dossier(base)
    reponse = api.post(
        "/assure/session", json={"identifiant": "claire", "mot_de_passe": "mdp-de-test"}
    )
    cookie = reponse.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=28800" in cookie
    assert api.delete("/assure/session").status_code == 204
    assert api.get("/assure/demandes").status_code == 401


def test_demande_d_un_autre_404(api: TestClient, base: Any) -> None:
    _dossier(base)
    autre = _dossier(base, "NOM-02", identifiant="paul")
    assert _connecter(api) == 204
    assert api.get(f"/assure/demandes/{autre}").status_code == 404
    assert api.get(f"/assure/demandes/{autre}/flux").status_code == 404
    assert api.post(f"/assure/demandes/{autre}/soumettre", json={}).status_code == 404
    assert api.post(f"/assure/demandes/{autre}/messages", json={"texte": "?"}).status_code == 404
    assert (
        api.post(
            f"/assure/demandes/{autre}/pieces",
            data={"type": "facture"},
            files={"fichier": ("f.png", PNG + b"x")},
        ).status_code
        == 404
    )
    assert api.get("/assure/demandes/KAL-26-9999").status_code == 404


def test_liste_et_vue(api: TestClient, base: Any) -> None:
    _dossier(base)
    _connecter(api)
    (resume,) = api.get("/assure/demandes").json()
    assert (resume["reference"], resume["etape"], resume["branche"]) == (
        "KAL-26-0101",
        1,
        "attente_pieces",
    )
    vue = api.get(URL).json()
    assert [(p["type"], p["statut"]) for p in vue["pieces"]] == [
        ("facture", "a_fournir"),
        ("photo", "a_fournir"),
    ]


def test_depot_doublon_multipage_et_refus(api: TestClient, base: Any) -> None:
    _dossier(base)
    _connecter(api)
    deux_pages = pdf_pages(2)
    premier = api.post(
        f"{URL}/pieces", data={"type": "facture"}, files={"fichier": ("f.pdf", deux_pages)}
    )
    assert premier.status_code == 202
    assert premier.json() == {"statut": "recu", "avertissement_multipage": True}
    second = api.post(
        f"{URL}/pieces", data={"type": "facture"}, files={"fichier": ("f.pdf", deux_pages)}
    )
    assert (second.status_code, second.json()["statut"]) == (200, "deja_recu")
    heic = api.post(
        f"{URL}/pieces",
        data={"type": "photo"},
        files={"fichier": ("p.heic", b"\x00\x00\x00 ftypheic")},
    )
    assert heic.status_code == 415
    assert heic.json()["detail"] == "Format non accepté : PDF, PNG ou JPEG uniquement."
    assert api.get(URL).json()["pieces"][0]["statut"] == "en_analyse"
    assert DepotAssure(base).evenements_depuis("KAL-26-0101", 0)[-1]["type"] == "piece"


def test_soumission(api: TestClient, base: Any) -> None:
    _dossier(base)
    _connecter(api)
    facture = pdf_texte("Total 1850.00 EUR")
    api.post(f"{URL}/pieces", data={"type": "facture"}, files={"fichier": ("f.pdf", facture)})
    assert api.post(f"{URL}/soumettre", json={}).json()["detail"] == "analyse_en_cours"
    with base.connection() as conn:
        conn.execute("UPDATE pieces SET statut_analyse = 'ok', lisible = true")
    refus = api.post(f"{URL}/soumettre", json={})
    assert (refus.status_code, refus.json()["detail"]) == (
        409,
        "confirmation_requise",
    )  # photo manque
    vue = api.post(f"{URL}/soumettre", json={"confirmer": True})
    assert vue.status_code == 200 and vue.json()["soumise"] is True
    double = api.post(f"{URL}/soumettre", json={"confirmer": True})
    assert (double.status_code, double.json()["detail"]) == (409, "deja_soumise")
    tard = api.post(
        f"{URL}/pieces", data={"type": "photo"}, files={"fichier": ("p.png", PNG + b"y")}
    )
    assert tard.status_code == 409
    assert tard.json()["detail"].startswith("Votre dossier a déjà été soumis")


def test_messages(api: TestClient, base: Any) -> None:
    _dossier(base)
    _connecter(api)
    for texte in ("", "   ", "x" * 1001):
        assert api.post(f"{URL}/messages", json={"texte": texte}).status_code == 422
    reponse = api.post(f"{URL}/messages", json={"texte": "Quelles pièces dois-je fournir ?"})
    assert reponse.status_code == 202 and reponse.json()["auteur"] == "agent"
    assert "facture" in reponse.json()["texte"].lower()
    messages = [
        e["contenu"]["auteur"]
        for e in DepotAssure(base).evenements_depuis("KAL-26-0101", 0)
        if e["type"] == "message"
    ]
    assert messages == ["assure", "agent"]
    for _ in range(29):
        DepotAssure(base).inserer_evenement(
            "KAL-26-0101", "message", None, {"auteur": "assure", "texte": "?"}
        )
    assert api.post(f"{URL}/messages", json={"texte": "encore ?"}).status_code == 429


def test_message_sur_dossier_clos_409(api: TestClient, base: Any) -> None:
    _dossier(base)
    _connecter(api)
    with base.connection() as conn:
        conn.execute("UPDATE demandes SET statut = 'terminee'")
    reponse = api.post(f"{URL}/messages", json={"texte": "Quelles pièces ?"})
    assert reponse.status_code == 409 and reponse.json()["detail"] == "dossier_clos"
    assert DepotAssure(base).evenements_depuis("KAL-26-0101", 0) == []


def test_flux_se_ferme_quand_le_client_part() -> None:
    class DepotMuet:
        def evenements_depuis(self, reference: str, apres: int) -> list[Any]:
            return []

        def statut(self, reference: str) -> str:
            return "admission"

    class Parti:
        async def is_disconnected(self) -> bool:
            return True

    async def lire() -> list[str]:
        flux = api_assure._flux(cast(Any, Parti()), cast(Any, DepotMuet()), "KAL-X", 0, 0.0)
        return [e async for e in flux]

    assert asyncio.run(asyncio.wait_for(lire(), 2.0)) == []


def test_flux_ordre_reprise_et_fin(api: TestClient, base: Any) -> None:
    _dossier(base)
    _connecter(api)
    depot = DepotAssure(base)
    premier = depot.inserer_evenement("KAL-26-0101", "piece", 1, {"etape": 1})
    depot.inserer_evenement("KAL-26-0101", "message", None, {"auteur": "agent", "texte": "a"})
    depot.inserer_evenement("KAL-26-0101", "verdict", 5, {"etape": 5})
    with api.stream("GET", f"{URL}/flux") as flux:
        assert flux.headers["content-type"].startswith("text/event-stream")
        evts = _sse(flux.read().decode())
    assert [t for _, t, _ in evts] == ["piece", "message", "verdict"]  # s'arrête au verdict
    with api.stream("GET", f"{URL}/flux", headers={"Last-Event-ID": str(premier)}) as flux:
        assert [t for _, t, _ in _sse(flux.read().decode())] == ["message", "verdict"]
    with base.connection() as conn:
        conn.execute("UPDATE demandes SET statut = 'terminee'")
    with api.stream("GET", f"{URL}/flux", headers={"Last-Event-ID": "999999"}) as flux:
        assert flux.read() == b""  # terminée, rien de neuf : fermeture immédiate
