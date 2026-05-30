from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
import time
import uuid


# ─── Request models ───────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ResponseFormat(BaseModel):
    type: str = "text"  # "text" | "json_object"


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None          # якщо None — авторотація
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: Optional[bool] = False
    response_format: Optional[ResponseFormat] = None
    preferred_provider: Optional[str] = None  # розширення: вказати конкретний провайдер

    class Config:
        json_schema_extra = {
            "example": {
                "model": "auto",
                "messages": [{"role": "user", "content": "Hello!"}],
                "preferred_provider": "groq"
            }
        }


# ─── Response models ──────────────────────────────────────────────────────────

class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatChoice]
    usage: UsageInfo = Field(default_factory=UsageInfo)


# ─── Models list ─────────────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "llm-gateway"


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


# ─── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    providers_available: int
    providers: List[Dict[str, Any]]
