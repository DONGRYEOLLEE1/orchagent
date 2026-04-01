from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_bind_repository_route_returns_binding(monkeypatch):
    async def fake_bind_repository(db, *, user_id, thread_id, source_type, source_ref):
        return SimpleNamespace(
            id="binding-1",
            thread_id=thread_id,
            source_type=source_type,
            source_ref=source_ref,
            display_name="sample-repo",
            default_branch="main",
            pinned_commit_sha=None,
            status="active",
            created_at=None,
            updated_at=None,
        )

    monkeypatch.setattr(
        "api.routes.repositories.RepositoryBindingService.bind_repository",
        fake_bind_repository,
    )

    response = client.post(
        "/api/repositories/bind",
        json={
            "thread_id": "thread-1",
            "source_type": "github_url",
            "source_ref": "https://github.com/example/sample-repo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["binding"]["id"] == "binding-1"
    assert payload["binding"]["thread_id"] == "thread-1"
    assert payload["binding"]["source_type"] == "github_url"
    assert payload["binding"]["display_name"] == "sample-repo"


def test_bind_repository_zip_route_returns_binding(monkeypatch):
    async def fake_bind_repository_zip(db, *, user_id, thread_id, file):
        assert file.filename == "sample.zip"
        return SimpleNamespace(
            binding=SimpleNamespace(
                id="binding-zip",
                thread_id=thread_id,
                source_type="repo_zip",
                source_ref="/tmp/sample.zip",
                display_name="sample.zip",
                default_branch=None,
                pinned_commit_sha=None,
                status="active",
                created_at=None,
                updated_at=None,
            )
        )

    monkeypatch.setattr(
        "api.routes.repositories.RepositoryBindingService.bind_repository_zip",
        fake_bind_repository_zip,
    )

    response = client.post(
        "/api/repositories/bind-zip",
        data={"thread_id": "thread-zip"},
        files={"file": ("sample.zip", BytesIO(b"PK\x03\x04test"), "application/zip")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["binding"]["id"] == "binding-zip"
    assert payload["binding"]["source_type"] == "repo_zip"
    assert payload["binding"]["display_name"] == "sample.zip"
