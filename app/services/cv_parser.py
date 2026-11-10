import io
import re
import struct
import zipfile
from dataclasses import dataclass

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.exceptions import InvalidXmlError
from lxml.etree import XMLSyntaxError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_ARCHIVE_ENTRIES = 1000
MAX_UNCOMPRESSED_DOCX_BYTES = 30 * 1024 * 1024

SECTION_HEADERS: dict[str, tuple[str, ...]] = {
    "employment_history": (
        "experience", "work experience", "employment", "professional experience",
        "work history",
    ),
    "education": ("education", "academic background", "educational background"),
    "skills": ("skills", "technical skills", "core competencies", "competencies"),
    "certifications": ("certifications", "certificates", "licenses", "licences"),
    "projects": ("projects", "selected projects", "personal projects"),
}
ALL_HEADERS = {
    re.sub(r"[^a-z0-9 ]", "", header.lower()).strip(): section
    for section, headers in SECTION_HEADERS.items()
    for header in headers
}
STOP_HEADERS = {
    "references",
    "references available on request",
    "languages",
    "interests",
    "hobbies",
    "personal details",
    "contact details",
}


@dataclass(frozen=True)
class ParsedCV:
    text: str
    sections: dict[str, list[str]]
    review_flags: list[str]


def parse_cv(data: bytes, extension: str) -> ParsedCV:
    if extension == ".pdf":
        text = _extract_pdf(data)
    elif extension == ".docx":
        text = _extract_docx(data)
    else:
        raise ValueError("Only PDF and DOCX documents are supported.")

    normalized_text = _normalize_text(text)
    if not normalized_text:
        raise ValueError(
            "No selectable text was found. Scanned PDFs require OCR, which is not "
            "enabled; please upload a text-based PDF or DOCX."
        )
    sections = _extract_sections(normalized_text)
    flags = [
        "Extracted content is unverified. Confirm every profile detail against the source CV."
    ]
    if not sections["employment_history"]:
        flags.append("No clearly labeled employment-history section was detected.")
    if not sections["education"]:
        flags.append("No clearly labeled education section was detected.")
    if not sections["skills"]:
        flags.append("No clearly labeled skills section was detected.")
    return ParsedCV(text=normalized_text, sections=sections, review_flags=flags)


def _extract_pdf(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise ValueError("The uploaded file does not have a valid PDF signature.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported.")
        if len(reader.pages) > 100:
            raise ValueError("PDF documents may contain at most 100 pages.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, OSError, struct.error) as exc:
        raise ValueError("The PDF could not be safely parsed.") from exc


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("The DOCX archive contains too many entries.")
            if sum(item.file_size for item in entries) > MAX_UNCOMPRESSED_DOCX_BYTES:
                raise ValueError("The uncompressed DOCX document is too large.")
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("The uploaded file is not a valid DOCX document.")
        document = Document(io.BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    except (
        zipfile.BadZipFile,
        KeyError,
        PackageNotFoundError,
        InvalidXmlError,
        XMLSyntaxError,
        OSError,
    ) as exc:
        raise ValueError("The uploaded file is not a valid DOCX document.") from exc


def _normalize_text(text: str) -> str:
    lines = []
    for line in text.replace("\x00", "").splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _extract_sections(text: str) -> dict[str, list[str]]:
    result = {section: [] for section in SECTION_HEADERS}
    current_section: str | None = None
    for line in text.splitlines():
        normalized_header = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()
        header_section = ALL_HEADERS.get(normalized_header)
        if header_section is not None:
            current_section = header_section
        elif normalized_header in STOP_HEADERS:
            current_section = None
        elif current_section is not None:
            result[current_section].append(line)
    return result
