import io
import re
import unicodedata
from docx import Document
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.models import CVVersion, GeneratedCV, MasterCV
from app.services.cv_parser import ALL_HEADERS, STOP_HEADERS
from app.services.pdf_fonts import register_pdf_fonts, render_pdf_lines
from app.services.cv_review import (
    blocking_warnings, effective_blocks, effective_text, quality_warnings,
)

STOP_WORDS = {
    "and", "are", "for", "from", "have", "our", "the", "this", "that", "with",
    "you", "your", "will", "role", "work", "job", "experience", "required",
}


def keywords(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[^\W_][\w+#.-]*", text, flags=re.UNICODE)
        if len(token) > 2 and token.casefold() not in STOP_WORDS
    }


def content_blocks(text: str) -> list[list[str]]:
    """Keep complete sections together so role titles, dates and bullets stay linked."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        heading = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()
        if heading in ALL_HEADERS or heading in STOP_HEADERS:
            if current:
                blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def clean_document_blocks(
    blocks: list[list[str]],
) -> tuple[list[list[str]], list[str]]:
    removed = sorted({
        ord(char) for block in blocks for line in block for char in line
        if unicodedata.category(char) == "Cc" and char not in "\t\n\r"
    })
    cleaned = [
        [
            "".join(
                char for char in line
                if unicodedata.category(char) != "Cc" or char in "\t\n\r"
            )
            for line in block
        ]
        for block in blocks
    ]
    notes = []
    if removed:
        notes.append(
            "Removed nonprinting extraction controls from generated output only: "
            + ", ".join(f"U+{code:04X}" for code in removed)
            + ". Original source text and file are unchanged."
        )
    return cleaned, notes


def generate_cv(
    masters: list[MasterCV], job_title: str, job_description: str
) -> GeneratedCV:
    candidates: list[tuple[MasterCV, CVVersion]] = []
    for master in masters:
        if master.versions:
            latest = max(master.versions, key=lambda version: version.version)
            text = effective_text(latest)
            if (
                latest.verified_at is not None
                and not blocking_warnings(text)
                and (latest.review_revision or not quality_warnings(text))
            ):
                candidates.append((master, latest))
    if not candidates:
        raise ValueError(
            "Verify a current master CV before generating documents. "
            "Resolve source quality warnings in the review editor first."
        )

    terms = keywords(f"{job_title} {job_description}")
    master, selected = max(
        candidates,
        key=lambda pair: (
            len(terms & keywords(effective_text(pair[1]))),
            -pair[0].slot,
        ),
    )
    matched = sorted(terms & keywords(effective_text(selected)))
    if not matched:
        raise ValueError(
            "No keyword overlap with a verified current CV. "
            "Review the vacancy and source documents before generating."
        )
    blocks, cleanup_notes = clean_document_blocks(
        effective_blocks(selected) or content_blocks(selected.extracted_text)
    )

    def relevance(block: list[str]) -> int:
        return len(terms & keywords("\n".join(block)))

    # Keep identity/contact details first and move only whole recognized sections.
    prefix: list[list[str]] = []
    tail: list[list[str]] = []
    sortable: list[list[str]] = []
    for block in blocks:
        heading = re.sub(r"[^a-z0-9 ]", "", block[0].lower()).strip()
        if heading in ALL_HEADERS:
            sortable.append(block)
        elif not sortable:
            prefix.append(block)
        else:
            tail.append(block)
    ordered = prefix + sorted(sortable, key=relevance, reverse=True) + tail
    comparison = [
        (
            "Source wording retained except documented nonprinting-control cleanup; "
            "no skills, dates, titles or metrics added."
            if cleanup_notes else
            "All source lines retained verbatim; no skills, dates, titles or metrics added."
        ),
        "Whole sections ranked by exact keyword overlap; lines within sections stay together.",
        f"Original block order: {' / '.join(block[0] for block in blocks)}",
        f"Generated block order: {' / '.join(block[0] for block in ordered)}",
        "No AI rewriting or proficiency inference. Check layout and relevance before use.",
        *cleanup_notes,
    ]
    if selected.review_revision:
        review = selected.review_history[-1]
        comparison[0] = (
            f"Uses owner-reviewed revision {selected.review_revision}; "
            "corrections and exclusions are explicitly recorded against source lines."
        )
        comparison.extend([
            "Review reason: " + review["reason"],
            "Excluded original source lines: "
            + (", ".join(map(str, review["excluded_source_lines"])) or "none"),
            *[
                f"Reviewed entry from source lines {', '.join(map(str, entry['source_lines']))}: "
                + entry["text"]
                for entry in review["entries"]
                if entry["text"] != "\n".join(
                    selected.extracted_text.splitlines()[line - 1]
                    for line in entry["source_lines"]
                )
            ],
        ])
    pdf, docx = render_documents(ordered)
    return GeneratedCV(
        source_version_id=selected.id,
        job_title=job_title.strip(),
        job_description=job_description,
        selection_explanation=(
            f"Selected CV {master.slot}, version {selected.version}: "
            f"{len(matched)} distinct keyword overlaps among "
            f"{len(candidates)} verified current CV(s). Ties favor the lower slot. "
            "This is lexical selection, not a suitability score."
        ),
        matched_keywords=matched,
        comparison=comparison,
        content_blocks=ordered,
        review_revision=selected.review_revision or 0,
        pdf_content=pdf,
        docx_content=docx,
    )


def render_documents(blocks: list[list[str]]) -> tuple[bytes, bytes]:
    blocks, _ = clean_document_blocks(blocks)
    fonts = register_pdf_fonts()
    pdf_lines = iter(render_pdf_lines(
        [line.expandtabs(4) for block in blocks for line in block], fonts
    ))

    document = Document()
    pdf_buffer = io.BytesIO()
    story = []
    style = ParagraphStyle(
        "SourceText", fontName=fonts[0], fontSize=10, leading=14,
        splitLongWords=True,
    )
    for block in blocks:
        for line in block:
            document.add_paragraph(line)
            # Paragraph is XML-based: source text is data, never document markup.
            story.append(Paragraph(next(pdf_lines), style))
        story.append(Spacer(1, 10))
    SimpleDocTemplate(
        pdf_buffer, title="Curriculum Vitae", author="",
        leftMargin=45, rightMargin=45, topMargin=45, bottomMargin=45,
    ).build(story)
    docx_buffer = io.BytesIO()
    document.save(docx_buffer)
    return pdf_buffer.getvalue(), docx_buffer.getvalue()
