import pytest
from pydantic import ValidationError
from schemas.chat import ChatRequest
from schemas.auth import ChangePasswordRequest, LoginRequest, SignupRequest


def test_chat_request_valid():
    """Test valid instantiation of ChatRequest."""
    req = ChatRequest(message="Hello API", thread_id="thread_abc123")
    assert req.message == "Hello API"
    assert req.thread_id == "thread_abc123"


def test_chat_request_invalid_missing_thread():
    """Test Pydantic validation catches missing required fields."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(message="I forgot my thread id")

    assert "thread_id" in str(exc_info.value)


def test_chat_request_with_images():
    """Test valid instantiation of ChatRequest with images."""
    req = ChatRequest(
        message="Look at this",
        thread_id="thread_123",
        images=["base64_data_1", "base64_data_2"],
    )
    assert req.images == ["base64_data_1", "base64_data_2"]


def test_signup_request_valid():
    req = SignupRequest(login_id="user1", password="abcdefghijklmn1")
    assert req.login_id == "user1"


def test_login_request_valid():
    req = LoginRequest(login_id="admin", password="admin1")
    assert req.login_id == "admin"


def test_change_password_request_requires_fields():
    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password="old")
