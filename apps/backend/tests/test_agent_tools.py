from agent_tools.file_io import write_document, read_document


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
