from fastapi import APIRouter, Depends, HTTPException, Request
from app.models import ChatCompletionRequest, ChatCompletionResponse, ChatChoice, ChatMessage, UsageInfo
from app.auth import verify_api_key

router = APIRouter()


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="Create chat completion",
    description="""
OpenAI-compatible chat completion endpoint.

Set `model` to `"auto"` (or omit it) for automatic provider rotation.  
Set `preferred_provider` to bias toward a specific provider (e.g. `"groq"`, `"cerebras"`).

**Example with openai Python SDK:**
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-gateway-key"
)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```
""",
)
async def create_chat_completion(
    body: ChatCompletionRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    rotator = request.state.rotator
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    response_format = None
    if body.response_format and body.response_format.type == "json_object":
        response_format = {"type": "json_object"}

    try:
        result = rotator.chat_completion(
            messages=messages,
            response_format=response_format,
            preferred_provider=body.preferred_provider,
            model_hint=body.model,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"All LLM providers failed: {exc}")

    return ChatCompletionResponse(
        model=result["model"],
        choices=[
            ChatChoice(
                message=ChatMessage(role="assistant", content=result["content"]),
                finish_reason="stop",
            )
        ],
        usage=UsageInfo(),
    )
