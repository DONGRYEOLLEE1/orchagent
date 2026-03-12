from pydantic import BaseModel
from typing import List, Optional


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    images: Optional[List[str]] = None


class ResumeRequest(BaseModel):
    thread_id: str
    action: str  # e.g., 'approve', 'reject', 'feedback'
    feedback: Optional[str] = None
