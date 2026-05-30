from fastapi import APIRouter, Depends, Request
from app.models import ModelsResponse, ModelInfo
from app.auth import verify_api_key

router = APIRouter()


@router.get(
    "/models",
    response_model=ModelsResponse,
    summary="List available models",
    description="Returns all configured LLM providers/models that have valid API keys.",
)
async def list_models(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    rotator = request.state.rotator
    providers = rotator.available_providers()
    data = [
        ModelInfo(id=f"{p['name']}/{p['model']}", owned_by=p["name"])
        for p in providers
    ]
    return ModelsResponse(data=data)
