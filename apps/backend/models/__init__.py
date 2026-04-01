from core.database import Base
from models.analytics import (
    ChatTurn,
    LLMUsageEvent,
    LLMPricingSnapshot,
    ToolExecutionEvent,
    UserDailyUsageRollup,
)
from models.auth import AuthSession, AuthUser
from models.trace import TraceEvent
from models.logging import ChatSession, ChatMessageLog
from models.repository import ThreadRepositoryBinding, WorkspaceJob
from models.thread_profile import ThreadProfile
from models.upload import UploadedFile
from models.user_memory import (
    MemoryReferenceEvent,
    UserMemoryEntry,
    UserMemorySettings,
    UserPersonalizationInstruction,
)

# This ensures that when Base.metadata.create_all is called,
# all models are registered.
__all__ = [
    "Base",
    "TraceEvent",
    "ChatSession",
    "ChatMessageLog",
    "ThreadRepositoryBinding",
    "WorkspaceJob",
    "ChatTurn",
    "AuthUser",
    "AuthSession",
    "LLMUsageEvent",
    "LLMPricingSnapshot",
    "ThreadProfile",
    "ToolExecutionEvent",
    "UserDailyUsageRollup",
    "UploadedFile",
    "UserMemorySettings",
    "UserMemoryEntry",
    "UserPersonalizationInstruction",
    "MemoryReferenceEvent",
]
