import re
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from app.models import CVVersion

SECTION_TITLES = {
    "contact": "",
    "summary": "Professional Summary",
    "skills": "Skills",
    "employment_history": "Work Experience",
    "education": "Education",
    "certifications": "Certifications",
    "projects": "Projects",
    "languages": "Languages",
    "other": "Additional Information",
}
Section = Literal[
    "contact", "summary", "skills", "employment_history", "education",
    "certifications", "projects", "languages", "other",
]


class ReviewedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: Section
    text: str = Field(min_length=1, max_length=10000, pattern=r"\S")
    source_lines: list[int] = Field(min_length=1, max_length=1000)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_revision: int = Field(ge=0)
    entries: list[ReviewedEntry] = Field(min_length=1, max_length=3000)
    excluded_source_lines: list[int] = Field(default_factory=list, max_length=10000)
    reason: str = Field(min_length=5, max_length=2000, pattern=r"\S")

    @model_validator(mode="after")
    def unique_source_references(self) -> "ReviewRequest":
        if sum(len(entry.text) for entry in self.entries) > 1_000_000:
            raise ValueError("Reviewed text must not exceed one million characters.")
        references = [
            line for entry in self.entries for line in entry.source_lines
        ] + self.excluded_source_lines
        if any(line < 1 for line in references):
            raise ValueError("Source line numbers start at 1.")
        if len(set(references)) != len(references):
            raise ValueError("Every source line must be included or excluded exactly once.")
        return self


def review_blocks(entries: list[dict]) -> list[list[str]]:
    grouped: dict[str, list[str]] = {}
    for entry in entries:
        grouped.setdefault(entry["section"], []).extend(entry["text"].splitlines())
    return [
        ([SECTION_TITLES[section]] if SECTION_TITLES[section] else []) + lines
        for section in SECTION_TITLES
        if (lines := grouped.get(section))
    ]


def quality_warnings(text: str) -> list[str]:
    """Conservative signals for human review, never automatic identity inference."""
    warnings = []
    folded = text.casefold()
    if any(marker in folded for marker in (
        "reallygreatsite.com", "123 anywhere st", "+123-456-7890",
        "lorem ipsum",
    )):
        warnings.append(
            "Possible template/sample contact information remains. "
            "Exclude or correct it using the source review editor."
        )
    if "\ufffd" in text:
        warnings.append(
            "Replacement characters indicate damaged extraction. "
            "Compare with the original and correct or exclude affected lines."
        )
    if re.search(r"\b(?:[A-Z]\s+){4,}[A-Z]\b", text):
        warnings.append(
            "Widely spaced text may indicate PDF reading-order or heading errors. "
            "Assign sections and correct the text against the original."
        )
    lines = [" ".join(line.casefold().split()) for line in text.splitlines()]
    if any(count > 1 for line, count in Counter(lines).items() if len(line) > 20):
        warnings.append("Repeated lines detected. Review for duplicate source/template content.")
    if re.search(r"\b\d+(?:\.\d+)?\s*%", text):
        warnings.append(
            "Performance percentages require your evidence check. "
            "Retain only metrics you can substantiate."
        )
    if len(set(re.findall(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", folded))) > 1:
        warnings.append(
            "Multiple email addresses detected. Check for template identities or "
            "unintended third-party contact details."
        )
    if any(int(year) > datetime.now(timezone.utc).year for year in re.findall(
        r"\b(?:19|20)\d{2}\b", text
    )):
        warnings.append(
            "Future years detected. Check qualifications, award dates and employment "
            "against the original; planned dates must be clearly identified."
        )
    headings = [
        re.sub(r"\s+", "", line.casefold()).strip(":")
        for line in text.splitlines()
    ]
    if any(headings.count(heading) > 1 for heading in (
        "education", "academichistory", "summary", "professionalsummary",
        "skills", "workexperience", "employmenthistory",
    )):
        warnings.append(
            "Repeated section headings detected. Check reading order, duplicate "
            "histories and conflicting qualification dates against the original."
        )
    return warnings


def blocking_warnings(text: str) -> list[str]:
    return [
        warning for warning in quality_warnings(text)
        if warning.startswith(("Possible template/", "Replacement characters"))
    ]


def effective_blocks(version: "CVVersion") -> list[list[str]] | None:
    if version.review_revision:
        return review_blocks(version.review_history[-1]["entries"])
    return None


def effective_text(version: "CVVersion") -> str:
    blocks = effective_blocks(version)
    return (
        "\n".join(line for block in blocks for line in block)
        if blocks is not None else version.extracted_text
    )
