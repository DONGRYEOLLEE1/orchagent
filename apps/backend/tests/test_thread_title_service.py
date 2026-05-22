import pytest

from services.thread_title_service import ThreadTitleResult, ThreadTitleService


def test_thread_title_service_normalize_title_enforces_one_line_and_length():
    normalized = ThreadTitleService.normalize_title(
        '  "RoPE 논문 탐색: 메인 연구자 의도 분석!!!"  ',
        fallback_message="fallback question",
    )

    assert '"' not in normalized
    assert ":" not in normalized
    assert "!" not in normalized
    assert len(normalized) <= ThreadTitleService.TITLE_MAX_LENGTH


@pytest.mark.asyncio
async def test_thread_title_service_generate_title_from_transcript(monkeypatch):
    class FakeModel:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            assert "Conversation transcript:" in messages[1]["content"]
            assert "User: JWT와 세션 쿠키 차이 설명" in messages[1]["content"]
            return ThreadTitleResult(title="JWT 인증 전략 비교")

    ThreadTitleService._get_model.cache_clear()
    monkeypatch.setattr(ThreadTitleService, "_get_model", staticmethod(lambda: FakeModel()))

    title = await ThreadTitleService.generate_title_from_transcript(
        [
            ("user", "JWT와 세션 쿠키 차이 설명"),
            ("assistant", "세션 쿠키를 추천합니다"),
        ],
        fallback_message="JWT와 세션 쿠키 차이 설명",
    )

    assert title == "JWT 인증 전략 비교"
