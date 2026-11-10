import hashlib
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import get_settings
from app.core.limiting import limiter
from app.models import CVVersion, MasterCV, ProfessionalProfile, User
from app.schemas.profile import (
    CVSlotRead,
    CVUploadRead,
    ProfessionalProfileRead,
)
from app.services.cv_parser import parse_cv
from app.services.cv_storage import make_storage_key, storage_path
from app.services.profile_builder import rebuild_candidate_profile

router = APIRouter(prefix="/profile", tags=["professional profile"])
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _validate_slot(slot: int) -> None:
    if slot not in (1, 2):
        raise HTTPException(
            status_code=422,
            detail="CV slot must be 1 or 2.",
        )


def _get_master_cv(db: Session, user_id: UUID, slot: int) -> MasterCV:
    master_cv = (
        db.query(MasterCV)
        .filter(MasterCV.user_id == user_id, MasterCV.slot == slot)
        .one_or_none()
    )
    if master_cv is None:
        raise HTTPException(status_code=404, detail="CV slot not found.")
    return master_cv


@router.get("", response_model=ProfessionalProfileRead)
def read_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfessionalProfile:
    profile = db.get(ProfessionalProfile, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Upload a master CV to create your professional profile.",
        )
    return profile


@router.get("/cvs", response_model=list[CVSlotRead])
def list_master_cvs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MasterCV]:
    return (
        db.query(MasterCV)
        .filter(MasterCV.user_id == current_user.id)
        .order_by(MasterCV.slot)
        .all()
    )


@router.post("/cvs/{slot}", response_model=CVUploadRead, status_code=201)
@limiter.limit("10/hour")
async def upload_master_cv(
    slot: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CVUploadRead:
    _validate_slot(slot)
    filename = Path((file.filename or "").replace("\\", "/")).name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415, detail="Upload a PDF or DOCX file."
        )
    max_upload_size = get_settings().max_upload_size_bytes
    data = await file.read(max_upload_size + 1)
    await file.close()
    if len(data) > max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=(
                f"CV file exceeds the {max_upload_size // (1024 * 1024)} MB "
                "upload limit."
            ),
        )
    try:
        parsed = parse_cv(data, extension)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    master_cv = (
        db.query(MasterCV)
        .filter(MasterCV.user_id == current_user.id, MasterCV.slot == slot)
        .one_or_none()
    )
    if master_cv is None:
        master_cv = MasterCV(user_id=current_user.id, slot=slot)
        db.add(master_cv)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="This CV slot changed concurrently. Refresh and retry.",
            ) from exc
    next_version = max(
        (version.version for version in master_cv.versions), default=0
    ) + 1
    storage_key = make_storage_key(
        current_user.id, slot, next_version, extension
    )
    path = storage_path(storage_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stored_file:
            stored_file.write(data)
    except OSError as exc:
        db.rollback()
        try:
            path.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            raise HTTPException(
                status_code=500,
                detail="CV storage failed and partial-file cleanup also failed.",
            ) from cleanup_exc
        raise HTTPException(
            status_code=500, detail="Could not store the uploaded CV."
        ) from exc

    safe_filename = (
        re.sub(r"[\x00-\x1f\x7f]", "", filename)[:255] or f"cv{extension}"
    )
    version = CVVersion(
        master_cv=master_cv,
        master_cv_id=master_cv.id,
        version=next_version,
        original_filename=safe_filename,
        media_type=ALLOWED_EXTENSIONS[extension],
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=storage_key,
        extracted_text=parsed.text,
        extracted_sections=parsed.sections,
        review_flags=parsed.review_flags,
    )
    db.add(version)
    try:
        db.flush()
        profile = rebuild_candidate_profile(db, current_user.id)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            path.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            raise HTTPException(
                status_code=500,
                detail="CV database save failed and partial-file cleanup also failed.",
            ) from cleanup_exc
        raise HTTPException(
            status_code=500, detail="Could not save the CV profile."
        ) from exc
    db.refresh(version)
    db.refresh(profile)
    return CVUploadRead(slot=slot, current=version, review_flags=profile.review_flags)


@router.get("/cvs/{slot}", response_model=CVSlotRead)
def get_master_cv(
    slot: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MasterCV:
    _validate_slot(slot)
    return _get_master_cv(db, current_user.id, slot)


@router.get("/cvs/{slot}/versions/{version_number}/download")
def download_cv_version(
    slot: int,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    _validate_slot(slot)
    master_cv = _get_master_cv(db, current_user.id, slot)
    version = next(
        (item for item in master_cv.versions if item.version == version_number), None
    )
    if version is None:
        raise HTTPException(status_code=404, detail="CV version not found.")
    path = storage_path(version.storage_key)
    if not path.is_file():
        raise HTTPException(
            status_code=500, detail="The stored CV file is unavailable."
        )
    return FileResponse(
        path,
        media_type=version.media_type,
        filename=version.original_filename,
    )


@router.delete("/cvs/{slot}", status_code=204)
def delete_master_cv(
    slot: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _validate_slot(slot)
    master_cv = _get_master_cv(db, current_user.id, slot)
    files = [storage_path(version.storage_key) for version in master_cv.versions]
    profile = db.get(ProfessionalProfile, current_user.id)
    try:
        db.delete(master_cv)
        db.flush()
        if profile is not None:
            rebuild_candidate_profile(db, current_user.id)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Could not delete the CV."
        ) from exc
    for path in files:
        path.unlink(missing_ok=True)
