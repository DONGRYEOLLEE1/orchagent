import pytest
from pydantic import ValidationError

from schemas.thread_patch import ThreadPatchRequest
from schemas.user_patch import AdminUserPatchRequest, UserSelfPatchRequest


def test_thread_patch_request_accepts_partial_fields():
    req = ThreadPatchRequest(title="Renamed")
    assert req.title == "Renamed"


def test_thread_patch_request_rejects_empty_body():
    with pytest.raises(ValidationError):
        ThreadPatchRequest()


def test_user_self_patch_request_accepts_display_name_only():
    req = UserSelfPatchRequest(display_name="Dr. Lee")
    assert req.display_name == "Dr. Lee"


def test_user_self_patch_request_rejects_empty_body():
    with pytest.raises(ValidationError):
        UserSelfPatchRequest()


def test_admin_user_patch_request_requires_status():
    req = AdminUserPatchRequest(status="disabled")
    assert req.status == "disabled"

    with pytest.raises(ValidationError):
        AdminUserPatchRequest()
