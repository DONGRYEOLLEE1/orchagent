import os
import json
from datetime import datetime
import pytz

KST = pytz.timezone('Asia/Seoul')
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

class JsonLogger:
    @staticmethod
    def _write_log(filename: str, data: dict):
        # Add timestamp to every log
        data["timestamp"] = datetime.now(KST).isoformat()
        filepath = os.path.join(LOG_DIR, filename)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    @staticmethod
    def log_user(user_id: str, action: str, metadata: dict = None):
        """Log user activity (e.g., login, signup)."""
        payload = {"user_id": user_id, "action": action}
        if metadata:
            payload.update(metadata)
        JsonLogger._write_log("user.jsonl", payload)

    @staticmethod
    def log_usage(user_id: str, model: str, prompt_tokens: int, completion_tokens: int):
        """Log LLM token usage per user."""
        payload = {
            "user_id": user_id,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
        JsonLogger._write_log("usage.jsonl", payload)

    @staticmethod
    def log_session(session_id: str, user_id: str, event_type: str, metadata: dict = None):
        """Log session events (e.g., turn_count, feedback)."""
        payload = {"session_id": session_id, "user_id": user_id, "event_type": event_type}
        if metadata:
            payload.update(metadata)
        JsonLogger._write_log("session.jsonl", payload)
