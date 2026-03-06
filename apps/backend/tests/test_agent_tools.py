import pytest
from pathlib import Path
from agent_tools.file_io import write_document, read_document

def test_file_io_tools(monkeypatch, tmp_path):
    """Test file writing and reading tools in a sandboxed temporary directory."""
    
    # 1. Redirect WORKING_DIRECTORY to a safe tmp_path managed by pytest
    monkeypatch.setattr("agent_tools.file_io.WORKING_DIRECTORY", tmp_path)
    
    file_name = "test_doc.txt"
    content_to_write = "This is a mock research result."
    
    # 2. Test Write Document
    write_result = write_document.invoke({"content": content_to_write, "file_name": file_name})
    assert "saved to" in write_result
    assert (tmp_path / file_name).exists()
    
    # 3. Test Read Document
    read_result = read_document.invoke({"file_name": file_name})
    assert read_result == content_to_write

def test_read_document_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_tools.file_io.WORKING_DIRECTORY", tmp_path)
    read_result = read_document.invoke({"file_name": "non_existent.txt"})
    assert "Error: File" in read_result
