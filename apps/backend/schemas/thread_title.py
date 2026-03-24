from pydantic import BaseModel, model_validator


class ThreadAiTitleRequest(BaseModel):
    message: str

    @model_validator(mode="after")
    def validate_message(self):
        if not self.message.strip():
            raise ValueError("message must not be empty")
        return self
