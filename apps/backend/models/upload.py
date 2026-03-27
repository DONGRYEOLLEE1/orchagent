import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base
from models.logging import KST


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String, nullable=False, index=True)
    thread_id = Column(String, nullable=True, index=True)
    kind = Column(String, nullable=False)
    source_type = Column(String, nullable=False, default="device")
    processing_status = Column(String, nullable=False, default="ready")
    preview_status = Column(String, nullable=False, default="pending")
    file_name = Column(String, nullable=False)
    declared_extension = Column(String, nullable=True)
    mime_type = Column(String, nullable=False)
    sniffed_mime_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(KST))
