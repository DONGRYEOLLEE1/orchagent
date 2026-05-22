import json

import pandas as pd
import pytest
from docx import Document

from agent_tools.data import (
    extract_document_text,
    inspect_attachments,
    preview_tabular_file,
    profile_dataframe,
    python_repl_data_tool,
    register_analysis_artifact,
)
from agent_tools.file_io import write_document, read_document
from agent_tools.web import scrape_webpages
from agent_tools.runtime import (
    ToolAttachment,
    ToolRuntimeContext,
    collect_runtime_artifacts,
    reset_tool_runtime_context,
    set_tool_runtime_context,
)


def test_file_io_tools_round_trip(monkeypatch, tmp_path):
    """write_document → read_document round-trip inside a sandboxed dir."""
    monkeypatch.setattr("agent_tools.file_io.WORKING_DIRECTORY", tmp_path)

    write_result = write_document.invoke(
        {"content": "This is a mock research result.", "file_name": "doc.txt"}
    )
    assert "saved to" in write_result
    assert (tmp_path / "doc.txt").exists()

    assert read_document.invoke({"file_name": "doc.txt"}) == "This is a mock research result."
    assert "Error: File" in read_document.invoke({"file_name": "missing.txt"})


@pytest.mark.asyncio
async def test_scrape_webpages_uses_requests_and_bs4_without_event_loop_errors(monkeypatch):
    class DummyResponse:
        text = "<html><head><title>Example Title</title></head><body><h1>Hello</h1></body></html>"
        headers = {"content-type": "text/html; charset=utf-8"}

        def raise_for_status(self):
            return None

    class DummySession:
        def __init__(self):
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, timeout):
            return DummyResponse()

    monkeypatch.setattr("agent_tools.web.requests.Session", DummySession)

    content = await scrape_webpages.ainvoke({"urls": ["https://example.com"]})

    assert '<Document name="Example Title" url="https://example.com">' in content
    assert "Hello" in content


def test_vision_tools_with_dummy_image():
    """vision tools must accept a base64 image and emit metadata / resized output."""
    import base64
    import io
    from PIL import Image
    from agent_tools.vision import get_image_metadata, resize_image

    img = Image.new("RGB", (100, 100), color="red")
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    dummy_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    meta_result = get_image_metadata.invoke({"base64_image": dummy_base64})
    assert "JPEG" in meta_result
    assert "100, 100" in meta_result

    resize_result = resize_image.invoke(
        {"base64_image": dummy_base64, "max_width": 50, "max_height": 50}
    )
    assert "successfully resized to (50, 50)" in resize_result


def _make_runtime(tmp_path, attachments):
    return set_tool_runtime_context(
        ToolRuntimeContext(
            thread_id="thread-1",
            user_id="user-1",
            attachments=attachments,
            workspace_dir=tmp_path / "workspace",
            artifact_dir=tmp_path / "artifacts",
        )
    )


def test_data_tools_inspect_preview_and_profile(tmp_path):
    """inspect_attachments / preview_tabular_file / profile_dataframe pipeline on CSV."""
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("month,revenue\nJan,10\nFeb,20\n", encoding="utf-8")

    token = _make_runtime(
        tmp_path,
        {
            "att-1": ToolAttachment(
                id="att-1",
                kind="csv",
                file_name="sales.csv",
                mime_type="text/csv",
                size_bytes=csv_path.stat().st_size,
                storage_path=str(csv_path),
            )
        },
    )
    try:
        manifest = json.loads(inspect_attachments.invoke({}))
        assert manifest["attachments"][0]["id"] == "att-1"

        preview = json.loads(preview_tabular_file.invoke({"attachment_id": "att-1", "rows": 2}))
        assert preview["columns"] == ["month", "revenue"]

        profile = json.loads(profile_dataframe.invoke({"attachment_id": "att-1"}))
        assert profile["row_count"] == 2
    finally:
        reset_tool_runtime_context(token)


def test_extract_document_text_reads_docx(tmp_path):
    """docx attachments must extract paragraph text into ``text_excerpt``."""
    docx_path = tmp_path / "brief.docx"
    document = Document()
    document.add_paragraph("Quarterly performance summary")
    document.save(docx_path)

    token = _make_runtime(
        tmp_path,
        {
            "doc-1": ToolAttachment(
                id="doc-1",
                kind="docx",
                file_name="brief.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                size_bytes=docx_path.stat().st_size,
                storage_path=str(docx_path),
            )
        },
    )
    try:
        extracted = json.loads(extract_document_text.invoke({"attachment_id": "doc-1"}))
        assert "Quarterly performance summary" in extracted["text_excerpt"]
    finally:
        reset_tool_runtime_context(token)


def test_extract_document_text_warns_for_image_based_pdf(tmp_path):
    """PDFs whose pages are images (no extractable text) must surface a warning."""
    from PIL import Image, ImageDraw

    pdf_path = tmp_path / "scanned-like.pdf"
    image = Image.new("RGB", (400, 180), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 70), "Revenue Notes", fill="black")
    image.save(pdf_path, "PDF")

    token = _make_runtime(
        tmp_path,
        {
            "pdf-2": ToolAttachment(
                id="pdf-2",
                kind="pdf",
                file_name="scanned-like.pdf",
                mime_type="application/pdf",
                size_bytes=pdf_path.stat().st_size,
                storage_path=str(pdf_path),
            )
        },
    )
    try:
        extracted = json.loads(extract_document_text.invoke({"attachment_id": "pdf-2"}))
        assert extracted["warning"] is not None
    finally:
        reset_tool_runtime_context(token)


def test_python_repl_data_tool_registers_generated_artifacts(tmp_path):
    """REPL tool must auto-register files written to artifact_path()."""
    csv_path = tmp_path / "trend.csv"
    pd.DataFrame({"x": [1, 2, 3], "y": [3, 5, 8]}).to_csv(csv_path, index=False)

    token = _make_runtime(
        tmp_path,
        {
            "csv-1": ToolAttachment(
                id="csv-1",
                kind="csv",
                file_name="trend.csv",
                mime_type="text/csv",
                size_bytes=csv_path.stat().st_size,
                storage_path=str(csv_path),
            )
        },
    )
    try:
        result = json.loads(
            python_repl_data_tool.invoke(
                {
                    "code": "\n".join(
                        [
                            "df = load_dataframe('csv-1')",
                            "ax = df.plot(x='x', y='y')",
                            "plt.tight_layout()",
                            "plt.savefig(artifact_path('trend.png'))",
                        ]
                    )
                }
            )
        )
        assert "trend.png" in result["generated_files"]
        artifacts = collect_runtime_artifacts()
        assert any(artifact.file_name == "trend.png" for artifact in artifacts)
    finally:
        reset_tool_runtime_context(token)


def test_register_analysis_artifact_reuses_latest_registered_artifact(tmp_path):
    """register_analysis_artifact must dedupe by basename even when given a longer path."""
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    token = _make_runtime(tmp_path, {})
    try:
        result = json.loads(
            python_repl_data_tool.invoke(
                {
                    "code": "\n".join(
                        [
                            "from pathlib import Path",
                            "target = Path(artifact_path('sales_trend_chart.png'))",
                            "target.write_bytes(b'png')",
                        ]
                    )
                }
            )
        )
        assert "sales_trend_chart.png" in result["registered_artifacts"]

        reused = json.loads(
            register_analysis_artifact.invoke(
                {
                    "file_name": "apps/backend/data/uploads/analysis/thread-x/artifacts/sales_trend_chart.png",
                    "title": "sales trend chart",
                }
            )
        )
        assert reused["status"] in {"registered", "registered_existing"}
    finally:
        reset_tool_runtime_context(token)
