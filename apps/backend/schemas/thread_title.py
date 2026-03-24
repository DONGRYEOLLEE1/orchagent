from pydantic import BaseModel, model_validator


class ThreadAiTitleRequest(BaseModel):
    message: str | None = None

    @model_validator(mode="after")
    def validate_message(self):
        if self.message is not None and not self.message.strip():
            raise ValueError("message must not be empty")
        return self
