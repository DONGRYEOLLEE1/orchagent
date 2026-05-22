from agent_core.state import merge_state_maps


def test_merge_state_maps_recursively_merges_nested_context():
    """``merge_state_maps`` is the non-trivial Annotated reducer behind shared_context
    fan-in — verify it deep-merges instead of last-write-wins overwriting."""
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
