"""Pydantic schemas for chat endpoints."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str
    ts: str | None = None


class ConversationSummarySchema(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[Message] = []


class SendMessageRequest(BaseModel):
    content: str
    context: Optional[str] = None
