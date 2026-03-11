from agent_core.state import (
    append_route_history,
    build_route_entry,
    merge_state_maps,
    normalize_team_name,
)


def test_merge_state_maps_recursively_merges_nested_context():
    left = {
        "research": {
            "query": "latest ai chips",
            "facts": {"vendors": ["nvidia"]},
        }
    }
    right = {
        "research": {
            "summary": "Found updated vendor landscape.",
            "facts": {"markets": ["usa"]},
        },
        "vision": {"enabled": True},
    }

    merged = merge_state_maps(left, right)

    assert merged["research"]["query"] == "latest ai chips"
    assert merged["research"]["summary"] == "Found updated vendor landscape."
    assert merged["research"]["facts"] == {
        "vendors": ["nvidia"],
        "markets": ["usa"],
    }
    assert merged["vision"]["enabled"] is True


def test_append_route_history_preserves_full_timeline():
    history = append_route_history(
        [build_route_entry(layer="head", node="head_supervisor", next_node="research_team")],
        [build_route_entry(layer="team", node="supervisor", next_node="search", team="research", worker="search")],
    )

    assert len(history) == 2
    assert history[0]["layer"] == "head"
    assert history[1]["worker"] == "search"


def test_normalize_team_name_handles_graph_and_builder_names():
    assert normalize_team_name("research_team") == "research"
    assert normalize_team_name("ResearchTeam") == "research"
    assert normalize_team_name(None) is None
