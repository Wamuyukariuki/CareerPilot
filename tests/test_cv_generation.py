from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import reportlab
from docx import Document
from pypdf import PdfReader

from app.models import CVVersion, MasterCV
from app.services.cv_generation import generate_cv, render_documents
from app.services.cv_review import quality_warnings, blocking_warnings


def source(slot, text, verified=True, version_number=1):
    master = MasterCV(id=uuid4(), slot=slot)
    version = CVVersion(
        id=uuid4(), master_cv=master, version=version_number,
        extracted_text=text, verified_at=(
            datetime.now(timezone.utc) if verified else None
        ),
    )
    return master, version


def test_selects_verified_source_preserves_role_context_and_all_wording():
    software, selected = source(
        1,
        "Applicant Name\napplicant@example.com\n"
        "Education\nBSc Engineering, 2020\n"
        "Experience\nBackend Engineer, Example Co, 2021-2024\n"
        "Built Python APIs with Django.\n"
        "Skills\nPython, Django, SQL\n"
        "Personal Projects\nPersonal Python inventory app\n"
        "References\nAvailable on request",
    )
    electrical, _ = source(2, "Experience\nElectrical maintenance and power systems")
    generated = generate_cv(
        [software, electrical], "Python Backend Engineer",
        "Python Django SQL APIs for backend services",
    )
    assert generated.source_version_id == selected.id
    assert generated.matched_keywords == ["apis", "backend", "django", "engineer", "python", "sql"]
    assert Counter(
        line for block in generated.content_blocks for line in block
    ) == Counter(selected.extracted_text.splitlines())
    experience = next(
        block for block in generated.content_blocks if block[0] == "Experience"
    )
    assert experience == [
        "Experience",
        "Backend Engineer, Example Co, 2021-2024",
        "Built Python APIs with Django.",
    ]
    assert generated.content_blocks[0] == [
        "Applicant Name", "applicant@example.com"
    ]
    assert generated.content_blocks[1][0] == "Experience"
    assert generated.comparison
    assert "lexical selection" in generated.selection_explanation

    docx = Document(BytesIO(generated.docx_content))
    assert [paragraph.text for paragraph in docx.paragraphs] == [
        line for block in generated.content_blocks for line in block
    ]
    pdf_text = "\n".join(
        page.extract_text() for page in PdfReader(BytesIO(generated.pdf_content)).pages
    )
    assert "Backend Engineer, Example Co, 2021-2024" in pdf_text
    assert "Personal Python inventory app" in pdf_text
    assert "applicant@example.com" in pdf_text


def test_latest_unverified_replacement_cannot_reuse_old_verified_source():
    master, _ = source(1, "Experience\nPython developer")
    CVVersion(
        id=uuid4(), master_cv=master, version=2,
        extracted_text="Experience\nPython developer", verified_at=None,
    )
    with pytest.raises(ValueError, match="Verify a current master CV"):
        generate_cv([master], "Python", "Python developer wanted for backend role")


def test_no_overlap_is_not_presented_as_a_suitable_source():
    master, _ = source(1, "Skills\nElectrical power engineering")
    with pytest.raises(ValueError, match="No keyword overlap"):
        generate_cv([master], "Accountant", "Financial bookkeeping taxation reporting")


@pytest.mark.parametrize("text, signal", [
    ("hello@reallygreatsite.com", "template/sample"),
    ("Broken \ufffd text", "Replacement characters"),
    ("W O R K E X P E R I E N C E", "Widely spaced"),
    ("Repeated long paragraph in a CV.\nRepeated long paragraph in a CV.", "Repeated lines"),
    ("Improved efficiency by 15%", "Performance percentages"),
    ("one@example.com\ntwo@example.com", "Multiple email"),
    ("Education\nBSc 2020\nEducation\nBSc 2022", "Repeated section"),
    ("Excellence award 2099", "Future years"),
])
def test_quality_signals_require_review_without_guessing_truth(text, signal):
    assert any(signal in warning for warning in quality_warnings(text))
    master, _ = source(1, text)
    with pytest.raises(ValueError, match="source quality warnings"):
        generate_cv([master], "Python", "Python backend development")


def test_soft_findings_require_review_but_can_be_explicitly_owner_verified():
    text = "Personal project reduced example runtime by 10%"
    assert quality_warnings(text)
    assert not blocking_warnings(text)
    master, version = source(1, text)
    version.review_revision = 1
    version.review_history = [{
        "entries": [{"section": "projects", "text": text, "source_lines": [1]}],
        "reason": "Checked project benchmarks.", "excluded_source_lines": [],
    }]
    generated = generate_cv([master], "Runtime", "Personal runtime project")
    assert generated.review_revision == 1
    assert text in generated.content_blocks[0]


def test_source_selection_and_overlap_use_reviewed_not_excluded_claims():
    master, version = source(1, "Python\nKubernetes Azure deployment")
    version.review_revision = 1
    version.review_history = [{
        "entries": [{"section": "skills", "text": "Python", "source_lines": [1]}],
        "reason": "Excluded unrelated template skills.", "excluded_source_lines": [2],
    }]
    with pytest.raises(ValueError, match="No keyword overlap"):
        generate_cv([master], "Kubernetes", "Kubernetes Azure deployment")
    other, selected = source(2, "Skills\nKubernetes Azure deployment")
    generated = generate_cv([master, other], "Kubernetes", "Kubernetes Azure deployment")
    assert generated.source_version_id == selected.id
    assert version.extracted_text == "Python\nKubernetes Azure deployment"


def test_rendering_escapes_markup_and_preserves_supported_unicode():
    blocks = [["Applicant"], ["Skills", "Python & SQL <advanced> – personal project"]]
    pdf, docx = render_documents(blocks)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert "Python & SQL <advanced>" in text
    assert "– personal project" in text
    assert Document(BytesIO(docx)).paragraphs[-1].text == blocks[-1][-1]


def test_renderer_fails_instead_of_silently_replacing_unsupported_characters():
    with pytest.raises(ValueError, match="U\\+10FFFF"):
        render_documents([["Applicant \U0010ffff"]])


def test_renderer_preserves_tabs_in_docx_and_expands_pdf_layout():
    pdf, docx = render_documents([["Python\tDjango"]])
    assert "Python" in PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert Document(BytesIO(docx)).paragraphs[0].text == "Python\tDjango"


def test_missing_configured_font_has_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.pdf_fonts.get_settings",
        lambda: SimpleNamespace(pdf_font_paths=[str(tmp_path / "missing.ttf")]),
    )
    with pytest.raises(ValueError, match="Configured PDF font 1 is unavailable"):
        render_documents([["Applicant"]])


def test_control_cleanup_is_reported_without_changing_verified_source():
    master, version = source(
        1, "Applicant\x02 Name\nExperience\nPython Developer\x7f\nSkills\nPython"
    )
    original = version.extracted_text
    generated = generate_cv(
        [master], "Python Developer", "Python backend development"
    )
    assert version.extracted_text == original
    assert generated.content_blocks[0] == ["Applicant Name"]
    assert any("U+0002, U+007F" in note for note in generated.comparison)
    assert not any("retained verbatim" in note for note in generated.comparison)
    docx = Document(BytesIO(generated.docx_content))
    assert docx.paragraphs[0].text == "Applicant Name"
    assert all("\x02" not in p.text and "\x7f" not in p.text for p in docx.paragraphs)
    assert "Applicant Name" in PdfReader(BytesIO(generated.pdf_content)).pages[0].extract_text()


@pytest.mark.skipif(
    not Path("/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf").is_file(),
    reason="Docker contact-icon integration requires Symbola",
)
def test_reported_contact_icons_and_control_generate_with_lossless_symbols(monkeypatch):
    monkeypatch.setattr(
        "app.services.pdf_fonts.get_settings",
        lambda: SimpleNamespace(pdf_font_paths=[
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf",
        ]),
    )
    line = "\U0001f4de +254000000000 \U0001f4e7 applicant@example.com \U0001f517 example.com"
    master, version = source(1, f"Applicant\x02\n{line}\nSkills\nPython")
    generated = generate_cv([master], "Python", "Python developer needed")
    text = "\n".join(
        page.extract_text()
        for page in PdfReader(BytesIO(generated.pdf_content)).pages
    )
    assert line in text
    assert Document(BytesIO(generated.docx_content)).paragraphs[1].text == line
    assert any("U+0002" in note for note in generated.comparison)
    assert "\x02" in version.extracted_text


@pytest.mark.skipif(
    not Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf").is_file(),
    reason="Docker Unicode-font integration test requires installed DejaVu",
)
def test_docker_unicode_font_preserves_common_cv_symbols(monkeypatch):
    monkeypatch.setattr(
        "app.services.pdf_fonts.get_settings",
        lambda: SimpleNamespace(
            pdf_font_paths=[
                str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"),
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        ),
    )
    line = "Python \u2022 SQL \u2192 APIs \u2713 \u260e \u201cDjango\u201d"
    pdf, docx = render_documents([[line]])
    assert line in PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert Document(BytesIO(docx)).paragraphs[0].text == line
