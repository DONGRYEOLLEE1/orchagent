from prompt_kit.prompts import (
    CODING_TEAM_SUPERVISOR_PROMPT,
    DATA_SCIENCE_TEAM_SUPERVISOR_PROMPT,
    RESEARCH_TEAM_SUPERVISOR_PROMPT,
    SYSTEM_SUPERVISOR_PROMPT,
    TEAM_SUPERVISOR_PROMPT,
)


def test_head_prompt_contains_required_first_route_contracts() -> None:
    prompt = SYSTEM_SUPERVISOR_PROMPT.template

    required_fragments = [
        "# REQUIRED FIRST ROUTES",
        "Data attachment",
        "`data_science_team`",
        "`data_engineer`",
        "`data_analyst`",
        "Image attachment",
        "`vision_team`",
        "`vision_analyst`",
        "Current events, news, or \"latest\"",
        "`research_team`",
        "`search`",
        "`web_scraper`",
        "Bound repository plus code",
        "`coding_team`",
        "`codebase_explorer`",
        "`implementation_engineer`",
        "`runtime_verifier`",
        "Explicit report",
        "`writing_team`",
        "`note_taker`",
        "`doc_writer`",
        "Simple greetings",
        "`FINISH`",
        "`content`",
    ]

    for fragment in required_fragments:
        assert fragment in prompt


def test_team_prompt_contains_generic_worker_handoff_contracts() -> None:
    prompt = TEAM_SUPERVISOR_PROMPT.template

    assert "# DATA SCIENCE TEAM HANDOFF" in prompt
    assert "next worker is ALWAYS `data_analyst`" in prompt
    assert "# WRITING TEAM HANDOFF" in prompt
    assert "Start a new report" in prompt
    assert "route to `doc_writer`" in prompt
    assert "# VISION TEAM HANDOFF" in prompt
    assert "Start image-attachment requests with `vision_analyst`" in prompt


def test_dedicated_team_prompts_pin_first_workers() -> None:
    assert "Start with `search`" in RESEARCH_TEAM_SUPERVISOR_PROMPT.template
    assert "Start with `data_engineer`" in DATA_SCIENCE_TEAM_SUPERVISOR_PROMPT.template
    assert "Start with `codebase_explorer`" in CODING_TEAM_SUPERVISOR_PROMPT.template
