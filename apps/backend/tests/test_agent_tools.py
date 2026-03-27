import json

import pandas as pd
from docx import Document

from agent_tools.data import (
    extract_document_text,
    inspect_attachments,
    preview_tabular_file,
    profile_dataframe,
    python_repl_data_tool,
)
from agent_tools.file_io import write_document, read_document
from agent_tools.runtime import (
    ToolAttachment,
    ToolRuntimeContext,
    collect_runtime_artifacts,
    reset_tool_runtime_context,
    set_tool_runtime_context,
)


def test_file_io_tools(monkeypatch, tmp_path):
    """Test file writing and reading tools in a sandboxed temporary directory."""

    # 1. Redirect WORKING_DIRECTORY to a safe tmp_path managed by pytest
    monkeypatch.setattr("agent_tools.file_io.WORKING_DIRECTORY", tmp_path)

    file_name = "test_doc.txt"
    content_to_write = "This is a mock research result."

    # 2. Test Write Document
    write_result = write_document.invoke(
        {"content": content_to_write, "file_name": file_name}
    )
    assert "saved to" in write_result
    assert (tmp_path / file_name).exists()

    # 3. Test Read Document
    read_result = read_document.invoke({"file_name": file_name})
    assert read_result == content_to_write


def test_read_document_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_tools.file_io.WORKING_DIRECTORY", tmp_path)
    read_result = read_document.invoke({"file_name": "non_existent.txt"})
    assert "Error: File" in read_result


def test_vision_tools_with_dummy_image():
    """Test vision metadata and resizing tools using a generated dummy image."""
    import base64
    import io
    from PIL import Image
    from agent_tools.vision import get_image_metadata, resize_image

    # 1. Create a 100x100 dummy red JPEG image in memory
    img = Image.new("RGB", (100, 100), color="red")
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    dummy_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    # 2. Test get_image_metadata
    meta_result = get_image_metadata.invoke({"base64_image": dummy_base64})
    assert "JPEG" in meta_result
    assert "100, 100" in meta_result

    # 3. Test resize_image
    resize_result = resize_image.invoke(
        {"base64_image": dummy_base64, "max_width": 50, "max_height": 50}
    )
    assert "successfully resized to (50, 50)" in resize_result


def test_data_tools_inspect_preview_and_profile(tmp_path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("month,revenue\nJan,10\nFeb,20\n", encoding="utf-8")

    token = set_tool_runtime_context(
        ToolRuntimeContext(
            thread_id="thread-1",
            user_id="user-1",
            attachments={
                "att-1": ToolAttachment(
                    id="att-1",
                    kind="csv",
                    file_name="sales.csv",
                    mime_type="text/csv",
                    size_bytes=csv_path.stat().st_size,
                    storage_path=str(csv_path),
                )
            },
            workspace_dir=tmp_path / "workspace",
            artifact_dir=tmp_path / "artifacts",
        )
    )
    try:
        manifest = json.loads(inspect_attachments.invoke({}))
        assert manifest["attachments"][0]["id"] == "att-1"

        preview = json.loads(preview_tabular_file.invoke({"attachment_id": "att-1", "rows": 2}))
        assert preview["columns"] == ["month", "revenue"]
        assert preview["preview_rows"][0]["month"] == "Jan"

        profile = json.loads(profile_dataframe.invoke({"attachment_id": "att-1"}))
        assert profile["row_count"] == 2
        assert profile["column_count"] == 2
    finally:
        reset_tool_runtime_context(token)


def test_extract_document_text_reads_docx(tmp_path):
    docx_path = tmp_path / "brief.docx"
    document = Document()
    document.add_paragraph("Quarterly performance summary")
    document.save(docx_path)

    token = set_tool_runtime_context(
        ToolRuntimeContext(
            thread_id="thread-doc",
            user_id="user-1",
            attachments={
                "doc-1": ToolAttachment(
                    id="doc-1",
                    kind="docx",
                    file_name="brief.docx",
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    size_bytes=docx_path.stat().st_size,
                    storage_path=str(docx_path),
                )
            },
            workspace_dir=tmp_path / "workspace",
            artifact_dir=tmp_path / "artifacts",
        )
    )
    try:
        extracted = json.loads(extract_document_text.invoke({"attachment_id": "doc-1"}))
        assert "Quarterly performance summary" in extracted["text_excerpt"]
    finally:
        reset_tool_runtime_context(token)


def test_python_repl_data_tool_registers_generated_artifacts(tmp_path):
    csv_path = tmp_path / "trend.csv"
    pd.DataFrame({"x": [1, 2, 3], "y": [3, 5, 8]}).to_csv(csv_path, index=False)

    token = set_tool_runtime_context(
        ToolRuntimeContext(
            thread_id="thread-chart",
            user_id="user-1",
            attachments={
                "csv-1": ToolAttachment(
                    id="csv-1",
                    kind="csv",
                    file_name="trend.csv",
                    mime_type="text/csv",
                    size_bytes=csv_path.stat().st_size,
                    storage_path=str(csv_path),
                )
            },
            workspace_dir=tmp_path / "workspace",
            artifact_dir=tmp_path / "artifacts",
        )
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
