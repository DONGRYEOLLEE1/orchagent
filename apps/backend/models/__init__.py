from core.database import Base
from models.auth import AuthSession, AuthUser
from models.trace import TraceEvent
from models.logging import ChatSession, ChatMessageLog

# This ensures that when Base.metadata.create_all is called,
# all models are registered.
__all__ = [
    "Base",
    "TraceEvent",
    "ChatSession",
    "ChatMessageLog",
    "AuthUser",
    "AuthSession",
]
