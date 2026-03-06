import uuid
from datetime import datetime
import pytz
from sqlalchemy import Column, String, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from core.database import Base

KST = pytz.timezone('Asia/Seoul')

class TraceEvent(Base):
    __tablename__ = "trace_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    thread_id = Column(String, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)  # e.g., SESSION_START, NODE_START, NODE_END, TOOL_START, TOOL_END, FINAL_ANSWER, ERROR
    node_name = Column(String, nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))

    def __repr__(self):
        return f"<TraceEvent(thread_id={self.thread_id}, type={self.event_type}, node={self.node_name})>"
