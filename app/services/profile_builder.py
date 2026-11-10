from uuid import UUID

from sqlalchemy.orm import Session

from app.models import CVVersion, MasterCV, ProfessionalProfile

PROFILE_SECTIONS = (
    "employment_history",
    "education",
    "skills",
    "certifications",
    "projects",
)


def rebuild_candidate_profile(
    db: Session, user_id: UUID
) -> ProfessionalProfile:
    current_versions: list[tuple[int, CVVersion]] = []
    master_cvs = (
        db.query(MasterCV)
        .filter(MasterCV.user_id == user_id)
        .order_by(MasterCV.slot)
        .all()
    )
    profile_flags: list[str] = []
    for master_cv in master_cvs:
        if not master_cv.versions:
            continue
        current = max(master_cv.versions, key=lambda version: version.version)
        current_versions.append((master_cv.slot, current))
        profile_flags.extend(current.review_flags)

    candidate_data: dict[str, list[dict]] = {}
    for section in PROFILE_SECTIONS:
        merged: dict[str, dict] = {}
        for slot, version in current_versions:
            for entry in version.extracted_sections.get(section, []):
                normalized = " ".join(entry.casefold().split())
                item = merged.setdefault(
                    normalized,
                    {
                        "text": entry,
                        "source_version_ids": [],
                        "source_slots": [],
                        "verified": False,
                    },
                )
                if str(version.id) not in item["source_version_ids"]:
                    item["source_version_ids"].append(str(version.id))
                if slot not in item["source_slots"]:
                    item["source_slots"].append(slot)
        candidate_data[section] = list(merged.values())
        if any(
            len(set(entry["source_slots"])) > 1 for entry in candidate_data[section]
        ):
            profile_flags.append(
                f"Some {section.replace('_', ' ')} entries appear in both current CVs."
            )

    profile = db.get(ProfessionalProfile, user_id)
    if profile is None:
        profile = ProfessionalProfile(
            user_id=user_id,
            candidate_data=candidate_data,
            review_flags=list(dict.fromkeys(profile_flags)),
        )
        db.add(profile)
    else:
        profile.candidate_data = candidate_data
        profile.review_flags = list(dict.fromkeys(profile_flags))
    return profile
