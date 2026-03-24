from sqlalchemy import create_mock_engine

import models  # noqa: F401
from core.database import Base
from models.analytics import ChatTurn, LLMUsageEvent, LLMPricingSnapshot, ToolExecutionEvent
from models.trace import TraceEvent


def test_analytics_tables_registered_in_metadata():
    table_names = set(Base.metadata.tables.keys())

    assert "chat_turns" in table_names
    assert "llm_usage_events" in table_names
    assert "tool_execution_events" in table_names
    assert "llm_pricing_snapshots" in table_names
    assert "user_daily_usage_rollups" in table_names


def test_trace_event_columns_extended_for_turn_and_span_keys():
    columns = TraceEvent.__table__.c

    assert "user_id" in columns
    assert "turn_id" in columns
    assert "seq" in columns
    assert "run_id" in columns
    assert "trace_id" in columns
    assert "span_id" in columns
    assert "parent_span_id" in columns


def test_analytics_tables_compile_with_postgres_dialect():
    emitted_sql: list[str] = []
    engine = create_mock_engine(
        "postgresql://",
        lambda sql, *args, **kwargs: emitted_sql.append(
            str(sql.compile(dialect=engine.dialect))
        ),
    )

    Base.metadata.create_all(engine, checkfirst=False)

    ddl = "\n".join(emitted_sql)
    assert "CREATE TABLE chat_turns" in ddl
    assert "CREATE TABLE llm_usage_events" in ddl
    assert "CREATE TABLE tool_execution_events" in ddl
    assert "CREATE TABLE llm_pricing_snapshots" in ddl


def test_analytics_models_expose_expected_cost_and_latency_columns():
    turn_columns = ChatTurn.__table__.c
    usage_columns = LLMUsageEvent.__table__.c
    pricing_columns = LLMPricingSnapshot.__table__.c
    tool_columns = ToolExecutionEvent.__table__.c

    assert "latency_ms" in turn_columns
    assert "ttft_ms" in turn_columns
    assert "reasoning_output_tokens" in usage_columns
    assert "estimated_reasoning_cost_microusd" in usage_columns
    assert "is_estimated" in pricing_columns
    assert "duration_ms" in tool_columns
