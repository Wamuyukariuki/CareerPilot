from io import BytesIO
from types import SimpleNamespace

from docx import Document


def make_docx_bytes(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def register_and_login(client, email="person@example.com"):
    payload = {
        "email": email,
        "full_name": "A Person",
        "password": "a-very-long-test-password",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    response = client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_upload_replace_history_profile_and_delete(client, tmp_path, monkeypatch):
    settings = SimpleNamespace(
        upload_dir=str(tmp_path), max_upload_size_bytes=10 * 1024 * 1024
    )
    monkeypatch.setattr("app.services.cv_storage.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.profile.get_settings", lambda: settings)
    headers = register_and_login(client)
    first_document = make_docx_bytes(
        "Experience",
        "Python developer at Example Co",
        "Built internal APIs.",
        "Skills",
        "Python, SQL",
    )

    upload_response = client.post(
        "/api/profile/cvs/1",
        headers=headers,
        files={
            "file": (
                "first.docx",
                first_document,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_response.status_code == 201, upload_response.text
    assert upload_response.json()["current"]["version"] == 1
    first_id = upload_response.json()["current"]["id"]
    assert upload_response.json()["current"]["extracted_sections"]["skills"] == [
        "Python, SQL"
    ]

    profile_response = client.get("/api/profile", headers=headers)
    assert profile_response.status_code == 200
    candidate_data = profile_response.json()["candidate_data"]
    assert candidate_data["employment_history"][0]["text"] == (
        "Python developer at Example Co"
    )
    assert candidate_data["employment_history"][0]["verified"] is False
    assert candidate_data["employment_history"][0]["source_slots"] == [1]

    second_document = make_docx_bytes(
        "Experience",
        "Python developer at Example Co",
        "Maintained backend services.",
        "Education",
        "BSc Computer Science",
    )
    replacement = client.post(
        "/api/profile/cvs/1",
        headers=headers,
        files={
            "file": (
                "replacement.docx",
                second_document,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["current"]["version"] == 2

    history = client.get("/api/profile/cvs", headers=headers).json()
    assert len(history) == 1
    assert [version["version"] for version in history[0]["versions"]] == [1, 2]
    downloaded = client.get(
        "/api/profile/cvs/1/versions/1/download", headers=headers
    )
    assert downloaded.status_code == 200
    assert downloaded.content == first_document

    delete_response = client.delete("/api/profile/cvs/1", headers=headers)
    assert delete_response.status_code == 204
    assert list(tmp_path.iterdir()) == []
    assert client.get("/api/profile/cvs", headers=headers).json() == []
    assert client.get("/api/profile", headers=headers).json()["candidate_data"] == {
        "employment_history": [],
        "education": [],
        "skills": [],
        "certifications": [],
        "projects": [],
    }
    assert first_id != replacement.json()["current"]["id"]


def test_cv_access_is_scoped_to_the_authenticated_user(client, tmp_path, monkeypatch):
    settings = SimpleNamespace(
        upload_dir=str(tmp_path), max_upload_size_bytes=10 * 1024 * 1024
    )
    monkeypatch.setattr("app.services.cv_storage.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.profile.get_settings", lambda: settings)
    first_user_headers = register_and_login(client, "first@example.com")
    second_user_headers = register_and_login(client, "second@example.com")
    upload = client.post(
        "/api/profile/cvs/1",
        headers=first_user_headers,
        files={"file": ("resume.docx", make_docx_bytes("Experience", "Engineer"), "application/octet-stream")},
    )
    assert upload.status_code == 201, upload.text

    assert client.get("/api/profile/cvs", headers=second_user_headers).json() == []
    assert client.get(
        "/api/profile/cvs/1", headers=second_user_headers
    ).status_code == 404
    assert client.get("/api/profile", headers=second_user_headers).status_code == 404


def test_rejects_unsupported_and_invalid_files(client):
    headers = register_and_login(client)
    unsupported = client.post(
        "/api/profile/cvs/1",
        headers=headers,
        files={"file": ("resume.txt", b"untrusted content", "text/plain")},
    )
    assert unsupported.status_code == 415

    invalid_pdf = client.post(
        "/api/profile/cvs/1",
        headers=headers,
        files={"file": ("resume.pdf", b"not a PDF", "application/pdf")},
    )
    assert invalid_pdf.status_code == 422
    assert client.get("/api/profile/cvs", headers=headers).json() == []


def test_only_two_cv_slots_are_available(client):
    headers = register_and_login(client)
    response = client.post(
        "/api/profile/cvs/3",
        headers=headers,
        files={"file": ("resume.docx", make_docx_bytes("Experience"), "application/octet-stream")},
    )
    assert response.status_code == 422


def test_exact_duplicate_profile_evidence_retains_both_sources(
    client, tmp_path, monkeypatch
):
    settings = SimpleNamespace(
        upload_dir=str(tmp_path), max_upload_size_bytes=10 * 1024 * 1024
    )
    monkeypatch.setattr("app.services.cv_storage.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.profile.get_settings", lambda: settings)
    headers = register_and_login(client)
    source = make_docx_bytes("Skills", "Python, SQL and Django")
    for slot in (1, 2):
        response = client.post(
            f"/api/profile/cvs/{slot}",
            headers=headers,
            files={"file": (f"cv-{slot}.docx", source, "application/octet-stream")},
        )
        assert response.status_code == 201, response.text

    profile = client.get("/api/profile", headers=headers).json()
    skill = profile["candidate_data"]["skills"][0]
    assert skill["source_slots"] == [1, 2]
    assert len(skill["source_version_ids"]) == 2
    assert any("appear in both current CVs" in flag for flag in profile["review_flags"])


def test_upload_size_limit_is_enforced(client, tmp_path, monkeypatch):
    settings = SimpleNamespace(upload_dir=str(tmp_path), max_upload_size_bytes=32)
    monkeypatch.setattr("app.services.cv_storage.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.profile.get_settings", lambda: settings)
    headers = register_and_login(client)
    response = client.post(
        "/api/profile/cvs/1",
        headers=headers,
        files={"file": ("large.docx", b"x" * 33, "application/octet-stream")},
    )
    assert response.status_code == 413


def test_verification_generation_revocation_and_owned_history(
    client, tmp_path, monkeypatch, db_session
):
    from app.models import AuditLog

    settings = SimpleNamespace(
        upload_dir=str(tmp_path), max_upload_size_bytes=10 * 1024 * 1024
    )
    monkeypatch.setattr("app.services.cv_storage.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.profile.get_settings", lambda: settings)
    headers = register_and_login(client)
    stranger = register_and_login(client, "stranger@example.com")
    source = make_docx_bytes(
        "Applicant", "Experience", "Python Developer, Example Co, 2020-2024",
        "Personal Projects", "Personal Django app", "Skills", "Python, Django",
    )
    upload = client.post(
        "/api/profile/cvs/1", headers=headers,
        files={"file": ("source.docx", source, "application/octet-stream")},
    ).json()["current"]
    version_id = upload["id"]
    verify_url = f"/api/profile/versions/{version_id}/verify"
    payload = {"job_title": "Python Developer", "job_description": "Python and Django backend applications"}
    assert client.post("/api/documents/cvs", headers=headers, json=payload).status_code == 422
    assert client.post(
        verify_url, headers=headers,
        json={"source_sha256": upload["sha256"], "confirmed": False},
    ).status_code == 422
    assert client.post(
        verify_url, headers=headers,
        json={"source_sha256": upload["sha256"], "confirmed": 1},
    ).status_code == 422
    assert client.post(
        verify_url, headers=headers,
        json={"source_sha256": "0" * 64, "confirmed": True},
    ).status_code == 409
    assert client.post(
        verify_url, headers=stranger,
        json={"source_sha256": upload["sha256"], "confirmed": True},
    ).status_code == 404
    verified = client.post(
        verify_url, headers=headers,
        json={"source_sha256": upload["sha256"], "confirmed": True},
    )
    assert verified.status_code == 200
    assert verified.json()["verified_at"]
    profile = client.get("/api/profile", headers=headers).json()
    assert profile["candidate_data"]["employment_history"][0]["verified"] is True
    created = client.post("/api/documents/cvs", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    doc = created.json()
    assert doc["source_version_id"] == version_id
    assert "pdf_content" not in doc
    history = client.get("/api/documents/cvs", headers=headers).json()
    assert history[0]["id"] == doc["id"]
    assert client.get("/api/documents/cvs", headers=stranger).json() == []
    download = f"/api/documents/cvs/{doc['id']}/download"
    assert client.get(download + "/pdf", headers=stranger).status_code == 404
    assert client.get(download + "/pdf", headers=headers).content.startswith(b"%PDF-")
    exported_docx = client.get(download + "/docx", headers=headers)
    assert exported_docx.content.startswith(b"PK")
    assert exported_docx.headers["cache-control"] == "no-store"
    assert client.get(download + "/txt", headers=headers).status_code == 422
    revoked = client.delete(
        f"/api/profile/versions/{version_id}/verification", headers=headers
    )
    assert revoked.status_code == 204
    audit_actions = {item.action for item in db_session.query(AuditLog).all()}
    assert audit_actions == {
        "cv_source_verified", "cv_documents_generated", "cv_verification_revoked"
    }
    assert client.get(download + "/pdf", headers=headers).status_code == 409
    profile = client.get("/api/profile", headers=headers).json()
    assert profile["candidate_data"]["employment_history"][0]["verified"] is False
    assert client.delete("/api/profile/cvs/1", headers=headers).status_code == 204
    assert client.get("/api/documents/cvs", headers=headers).json() == []
    assert client.get(download + "/pdf", headers=headers).status_code == 404


def test_replacement_requires_fresh_verification(client, tmp_path, monkeypatch):
    settings = SimpleNamespace(
        upload_dir=str(tmp_path), max_upload_size_bytes=10 * 1024 * 1024
    )
    monkeypatch.setattr("app.services.cv_storage.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.profile.get_settings", lambda: settings)
    headers = register_and_login(client)
    source = make_docx_bytes("Experience", "Python developer")

    def upload():
        return client.post(
            "/api/profile/cvs/1", headers=headers,
            files={"file": ("source.docx", source, "application/octet-stream")},
        ).json()["current"]

    original = upload()
    assert client.post(
        f"/api/profile/versions/{original['id']}/verify", headers=headers,
        json={"source_sha256": original["sha256"], "confirmed": True},
    ).status_code == 200
    replacement = upload()
    assert replacement["verified_at"] is None
    assert client.post(
        f"/api/profile/versions/{original['id']}/verify", headers=headers,
        json={"source_sha256": original["sha256"], "confirmed": True},
    ).status_code == 409
    assert client.post(
        "/api/documents/cvs", headers=headers,
        json={"job_title": "Python", "job_description": "Python developer for backend applications"},
    ).status_code == 422


def test_source_review_excludes_templates_preserves_history_and_invalidates_exports(
    client, tmp_path, monkeypatch, db_session
):
    from datetime import datetime, timezone
    from uuid import UUID

    from app.models import AuditLog, CVVersion, GeneratedCV
    from pypdf import PdfReader

    settings = SimpleNamespace(
        upload_dir=str(tmp_path), max_upload_size_bytes=10 * 1024 * 1024
    )
    monkeypatch.setattr("app.services.cv_storage.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.profile.get_settings", lambda: settings)
    headers = register_and_login(client)
    stranger = register_and_login(client, "stranger@example.com")
    original = make_docx_bytes(
        "Applicant", "Professional Summary", "Personal Python project",
        "Skills", "Python, SQL", "Education", "BSc Engineering, 2020",
        "hello@reallygreatsite.com", "Template sample history",
    )
    uploaded = client.post(
        "/api/profile/cvs/1", headers=headers,
        files={"file": ("source.docx", original, "application/octet-stream")},
    ).json()["current"]
    url = f"/api/profile/versions/{uploaded['id']}"
    confirmation = {"source_sha256": uploaded["sha256"], "confirmed": True}
    vacancy = {"job_title": "Python Developer", "job_description": "Python and SQL backend applications"}
    assert uploaded["quality_warnings"]
    assert client.post(url + "/verify", headers=headers, json=confirmation).status_code == 422

    # Simulate a source and export verified before quality checks were introduced.
    version = db_session.get(CVVersion, UUID(uploaded["id"]))
    version.verified_at = datetime.now(timezone.utc)
    legacy = GeneratedCV(
        source_version_id=version.id, job_title="Python", job_description="Python",
        selection_explanation="Legacy selection", matched_keywords=["python"],
        comparison=[], content_blocks=[["Template sample history"]],
        pdf_content=b"legacy", docx_content=b"legacy",
    )
    db_session.add(legacy)
    db_session.commit()
    legacy_url = f"/api/documents/cvs/{legacy.id}/download/pdf"
    assert client.get(legacy_url, headers=headers).status_code == 409
    assert client.post("/api/documents/cvs", headers=headers, json=vacancy).status_code == 422

    review = {
        "source_sha256": uploaded["sha256"], "expected_revision": 0,
        "entries": [
            {"section": "contact", "text": "Applicant", "source_lines": [1]},
            {"section": "summary", "text": "Personal Python project (not employment)", "source_lines": [3]},
            {"section": "skills", "text": "Python, SQL", "source_lines": [5]},
            {"section": "education", "text": "BSc Engineering, 2020", "source_lines": [7]},
        ],
        "excluded_source_lines": [2, 4, 6, 8, 9],
        "reason": "Checked original; excluded template examples and clarified personal project.",
    }
    assert client.post(url + "/review", headers=stranger, json=review).status_code == 404
    assert client.post(
        url + "/review", headers=headers, json={**review, "source_sha256": "0" * 64}
    ).status_code == 409
    saved = client.post(url + "/review", headers=headers, json=review)
    assert saved.status_code == 200, saved.text
    reviewed = saved.json()
    assert reviewed["review_revision"] == 1
    assert reviewed["verified_at"] is None
    assert reviewed["extracted_text"] == uploaded["extracted_text"]
    assert reviewed["quality_warnings"] == []
    assert reviewed["review_history"][0]["entries"] == review["entries"]
    assert client.get(
        "/api/profile/cvs/1/versions/1/download", headers=headers
    ).content == original
    assert client.post(url + "/review", headers=headers, json=review).status_code == 409
    assert client.post(url + "/verify", headers=headers, json=confirmation).status_code == 409
    assert client.post("/api/documents/cvs", headers=headers, json=vacancy).status_code == 422
    profile = client.get("/api/profile", headers=headers).json()["candidate_data"]
    assert profile["skills"][0]["source_review_revisions"] == {uploaded["id"]: 1}
    assert profile["skills"][0]["verified"] is False
    assert "template" not in str(profile).lower()

    assert client.post(
        url + "/verify", headers=headers, json={**confirmation, "review_revision": 1}
    ).status_code == 200
    generated = client.post("/api/documents/cvs", headers=headers, json=vacancy)
    assert generated.status_code == 201, generated.text
    result = generated.json()
    assert result["review_revision"] == 1
    assert any("owner-reviewed revision 1" in note for note in result["comparison"])
    assert any("Excluded original source lines: 2, 4, 6, 8, 9" in note for note in result["comparison"])
    preview_lines = [line for block in result["content_blocks"] for line in block]
    assert "Template sample history" not in preview_lines
    assert "Personal Python project (not employment)" in preview_lines
    download = f"/api/documents/cvs/{result['id']}/download"
    docx = Document(BytesIO(client.get(download + "/docx", headers=headers).content))
    assert [paragraph.text for paragraph in docx.paragraphs] == preview_lines
    pdf = PdfReader(BytesIO(client.get(download + "/pdf", headers=headers).content))
    pdf_text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "reallygreatsite" not in pdf_text
    assert "Personal Python project (not employment)" in pdf_text

    second_review = {**review, "expected_revision": 1, "reason": "Rechecked section ordering against original."}
    second_review["entries"] = list(reversed(review["entries"]))
    saved = client.post(url + "/review", headers=headers, json=second_review).json()
    assert saved["review_revision"] == 2
    assert saved["review_history"][0]["entries"] == review["entries"]
    assert saved["review_history"][1]["entries"] == second_review["entries"]
    assert client.get(download + "/pdf", headers=headers).status_code == 409
    assert client.post(
        url + "/verify", headers=headers, json={**confirmation, "review_revision": 1}
    ).status_code == 409
    assert client.post(
        url + "/verify", headers=headers, json={**confirmation, "review_revision": 2}
    ).status_code == 200
    for file_format in ("pdf", "docx"):
        assert client.get(download + "/" + file_format, headers=headers).status_code == 409
    assert client.get(legacy_url, headers=headers).status_code == 409
    assert db_session.query(AuditLog).filter_by(action="cv_source_review_saved").count() == 2
    history = client.get("/api/documents/cvs", headers=headers).json()
    assert len(history) == 2
    assert any(doc["review_revision"] == 1 for doc in history)


def test_review_requires_complete_unique_source_line_accounting(
    client, tmp_path, monkeypatch
):
    settings = SimpleNamespace(
        upload_dir=str(tmp_path), max_upload_size_bytes=10 * 1024 * 1024
    )
    monkeypatch.setattr("app.services.cv_storage.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.profile.get_settings", lambda: settings)
    headers = register_and_login(client)
    original = make_docx_bytes("Skills", "Python")
    uploaded = client.post(
        "/api/profile/cvs/1", headers=headers,
        files={"file": ("source.docx", original, "application/octet-stream")},
    ).json()["current"]
    url = f"/api/profile/versions/{uploaded['id']}"
    payload = {
        "source_sha256": uploaded["sha256"], "expected_revision": 0,
        "entries": [{"section": "skills", "text": "Python", "source_lines": [2]}],
        "excluded_source_lines": [1], "reason": "Checked the original.",
    }
    invalid_payloads = [
        {**payload, "excluded_source_lines": []},
        {**payload, "excluded_source_lines": [1, 2]},
        {**payload, "excluded_source_lines": [1, 999]},
        {**payload, "excluded_source_lines": [0, 1]},
        {**payload, "entries": []},
        {**payload, "reason": " "},
        {**payload, "entries": [{"section": "unsupported", "text": "Python", "source_lines": [2]}]},
        {**payload, "entries": [{"section": "skills", "text": " ", "source_lines": [2]}]},
    ]
    for invalid in invalid_payloads:
        rejected = client.post(url + "/review", headers=headers, json=invalid)
        assert rejected.status_code == 422, rejected.text
    assert client.get("/api/profile/cvs", headers=headers).json()[0]["versions"][0]["review_revision"] == 0
    # Saving does not imply approval and cannot bypass unresolved hard findings.
    unsafe = {**payload, "entries": [
        {"section": "skills", "text": "Python hello@reallygreatsite.com", "source_lines": [2]}
    ]}
    assert client.post(url + "/review", headers=headers, json=unsafe).status_code == 200
    assert client.post(
        url + "/verify", headers=headers,
        json={"source_sha256": uploaded["sha256"], "review_revision": 1, "confirmed": True},
    ).status_code == 422
    # Replacing a source preserves history but disallows editing old versions.
    replacement = client.post(
        "/api/profile/cvs/1", headers=headers,
        files={"file": ("source.docx", original, "application/octet-stream")},
    ).json()["current"]
    assert replacement["review_revision"] == 0
    assert replacement["review_history"] == []
    assert client.post(
        url + "/review", headers=headers, json={**payload, "expected_revision": 1}
    ).status_code == 409
