"""Regenerate the small deterministic Playwright upload fixtures."""

import io
from pathlib import Path

from docx import Document


OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "e2e" / "fixtures"
OUTPUT.mkdir(parents=True, exist_ok=True)

(OUTPUT / "evidence.txt").write_text("The garden trial ended after four weeks.", encoding="utf-8")

text = "The garden trial ended after four weeks."
stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
]
pdf = bytearray(b"%PDF-1.4\n")
offsets = [0]
for index, body in enumerate(objects, 1):
    offsets.append(len(pdf))
    pdf.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
xref = len(pdf)
pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
for offset in offsets[1:]:
    pdf.extend(f"{offset:010d} 00000 n \n".encode())
pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
(OUTPUT / "evidence.pdf").write_bytes(pdf)

document = Document()
document.add_paragraph(text)
docx = io.BytesIO()
document.save(docx)
(OUTPUT / "evidence.docx").write_bytes(docx.getvalue())
