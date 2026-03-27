from io import BytesIO
from types import SimpleNamespace

import pytest
from starlette.datastructures import Headers, UploadFile

from services.upload_service import UploadService


@pytest.mark.asyncio
async def test_prepare_upload_batch_collects_partial_errors(monkeypatch):
    monkeypatch.setattr("services.upload_service.settings.ATTACHMENT_MAX_CSV_BYTES", 4)

    keep = UploadFile(
        filename="keep.json",
        file=BytesIO(b'{"ok":1}'),
        headers=Headers({"content-type": "application/json"}),
    )
    reject = UploadFile(
        filename="reject.csv",
        file=BytesIO(b"a,b\n1,2\n"),
        headers=Headers({"content-type": "text/csv"}),
    )

    prepared, errors, total_size_bytes = await UploadService.prepare_upload_batch(
        files=[keep, reject],
        source_type="device",
    )

    assert len(prepared) == 1
    assert prepared[0].file_name == "keep.json"
    assert total_size_bytes == len(b'{"ok":1}')
    assert len(errors) == 1
    assert errors[0].input_index == 1
    assert errors[0].file_name == "reject.csv"
    assert errors[0].error_code == "file_too_large"
    assert errors[0].detail == "CSV file exceeds 4B limit"


@pytest.mark.asyncio
async def test_register_generated_artifact_sets_generated_source_type(tmp_path):
    artifact_path = tmp_path / "chart.png"
    artifact_path.write_bytes(b"\x89PNG\r\n\x1a\nchart")

    stored_uploads = []

    class DummyDB:
        def add(self, upload):
            stored_uploads.append(upload)

        async def commit(self):
            return None

        async def refresh(self, upload):
            return None

    upload = await UploadService.register_generated_artifact(
        DummyDB(),
        user_id="user-1",
        thread_id="thread-1",
        artifact=SimpleNamespace(
            kind="image",
            file_name="chart.png",
            mime_type="image/png",
            size_bytes=artifact_path.stat().st_size,
            storage_path=str(artifact_path),
            title="Chart",
        ),
    )

    assert upload.source_type == "generated_artifact"
    assert upload.processing_status == "ready"
    assert upload.preview_status == "ready"
    assert upload.file_name == "chart.png"
    assert upload.storage_path == str(artifact_path)
    assert len(stored_uploads) == 1
