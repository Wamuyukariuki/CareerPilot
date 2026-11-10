from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    extracted_sections: dict[str, list[str]]
    review_flags: list[str]


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
    verified: bool = False


class ProfessionalProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_data: dict[str, list[CandidateProfileEntry]] = Field(default_factory=dict)
    review_flags: list[str]
    updated_at: datetime
