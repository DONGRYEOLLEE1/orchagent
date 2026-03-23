from pydantic import BaseModel, model_validator


class ThreadPatchRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None

    @model_validator(mode="after")
    def validate_non_empty_patch(self):
        if self.title is None and self.pinned is None and self.archived is None:
            raise ValueError("At least one thread field must be provided.")
        return self
