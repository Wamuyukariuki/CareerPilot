from uuid import UUID

from app.models import CareerPreference

DEFAULT_TRACKS: dict[str, list[str]] = {
    "software_engineering": [
        "Python Developer",
        "Backend Developer",
        "Software Engineer",
        "Django Developer",
        "FastAPI Developer",
        "API Developer",
        "Full-Stack Developer",
        "FinTech Software Engineer",
        "AI Integration Engineer",
        "Remote Python Developer",
    ],
    "cybersecurity": [
        "Cybersecurity Analyst",
        "Application Security Engineer",
        "Security Engineer",
        "Penetration Testing Analyst",
        "Vulnerability Assessment Analyst",
        "DevSecOps Engineer",
        "Information Security Officer",
        "Security Operations Analyst",
        "Digital Forensics Analyst",
        "Cloud Security Engineer",
    ],
    "electrical_engineering": [
        "Electrical Engineer",
        "Electrical Maintenance Engineer",
        "Power Systems Engineer",
        "Renewable Energy Engineer",
        "Data Centre Engineer",
        "Electrical Infrastructure Engineer",
        "Technical Service Engineer",
        "Field Service Engineer",
        "Industrial Automation Engineer",
    ],
}


def default_preferences(user_id: UUID) -> list[CareerPreference]:
    return [
        CareerPreference(
            user_id=user_id,
            track=track,
            target_titles=titles,
            enabled=True,
            locations=[],
            remote_preferred=False,
        )
        for track, titles in DEFAULT_TRACKS.items()
    ]
