from fastapi import APIRouter, Request
from app.models import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns gateway status and list of available providers. No authentication required.",
)
async def health_check(request: Request):
    rotator = request.state.rotator
    providers = rotator.available_providers()
    return HealthResponse(
        status="ok",
        providers_available=len(providers),
        providers=providers,
    )
