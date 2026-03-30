from prompt_kit.prompts import (
    RESEARCH_TEAM_SUPERVISOR_PROMPT,
    SEARCH_WORKER_PROMPT,
    WEB_SCRAPER_PROMPT,
)


def test_search_worker_prompt_emphasizes_recency_and_source_quality():
    prompt = SEARCH_WORKER_PROMPT.template

    assert "publication date" in prompt or "publish date" in prompt
    assert "primary sources" in prompt
    assert "Do not treat search snippets alone as conclusive evidence" in prompt
    assert "Do not claim you scraped page contents" in prompt


def test_web_scraper_prompt_emphasizes_page_body_grounding():
    prompt = WEB_SCRAPER_PROMPT.template

    assert "Work only from concrete URLs" in prompt
    assert "actual page body" in prompt
    assert "lacks publish dates" in prompt
    assert "instead of guessing" in prompt


def test_research_team_supervisor_prompt_allows_early_finish_with_reliable_search():
    prompt = RESEARCH_TEAM_SUPERVISOR_PROMPT.template

    assert "Start with `search`" in prompt
    assert "you may FINISH without calling `web_scraper`" in prompt
    assert "Do not call `web_scraper` first" in prompt
