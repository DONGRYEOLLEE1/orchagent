from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from langchain_core.tools import tool

from agent_tools.runtime import get_tool_runtime_context, register_runtime_artifact


MAX_TEXT_CHARS = 12000
ALLOWED_COMMAND_PREFIXES = {
    "pytest",
    "uv",
    "python",
    "python3",
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "node",
}
DISALLOWED_SHELL_TOKENS = {"&&", "||", ";", "|", ">", ">>", "<", "$(", "`"}


def _truncate_text(value: str, *, limit: int = MAX_TEXT_CHARS) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n...(truncated)"


def _workspace_root() -> Path:
    return get_tool_runtime_context().workspace_dir.resolve()


def _log_root() -> Path:
    context = get_tool_runtime_context()
    if context.log_dir is not None:
        return context.log_dir.resolve()
    return context.artifact_dir.resolve()


def _resolve_repo_path(relative_path: str) -> Path:
    candidate = (_workspace_root() / relative_path).resolve()
    if not str(candidate).startswith(str(_workspace_root())):
        raise ValueError("Path must stay within the current repository workspace.")
    return candidate


def _line_numbered(lines: list[str], start_line: int) -> str:
    return "".join(
        f"{index + start_line:>4}: {line}" for index, line in enumerate(lines)
    )


def _write_log_file(name_hint: str, content: str) -> str:
    log_root = _log_root()
    log_root.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name_hint)
    log_path = log_root / f"{safe_name}_{uuid.uuid4().hex[:8]}.log"
    log_path.write_text(content)
    register_runtime_artifact(
        file_path=log_path,
        title=f"{name_hint} log",
        kind="artifact",
        mime_type="text/plain",
    )
    return str(log_path)


def _run_subprocess(args: list[str]) -> dict:
    command_label = " ".join(args)
    try:
        result = subprocess.run(
            args,
            cwd=str(_workspace_root()),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        return {
            "success": False,
            "exit_code": None,
            "stdout": "",
            "stderr": f"Required command not found: {args[0]}",
            "log_file": None,
            "command": command_label,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": None,
            "stdout": "",
            "stderr": f"Command timed out after 180s: {command_label}",
            "log_file": None,
            "command": command_label,
        }

    log_file = _write_log_file(
        args[0],
        f"$ {command_label}\n\n[stdout]\n{result.stdout}\n\n[stderr]\n{result.stderr}",
    )
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": _truncate_text(result.stdout or ""),
        "stderr": _truncate_text(result.stderr or ""),
        "log_file": log_file,
        "command": command_label,
    }


@tool
def list_repo_tree(
    relative_path: str = ".",
    max_depth: int = 2,
    max_entries: int = 200,
) -> str:
    """List repository files and directories within the current workspace."""
    root = _resolve_repo_path(relative_path)
    if not root.exists():
        return f"Path not found: {relative_path}"

    lines: list[str] = []
    root_depth = len(root.parts)
    for current_root, dirs, files in os.walk(root):
        depth = len(Path(current_root).parts) - root_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        indent = "  " * depth
        current_path = Path(current_root)
        label = "." if current_path == root else current_path.name
        lines.append(f"{indent}{label}/")
        for file_name in sorted(files):
            lines.append(f"{indent}  {file_name}")
        if len(lines) >= max_entries:
            lines.append("... truncated")
            break
    return "\n".join(lines)


@tool
def search_repo(
    query: str,
    relative_path: str = ".",
    max_results: int = 50,
) -> str:
    """Search for text across repository files."""
    root = _resolve_repo_path(relative_path)
    if shutil.which("rg"):
        result = subprocess.run(
            ["rg", "-n", "-S", query, str(root)],
            capture_output=True,
            text=True,
            cwd=str(_workspace_root()),
        )
        text = result.stdout or result.stderr or ""
        lines = text.splitlines()[:max_results]
        if len(text.splitlines()) > max_results:
            lines.append("... truncated")
        return "\n".join(lines) if lines else "No matches found."

    matches: list[str] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text()
        except Exception:
            continue
        for index, line in enumerate(content.splitlines(), start=1):
            if query in line:
                rel = file_path.relative_to(_workspace_root())
                matches.append(f"{rel}:{index}:{line}")
                if len(matches) >= max_results:
                    matches.append("... truncated")
                    return "\n".join(matches)
    return "\n".join(matches) if matches else "No matches found."


@tool
def read_repo_file(
    file_path: str,
    start_line: int = 1,
    end_line: int = 200,
) -> str:
    """Read a repository file with line numbers."""
    target = _resolve_repo_path(file_path)
    if not target.exists() or not target.is_file():
        return f"File not found: {file_path}"
    lines = target.read_text().splitlines(keepends=True)
    start = max(start_line - 1, 0)
    end = max(end_line, start_line)
    return _line_numbered(lines[start:end], start + 1)


@tool
def apply_patch_edit(
    file_path: str,
    old_text: str,
    new_text: str,
) -> dict:
    """Replace one exact snippet in a repository file."""
    target = _resolve_repo_path(file_path)
    if not target.exists() or not target.is_file():
        return {"success": False, "message": f"File not found: {file_path}"}

    content = target.read_text()
    if old_text not in content:
        return {"success": False, "message": "Target snippet was not found in the file."}

    updated = content.replace(old_text, new_text, 1)
    target.write_text(updated)
    return {
        "success": True,
        "file_path": str(target.relative_to(_workspace_root())),
        "message": "Snippet replaced successfully.",
    }


@tool
def create_repo_file(
    file_path: str,
    content: str,
    overwrite: bool = False,
) -> dict:
    """Create a new file inside the repository workspace."""
    target = _resolve_repo_path(file_path)
    if target.exists() and not overwrite:
        return {"success": False, "message": "File already exists. Set overwrite=true to replace it."}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {
        "success": True,
        "file_path": str(target.relative_to(_workspace_root())),
        "message": "File written successfully.",
    }


@tool
def run_repo_command(command: str) -> dict:
    """Run an allowlisted repository command such as tests, lint, build, or dev server."""
    if any(token in command for token in DISALLOWED_SHELL_TOKENS):
        return {"success": False, "message": "Shell metacharacters are not allowed."}

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return {"success": False, "message": f"Invalid command: {exc}"}

    if not args:
        return {"success": False, "message": "Command is required."}
    if args[0] not in ALLOWED_COMMAND_PREFIXES:
        return {
            "success": False,
            "message": f"Command prefix '{args[0]}' is not allowed.",
        }

    return _run_subprocess(args)


@tool
def git_status() -> dict:
    """Return git status for the current repository workspace."""
    return _run_subprocess(["git", "status", "--short"])


@tool
def git_diff() -> dict:
    """Return git diff for the current repository workspace."""
    return _run_subprocess(["git", "diff"])


@tool
def git_log(limit: int = 5) -> dict:
    """Return recent git commits for the current repository workspace."""
    return _run_subprocess(["git", "log", f"-{max(limit, 1)}", "--oneline"])


@tool
def verify_local_page(url: str, expected_text: str = "") -> dict:
    """Fetch a localhost URL and optionally verify that specific text is present."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return {"success": False, "message": "Only localhost URLs are allowed."}

    try:
        with urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8", errors="ignore")
            body_excerpt = _truncate_text(body, limit=4000)
            return {
                "success": expected_text in body if expected_text else True,
                "status_code": getattr(response, "status", None),
                "expected_text_found": expected_text in body if expected_text else None,
                "body_excerpt": body_excerpt,
            }
    except Exception as exc:
        return {"success": False, "message": str(exc)}
