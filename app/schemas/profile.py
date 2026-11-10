from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.services.cv_review import ReviewedEntry, quality_warnings, review_blocks


class SourceReviewRead(BaseModel):
    revision: int
    entries: list[ReviewedEntry]
    excluded_source_lines: list[int]
    reason: str
    reviewed_at: datetime


class CareerPreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    track: str
    target_titles: list[str]
    enabled: bool
    locations: list[str]
    remote_preferred: bool
    created_at: datetime
    updated_at: datetime


class CVVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    original_filename: str
    media_type: str
    sha256: str
    uploaded_at: datetime
    extracted_text: str
    extracted_sections: dict[str, list[str]]
    review_flags: list[str]
    verified_at: datetime | None
    review_revision: int
    review_history: list[SourceReviewRead]

    @computed_field
    @property
    def quality_warnings(self) -> list[str]:
        if self.review_history:
            text = "\n".join(
                line for block in review_blocks([
                    entry.model_dump() for entry in self.review_history[-1].entries
                ]) for line in block
            )
        else:
            text = self.extracted_text
        return quality_warnings(text)


class CVSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot: int
    created_at: datetime
    updated_at: datetime
    versions: list[CVVersionRead]


class CVUploadRead(BaseModel):
    slot: int
    current: CVVersionRead
    review_flags: list[str]


class CandidateProfileEntry(BaseModel):
    text: str
    source_version_ids: list[str]
    source_slots: list[int]
    source_review_revisions: dict[str, int] = Field(default_factory=dict)
    verified: bool = False


class ProfessionalProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_data: dict[str, list[CandidateProfileEntry]] = Field(default_factory=dict)
    review_flags: list[str]
    updated_at: datetime


class VerifyCVRequest(BaseModel):
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]
    review_revision: int = Field(default=0, ge=0)

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_explicit_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Confirm source accuracy explicitly before verifying.")
        return value


class GenerateCVRequest(BaseModel):
    job_title: str = Field(min_length=1, max_length=200, pattern=r"\S")
    job_description: str = Field(min_length=20, max_length=30000, pattern=r"\S")


class GeneratedCVRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_version_id: UUID
    job_title: str
    selection_explanation: str
    matched_keywords: list[str]
    comparison: list[str]
    content_blocks: list[list[str]]
    review_revision: int
    created_at: datetime
