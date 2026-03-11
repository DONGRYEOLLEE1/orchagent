from collections.abc import Mapping
from typing import Any, Literal, TypedDict

from langgraph.graph import MessagesState
from typing_extensions import Annotated


StreamingStatus = Literal["idle", "running", "completed", "errored"]


class RouteEntry(TypedDict, total=False):
    layer: Literal["head", "team", "worker", "tool"]
    node: str
    next: str
    team: str
    worker: str
    status: StreamingStatus


def merge_state_maps(
    left: Mapping[str, Any] | None, right: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Recursively merge structured state maps while letting right-hand values win."""
    merged = dict(left or {})

    for key, value in dict(right or {}).items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = merge_state_maps(existing, value)
        else:
            merged[key] = value

    return merged


def append_route_history(
    left: list[RouteEntry] | None, right: list[RouteEntry] | None
) -> list[RouteEntry]:
    """Keep the full routing timeline across graph, team, and worker hops."""
    return [*(left or []), *(right or [])]


def normalize_team_name(team_name: str | None) -> str | None:
    if not team_name:
        return None

    normalized = team_name
    if normalized.endswith("_team"):
        normalized = normalized[: -len("_team")]
    elif normalized.endswith("Team"):
        normalized = normalized[: -len("Team")]

    return normalized.lower()


def build_route_entry(
    *,
    layer: Literal["head", "team", "worker", "tool"],
    node: str,
    next_node: str,
    team: str | None = None,
    worker: str | None = None,
    status: StreamingStatus | None = None,
) -> RouteEntry:
    entry: RouteEntry = {"layer": layer, "node": node, "next": next_node}
    if team:
        entry["team"] = team
    if worker:
        entry["worker"] = worker
    if status:
        entry["status"] = status
    return entry


class BaseAgentState(MessagesState):
    next: str
    shared_context: Annotated[dict[str, Any], merge_state_maps]
    artifacts: Annotated[dict[str, Any], merge_state_maps]
    route_history: Annotated[list[RouteEntry], append_route_history]
    active_team: str | None
    active_worker: str | None
    streaming_status: StreamingStatus
