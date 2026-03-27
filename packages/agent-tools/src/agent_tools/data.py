from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Annotated, Any

import duckdb
import numpy as np
import pandas as pd
import seaborn as sns
from docx import Document
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL
from matplotlib import pyplot as plt
from pypdf import PdfReader

from agent_tools.runtime import (
    artifact_path,
    attachment_manifest,
    collect_runtime_artifacts,
    get_tool_runtime_context,
    register_runtime_artifact,
    resolve_runtime_attachment,
)


plt.switch_backend("Agg")


def _load_dataframe(
    attachment_id: str,
    *,
    sheet_name: str | None = None,
    rows: int | None = None,
) -> pd.DataFrame:
    attachment = resolve_runtime_attachment(attachment_id)
    path = Path(attachment.storage_path)
    if attachment.kind == "csv":
        frame = pd.read_csv(path)
    elif attachment.kind == "spreadsheet":
        frame = pd.read_excel(path, sheet_name=sheet_name or 0)
    elif attachment.kind == "json":
        frame = pd.read_json(path)
    else:
        raise ValueError(f"Attachment {attachment_id} is not a tabular file.")

    if isinstance(frame, dict):
        first_key = next(iter(frame))
        frame = frame[first_key]
    if rows is not None:
        return frame.head(rows)
    return frame


def _extract_document_text_internal(attachment_id: str, max_chars: int = 6000) -> dict[str, Any]:
    attachment = resolve_runtime_attachment(attachment_id)
    path = Path(attachment.storage_path)

    if attachment.kind == "pdf":
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(len(part) for part in parts) >= max_chars:
                break
        text = "\n".join(parts)[:max_chars]
        return {
            "attachment_id": attachment_id,
            "file_name": attachment.file_name,
            "kind": attachment.kind,
            "page_count": len(reader.pages),
            "text_excerpt": text,
            "truncated": len(text) >= max_chars,
            "warning": (
                "No extractable text was found. This PDF may be scanned or image-based and may require OCR."
                if not text.strip()
                else None
            ),
        }

    if attachment.kind == "docx":
        document = Document(str(path))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        table_cells = [
            cell.text.strip()
            for table in document.tables
            for row in table.rows
            for cell in row.cells
            if cell.text.strip()
        ]
        text = "\n".join([*paragraphs, *table_cells])[:max_chars]
        return {
            "attachment_id": attachment_id,
            "file_name": attachment.file_name,
            "kind": attachment.kind,
            "paragraph_count": len(paragraphs),
            "table_cell_count": len(table_cells),
            "text_excerpt": text,
            "truncated": len(text) >= max_chars,
        }

    raise ValueError(f"Attachment {attachment_id} is not a supported document file.")


@tool
def inspect_attachments() -> str:
    """Inspect the currently attached files for this turn. Use first before deeper analysis."""
    return json.dumps({"attachments": attachment_manifest()}, ensure_ascii=False, indent=2)


@tool
def preview_tabular_file(
    attachment_id: Annotated[str, "Attachment id returned by inspect_attachments."],
    rows: Annotated[int, "How many preview rows to return."] = 8,
    sheet_name: Annotated[str | None, "Optional worksheet name for .xlsx files."] = None,
) -> str:
    """Preview a CSV/XLSX/JSON attachment. Use this before writing analysis code."""
    attachment = resolve_runtime_attachment(attachment_id)
    frame = _load_dataframe(attachment_id, sheet_name=sheet_name, rows=rows)
    available_sheets: list[str] | None = None
    if attachment.kind == "spreadsheet":
        available_sheets = pd.ExcelFile(attachment.storage_path).sheet_names
    return json.dumps(
        {
            "attachment_id": attachment_id,
            "file_name": attachment.file_name,
            "kind": attachment.kind,
            "sheet_name": sheet_name,
            "available_sheets": available_sheets,
            "columns": list(map(str, frame.columns.tolist())),
            "preview_rows": frame.replace({np.nan: None}).to_dict(orient="records"),
            "row_count_sampled": len(frame),
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


@tool
def extract_document_text(
    attachment_id: Annotated[str, "Attachment id returned by inspect_attachments."],
    max_chars: Annotated[int, "Maximum characters to return from the document."] = 6000,
) -> str:
    """Extract text from a PDF or DOCX attachment. Use when the task needs document text."""
    return json.dumps(
        _extract_document_text_internal(attachment_id, max_chars=max_chars),
        ensure_ascii=False,
        indent=2,
    )


@tool
def profile_dataframe(
    attachment_id: Annotated[str, "Attachment id returned by inspect_attachments."],
    sheet_name: Annotated[str | None, "Optional worksheet name for .xlsx files."] = None,
) -> str:
    """Profile a tabular attachment to understand schema, types, nulls, and numeric summary."""
    frame = _load_dataframe(attachment_id, sheet_name=sheet_name)
    numeric_columns = frame.select_dtypes(include=[np.number]).columns.tolist()
    missing_counts = {str(column): int(value) for column, value in frame.isna().sum().to_dict().items()}
    dtypes = {str(column): str(dtype) for column, dtype in frame.dtypes.to_dict().items()}
    distinct_counts = {
        str(column): int(frame[column].nunique(dropna=True))
        for column in frame.columns[:20]
    }
    numeric_summary = (
        frame[numeric_columns].describe().transpose().round(4).replace({np.nan: None}).to_dict(orient="index")
        if numeric_columns
        else {}
    )
    return json.dumps(
        {
            "attachment_id": attachment_id,
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "columns": list(map(str, frame.columns.tolist())),
            "dtypes": dtypes,
            "missing_counts": missing_counts,
            "distinct_counts": distinct_counts,
            "numeric_summary": numeric_summary,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _build_repl() -> PythonREPL:
    context = get_tool_runtime_context()
    workspace_dir = context.workspace_dir.resolve()
    artifact_dir = context.artifact_dir.resolve()

    def attachment_path_fn(attachment_id: str) -> str:
        return resolve_runtime_attachment(attachment_id).storage_path

    def load_dataframe_fn(attachment_id: str, sheet_name: str | None = None) -> pd.DataFrame:
        return _load_dataframe(attachment_id, sheet_name=sheet_name)

    def read_document_fn(attachment_id: str, max_chars: int = 6000) -> str:
        return _extract_document_text_internal(attachment_id, max_chars=max_chars)["text_excerpt"]

    def artifact_path_fn(file_name: str) -> str:
        return str(artifact_path(file_name))

    def register_artifact_fn(file_name: str, title: str | None = None) -> str:
        artifact = register_runtime_artifact(file_path=file_name, title=title)
        return json.dumps(
            {
                "file_name": artifact.file_name,
                "storage_path": artifact.storage_path,
                "mime_type": artifact.mime_type,
            },
            ensure_ascii=False,
        )

    globals_dict: dict[str, Any] = {
        "__name__": "__main__",
        "pd": pd,
        "np": np,
        "plt": plt,
        "sns": sns,
        "duckdb": duckdb,
        "Path": Path,
        "json": json,
        "os": os,
        "ATTACHMENTS": attachment_manifest(),
        "WORKSPACE_DIR": str(workspace_dir),
        "ARTIFACT_DIR": str(artifact_dir),
        "attachment_path": attachment_path_fn,
        "load_dataframe": load_dataframe_fn,
        "read_document_text": read_document_fn,
        "artifact_path": artifact_path_fn,
        "register_artifact": register_artifact_fn,
    }
    return PythonREPL(_globals=globals_dict, _locals={})


def _stage_attachments_for_repl() -> None:
    context = get_tool_runtime_context()

    def _materialize(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return
        try:
            destination.symlink_to(source)
        except OSError:
            shutil.copy2(source, destination)

    for attachment in attachment_manifest():
        source = Path(str(attachment["storage_path"]))
        if not source.exists() or not source.is_file():
            continue
        aliases = {source.name}
        file_name = attachment.get("file_name")
        if isinstance(file_name, str) and file_name:
            aliases.add(Path(file_name).name)

        for alias in aliases:
            _materialize(source, context.artifact_dir / alias)

        storage_path_value = str(attachment.get("storage_path") or "")
        if storage_path_value and not Path(storage_path_value).is_absolute():
            _materialize(source, context.artifact_dir / storage_path_value)


@tool
def python_repl_data_tool(
    code: Annotated[str, "Python code for data processing or visualization."],
) -> str:
    """Execute Python for dataframe analysis and chart generation in a restricted analysis workspace."""
    context = get_tool_runtime_context()
    _stage_attachments_for_repl()
    before_files = {path.name for path in context.artifact_dir.glob("*")}
    repl = _build_repl()
    prelude = f"""
import os
import socket
import urllib.request
import requests
os.chdir(r"{context.artifact_dir}")

def _disabled_network(*args, **kwargs):
    raise RuntimeError("Network access is disabled inside python_repl_data_tool.")

urllib.request.urlopen = _disabled_network
requests.get = _disabled_network
requests.post = _disabled_network
requests.put = _disabled_network
requests.delete = _disabled_network
requests.sessions.Session.request = _disabled_network
socket.create_connection = _disabled_network
"""
    normalized_code = code.replace("/mnt/data", str(context.artifact_dir))
    result = repl.run(f"{prelude}\n{normalized_code}")
    after_files = {path.name for path in context.artifact_dir.glob("*")}
    new_files = sorted(after_files - before_files)
    auto_registered: list[str] = []
    for file_name in new_files:
        artifact = register_runtime_artifact(file_path=file_name)
        auto_registered.append(artifact.file_name)

    return json.dumps(
        {
            "status": "success" if "Failed to execute" not in result else "error",
            "stdout": result,
            "generated_files": new_files,
            "registered_artifacts": auto_registered,
            "artifact_count": len(collect_runtime_artifacts()),
        },
        ensure_ascii=False,
        indent=2,
    )


@tool
def register_analysis_artifact(
    file_name: Annotated[str, "A file name relative to the current artifact workspace."],
    title: Annotated[str | None, "Optional title for the artifact."] = None,
) -> str:
    """Register an analysis output file so it can be attached to the assistant response."""
    try:
        artifact = register_runtime_artifact(file_path=file_name, title=title)
        status = "registered"
    except ValueError:
        existing_artifacts = collect_runtime_artifacts()
        if not existing_artifacts:
            raise
        artifact = existing_artifacts[-1]
        status = "registered_existing"
    return json.dumps(
        {
            "status": status,
            "file_name": artifact.file_name,
            "mime_type": artifact.mime_type,
            "storage_path": artifact.storage_path,
        },
        ensure_ascii=False,
    )
