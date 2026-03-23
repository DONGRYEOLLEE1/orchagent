from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    login_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)
    display_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)


class LoginRequest(BaseModel):
    login_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=1, max_length=256)


class AuthUserResponse(BaseModel):
    id: str
    login_id: str
    role: str
    status: str
    display_name: str | None
    email: str | None
    must_change_password: bool


class AuthStatusResponse(BaseModel):
    message: str
