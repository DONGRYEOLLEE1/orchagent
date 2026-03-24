import uuid
from datetime import datetime

import pytz
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base

KST = pytz.timezone("Asia/Seoul")


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint("thread_id", "turn_index", name="uq_chat_turns_thread_turn_index"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    thread_id = Column(
        String, ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    turn_index = Column(Integer, nullable=False)
    request_message_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id"), nullable=True, index=True
    )
    response_message_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id"), nullable=True, index=True
    )
    request_kind = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    first_token_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    interrupted_at = Column(DateTime(timezone=True), nullable=True)
    errored_at = Column(DateTime(timezone=True), nullable=True)
    latency_ms = Column(BigInteger, nullable=True)
    ttft_ms = Column(BigInteger, nullable=True)
    final_checkpoint_id = Column(String, nullable=True)
    final_status_node = Column(String, nullable=True)
    response_mode = Column(String, nullable=True)
    active_team_final = Column(String, nullable=True)
    active_worker_final = Column(String, nullable=True)
    trace_id = Column(String, nullable=True, index=True)
    assistant_char_count = Column(Integer, nullable=False, default=0)
    tool_call_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column("metadata", JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        index=True,
    )


class LLMPricingSnapshot(Base):
    __tablename__ = "llm_pricing_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    provider = Column(String, nullable=False, index=True)
    model = Column(String, nullable=False, index=True)
    pricing_version = Column(String, nullable=False, index=True)
    effective_from = Column(DateTime(timezone=True), nullable=False, index=True)
    effective_to = Column(DateTime(timezone=True), nullable=True, index=True)
    input_cost_per_1m_microusd = Column(BigInteger, nullable=False)
    output_cost_per_1m_microusd = Column(BigInteger, nullable=False)
    reasoning_cost_per_1m_microusd = Column(BigInteger, nullable=True)
    cache_read_cost_per_1m_microusd = Column(BigInteger, nullable=True)
    is_estimated = Column(Boolean, nullable=False, default=False)
    notes = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(KST)
    )


class LLMUsageEvent(Base):
    __tablename__ = "llm_usage_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    thread_id = Column(
        String, ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    turn_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_turns.id"), nullable=False, index=True
    )
    run_id = Column(String, nullable=True, index=True)
    trace_id = Column(String, nullable=True, index=True)
    span_id = Column(String, nullable=True, index=True)
    parent_span_id = Column(String, nullable=True, index=True)
    node_name = Column(String, nullable=True, index=True)
    provider = Column(String, nullable=False, index=True)
    model = Column(String, nullable=False, index=True)
    request_role = Column(String, nullable=True, index=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cache_read_input_tokens = Column(Integer, nullable=False, default=0)
    cache_write_input_tokens = Column(Integer, nullable=False, default=0)
    reasoning_output_tokens = Column(Integer, nullable=False, default=0)
    text_output_tokens = Column(Integer, nullable=False, default=0)
    usage_metadata = Column(JSONB, nullable=False, default=dict)
    pricing_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_pricing_snapshots.id"),
        nullable=True,
        index=True,
    )
    input_cost_microusd = Column(BigInteger, nullable=False, default=0)
    output_cost_microusd = Column(BigInteger, nullable=False, default=0)
    reasoning_cost_microusd = Column(BigInteger, nullable=True)
    estimated_reasoning_cost_microusd = Column(BigInteger, nullable=False, default=0)
    total_cost_microusd = Column(BigInteger, nullable=False, default=0)
    cost_is_estimated = Column(Boolean, nullable=False, default=False)
    reasoning_cost_is_estimated = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        index=True,
    )


class ToolExecutionEvent(Base):
    __tablename__ = "tool_execution_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String, ForeignKey("auth_users.id"), nullable=False, index=True)
    thread_id = Column(
        String, ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    turn_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_turns.id"), nullable=False, index=True
    )
    run_id = Column(String, nullable=True, index=True)
    trace_id = Column(String, nullable=True, index=True)
    span_id = Column(String, nullable=True, index=True)
    parent_span_id = Column(String, nullable=True, index=True)
    node_name = Column(String, nullable=True, index=True)
    tool_name = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    status = Column(String, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(BigInteger, nullable=True)
    input_summary = Column(JSONB, nullable=True)
    output_summary = Column(JSONB, nullable=True)
    error_summary = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        index=True,
    )


class UserDailyUsageRollup(Base):
    __tablename__ = "user_daily_usage_rollups"
    __table_args__ = (
        UniqueConstraint("usage_date", "user_id", name="uq_user_daily_usage_rollups"),
    )

    usage_date = Column(Date, primary_key=True)
    user_id = Column(String, ForeignKey("auth_users.id"), primary_key=True)
    total_turns = Column(Integer, nullable=False, default=0)
    total_input_tokens = Column(BigInteger, nullable=False, default=0)
    total_output_tokens = Column(BigInteger, nullable=False, default=0)
    total_reasoning_tokens = Column(BigInteger, nullable=False, default=0)
    total_cost_microusd = Column(BigInteger, nullable=False, default=0)
    exact_total_cost_microusd = Column(BigInteger, nullable=False, default=0)
    estimated_total_cost_microusd = Column(BigInteger, nullable=False, default=0)
    exact_reasoning_cost_microusd = Column(BigInteger, nullable=False, default=0)
    estimated_reasoning_cost_microusd = Column(BigInteger, nullable=False, default=0)
    avg_latency_ms = Column(BigInteger, nullable=True)
    avg_ttft_ms = Column(BigInteger, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST),
    )
