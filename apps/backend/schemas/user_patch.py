from pydantic import BaseModel, model_validator


class UserSelfPatchRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def validate_non_empty_patch(self):
        if self.display_name is None and self.email is None:
            raise ValueError("At least one user profile field must be provided.")
        return self


class AdminUserPatchRequest(BaseModel):
    status: str | None = None

    @model_validator(mode="after")
    def validate_non_empty_patch(self):
        if self.status is None:
            raise ValueError("At least one admin user field must be provided.")
        return self
