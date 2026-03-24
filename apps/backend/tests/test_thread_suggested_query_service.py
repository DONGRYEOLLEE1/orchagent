from services.thread_suggested_query_service import ThreadSuggestedQueryService


def test_normalize_suggestions_dedupes_and_limits():
    suggestions = ThreadSuggestedQueryService.normalize_suggestions(
        [
            '  RoPE와 ALiBi 차이도 비교해줘  ',
            'RoPE와 ALiBi 차이도 비교해줘',
            '"대표 후속 연구 흐름도 정리해줘"',
            '실제 적용 장단점만 따로 설명해줘.',
            '너무 긴 질문입니다 ' + ('a' * 80),
            '',
        ]
    )

    assert suggestions[:3] == [
        'RoPE와 ALiBi 차이도 비교해줘',
        '대표 후속 연구 흐름도 정리해줘',
        '실제 적용 장단점만 따로 설명해줘',
    ]
    assert len(suggestions) == 4
    assert all(len(item) <= ThreadSuggestedQueryService.MAX_QUERY_LENGTH for item in suggestions)
