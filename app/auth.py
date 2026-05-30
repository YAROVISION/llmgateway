import os
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    gateway_key = os.getenv("GATEWAY_API_KEY", "change-me-in-env")
    if not credentials or credentials.credentials != gateway_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return credentials.credentials
