from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.limiting import limiter
from app.models import AuditLog, CVVersion, GeneratedCV, MasterCV, User
from app.schemas.profile import (
    CVVersionRead,
    GenerateCVRequest,
    GeneratedCVRead,
    VerifyCVRequest,
)
from app.services.cv_generation import generate_cv
from app.services.profile_builder import rebuild_candidate_profile
from app.services.cv_review import (
    ReviewRequest, blocking_warnings, effective_text, quality_warnings,
)

router = APIRouter(tags=["verified CV documents"])


def owned_version(db: Session, user_id: UUID, version_id: UUID) -> CVVersion:
    version = (
        db.query(CVVersion)
        .join(MasterCV)
        .filter(CVVersion.id == version_id, MasterCV.user_id == user_id)
        .with_for_update(of=CVVersion)
        .one_or_none()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="CV version not found.")
    return version


def commit_changes(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Could not save document changes."
        ) from exc


@router.post("/profile/versions/{version_id}/verify", response_model=CVVersionRead)
def verify_cv(
    version_id: UUID,
    payload: VerifyCVRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CVVersion:
    version = owned_version(db, current_user.id, version_id)
    if version.sha256 != payload.source_sha256:
        raise HTTPException(status_code=409, detail="Source hash does not match.")
    latest = max(version.master_cv.versions, key=lambda item: item.version)
    if latest.id != version.id:
        raise HTTPException(
            status_code=409, detail="This source was replaced. Review the current CV."
        )
    if payload.review_revision != version.review_revision:
        raise HTTPException(
            status_code=409, detail="Source review changed. Refresh and review it again."
        )
    warnings = quality_warnings(effective_text(version))
    if (warnings and not version.review_revision) or blocking_warnings(effective_text(version)):
        raise HTTPException(
            status_code=422,
            detail="Source quality checks require corrections in the review editor: "
            + " ".join(warnings),
        )
    version.verified_at = datetime.now(timezone.utc)
    rebuild_candidate_profile(db, current_user.id)
    db.add(AuditLog(
        user_id=current_user.id, action="cv_source_verified", resource_id=version.id
    ))
    commit_changes(db)
    return version


@router.post("/profile/versions/{version_id}/review", response_model=CVVersionRead)
def save_source_review(
    version_id: UUID,
    payload: ReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CVVersion:
    version = owned_version(db, current_user.id, version_id)
    if payload.source_sha256 != version.sha256:
        raise HTTPException(status_code=409, detail="Source hash does not match.")
    if max(version.master_cv.versions, key=lambda item: item.version).id != version.id:
        raise HTTPException(status_code=409, detail="Review the current source version.")
    if payload.expected_revision != version.review_revision:
        raise HTTPException(status_code=409, detail="Review changed. Refresh before editing.")
    line_count = len(version.extracted_text.splitlines())
    referenced = {
        line for entry in payload.entries for line in entry.source_lines
    } | set(payload.excluded_source_lines)
    if referenced != set(range(1, line_count + 1)):
        raise HTTPException(
            status_code=422,
            detail="Include or exclude every original source line exactly once.",
        )
    new_revision = version.review_revision + 1
    version.review_history = [
        *version.review_history,
        {
            "revision": new_revision,
            "entries": [entry.model_dump() for entry in payload.entries],
            "excluded_source_lines": payload.excluded_source_lines,
            "reason": payload.reason,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    version.review_revision = new_revision
    version.verified_at = None
    rebuild_candidate_profile(db, current_user.id)
    db.add(AuditLog(
        user_id=current_user.id, action="cv_source_review_saved", resource_id=version.id
    ))
    commit_changes(db)
    return version


@router.delete("/profile/versions/{version_id}/verification", status_code=204)
def revoke_verification(
    version_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    version = owned_version(db, current_user.id, version_id)
    version.verified_at = None
    rebuild_candidate_profile(db, current_user.id)
    db.add(AuditLog(
        user_id=current_user.id, action="cv_verification_revoked", resource_id=version.id
    ))
    commit_changes(db)


@router.post("/documents/cvs", response_model=GeneratedCVRead, status_code=201)
@limiter.limit("20/hour")
def create_document(
    payload: GenerateCVRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GeneratedCV:
    db.query(CVVersion).join(MasterCV).filter(
        MasterCV.user_id == current_user.id
    ).with_for_update(of=CVVersion).all()
    masters = (
        db.query(MasterCV)
        .filter(MasterCV.user_id == current_user.id)
        .order_by(MasterCV.slot)
        .all()
    )
    try:
        generated = generate_cv(masters, payload.job_title, payload.job_description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    generated.id = uuid4()
    db.add(generated)
    db.add(AuditLog(
        user_id=current_user.id, action="cv_documents_generated", resource_id=generated.id
    ))
    commit_changes(db)
    return generated


@router.get("/documents/cvs", response_model=list[GeneratedCVRead])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GeneratedCV]:
    return (
        db.query(GeneratedCV)
        .join(CVVersion)
        .join(MasterCV)
        .filter(MasterCV.user_id == current_user.id)
        .order_by(GeneratedCV.created_at.desc(), GeneratedCV.id)
        .limit(100)
        .all()
    )


@router.get("/documents/cvs/{document_id}/download/{file_format}")
def download_document(
    document_id: UUID,
    file_format: Literal["pdf", "docx"],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    generated = (
        db.query(GeneratedCV)
        .join(CVVersion)
        .join(MasterCV)
        .filter(GeneratedCV.id == document_id, MasterCV.user_id == current_user.id)
        .one_or_none()
    )
    if generated is None:
        raise HTTPException(status_code=404, detail="Generated CV not found.")
    if generated.source_version.verified_at is None:
        raise HTTPException(
            status_code=409,
            detail="Source verification was revoked. Review the source before exporting.",
        )
    if generated.review_revision != generated.source_version.review_revision:
        raise HTTPException(
            status_code=409,
            detail="This document predates the current source review. Generate a new CV.",
        )
    source_text = effective_text(generated.source_version)
    if blocking_warnings(source_text) or (
        not generated.source_version.review_revision and quality_warnings(source_text)
    ):
        raise HTTPException(
            status_code=409, detail="Review source quality warnings before exporting."
        )
    media_type = (
        "application/pdf" if file_format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return Response(
        content=(
            generated.pdf_content if file_format == "pdf" else generated.docx_content
        ),
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="careerpilot-{document_id}.{file_format}"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
