"""PDF de test écrits à la main : une page, couche texte en Helvetica (ASCII)."""

from __future__ import annotations

PNG = b"\x89PNG\r\n\x1a\n"


def _echapper(ligne: str) -> str:
    return ligne.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(flux: bytes) -> bytes:
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(flux) + flux + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    sortie, positions = bytearray(b"%PDF-1.4\n"), []
    for numero, objet in enumerate(objets, start=1):
        positions.append(len(sortie))
        sortie += b"%d 0 obj\n" % numero + objet + b"\nendobj\n"
    xref = len(sortie)
    sortie += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
    sortie += b"".join(b"%010d 00000 n \n" % p for p in positions)
    sortie += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objets) + 1,
        xref,
    )
    return bytes(sortie)


def pdf_texte(*lignes: str) -> bytes:
    """PDF natif dont la couche texte contient ces lignes (ASCII)."""
    corps = " ".join(f"({_echapper(ligne)}) Tj T*" for ligne in lignes)
    return _pdf(f"BT /F1 12 Tf 14 TL 50 750 Td {corps} ET".encode("latin-1"))


def pdf_sans_texte() -> bytes:
    """PDF sans couche texte, comme un scan."""
    return _pdf(b"0 0 m 100 100 l S")


def pdf_pages(n: int) -> bytes:
    """PDF de ``n`` pages blanches (avertissement « plusieurs pages », UI1)."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(n):
        writer.add_blank_page(612, 792)
    tampon = io.BytesIO()
    writer.write(tampon)
    return tampon.getvalue()
