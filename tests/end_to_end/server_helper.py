import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from demo.api.main import app as api_app

# Create a simple SPA server for demo/web/dist
web_app = FastAPI()
dist_dir = Path(__file__).parent.parent.parent / "demo" / "web" / "dist"

if dist_dir.exists():
    web_app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")


@web_app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    from fastapi.responses import FileResponse

    return FileResponse(dist_dir / "index.html")


@asynccontextmanager
async def run_demo_servers():
    api_config = uvicorn.Config(api_app, host="127.0.0.1", port=8001, log_level="warning")
    web_config = uvicorn.Config(web_app, host="127.0.0.1", port=3000, log_level="warning")

    api_server = uvicorn.Server(api_config)
    web_server = uvicorn.Server(web_config)

    api_task = asyncio.create_task(api_server.serve())
    web_task = asyncio.create_task(web_server.serve())

    # Wait until servers are up
    await asyncio.sleep(0.5)

    try:
        yield
    finally:
        api_server.should_exit = True
        web_server.should_exit = True
        await asyncio.gather(api_task, web_task, return_exceptions=True)
