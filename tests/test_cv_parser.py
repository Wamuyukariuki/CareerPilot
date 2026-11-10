from io import BytesIO

import pytest
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.cv_parser import parse_cv


def make_docx_bytes(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extracts_labeled_sections_without_inventing_content():
    source = make_docx_bytes(
        "Professional Experience",
        "Backend Engineer | Example Co | 2022-2025",
        "Built APIs using Python.",
        "Education",
        "BSc Electrical Engineering, Example University",
        "Technical Skills",
        "Python, SQL, Django",
        "Certifications",
        "Cloud Fundamentals",
        "Projects",
        "Personal inventory application",
        "References available on request",
    )

    parsed = parse_cv(source, ".docx")

    assert parsed.sections["employment_history"] == [
        "Backend Engineer | Example Co | 2022-2025",
        "Built APIs using Python.",
    ]
    assert parsed.sections["education"] == [
        "BSc Electrical Engineering, Example University"
    ]
    assert parsed.sections["skills"] == ["Python, SQL, Django"]
    assert parsed.sections["certifications"] == ["Cloud Fundamentals"]
    assert parsed.sections["projects"] == ["Personal inventory application"]
    assert "References available on request" not in parsed.sections["projects"]
    assert parsed.review_flags[0].startswith("Extracted content is unverified.")


def test_rejects_invalid_pdf_signature_and_malformed_docx():
    with pytest.raises(ValueError, match="valid PDF signature"):
        parse_cv(b"not a pdf", ".pdf")
    with pytest.raises(ValueError, match="valid DOCX"):
        parse_cv(b"not a word document", ".docx")

    blank_pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(blank_pdf)
    with pytest.raises(ValueError, match="No selectable text"):
        parse_cv(blank_pdf.getvalue(), ".pdf")


def test_extracts_selectable_pdf_text():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_ref}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 12 Tf 72 720 Td (Experience) Tj 0 -18 Td "
        b"(Engineer at Example) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    pdf_buffer = BytesIO()
    writer.write(pdf_buffer)

    parsed = parse_cv(pdf_buffer.getvalue(), ".pdf")

    assert parsed.text == "Experience\nEngineer at Example"
    assert parsed.sections["employment_history"] == ["Engineer at Example"]


def test_flags_text_documents_without_detectable_sections():
    parsed = parse_cv(make_docx_bytes("A profile without labeled sections."), ".docx")

    assert parsed.text == "A profile without labeled sections."
    assert all(not entries for entries in parsed.sections.values())
    assert len(parsed.review_flags) == 4
