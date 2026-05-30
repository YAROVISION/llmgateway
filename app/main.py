import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from colorama import Fore, Style, init

sys.path.append(str(Path(__file__).resolve().parent.parent))
init(autoreset=True)

from app.routes import chat, models, health
from app.services.rotator import LLMRotator


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rotator = LLMRotator()
    print(Fore.CYAN + Style.BRIGHT + """
  ██╗     ██╗     ███╗   ███╗     ██████╗  █████╗ ████████╗███████╗██╗    ██╗ █████╗ ██╗   ██╗
  ██║     ██║     ████╗ ████║    ██╔════╝ ██╔══██╗╚══██╔══╝██╔════╝██║    ██║██╔══██╗╚██╗ ██╔╝
  ██║     ██║     ██╔████╔██║    ██║  ███╗███████║   ██║   █████╗  ██║ █╗ ██║███████║ ╚████╔╝
  ██║     ██║     ██║╚██╔╝██║    ██║   ██║██╔══██║   ██║   ██╔══╝  ██║███╗██║██╔══██║  ╚██╔╝
  ███████╗███████╗██║ ╚═╝ ██║    ╚██████╔╝██║  ██║   ██║   ███████╗╚███╔███╔╝██║  ██║   ██║
  ╚══════╝╚══════╝╚═╝     ╚═╝     ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝

  🚀 LLM Gateway — OpenAI-compatible API with automatic provider rotation
  📡 Docs:   http://localhost:8000/docs
  💊 Health: http://localhost:8000/health
  🔑 Set GATEWAY_API_KEY in .env to secure the endpoint
""" + Style.RESET_ALL)
    yield


app = FastAPI(
    title="LLM Gateway",
    description="""
OpenAI-compatible API gateway with automatic provider rotation.

**Authentication:** Pass your `GATEWAY_API_KEY` as a Bearer token:
```
Authorization: Bearer <your-key>
```

**Drop-in replacement** for any OpenAI client — just change `base_url` and `api_key`.
""",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


app.include_router(health.router, tags=["Health"])
app.include_router(chat.router,   prefix="/v1", tags=["Chat"])
app.include_router(models.router, prefix="/v1", tags=["Models"])


@app.middleware("http")
async def inject_rotator(request: Request, call_next):
    request.state.rotator = app.state.rotator
    return await call_next(request)


def run():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()
