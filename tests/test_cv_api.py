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
