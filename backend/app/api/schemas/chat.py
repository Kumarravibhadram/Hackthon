"""Public request and response models for chat."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    agent: str | None = Field(default=None, min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    route: str | None = None


class EmailSendRequest(BaseModel):
    recipient: str = Field(min_length=3)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
